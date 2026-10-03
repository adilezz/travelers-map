"""Kind selection: deterministic, auditable, and geographically sensible on the golden places."""
import csv
import itertools
import random
from pathlib import Path

import pytest

from atlas import kinds as K
from atlas.kinds import Fired, load_pairs, select_kinds
from atlas.vocab import KIND_LABELS, KIND_PRIORITY, KINDS

ROOT = Path(__file__).resolve().parents[2]
PAIRS = load_pairs(ROOT / "data" / "rules" / "kind_pairs.csv")


def f(rule, kind, source, s, role="core", excludes=()):
    return Fired(rule, kind, source, s, role, tuple(excludes))


def test_vocabulary_is_consistent():
    assert len(KINDS) == 14 and len(set(KINDS)) == 14
    assert set(KIND_PRIORITY) == set(KINDS) and len(KIND_PRIORITY) == 14
    assert set(KIND_LABELS) == set(KINDS)
    assert "coast" not in KINDS and {"seaside", "maritime"} <= set(KINDS)


def test_every_pair_condition_has_a_predicate_and_every_kind_rule_is_valid():
    assert {p.condition for p in PAIRS} <= set(K.CONDITIONS)
    with open(ROOT / "data" / "rules" / "kinds.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    ids = [r["rule_id"] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        assert r["kind"] in KINDS and r["role"] in ("core", "support", "fallback")
        assert 0 < float(r["strength"]) <= 1 and r["calibrated"] in ("yes", "no")
        assert all(x in KINDS for x in r["excludes"].split("|") if x)
    assert {r["kind"] for r in rows} == set(KINDS) - {"sacred"} | {"sacred"}   # every kind has a rule


def test_a_support_rule_alone_cannot_create_a_kind():
    sel = select_kinds([f("R4", "seaside", "coast", 0.65, role="support")])
    assert sel.kinds() == [] and sel.cut[0]["reason"] == "no_core_rule"


def test_weak_kinds_are_cut_and_support_adds_strength():
    assert select_kinds([f("a", "forest", "landcover", 0.4)]).kinds() == []
    sel = select_kinds([f("a", "seaside", "wikidata", 0.4), f("b", "seaside", "coast", 0.4, role="support")])
    assert sel.kinds() == ["seaside"]            # 1 - 0.6 * 0.6 = 0.64


def test_correlated_rules_from_one_source_do_not_inflate():
    many = [f(f"w{i}", "ruins", "wikidata", 0.8) for i in range(6)]
    assert select_kinds(many).kept[0].strength == 0.8
    assert select_kinds(many + [f("o", "ruins", "osm", 0.7, role="support")]).kept[0].strength == pytest.approx(0.94)
    assert select_kinds(many + [f("o", "ruins", "osm", 0.9), f("u", "ruins", "unesco", 0.9)]).kept[0].strength == 0.95  # capped


# ---- the owner's overlap questions ------------------------------------------------------
def test_sacred_means_a_living_faith_and_ruins_a_dead_one():
    fired = [f("R10", "sacred", "wikidata", 0.8), f("R07", "ruins", "wikidata", 0.8)]
    karnak = select_kinds(fired, {"living_worship": False}, PAIRS)          # a temple nobody worships in
    assert karnak.kinds() == ["ruins"] and "pair:ruins>sacred" in karnak.cut[0]["reason"]
    sinai = select_kinds(fired, {"living_worship": True}, PAIRS)            # St Catherine's: a living monastery
    assert sinai.kinds() == ["sacred"]


def test_a_park_with_farms_is_wildlife_only_when_the_park_dominates():
    fired = [f("R12", "wildlife", "iucn", 0.85), f("R20", "rural", "landcover", 0.65)]
    assert select_kinds(fired, {"protected_overlap": 0.8, "cropland_share": 0.1}, PAIRS).kinds() == ["wildlife"]
    both = select_kinds(fired, {"protected_overlap": 0.5, "cropland_share": 0.5}, PAIRS)
    assert both.kinds() == ["wildlife", "rural"]                           # farmland is a real part of it


def test_wildlife_rule_excludes_rural_by_data():
    fired = [f("R12", "wildlife", "iucn", 0.85, excludes=("rural",)), f("R20", "rural", "landcover", 0.65)]
    assert select_kinds(fired).kinds() == ["wildlife"]


def test_capital_and_old_town_are_independent():
    fired = [f("R01", "capital", "wikidata", 0.9), f("R17", "old_town", "unesco", 0.85)]
    assert select_kinds(fired, {}, PAIRS).kinds() == ["capital", "old_town"]


def test_seaside_and_maritime_split():
    port = [f("R05", "maritime", "wikidata", 0.85), f("R03", "seaside", "wikidata", 0.8)]
    venice = select_kinds(port, {"population": 255_000, "beach_within_2km": False}, PAIRS)
    assert venice.kinds() == ["maritime"]
    resort_port = select_kinds(port, {"population": 120_000, "beach_within_2km": True}, PAIRS)
    assert resort_port.kinds() == ["maritime", "seaside"]                   # Aqaba-like: both are true
    assert select_kinds([f("R03", "seaside", "wikidata", 0.8)], {}, PAIRS).kinds() == ["seaside"]


def test_marine_water_is_seaside_not_water():
    fired = [f("R18", "water", "wikidata", 0.8), f("R03", "seaside", "wikidata", 0.8)]
    assert select_kinds(fired, {"water_is_marine": True}, PAIRS).kinds() == ["seaside"]
    assert select_kinds(fired, {"water_is_marine": False}, PAIRS).kinds() == ["seaside", "water"]


def test_a_big_city_is_not_the_countryside():
    fired = [f("R16", "metropolis", "pop", 0.85), f("R20", "rural", "landcover", 0.65)]
    assert select_kinds(fired, {}, PAIRS).kinds() == ["metropolis"]


# ---- worked examples with the 3-kind cap ----------------------------------------------------
def test_rome_keeps_capital_old_town_and_metropolis_and_cuts_ruins_by_the_cap():
    fired = [f("R01", "capital", "wikidata", 0.9), f("R17", "old_town", "unesco", 0.85),
             f("R16", "metropolis", "pop", 0.85), f("R07", "ruins", "wikidata", 0.8)]
    sel = select_kinds(fired, {}, PAIRS)
    assert sel.kinds() == ["capital", "old_town", "metropolis"]
    assert sel.cut == [{"kind": "ruins", "strength": 0.8, "reason": "cap"}]
    assert sel.crowded                     # ruins (0.80) was within 0.10 of the 3rd kind (0.85): flagged for review


def test_kilimanjaro_equal_strengths_are_ordered_by_priority_not_input_order():
    fired = [f("R12", "wildlife", "iucn", 0.85), f("R15", "volcanic", "wikidata", 0.85),
             f("R14", "mountain", "relief", 0.80), f("R19", "forest", "landcover", 0.8)]
    sel = select_kinds(fired, {}, PAIRS)
    assert sel.kinds() == ["volcanic", "wildlife", "mountain"]
    assert sel.cut[-1]["kind"] == "forest" and sel.crowded                   # forest was as strong as mountain


def test_more_independent_evidence_beats_priority_at_equal_strength():
    fired = [f("a", "rural", "landcover", 0.8), f("b", "rural", "wikidata", 0.2, role="support"),
             f("c", "sacred", "wikidata", 0.84)]
    sel = select_kinds(fired, {}, PAIRS)
    assert sel.kinds() == ["rural", "sacred"]                                # 0.84 combined with 2 sources > sacred's 0.84 with 1


def test_selection_is_independent_of_input_order():
    fired = [f("R01", "capital", "wikidata", 0.9), f("R17", "old_town", "unesco", 0.85), f("R16", "metropolis", "pop", 0.85),
             f("R05", "maritime", "wikidata", 0.85), f("R03", "seaside", "wikidata", 0.8), f("R07", "ruins", "wikidata", 0.8)]
    facts = {"population": 3_000_000, "beach_within_2km": False}
    baseline = select_kinds(fired, facts, PAIRS)
    rng = random.Random(7)
    for _ in range(40):
        shuffled = fired[:]
        rng.shuffle(shuffled)
        again = select_kinds(shuffled, facts, PAIRS)
        assert again.kinds() == baseline.kinds() and again.cut == baseline.cut


def test_every_pair_of_kinds_has_a_total_order():
    """No two distinct kinds can ever tie completely: the slug is the final tie-break."""
    for a, b in itertools.combinations(KINDS, 2):
        sel = select_kinds([f("x", a, "s", 0.8), f("y", b, "s", 0.8)], {}, [])
        assert sel.kinds() == sorted([a, b], key=lambda k: (KIND_PRIORITY.index(k), k))


def test_unknown_conditions_and_kinds_are_rejected(tmp_path):
    bad = tmp_path / "p.csv"
    bad.write_text("keep,drop,condition,rationale\nsacred,ruins,whenever,x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_pairs(bad)
    bad.write_text("keep,drop,condition,rationale\ncoast,ruins,always,x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_pairs(bad)


def test_fallback_rule_applies_only_when_nothing_else_survives():
    only = select_kinds([f("R21", "metropolis", "pop", 0.60, role="fallback")])
    assert only.kinds() == ["metropolis"]
    with_other = select_kinds([f("R21", "metropolis", "pop", 0.60, role="fallback"),
                               f("R17", "old_town", "unesco", 0.85)])
    assert with_other.kinds() == ["old_town"]
    assert select_kinds([f("R21", "metropolis", "pop", 0.40, role="fallback")]).kinds() == []
