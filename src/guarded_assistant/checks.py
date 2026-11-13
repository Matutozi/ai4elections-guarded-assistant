"""Consistency checks on a polling unit's result sheet.

These are the template's rules (src/ai4elections/checks.py) applied to one
sheet at a time, as it arrives. A flag means "a person should look at
this": it is never evidence of wrongdoing, and nothing here accepts,
rejects or declares a result.
"""

from __future__ import annotations

from .data import PARTIES, Result

# Flag names, matching the data pack's anomaly types where they overlap.
ACCREDITED_EXCEEDS_REGISTERED = "accredited_exceeds_registered"
SUM_MISMATCH = "sum_mismatch"
ROUND_NUMBERS = "suspicious_round_numbers"
DUPLICATE_OF_PREVIOUS = "duplicated_from_previous_unit"
REGISTER_MISMATCH = "registered_voters_differs_from_register"
NEGATIVE = "negative_count"

EXPLAIN = {
    ACCREDITED_EXCEEDS_REGISTERED: "more voters accredited than are registered at the unit",
    SUM_MISMATCH: "party votes plus rejected votes don't add up to the accredited voters",
    ROUND_NUMBERS: "every party's votes are a multiple of 100",
    DUPLICATE_OF_PREVIOUS: "the party votes are identical to the unit sent just before",
    REGISTER_MISMATCH: "the registered voters on the sheet differ from the voter register",
    NEGATIVE: "a count is negative",
}


def flags(sheet: Result, previous: Result | None = None, registered_on_roll: int | None = None) -> list[str]:
    """Return the flags a sheet raises, for human review.

    previous is the sheet received just before it, for the duplicate check;
    registered_on_roll is the unit's figure on the voter register.
    """
    out = []
    counts = [sheet.registered_voters, sheet.accredited_voters, sheet.rejected_votes, *sheet.votes.values()]
    if any(c < 0 for c in counts):
        out.append(NEGATIVE)
    if sheet.accredited_voters > sheet.registered_voters:
        out.append(ACCREDITED_EXCEEDS_REGISTERED)
    if sum(sheet.votes.values()) + sheet.rejected_votes != sheet.accredited_voters:
        out.append(SUM_MISMATCH)
    if all(sheet.votes[p] % 100 == 0 for p in PARTIES) and any(sheet.votes.values()):
        out.append(ROUND_NUMBERS)
    if previous is not None and previous.votes == sheet.votes:
        out.append(DUPLICATE_OF_PREVIOUS)
    if registered_on_roll is not None and registered_on_roll != sheet.registered_voters:
        out.append(REGISTER_MISMATCH)
    return out
