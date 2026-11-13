"""The synthetic data pack, read once with the standard library.

All of it is fictional (see data/synthetic/DATA_DICTIONARY.md). Numbers are
parsed here, so the tools work with ints and bools rather than text.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"

PARTIES = ("A", "B", "C", "D", "E")
LANGUAGES = {"en": "en", "pcm": "pcm_draft", "ha": "ha", "yo": "yo", "ig": "ig"}  # language -> FAQ column


def _rows(name: str, data_dir: Path) -> list[dict[str, str]]:
    with open(data_dir / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _bool(s: str) -> bool:
    return s.strip().lower() == "true"


@dataclass(frozen=True)
class Result:
    """One polling unit's result sheet."""

    pu_id: str
    registered_voters: int
    accredited_voters: int
    votes: dict[str, int]  # party -> votes
    rejected_votes: int


class DataPack:
    """The data pack's files, each read the first time it's used."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.dir = data_dir

    @cached_property
    def faq(self) -> list[dict[str, str]]:
        return _rows("voter_info_faq_multilingual.csv", self.dir)

    @cached_property
    def units(self) -> dict[str, dict]:
        out = {}
        for r in _rows("polling_units_synthetic.csv", self.dir):
            r["registered_voters"] = int(r["registered_voters"])
            r["distance_to_lga_hq_km"] = float(r["distance_to_lga_hq_km"])
            r["accessible_venue"] = _bool(r["accessible_venue"])
            r["has_grid_power"] = _bool(r["has_grid_power"])
            out[r["pu_id"]] = r
        return out

    @cached_property
    def results(self) -> dict[str, Result]:
        out = {}
        for r in _rows("results_synthetic.csv", self.dir):
            out[r["pu_id"]] = Result(
                pu_id=r["pu_id"],
                registered_voters=int(r["registered_voters"]),
                accredited_voters=int(r["accredited_voters"]),
                votes={p: int(r["votes_" + p]) for p in PARTIES},
                rejected_votes=int(r["rejected_votes"]),
            )
        return out

    @cached_property
    def incidents(self) -> list[dict]:
        out = []
        for r in _rows("incident_reports_synthetic.csv", self.dir):
            r["severity_0_4"] = int(r["severity_0_4"])
            r["verified"] = _bool(r["verified"])
            r["has_photo_evidence"] = _bool(r["has_photo_evidence"])
            out.append(r)
        return out

    @cached_property
    def survey(self) -> list[dict]:
        out = []
        for r in _rows("accessibility_barriers_survey_synthetic.csv", self.dir):
            r["confidence_finding_info_1_5"] = int(r["confidence_finding_info_1_5"])
            out.append(r)
        return out

    @cached_property
    def claims(self) -> list[dict]:
        with open(self.dir / "misinformation_claims_synthetic.jsonl", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
