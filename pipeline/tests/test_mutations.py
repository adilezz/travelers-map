"""Mutation suite: break the oracle bundle in the ways a real pipeline might, and assert the
right gate fails each time. A gate with no mutation here and no dedicated test elsewhere
cannot be added (see test_every_gate_is_tripped_by_a_test)."""
import copy

import pytest
from conftest import pid

from atlas import gates

CORE_AND_RELEASE = {g.gate_name for g in (*gates.CORE_GATES, *gates.RELEASE_GATES)}
# Gates that need inputs a mutation of the oracle cannot supply have dedicated tests in test_gates.py.
DEDICATED = {"G-GOLDEN", "G-KIND-PRECISION", "G-CHURN", "G-HOLDOUT", "G-PRECISION"}


def drop_ten_percent(ps):
    return [p for i, p in enumerate(ps) if i % 10 != 3]


def shift_ten_km(ps):
    for p in ps:
        p["lat"] += 0.09
    return ps


def swap_tiers(ps):
    for p in ps:
        p["tier"] = "Local" if p["tier"] in ("Icon", "Major") else "Icon"
    return ps


def duplicate_ids(ps):
    ps[1]["place_id"] = ps[0]["place_id"]
    return ps


def qid_as_name(ps):
    ps[0]["name_en"] = "Q130654972"
    return ps


def drop_kind_evidence(ps):
    ps[0]["kinds"][0]["evidence"] = []
    return ps


def shared_qid(ps):
    ps[1]["qid"] = ps[0]["qid"]
    return ps


def outside_scope(ps):
    ps.append({**ps[0], "place_id": pid("fr"), "iso3": "FRA", "qid": "Q42"})
    return ps


def empty(_ps):
    return []


MUTATIONS = {
    "drop 10% of places": (drop_ten_percent, "G-LANDMARK"),
    "shift every place 10 km": (shift_ten_km, "G-LANDMARK"),
    "swap tiers": (swap_tiers, "G-TIER"),
    "duplicate an id": (duplicate_ids, "G-ID"),
    "a QID as a name": (qid_as_name, "G-NAMES"),
    "kind without evidence": (drop_kind_evidence, "G-SCHEMA"),
    "two places share a QID": (shared_qid, "G-IDENT"),
    "a place outside the committed scope": (outside_scope, "G-COVER"),
    "empty bundle": (empty, "G-SCHEMA"),
}
# Gates tripped by the dedicated mutation tests below (each asserts the failure itself).
TRIPPED_ELSEWHERE = {"G-INTEGRITY", "G-COUNT", "G-EVIDENCE", "G-KIND"}


@pytest.mark.parametrize("label", MUTATIONS)
def test_mutation_is_caught(label, oracle, make_ctx):
    mutate, expected = MUTATIONS[label]
    ctx = make_ctx(mutate(copy.deepcopy(oracle)), name="m")
    results = {r.gate: r for r in gates.run_all(ctx)}
    assert not results[expected].passed, f"{label}: {expected} did not fail"


def test_tampering_and_count_mismatch_are_caught(oracle, make_ctx):
    ctx = make_ctx(oracle, name="t")
    f = next((ctx.bundle.root / "places").glob("*.json"))
    f.write_text(f.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert not gates.g_integrity(ctx).passed
    ctx2 = make_ctx(oracle, name="c")
    ctx2.bundle.manifest["counts"]["places"] += 1
    assert not gates.g_count(ctx2).passed


def test_evidence_and_kind_mutations(oracle, make_ctx):
    bad = copy.deepcopy(oracle)
    bad[0]["evidence"][0]["url"] = ""
    assert not gates.g_evidence(make_ctx(bad, name="e")).passed
    kind = copy.deepcopy(oracle)
    kind[0]["kinds"] = []
    assert not gates.g_kind(make_ctx(kind, name="k")).passed


def test_every_gate_is_tripped_by_a_test():
    """Adding a gate without a test that makes it fail fails this test."""
    tripped = {expected for _mutate, expected in MUTATIONS.values()} | TRIPPED_ELSEWHERE
    missing = CORE_AND_RELEASE - tripped - DEDICATED
    assert not missing, f"gates with no mutation or dedicated failing test: {sorted(missing)}"
