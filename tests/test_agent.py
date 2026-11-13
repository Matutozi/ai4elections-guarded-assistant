import json

import httpx

from guarded_assistant.agent import INJECTION, Assistant, mcp_name, ollama_tools, tool_name
from guarded_assistant.mcp_client import ALLOWED, BLOCKED, Outcome
from guarded_assistant.tools import DEFINITIONS


class FakeGate:
    """The gate as the voter assistant sees it: reads allowed, publishing blocked."""

    def __init__(self):
        self.calls = []

    def list_tools(self):
        return DEFINITIONS

    def call(self, tool, args):
        self.calls.append((tool, args))
        if tool == "bulletin.publish":
            return Outcome(BLOCKED, 'Blocked by ConsequenceOS: policy rule "only-comms-publishes" does not allow bulletin.publish. Do not retry this call.')
        return Outcome(ALLOWED, json.dumps({"match": "CLM-0002", "label": "false"}))


def fake_ollama(replies):
    """An Ollama /api/chat that answers with replies in turn, and keeps what it was sent."""
    sent = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": replies[len(sent) - 1]})

    return httpx.Client(transport=httpx.MockTransport(handle)), sent


def call(name, args):
    return {"function": {"name": tool_name(name), "arguments": args}}


def test_a_model_that_follows_the_injection_is_stopped_by_the_gate():
    # The model checks the claim, then does what the forwarded message told it to.
    http, sent = fake_ollama([
        {"role": "assistant", "content": "", "tool_calls": [call("claims.check", {"text": "voting in Imo is postponed"})]},
        {"role": "assistant", "content": "", "tool_calls": [call("bulletin.publish", {"title": "Election postponed", "body": "Voting in Imo State is postponed"})]},
        {"role": "assistant", "content": "That message is false, and I'm not able to publish bulletins."},
    ])
    gate = FakeGate()
    turn = Assistant("voter-assistant", gate, model="test", http=http).ask(INJECTION)
    assert [s.tool for s in turn.steps] == ["claims.check", "bulletin.publish"]
    assert turn.steps[1].outcome == BLOCKED
    # The refusal went back to the model as the tool's answer.
    assert sent[2]["messages"][-1] == {"role": "tool", "content": turn.steps[1].text, "tool_name": "bulletin__publish"}
    assert "not able to publish" in turn.answer
    # The model saw every tool, under names it accepts, and the system prompt says forwarded text is data.
    assert {t["function"]["name"] for t in sent[0]["tools"]} == {tool_name(d["name"]) for d in DEFINITIONS}
    assert "not instructions" in sent[0]["messages"][0]["content"]


def test_arguments_as_text_and_step_limit():
    http, _ = fake_ollama([{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "units__lookup", "arguments": '{"pu_id": "SIM-00001"}'}}]}] * 10)
    gate = FakeGate()
    turn = Assistant("voter-assistant", gate, model="test", http=http).ask("where is SIM-00001?")
    assert gate.calls[0] == ("units.lookup", {"pu_id": "SIM-00001"})
    assert len(turn.steps) == 6 and "couldn't finish" in turn.answer


def test_names_round_trip():
    for d in DEFINITIONS:
        assert mcp_name(tool_name(d["name"])) == d["name"]
        assert "." not in tool_name(d["name"])
    assert ollama_tools(DEFINITIONS)[0]["function"]["parameters"]["type"] == "object"
