"""`make verify`: run every gate against the PUBLISHED bundle. Exit 1 unless all pass.

A non-zero exit is the expected state until the pipeline produces a bundle that passes
every gate; `make: *** Error 1` is that exit status, not a crash.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from atlas import golden as G
from atlas.bundle import Bundle, BundleError
from atlas.gates import Context, GateResult, run_all
from atlas.registry import Registry

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict] | None:
    if not path.is_file():
        return None
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh)) or None


def build_context(a: argparse.Namespace, bundle: Bundle) -> Context:
    golden = G.load(a.golden) if a.golden.is_file() else []
    holdout_path: Path = a.holdout
    return Context(
        bundle=bundle, golden=golden,
        previous=Bundle.load(a.previous) if a.previous else None,
        registry=Registry.load(a.registry) if a.registry.is_file() else None,
        scope=read_json(a.scope), changelog=read_json(a.changelog),
        known_whs=G.whs_ids(a.whs) if a.whs.is_file() else None,
        holdout=G.load(holdout_path) if holdout_path.is_file() else None,
        holdout_sha=hashlib.sha256(holdout_path.read_bytes()).hexdigest() if holdout_path.is_file() else None,
        freeze=read_json(a.freeze), labels=read_csv(a.labels), review=read_csv(a.review),
        strict=not a.prototype, release=a.release,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle", type=Path, help="bundle directory containing manifest.json and places/")
    ap.add_argument("--previous", type=Path, help="previous bundle, for the churn and lost-id checks")
    ap.add_argument("--golden", type=Path, default=DATA / "golden" / "golden.csv")
    ap.add_argument("--registry", type=Path, default=DATA / "registry" / "place_registry.parquet")
    ap.add_argument("--whs", type=Path, default=DATA / "inputs" / "whs_properties.csv")
    ap.add_argument("--scope", type=Path, default=DATA / "scope.json")
    ap.add_argument("--changelog", type=Path, default=DATA / "changelog.json")
    ap.add_argument("--freeze", type=Path, default=DATA / "freeze.json")
    ap.add_argument("--holdout", type=Path, default=DATA / "holdout" / "H1.csv")
    ap.add_argument("--labels", type=Path, default=DATA / "golden" / "kind_labels.csv")
    ap.add_argument("--review", type=Path, default=DATA / "holdout" / "precision_review.csv")
    ap.add_argument("--prototype", action="store_true",
                    help="declare a prototype build: checks skipped for small n are reported, not failed")
    ap.add_argument("--release", action="store_true", help="also run the holdout and precision gates")
    ap.add_argument("--json", type=Path, help="write the results as JSON")
    a = ap.parse_args(argv)

    if a.bundle is None:
        print("G-BUNDLE           FAIL  no bundle given (expected until the pipeline publishes one)")
        return 1
    try:
        bundle = Bundle.load(a.bundle)
    except BundleError as e:
        print(f"G-BUNDLE           FAIL  {e}")
        return 1
    results: list[GateResult] = run_all(build_context(a, bundle))
    for r in results:
        tag = "PEND" if r.pending else ("ok  " if r.passed else "FAIL")
        n = f"[n={r.n}]" if r.n is not None else ""
        sk = f"[skipped {r.skipped}]" if r.skipped else ""
        print(f"{r.gate:18s} {tag}  {n}{sk} {r.detail}")
    failed = [r.gate for r in results if not r.passed]
    print(f"\n{len(failed)} of {len(results)} gates not passing" if failed else "\nall gates pass")
    if a.json:
        a.json.write_text(json.dumps([r.__dict__ for r in results], indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
