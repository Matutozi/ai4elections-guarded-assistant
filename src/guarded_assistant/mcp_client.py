"""A small MCP client for talking to the gate as one agent.

Each agent (role) has its own ConsequenceOS API key; the gate knows the
role from the key, never from anything the agent says. The client sorts
every answer into what the gate did with the call.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from typing import Any

import httpx

VERSION = "2026-07-28"
META = {"io.modelcontextprotocol/protocolVersion": VERSION, "io.modelcontextprotocol/clientCapabilities": {}}

# What happened to a call.
ALLOWED = "allowed"  # the gate allowed it and the tool ran
HELD = "held"  # waiting for a person to approve
BLOCKED = "blocked"  # the policy refused it
REFUSED = "refused"  # refused before or after the policy: bad arguments, or the tool server's receipt check
DECLINED = "declined"  # a person declined it
TOOL_ERROR = "tool_error"  # the tool ran and said no


@dataclass
class Outcome:
    outcome: str
    text: str
    approval_id: str | None = None


def classify(result: dict[str, Any] | None, error: dict[str, Any] | None = None) -> Outcome:
    if error is not None:
        return Outcome(REFUSED, str(error.get("message", error)))
    text = " ".join(c.get("text", "") for c in (result or {}).get("content", []) if c.get("type") == "text")
    if not (result or {}).get("isError"):
        return Outcome(ALLOWED, text)
    if text.startswith("Approval pending"):
        approval = text.split("Approval ID: ", 1)[1].split(".", 1)[0].strip() if "Approval ID: " in text else None
        return Outcome(HELD, text, approval)
    if text.startswith("Blocked by ConsequenceOS"):
        return Outcome(BLOCKED, text)
    if text.startswith("Rejected: an approver declined"):
        return Outcome(DECLINED, text)
    if text.startswith("Refused by ConsequenceOS"):
        return Outcome(REFUSED, text)
    return Outcome(TOOL_ERROR, text)


class GateClient:
    def __init__(self, url: str, api_key: str, timeout: float = 30.0) -> None:
        self.url = url.rstrip("/") + "/mcp" if not url.rstrip("/").endswith("/mcp") else url
        self.http = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {api_key}"})
        self.ids = itertools.count(1)

    def close(self) -> None:
        self.http.close()

    def _post(self, method: str, params: dict, name: str | None = None) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": VERSION, "Mcp-Method": method}
        if name is not None:
            headers["Mcp-Name"] = name
        body = {"jsonrpc": "2.0", "id": next(self.ids), "method": method, "params": {**params, "_meta": META}}
        r = self.http.post(self.url, content=json.dumps(body), headers=headers)
        if r.headers.get("content-type", "").startswith("text/event-stream"):
            data = [line[5:].strip() for line in r.text.splitlines() if line.startswith("data:")]
            return json.loads(data[-1]) if data else {}
        try:
            return r.json()
        except ValueError:
            return {"error": {"message": f"HTTP {r.status_code}: {r.text[:200]}"}}

    def list_tools(self) -> list[dict]:
        msg = self._post("tools/list", {})
        if "error" in msg:
            raise RuntimeError(msg["error"].get("message"))
        return msg["result"]["tools"]

    def call(self, tool: str, arguments: dict) -> Outcome:
        msg = self._post("tools/call", {"name": tool, "arguments": arguments}, name=tool)
        return classify(msg.get("result"), msg.get("error"))
