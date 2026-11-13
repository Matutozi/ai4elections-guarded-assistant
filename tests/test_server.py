import json

import pytest
from consequence_verify import ReceiptRejected
from starlette.testclient import TestClient

from guarded_assistant.server import VERSION, create_app
from guarded_assistant.tools import DEFINITIONS, Ledger, Tools


class FakeVerifier:
    """Accepts the receipt "good" once, for any call; refuses the rest."""

    def __init__(self):
        self.used = set()

    async def verify(self, receipt, tool, arguments):
        receipt = json.loads(receipt) if isinstance(receipt, str) else receipt
        if receipt.get("id") != "good":
            raise ReceiptRejected("bad_signature", "receipt signature is invalid")
        if receipt["n"] in self.used:
            raise ReceiptRejected("already_used", "receipt was already used")
        self.used.add(receipt["n"])
        return {"receipt_id": f"rcp_{receipt['n']}", "agent_id": "results-officer", "policy": "officer-transmits"}


@pytest.fixture
def client(tmp_path):
    app = create_app(Tools(ledger=Ledger(tmp_path / "ledger.jsonl")), FakeVerifier())
    return TestClient(app)


META = {"io.modelcontextprotocol/protocolVersion": VERSION, "io.modelcontextprotocol/clientCapabilities": {}}


def rpc(client, method, params=None, receipt=None, headers=None):
    params = {**(params or {}), "_meta": META}
    h = {"MCP-Protocol-Version": VERSION, "Mcp-Method": method}
    if method == "tools/call":
        h["Mcp-Name"] = params["name"]
    if receipt is not None:
        h["X-Consequence-Receipt"] = json.dumps(receipt)
    h.update(headers or {})
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, headers=h)


def test_lists_every_tool(client):
    r = rpc(client, "tools/list")
    assert r.status_code == 200
    result = r.json()["result"]
    assert [t["name"] for t in result["tools"]] == [d["name"] for d in DEFINITIONS]
    assert result["resultType"] == "complete" and result["cacheScope"] == "private"


def test_calls_need_a_valid_receipt(client):
    call = {"name": "results.unit", "arguments": {"pu_id": "SIM-00001"}}
    # No receipt: refused before the tool runs.
    r = rpc(client, "tools/call", call)
    assert r.status_code == 403 and "no receipt" in r.text
    # A forged one.
    r = rpc(client, "tools/call", call, receipt={"id": "forged", "n": 1})
    assert r.status_code == 403 and "signature" in r.text
    # A good one runs the tool, once.
    r = rpc(client, "tools/call", call, receipt={"id": "good", "n": 1})
    assert r.status_code == 200 and json.loads(r.json()["result"]["content"][0]["text"])["pu_id"] == "SIM-00001"
    r = rpc(client, "tools/call", call, receipt={"id": "good", "n": 1})
    assert r.status_code == 403 and "already" in r.text


def test_the_receipt_is_recorded_with_the_transmission(client, tmp_path):
    args = {"pu_id": "SIM-00001", "registered_voters": 1279, "accredited_voters": 569, "votes_A": 3, "votes_B": 51, "votes_C": 186, "votes_D": 31, "votes_E": 279, "rejected_votes": 19}
    r = rpc(client, "tools/call", {"name": "results.transmit", "arguments": args}, receipt={"id": "good", "n": 7})
    assert "raised no flags" in r.json()["result"]["content"][0]["text"]
    entry = Ledger(tmp_path / "ledger.jsonl").of("transmission")[0]
    assert entry["receipt_id"] == "rcp_7" and entry["agent"] == "results-officer"


def test_protocol_checks(client):
    r = rpc(client, "tools/list", headers={"Mcp-Method": "tools/call"})
    assert r.status_code == 400 and "Header mismatch" in r.text
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert r.json()["result"]["protocolVersion"] == "2025-06-18"
    assert client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    assert client.post("/mcp", content=b"{not json").json()["error"]["code"] == -32700
    assert rpc(client, "nope/nope").status_code == 404
    r = rpc(client, "tools/call", {"name": "no.such.tool", "arguments": {}}, receipt={"id": "good", "n": 9})
    assert "Unknown tool" in r.text
    assert client.post("/mcp", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
