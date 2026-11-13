"""The election-data tool server: MCP over Streamable HTTP.

It stands for the election body's systems behind the gate. Every tools/call
must carry a ConsequenceOS receipt for exactly that tool and those
arguments, checked by consequence_verify's middleware before any tool runs.
So a call that didn't go through the policy, was changed on the way, or is
a replay of one that did, is refused here too: the policy can't be walked
around by calling this server directly.

Run it with:

    CONSEQUENCE_KEY_RECEIVER_ELECTION_DATA=... python -m guarded_assistant.server
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from consequence_verify import Client, ReceiptMiddleware, receipt_from
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .tools import DEFINITIONS, Ledger, Tools

# MCP protocol details, as ConsequenceOS's proxy speaks them: revision
# 2026-07-28, with the older initialize handshake for older clients.
VERSION = "2026-07-28"
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPS = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO = {"name": "election-data", "version": "0.1.0"}

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
HEADER_MISMATCH, UNSUPPORTED_VERSION = -32020, -32022
MAX_BODY = 1 << 20

log = logging.getLogger("election_data")


def _error(id_: Any, code: int, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}, status_code=status)


def create_app(tools: Tools, verifier: Any) -> Starlette:
    """The app, with tools and a receipt verifier (consequence_verify.Client
    in production; anything with an async verify() in tests)."""

    async def mcp(request: Request) -> Response:
        if request.headers.get("origin") not in (None, "http://localhost", "http://127.0.0.1"):
            return Response("forbidden origin", status_code=403)
        body = await request.body()
        if len(body) > MAX_BODY:
            return _error(None, INVALID_REQUEST, "body too large", 413)
        try:
            msg = json.loads(body)
        except ValueError:
            return _error(None, PARSE_ERROR, "parse error")
        if not isinstance(msg, dict):
            return _error(None, INVALID_REQUEST, "batch requests are not supported")
        if msg.get("jsonrpc") != "2.0":
            return _error(msg.get("id"), INVALID_REQUEST, 'jsonrpc must be "2.0"')
        method, id_, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method and "id" not in msg:
            return Response(status_code=202)  # a notification
        if not method:
            if "result" in msg or "error" in msg:
                return Response(status_code=202)  # an answer to a request we never send
            return _error(id_, INVALID_REQUEST, "invalid request")
        if not isinstance(params, dict):
            return _error(id_, INVALID_PARAMS, "params must be an object")

        if method == "initialize":
            asked = params.get("protocolVersion")
            return _result(id_, {
                "protocolVersion": asked if asked in LEGACY_VERSIONS else LEGACY_VERSIONS[0],
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }, modern=False)

        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        modern = META_VERSION in meta
        if modern:
            bad = _check_modern(request, method, params, meta, id_)
            if bad is not None:
                return bad

        if method == "server/discover":
            return _result(id_, {"supportedVersions": [VERSION, *LEGACY_VERSIONS], "capabilities": {"tools": {}}}, modern)
        if method == "ping":
            return _result(id_, {}, modern)
        if method == "tools/list":
            return _result(id_, {"tools": DEFINITIONS}, modern, cacheable=True)
        if method == "tools/call":
            name, args = params.get("name"), params.get("arguments") or {}
            if not isinstance(name, str) or not isinstance(args, dict):
                return _error(id_, INVALID_PARAMS, "tools/call needs params.name and object arguments")
            if name not in tools.impl:
                return _error(id_, INVALID_PARAMS, "Unknown tool: " + name, 200)
            receipt = receipt_from(request) or {}
            text, is_error = tools.call(name, args, receipt)
            # Arguments are never logged: the receipt ID ties this to the gate's audit log.
            log.info("tools/call %s error=%s receipt=%s rule=%s", name, is_error, receipt.get("receipt_id"), receipt.get("policy"))
            return _result(id_, {"content": [{"type": "text", "text": text}], "isError": is_error}, modern)
        return _error(id_, METHOD_NOT_FOUND, "method not found: " + method, 404 if modern else 200)

    return Starlette(
        routes=[Route("/mcp", mcp, methods=["POST"])],
        middleware=[Middleware(ReceiptMiddleware, verifier=verifier, paths=["/mcp"])],
    )


def _result(id_: Any, result: dict, modern: bool, cacheable: bool = False) -> JSONResponse:
    if modern:
        result = {**result, "resultType": "complete", "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO}}
        if cacheable:
            result.update(ttlMs=0, cacheScope="private")
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result})


def _check_modern(request: Request, method: str, params: dict, meta: dict, id_: Any) -> Response | None:
    """2026-07-28's per-request checks: the version, and headers that must
    repeat what the body says, so a proxy routing on headers sees the truth."""
    if meta.get(META_VERSION) != VERSION:
        return _error(id_, UNSUPPORTED_VERSION, "Unsupported protocol version")
    if META_CAPS not in meta:
        return _error(id_, INVALID_PARAMS, "missing _meta " + META_CAPS)
    if request.headers.get("mcp-protocol-version") != VERSION:
        return _error(id_, HEADER_MISMATCH, "Header mismatch: MCP-Protocol-Version")
    if request.headers.get("mcp-method") != method:
        return _error(id_, HEADER_MISMATCH, "Header mismatch: Mcp-Method")
    if method == "tools/call" and request.headers.get("mcp-name") != params.get("name"):
        return _error(id_, HEADER_MISMATCH, "Header mismatch: Mcp-Name")
    return None


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    gate = os.environ.get("CONSEQUENCE_URL", "http://127.0.0.1:8080")
    key = os.environ["CONSEQUENCE_KEY_RECEIVER_ELECTION_DATA"]
    ledger = Path(os.environ.get("ELECTION_LEDGER", ".run/ledger.jsonl"))
    app = create_app(Tools(ledger=Ledger(ledger)), Client(gate, key))
    host, port = os.environ.get("ELECTION_DATA_ADDR", "127.0.0.1:9090").rsplit(":", 1)
    uvicorn.run(app, host=host, port=int(port), log_level="warning")


if __name__ == "__main__":
    main()
