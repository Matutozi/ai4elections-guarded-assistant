import json

import pytest

from guarded_assistant import checks
from guarded_assistant.data import DataPack, Result
from guarded_assistant.tools import MIN_GROUP_FLOOR, Ledger, Tools

pack = DataPack()


@pytest.fixture
def tools(tmp_path):
    return Tools(pack, Ledger(tmp_path / "ledger.jsonl"))


def ok(tools, name, args, receipt=None):
    text, is_error = tools.call(name, args, receipt)
    assert not is_error, text
    return text


def test_faq_in_each_language(tools):
    # The same question, asked in Hausa and answered in Yoruba.
    text = ok(tools, "faq.answer", {"question": "Ta ya zan duba ko na yi rajistar zaɓe?", "language": "yo"})
    assert text.startswith("[FAQ-001, registration] Bawo ni")
    # No answers are in the pack yet: it says so, rather than inventing one.
    assert "won't guess" in text
    text = ok(tools, "faq.answer", {"question": "how I go find my polling unit", "language": "pcm"})
    assert "[FAQ-007" in text and "How I go find" in text
    assert "couldn't match" in ok(tools, "faq.answer", {"question": "weather tomorrow"})
    assert tools.call("faq.answer", {"question": "x", "language": "fr"})[1]


def test_lookups(tools):
    assert json.loads(ok(tools, "units.lookup", {"pu_id": "SIM-00001"}))["state"] == "Benue"
    listed = json.loads(ok(tools, "units.lookup", {"state": "benue"}))
    assert listed["count"] > 0 and len(listed["shown"]) <= 20
    assert tools.call("units.lookup", {"pu_id": "SIM-99999"})[1]
    assert json.loads(ok(tools, "results.unit", {"pu_id": "SIM-00001"}))["accredited_voters"] == 569
    assert json.loads(ok(tools, "incidents.summary", {"state": "Imo"}))["count"] > 0


def test_claims_check_returns_the_claim_as_data(tools):
    claim = pack.claims[0]
    out = json.loads(ok(tools, "claims.check", {"text": claim["text"]}))
    assert out["match"] == claim["claim_id"] and out["label"] == claim["label"]
    assert json.loads(ok(tools, "claims.check", {"text": "zzz qqq"}))["match"] is None


def test_survey_aggregates_never_show_small_groups(tools):
    # Asking for groups of 1 still suppresses everything under the floor.
    out = json.loads(ok(tools, "survey.aggregate", {"group_by": ["state", "disability_type", "gender"], "min_group": 1}))
    assert out["min_group"] == MIN_GROUP_FLOOR
    assert all(g["respondents"] >= MIN_GROUP_FLOOR for g in out["groups"])
    assert out["suppressed_groups"] > 0
    for bad in ({"group_by": ["resp_id"], "min_group": 5}, {"group_by": [], "min_group": 5}, {"group_by": ["state", "state"], "min_group": 5},
                {"group_by": ["state"], "min_group": "5"}, {"group_by": ["state"], "min_group": True}, {"group_by": ["state"]}):
        assert tools.call("survey.aggregate", bad)[1], bad


def sheet(source="SIM-00001", **over):
    """The result sheet in the data pack for source, with fields changed."""
    r = pack.results[source]
    args = {"pu_id": source, "registered_voters": r.registered_voters, "accredited_voters": r.accredited_voters,
            **{"votes_" + p: v for p, v in r.votes.items()}, "rejected_votes": r.rejected_votes}
    return {**args, **over}


def test_transmit_records_and_flags_but_never_refuses(tools, tmp_path):
    receipt = {"receipt_id": "rcp_1", "agent_id": "results-officer", "policy": "officer-transmits"}
    text = ok(tools, "results.transmit", sheet(), receipt)
    assert "raised no flags" in text and "Nothing has been declared" in text
    # Accredited above registered, and votes that don't add up: recorded, and queued for a person.
    text = ok(tools, "results.transmit", sheet("SIM-00002", accredited_voters=5000), receipt)
    assert "queued it for human review" in text and "more voters accredited" in text and "don't add up" in text
    # The same unit again is recorded too, as a conflict.
    assert "second transmission for unit" in ok(tools, "results.transmit", sheet(), receipt)
    entries = Ledger(tmp_path / "ledger.jsonl").of("transmission")
    assert [e["sheet"]["pu_id"] for e in entries] == ["SIM-00001", "SIM-00002", "SIM-00001"]
    assert "second_transmission_for_unit" in entries[2]["flags"]
    assert entries[0]["receipt_id"] == "rcp_1" and entries[0]["allowed_by"] == "officer-transmits"
    # A unit that doesn't exist, or a count that isn't a whole number, records nothing.
    assert tools.call("results.transmit", sheet(pu_id="SIM-99999"))[1]
    assert tools.call("results.transmit", sheet(votes_A=1.5))[1]
    assert tools.call("results.transmit", sheet(votes_A=-1))[1]
    assert len(Ledger(tmp_path / "ledger.jsonl").of("transmission")) == 3


def test_unknown_arguments_are_refused(tools, tmp_path):
    text, is_error = tools.call("survey.aggregate", {"group_by": ["state"], "min_group": 5, "include_rows": True})
    assert is_error and "Unknown argument(s) include_rows" in text
    text, is_error = tools.call("results.transmit", {**sheet(), "override": True})
    assert is_error and not Ledger(tmp_path / "ledger.jsonl").of("transmission")


def test_no_tool_declares(tools):
    text, is_error = tools.call("results.declare", {"lga": "Imo LGA-1"})
    assert is_error and "never declares" in text


def test_checks():
    good = pack.results["SIM-00001"]
    assert checks.flags(good, None, good.registered_voters) == []
    def r(**kw):
        base = dict(pu_id="X", registered_voters=1000, accredited_voters=300, votes={"A": 100, "B": 100, "C": 50, "D": 25, "E": 15}, rejected_votes=10)
        base.update(kw)
        return Result(**base)
    assert checks.flags(r()) == []
    assert checks.ACCREDITED_EXCEEDS_REGISTERED in checks.flags(r(accredited_voters=1100))
    assert checks.SUM_MISMATCH in checks.flags(r(rejected_votes=11))
    assert checks.ROUND_NUMBERS in checks.flags(r(votes={p: 100 for p in "ABCDE"}, accredited_voters=510))
    assert checks.ROUND_NUMBERS not in checks.flags(r(votes={p: 0 for p in "ABCDE"}, accredited_voters=10))
    assert checks.DUPLICATE_OF_PREVIOUS in checks.flags(r(), previous=r(pu_id="Y"))
    assert checks.REGISTER_MISMATCH in checks.flags(r(), registered_on_roll=999)
    assert checks.NEGATIVE in checks.flags(r(rejected_votes=-1))
