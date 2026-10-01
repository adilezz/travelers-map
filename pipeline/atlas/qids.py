"""Resolving the golden set's QIDs, and checking the class table (the owner runs these locally).

    python -m atlas.qids resolve   # writes data/golden/qid_candidates.csv (never edits the golden set)
    python -m atlas.qids apply     # applies the owner's decisions in data/golden/qid_decisions.csv
    python -m atlas.qids classes   # checks data/rules/classes.csv labels against Wikidata

A QID is never accepted automatically: the tool proposes, the owner decides. Matching on a
wrong QID would be the v1 failure with a stamp of authority.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from atlas import golden as G
from atlas.geo import fold, haversine_km
from atlas.wikidata import Client

ROOT = Path(__file__).resolve().parents[2]
CAND_COLUMNS = ("golden_id", "expected_name", "iso3", "candidate_qid", "label", "description",
                "distance_km", "sitelinks", "instance_of", "found_by", "name_match", "status")
DECISION_COLUMNS = ("golden_id", "qid", "decision", "note")
SLACK = 1.5      # a candidate may lie this many tolerances away and still be proposed
MIN_SITELINKS = 10


def _aliases(row: G.Row) -> list[str]:
    return [a for a in row.raw["aliases"].split("|") if a]


def candidates_for(client: Client, row: G.Row) -> list[dict]:
    found: dict[str, str] = {}
    if row.whs_id:
        for q in client.items_with_whs_id(row.whs_id):
            found.setdefault(q, "whs")
    for name in [row.name, *_aliases(row)][:4]:
        for hit in client.search(name):
            found.setdefault(hit["id"], "search")
    ents = client.entities(list(found))
    out = []
    for qid, e in ents.items():
        dist = haversine_km(row.lat, row.lon, *e["coord"]) if e["coord"] and row.lat is not None else None
        names = {fold(e["label"])}
        out.append({
            "golden_id": row.golden_id, "expected_name": row.name, "iso3": row.iso3, "candidate_qid": qid,
            "label": e["label"], "description": e["description"],
            "distance_km": "" if dist is None else round(dist, 2), "sitelinks": e["sitelinks"],
            "instance_of": "|".join(e["instance_of"][:4]), "found_by": found[qid],
            "name_match": "yes" if names & row.names else "no", "status": "",
        })
    near = [c for c in out if c["distance_km"] != "" and c["distance_km"] <= row.tol_km * SLACK]
    near.sort(key=lambda c: (c["distance_km"], -c["sitelinks"]))
    strong = [c for c in near if c["sitelinks"] >= MIN_SITELINKS]
    for c in out:
        c["status"] = "far"
    for c in near:
        c["status"] = "near"
    if len(strong) == 1:
        strong[0]["status"] = "unique"
    elif len(strong) > 1:
        for c in strong:
            c["status"] = "ambiguous"
    out.sort(key=lambda c: ({"unique": 0, "ambiguous": 1, "near": 2, "far": 3}[c["status"]],
                            c["distance_km"] if c["distance_km"] != "" else 9e9, -c["sitelinks"]))
    return out


def resolve(client: Client, rows: list[G.Row]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        if r.row_kind != "positive" or r.qid:
            continue
        cands = candidates_for(client, r)
        out += cands or [{"golden_id": r.golden_id, "expected_name": r.name, "iso3": r.iso3, "status": "none"}]
    return out


def write_candidates(rows: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAND_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in CAND_COLUMNS})


def apply_decisions(golden_path: Path, decisions_path: Path, today: str | None = None) -> int:
    """Set `qid` and `qid_status` on golden rows from accepted decisions. Returns rows changed."""
    today = today or date.today().isoformat()
    with open(decisions_path, encoding="utf-8", newline="") as fh:
        decisions = list(csv.DictReader(fh))
    with open(golden_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames
        rows = list(reader)
    by = {r["golden_id"]: r for r in rows}
    seen_qids: dict[str, str] = {}
    for r in rows:
        if r["qid"]:
            seen_qids[r["qid"]] = r["golden_id"]
    changed = 0
    for d in decisions:
        if d["decision"] != "accept":
            continue
        row = by.get(d["golden_id"])
        if row is None or row["row_kind"] != "positive":
            raise ValueError(f"{d['golden_id']}: not a positive golden row")
        if not d["qid"].startswith("Q") or not d["qid"][1:].isdigit():
            raise ValueError(f"{d['golden_id']}: {d['qid']!r} is not a QID")
        if d["qid"] in seen_qids and seen_qids[d["qid"]] != d["golden_id"]:
            raise ValueError(f"{d['qid']} would be used by both {seen_qids[d['qid']]} and {d['golden_id']}")
        seen_qids[d["qid"]] = d["golden_id"]
        row["qid"], row["qid_status"] = d["qid"], f"resolved {today}"
        changed += 1
    with open(golden_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return changed


def check_classes(client: Client, classes_path: Path) -> list[str]:
    """Every class QID must carry the label we expect; a mismatch means a wrong QID."""
    with open(classes_path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    labels = client.labels([r["class_qid"] for r in rows])
    problems = []
    for r in rows:
        got = labels.get(r["class_qid"])
        if got is None:
            problems.append(f"{r['class_qid']}: not found (expected {r['expected_label']!r})")
        elif fold(got) != fold(r["expected_label"]):
            problems.append(f"{r['class_qid']}: is {got!r}, expected {r['expected_label']!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["resolve", "apply", "classes"])
    ap.add_argument("--golden", type=Path, default=ROOT / "data" / "golden" / "golden.csv")
    ap.add_argument("--candidates", type=Path, default=ROOT / "data" / "golden" / "qid_candidates.csv")
    ap.add_argument("--decisions", type=Path, default=ROOT / "data" / "golden" / "qid_decisions.csv")
    ap.add_argument("--classes", type=Path, default=ROOT / "data" / "rules" / "classes.csv")
    a = ap.parse_args(argv)
    if a.cmd == "resolve":
        rows = resolve(Client(), G.load(a.golden))
        write_candidates(rows, a.candidates)
        stat = {s: sum(1 for r in rows if r["status"] == s) for s in ("unique", "ambiguous", "near", "far", "none")}
        print(f"wrote {len(rows)} candidate rows to {a.candidates}: {stat}")
        print("Next: copy the right candidate for each golden_id into", a.decisions,
              "as golden_id,qid,decision,note (decision = accept or reject), then run 'apply'.")
        return 0
    if a.cmd == "apply":
        n = apply_decisions(a.golden, a.decisions)
        print(f"applied {n} QIDs to {a.golden}")
        return 0
    problems = check_classes(Client(), a.classes)
    for p in problems:
        print("MISMATCH", p)
    print("classes ok" if not problems else f"{len(problems)} mismatches: fix classes.csv before using it")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
