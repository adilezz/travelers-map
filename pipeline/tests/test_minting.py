"""The registry rules of document 2 section 3.2, one test each."""
import random

import pytest

from atlas import minting as M
from atlas.gates import GateResult
from atlas.registry import Registry


def reg():
    return Registry({})


def rng():
    return random.Random(1)


def test_a_new_candidate_gets_an_opaque_valid_id():
    r = reg()
    pid = M.mint_or_reuse(r, ["qid:Q1", "geonames:99"], "b1", rng())
    assert pid.startswith("pl_") and len(pid) == 13
    assert r.rows[pid]["keys"] == {"qid:Q1", "geonames:99"} and r.rows[pid]["status"] == "active"


def test_rule_1_a_known_key_reuses_the_id_and_may_add_keys():
    r = reg()
    a = M.mint_or_reuse(r, ["qid:Q1"], "b1", rng())
    b = M.mint_or_reuse(r, ["qid:Q1", "osm:n5"], "b2", rng())
    assert a == b and r.rows[a]["keys"] == {"qid:Q1", "osm:n5"} and r.rows[a]["last_seen_build"] == "b2"
    assert M.mint_or_reuse(r, ["osm:n5"], "b3", rng()) == a          # any held key finds it


def test_rule_2_a_retired_place_is_reactivated_not_reminted():
    r = reg()
    a = M.mint_or_reuse(r, ["qid:Q1"], "b1", rng())
    M.retire(r, a, "b2", "below threshold")
    assert r.rows[a]["status"] == "retired"
    assert M.mint_or_reuse(r, ["qid:Q1"], "b3", rng()) == a and r.rows[a]["status"] == "active"
    M.retire(r, a, "b4", "x")
    with pytest.raises(M.MintingError):
        M.retire(r, a, "b5", "again")                                 # already retired


def test_rule_3_merge_redirects_and_keeps_the_losers_keys_resolvable():
    r = reg()
    loser = M.mint_or_reuse(r, ["qid:Q10"], "b1", rng())
    keep = M.mint_or_reuse(r, ["qid:Q11"], "b1", rng())
    M.merge(r, loser, keep, "b2")
    assert r.resolve(loser) == keep
    assert M.mint_or_reuse(r, ["qid:Q10"], "b3", rng()) == keep      # the old QID now lands on the survivor
    with pytest.raises(M.MintingError):
        M.merge(r, keep, loser, "b3")                                 # would make a cycle
    with pytest.raises(M.MintingError):
        M.merge(r, keep, keep, "b3")


def test_rule_4_a_split_mints_a_new_id_and_the_original_keeps_its_own():
    r = reg()
    a = M.mint_or_reuse(r, ["qid:Q1"], "b1", rng())
    part = M.split(r, a, ["qid:Q2"], "b2", rng())
    assert part != a and r.rows[part]["status"] == f"split_from:{a}" and r.rows[a]["status"] == "active"
    with pytest.raises(M.MintingError):
        M.split(r, a, ["qid:Q1"], "b3", rng())                        # a key already held cannot be reused
    with pytest.raises(M.MintingError):
        M.split(r, a, [], "b3", rng())


def test_rule_5_keys_that_point_at_two_places_must_be_resolved_explicitly():
    r = reg()
    M.mint_or_reuse(r, ["qid:Q1"], "b1", rng())
    M.mint_or_reuse(r, ["qid:Q2"], "b1", rng())
    with pytest.raises(M.MintingError, match="2 different places"):
        M.mint_or_reuse(r, ["qid:Q1", "qid:Q2"], "b2", rng())
    with pytest.raises(M.MintingError):
        M.mint_or_reuse(r, [], "b2", rng())


def test_a_key_never_moves_to_another_place():
    r = reg()
    a = M.mint_or_reuse(r, ["qid:Q1", "wdpa:5"], "b1", rng())
    b = M.mint_or_reuse(r, ["qid:Q2"], "b1", rng())
    with pytest.raises(M.MintingError):
        M.mint_or_reuse(r, ["qid:Q2", "wdpa:5"], "b2", rng())        # wdpa:5 belongs to a, qid:Q2 to b
    assert r.rows[a]["keys"] == {"qid:Q1", "wdpa:5"} and r.rows[b]["keys"] == {"qid:Q2"}


def test_minted_ids_are_unique_and_deterministic_for_a_seed():
    r1, r2 = reg(), reg()
    ids1 = [M.mint_or_reuse(r1, [f"qid:Q{i}"], "b", random.Random(5 + i)) for i in range(50)]
    ids2 = [M.mint_or_reuse(r2, [f"qid:Q{i}"], "b", random.Random(5 + i)) for i in range(50)]
    assert ids1 == ids2 and len(set(ids1)) == 50


def test_keys_are_looked_up_qid_first_but_any_key_finds_the_place():
    assert M.ordered(["osm:n1", "geonames:3", "qid:Q9", "wdpa:2"]) == ["qid:Q9", "wdpa:2", "geonames:3", "osm:n1"]


def test_save_roundtrips_through_parquet_in_a_stable_order(tmp_path):
    r = reg()
    for i in range(5):
        M.mint_or_reuse(r, [f"qid:Q{i}"], "b1", random.Random(i))
    M.save(r, tmp_path / "a.parquet")
    back = Registry.load(tmp_path / "a.parquet")
    assert list(back.rows) == sorted(r.rows)                          # written sorted by id
    assert all(back.rows[i]["keys"] == r.rows[i]["keys"] for i in r.rows)
    M.save(back, tmp_path / "b.parquet")                              # a second round trip changes nothing
    again = Registry.load(tmp_path / "b.parquet")
    assert {i: again.rows[i]["keys"] for i in again.rows} == {i: r.rows[i]["keys"] for i in r.rows}


def test_rule_6_commit_needs_a_passing_landmark_gate_and_real_qids(tmp_path, golden_rows):
    r = reg()
    M.mint_or_reuse(r, ["qid:Q1"], "b1", rng())
    ok = [GateResult("G-LANDMARK", True, "")]
    bad = [GateResult("G-LANDMARK", False, "")]
    with pytest.raises(M.MintingError, match="has not passed"):
        M.commit(r, tmp_path / "r.parquet", bad, golden_rows)
    with pytest.raises(M.MintingError, match="has not passed"):
        M.commit(r, tmp_path / "r.parquet", [], golden_rows)
    with pytest.raises(M.MintingError, match="no QID"):
        M.commit(r, tmp_path / "r.parquet", ok, golden_rows)          # the real golden set has blank QIDs today
    filled = [type(row)(**{**row.__dict__, "qid": row.qid or "Q1"}) for row in golden_rows]
    M.commit(r, tmp_path / "r.parquet", ok, filled)
    assert (tmp_path / "r.parquet").is_file()
