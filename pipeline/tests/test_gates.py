"""Each gate passes on the oracle bundle and fails on the defect it exists to catch."""
import copy

from conftest import pid, registry_for

from atlas import gates
from atlas import golden as G
from atlas.matching import assign
from atlas.registry import Registry


def clone(places):
    return copy.deepcopy(places)


def named(places, name):
    return next(p for p in places if p["name_en"] == name)


# ------------------------------------------------------------------------ the oracle passes
def test_oracle_passes_every_gate_that_can_run(oracle, make_ctx):
    ctx = make_ctx(oracle)
    for g in (gates.g_schema, gates.g_golden, gates.g_landmark, gates.g_tier, gates.g_id,
              gates.g_ident, gates.g_names, gates.g_count, gates.g_cover, gates.g_evidence,
              gates.g_integrity, gates.g_churn):
        r = g(ctx)
        assert r.passed, f"{r.gate}: {r.detail}"
        assert r.n is not None


def test_run_all_is_never_green_before_m4(oracle, make_ctx):
    results = gates.run_all(make_ctx(oracle))
    assert any(not r.passed for r in results)
    assert {r.gate for r in results if r.pending} == {"G-DETERMINISM", "G-REGION", "G-DISPUTE", "G-PRINT"}
    assert all(not r.passed for r in results if r.pending)


# -------------------------------------------------------------------------------- landmarks
def test_v1_failure_machu_picchu_shipped_as_quillabamba(oracle, make_ctx):
    bad = clone(oracle)
    mp = named(bad, "Machu Picchu")
    mp.update(name_en="Quillabamba", aliases=[], lat=-12.86, lon=-72.69)
    r = gates.g_landmark(make_ctx(bad))
    assert not r.passed and "REGRESSION" in r.detail


def test_landmark_fails_when_a_regression_landmark_is_missing(oracle, make_ctx):
    kept = [p for p in oracle if p["name_en"] != "Petra"]
    r = gates.g_landmark(make_ctx(kept))
    assert not r.passed and "REGRESSION" in r.detail


def test_landmark_requires_the_right_type_and_country(oracle, make_ctx):
    wrong_type = clone(oracle)
    named(wrong_type, "Petra")["type"] = "settlement"
    assert not gates.g_landmark(make_ctx(wrong_type)).passed
    wrong_country = clone(oracle)
    named(wrong_country, "Petra")["iso3"] = "EGY"
    assert not gates.g_landmark(make_ctx(wrong_country)).passed


def test_a_duplicate_of_a_landmark_fails(oracle, make_ctx):
    dup = clone(oracle) + [{**named(oracle, "Florence"), "place_id": pid("dupflorence"), "qid": "Q1"}]
    r = gates.g_landmark(make_ctx(dup))
    assert not r.passed and "duplicates" in r.detail


def test_assignment_is_one_to_one():
    from atlas.geo import fold
    from atlas.golden import Row

    def row(gid, name):
        return Row(raw={}, golden_id=gid, iso3="EGY", name=name, names={fold(name), "shared"},
                   type="site", lat=30.0, lon=31.0, tol_km=5.0, min_tier="Icon")
    place = {"place_id": "p", "iso3": "EGY", "type": "site", "name_en": "Shared", "lat": 30.0, "lon": 31.0}
    a = assign([row("G1", "A"), row("G2", "B")], [place])
    assert len(a.matched) == 1 and len(a.missed) == 1


def test_serial_component_as_separate_place_fails(oracle, make_ctx):
    bad = clone(oracle) + [{**named(oracle, "Giza Pyramids"), "place_id": pid("khufu"),
                            "name_en": "Great Pyramid of Khufu", "aliases": [], "qid": "Q2"}]
    r = gates.g_landmark(make_ctx(bad))
    assert not r.passed and "Khufu" in r.detail


def test_relational_checks_cannot_be_evaded_by_another_country_label(oracle, make_ctx):
    """v1/M0 matched on a country name string; a place under another iso3 evaded the check."""
    bad = clone(oracle) + [{**named(oracle, "Giza Pyramids"), "place_id": pid("khufu2"),
                            "name_en": "Great Pyramid of Khufu", "aliases": [], "qid": "Q3", "iso3": "EGY"}]
    assert not gates.g_landmark(make_ctx(bad)).passed
    for p in bad:
        p["country"] = "EGY"   # an extra field changes nothing
    assert not gates.g_landmark(make_ctx(bad, name="b2")).passed


def test_relational_row_fails_closed_when_the_country_has_no_places(oracle, make_ctx):
    no_egypt = [p for p in oracle if p["iso3"] != "EGY"]
    r = gates.g_landmark(make_ctx(no_egypt))
    assert not r.passed and "no places in EGY" in r.detail


def test_nested_destinations_may_exist_or_not(oracle, make_ctx):
    """Colosseum and Uffizi are optional rows: both outcomes pass."""
    rome = named(oracle, "Rome")
    with_nested = clone(oracle) + [{**rome, "place_id": pid("colosseum"), "name_en": "Colosseum",
                                    "aliases": [], "type": "site", "qid": "Q4"}]
    assert gates.g_landmark(make_ctx(with_nested, name="n1")).passed
    assert gates.g_landmark(make_ctx(oracle, name="n2")).passed


def test_town_carrying_a_landmarks_evidence_fails(oracle, make_ctx):
    mp = named(oracle, "Machu Picchu")
    bad = clone(oracle) + [{**mp, "place_id": pid("quilla"), "name_en": "Quillabamba", "aliases": [],
                            "type": "settlement", "lat": -12.86, "lon": -72.69, "qid": "Q5"}]
    r = gates.g_landmark(make_ctx(bad))
    assert not r.passed and "evidence" in r.detail


def test_not_credited_fails_closed_when_the_target_is_missing(oracle, make_ctx):
    town = {**named(oracle, "Petra"), "place_id": pid("maan"), "name_en": "Ma'an", "aliases": [],
            "type": "settlement", "qid": "Q6"}
    bad = [p for p in oracle if p["name_en"] != "Petra"] + [town]
    r = gates.g_landmark(make_ctx(bad))
    assert not r.passed and "unresolved" in r.detail


# ----------------------------------------------------------------------------------- tiers
def test_tier_fails_when_florence_is_below_floor(oracle, make_ctx):
    bad = clone(oracle)
    named(bad, "Florence")["tier"] = "Notable"
    assert not gates.g_tier(make_ctx(bad)).passed


def test_tier_fails_when_belluno_outranks_florence(oracle, make_ctx):
    bad = clone(oracle) + [{**named(oracle, "Florence"), "place_id": pid("belluno"), "name_en": "Belluno",
                            "aliases": [], "qid": "Q7", "lat": 46.14, "lon": 12.22, "tier": "Icon"}]
    r = gates.g_tier(make_ctx(bad))
    assert not r.passed and "Belluno" in r.detail


def test_tier_respects_max_tier(oracle, make_ctx):
    bad = clone(oracle)
    named(bad, "Wadi Al-Hitan")["tier"] = "Icon"
    assert not gates.g_tier(make_ctx(bad)).passed


def test_egypt_ordering_test_needs_all_targets(oracle, make_ctx):
    bad = [p for p in oracle if p["name_en"] != "Cairo"]
    r = gates.g_tier(make_ctx(bad))
    assert not r.passed and "unresolved" in r.detail


# --------------------------------------------------------------------------------- identity
def test_id_rejects_a_v1_style_id_and_duplicates(oracle, make_ctx):
    bad = clone(oracle)
    bad[0]["place_id"] = "MOR-c2555567"
    assert not gates.g_id(make_ctx(bad)).passed
    dup = clone(oracle) + [clone(oracle)[0]]
    assert not gates.g_id(make_ctx(dup, name="d")).passed


def test_id_needs_a_registry(oracle, make_ctx):
    assert not gates.g_id(make_ctx(oracle, registry=None)).passed


def test_id_rejects_unregistered_and_retired(oracle, make_ctx):
    reg = registry_for(oracle)
    fresh = clone(oracle)
    fresh[0]["place_id"] = pid("never registered")
    assert not gates.g_id(make_ctx(fresh, registry=reg)).passed
    reg.rows[oracle[1]["place_id"]]["status"] = "retired"
    assert not gates.g_id(make_ctx(oracle, registry=reg, name="r")).passed


def test_id_rejects_a_registry_row_without_status(oracle, make_ctx):
    reg = registry_for(oracle)
    reg.rows[oracle[0]["place_id"]]["status"] = ""
    assert not gates.g_id(make_ctx(oracle, registry=reg)).passed


def test_id_rule_5_a_key_may_not_move_to_another_id(oracle, make_ctx):
    reg = registry_for(oracle)
    other = oracle[1]["place_id"]
    reg.rows[other]["keys"] = reg.rows[other]["keys"] | {f"qid:{oracle[0]['qid']}"}   # same QID, two ids
    r = gates.g_id(make_ctx(oracle, registry=reg))
    assert not r.passed and "more than one id" in r.detail or "registered to" in r.detail


def test_id_rejects_a_place_that_carries_unregistered_keys(oracle, make_ctx):
    reg = registry_for(oracle)
    reg.rows[oracle[0]["place_id"]]["keys"] = set()
    r = gates.g_id(make_ctx(oracle, registry=reg))
    assert not r.passed and "keys" in r.detail


def test_id_flags_ids_lost_without_a_registry_status(oracle, make_ctx):
    prev = make_ctx(oracle, name="prev").bundle
    reg = registry_for(oracle)
    smaller = make_ctx(oracle[:-1], registry=reg, previous=prev, name="cur")
    assert not gates.g_id(smaller).passed
    reg.rows[oracle[-1]["place_id"]]["status"] = "retired"
    assert gates.g_id(make_ctx(oracle[:-1], registry=reg, previous=prev, name="cur2")).passed


def test_ident_rejects_shared_qid_and_broken_chains(oracle, make_ctx):
    bad = clone(oracle)
    bad[1]["qid"] = bad[0]["qid"]
    assert not gates.g_ident(make_ctx(bad)).passed
    reg = registry_for(oracle)
    reg.rows["pl_aaaaaaaaaa"] = {"status": "merged_into:pl_bbbbbbbbbb", "keys": set()}
    assert not gates.g_ident(make_ctx(oracle, registry=reg, name="m")).passed


def test_registry_follows_merge_chains_and_loads_both_formats(tmp_path):
    reg = Registry({"a": {"status": "merged_into:b", "keys": set()}, "b": {"status": "merged_into:c", "keys": set()},
                    "c": {"status": "active", "keys": set()}})
    assert reg.resolve("a") == "c"
    cyc = Registry({"a": {"status": "merged_into:b", "keys": set()}, "b": {"status": "merged_into:a", "keys": set()}})
    assert cyc.resolve("a") is None
    p = tmp_path / "r.csv"
    p.write_text("place_id,keys,status\npl_0000000001,qid:Q1|whs:5,active\n", encoding="utf-8")
    assert Registry.load(p).rows["pl_0000000001"]["keys"] == {"qid:Q1", "whs:5"}
    import duckdb
    pq = tmp_path / "r.parquet"
    con = duckdb.connect()
    con.execute("create table r(place_id varchar, keys varchar[], status varchar, minted_build varchar, last_seen_build varchar, tombstone_reason varchar)")
    con.execute("insert into r values ('pl_0000000002', ['qid:Q2'], 'active', 'b1', 'b1', null)")
    con.execute(f"copy r to '{pq}' (format parquet)")
    assert Registry.load(pq).rows["pl_0000000002"]["keys"] == {"qid:Q2"}


# ------------------------------------------------------------------------ names, counts, evidence
def test_names_reject_v1_defects(oracle, make_ctx):
    for i, bad_name in enumerate(["Q130654972", "Fujian <em>Tulou</em>", "Rede de A\x81reas Marinhas",
                                  "Zones A2, A3, A4, A5 kai A7 periochis A Ethnikou Thalassiou Parkou Voreion Sporadon",
                                  "Ã\xa0 mojibake", ""]):
        bad = clone(oracle)
        bad[0]["name_en"] = bad_name
        assert not gates.g_names(make_ctx(bad, name=f"n{i}")).passed, bad_name


def test_names_report_a_skip_and_strict_builds_fail_on_it(oracle, make_ctx):
    assert gates.g_names(make_ctx(oracle)).skipped == 1
    assert not gates.g_names(make_ctx(oracle, strict=True, name="s")).passed


def test_count_gate_needs_per_country_and_matching_numbers(oracle, make_ctx):
    ctx = make_ctx(oracle)
    assert gates.g_count(ctx).passed
    ctx.bundle.manifest["counts"]["places"] += 1
    assert not gates.g_count(ctx).passed
    ctx.bundle.manifest["counts"]["places"] -= 1
    del ctx.bundle.manifest["counts"]["per_country"]
    assert not gates.g_count(ctx).passed


def test_evidence_gate(oracle, make_ctx):
    bad = clone(oracle)
    bad[0]["evidence"][0]["url"] = ""
    assert not gates.g_evidence(make_ctx(bad)).passed
    none_id = clone(oracle)
    none_id[0]["evidence"][0]["asset_id"] = None
    none_id[0]["kinds"][0]["evidence"] = [None]
    assert not gates.g_evidence(make_ctx(none_id, name="b2")).passed
    dangling = clone(oracle)
    dangling[0]["kinds"][0]["evidence"] = ["missing"]
    assert not gates.g_evidence(make_ctx(dangling, name="b3")).passed


def test_integrity_detects_tampering_and_needs_hashes(oracle, make_ctx):
    ctx = make_ctx(oracle)
    f = next((ctx.bundle.root / "places").glob("*.json"))
    f.write_text(f.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert not gates.g_integrity(ctx).passed
    ctx2 = make_ctx(oracle, name="b2")
    ctx2.bundle.manifest["hashes"] = {}
    assert not gates.g_integrity(ctx2).passed


# ----------------------------------------------------------------------------------- churn
def test_churn_first_build_passes_and_big_changes_need_a_committed_cause(oracle, make_ctx):
    prev = make_ctx(oracle, name="prev").bundle
    changed = clone(oracle)
    for p in changed[:10]:
        p["tier"] = "Local"
    assert not gates.g_churn(make_ctx(changed, previous=prev, name="a")).passed
    assert not gates.g_churn(make_ctx(changed, previous=prev, name="b", manifest_extra={"recorded_cause": "x"})).passed
    ok = make_ctx(changed, previous=prev, name="c", manifest_extra={"recorded_cause": "retune-2026-10"},
                  changelog={"causes": [{"id": "retune-2026-10", "description": "tier thresholds"}]})
    assert gates.g_churn(ok).passed


def test_churn_counts_renames_and_moves(oracle, make_ctx):
    prev = make_ctx(oracle, name="prev").bundle
    moved = clone(oracle)
    for p in moved:
        p["name_en"], p["lat"] = "Zzz", 0.0
    assert not gates.g_churn(make_ctx(moved, previous=prev, name="m")).passed


# -------------------------------------------------------------------------------- coverage
def test_cover_reads_the_committed_scope_not_the_bundles(oracle, make_ctx):
    only_peru = [p for p in oracle if p["iso3"] == "PER"]
    r = gates.g_cover(make_ctx(only_peru, manifest_extra={"scope": {"sovereign": ["PER"], "exemptions": ["EGY"]}}))
    assert not r.passed
    assert not gates.g_cover(make_ctx(oracle, scope=None, name="n")).passed
    outside = clone(oracle)
    outside.append({**oracle[0], "place_id": pid("fr"), "iso3": "FRA", "qid": "Q9"})
    assert not gates.g_cover(make_ctx(outside, name="o")).passed


# --------------------------------------------------------------------------------- kinds
def balanced_world(n_per_kind=30):
    from atlas.vocab import KINDS
    out = []
    for k in KINDS:
        for i in range(n_per_kind):
            out.append({"place_id": pid(f"{k}{i}"), "type": "site", "name_en": f"{k}{i}", "iso3": "EGY",
                        "lat": 30.0 + i * 0.01, "lon": 31.0, "tier": "Local", "status": "active", "aliases": [],
                        "kinds": [{"kind": k, "rule": "r", "evidence": ["a"]}],
                        "evidence": [{"asset_id": "a", "source": "s", "url": "https://x", "retrieved": "2026-10-01"}]})
    return out


def test_kind_gate_share_checks_are_skipped_loudly_on_small_bundles(oracle, make_ctx):
    lenient = gates.g_kind(make_ctx(oracle))
    assert lenient.passed and lenient.skipped == 1
    strict = gates.g_kind(make_ctx(oracle, strict=True, name="s"))
    assert not strict.passed and "prototype" in strict.detail


def test_kind_gate_on_a_balanced_world_and_its_defects(make_ctx):
    world = balanced_world()
    assert gates.g_kind(make_ctx(world, strict=True)).passed
    one_kind = clone(world)
    for p in one_kind[:200]:
        p["kinds"] = [{"kind": "ruins", "rule": "r", "evidence": ["a"]}]
    assert not gates.g_kind(make_ctx(one_kind, name="a")).passed
    repeated = clone(world)
    repeated[0]["kinds"] = [repeated[0]["kinds"][0]] * 2
    assert not gates.g_kind(make_ctx(repeated, name="b")).passed
    none = clone(world)
    none[0]["kinds"] = []
    assert not gates.g_kind(make_ctx(none, name="c")).passed


def test_kind_precision_needs_labels_for_every_kind(make_ctx):
    world = balanced_world()
    labels = [{"place_id": p["place_id"], "kinds": p["kinds"][0]["kind"]} for p in world]
    assert gates.g_kind_precision(make_ctx(world, labels=labels)).passed
    assert not gates.g_kind_precision(make_ctx(world, labels=None, name="n")).passed
    only_one = [lab for lab in labels if lab["kinds"] == "ruins"]
    assert not gates.g_kind_precision(make_ctx(world, labels=only_one, name="o")).passed   # unlabelled kinds fail
    wrong = [dict(lab, kinds="water") if lab["kinds"] == "coast" else lab for lab in labels]
    assert not gates.g_kind_precision(make_ctx(world, labels=wrong, name="w")).passed


# ------------------------------------------------------------------------ release-only gates
def holdout_world(n=100):
    rows, places = [], []
    for i in range(n):
        lat = 20.0 + i * 0.2
        name = f"Holdout {i}"
        rows.append(G.Row(raw={}, golden_id=f"H{i}", iso3="EGY", name=name, names={name.lower()}, type="site",
                          lat=lat, lon=33.0, tol_km=3.0, min_tier="Notable", kinds=("ruins",)))
        places.append({"place_id": pid(f"h{i}"), "type": "site", "name_en": name, "iso3": "EGY", "lat": lat, "lon": 33.0,
                       "tier": "Notable", "status": "active", "aliases": [], "kinds": [{"kind": "ruins", "rule": "r", "evidence": ["a"]}],
                       "evidence": [{"asset_id": "a", "source": "s", "url": "https://x", "retrieved": "2026-10-01"}]})
    return rows, places


def test_holdout_gate(make_ctx):
    rows, places = holdout_world()
    sha = "abc"
    base = dict(holdout=rows, holdout_sha=sha, freeze={"holdout_sha256": sha})
    assert gates.g_holdout(make_ctx(places, **base)).passed
    assert not gates.g_holdout(make_ctx(places, holdout=None, name="n")).passed                          # no holdout
    assert not gates.g_holdout(make_ctx(places, holdout=rows[:50], holdout_sha=sha, freeze={"holdout_sha256": sha}, name="s")).passed  # too small
    assert not gates.g_holdout(make_ctx(places, holdout=rows, holdout_sha=sha, freeze=None, name="f")).passed        # not frozen
    assert not gates.g_holdout(make_ctx(places, holdout=rows, holdout_sha="changed", freeze={"holdout_sha256": sha}, name="c")).passed
    assert not gates.g_holdout(make_ctx(places[:80], name="r", **base)).passed                            # recall too low


def test_holdout_must_be_disjoint_from_the_golden_set(make_ctx, golden_rows):
    rows, places = holdout_world()
    rows[0] = next(r for r in golden_rows if r.name == "Petra")
    sha = "abc"
    r = gates.g_holdout(make_ctx(places, holdout=rows, holdout_sha=sha, freeze={"holdout_sha256": sha}))
    assert not r.passed and "duplicate golden" in r.detail


def test_precision_gate_needs_linked_unique_reviews(make_ctx):
    world = balanced_world(10)[:120]
    review = [{"place_id": p["place_id"], "verdict": "right"} for p in world[:100]]
    assert gates.g_precision(make_ctx(world, review=review)).passed
    assert not gates.g_precision(make_ctx(world, review=[{"verdict": "right"}] * 100, name="a")).passed   # not linked
    assert not gates.g_precision(make_ctx(world, review=review[:50], name="b")).passed                     # too few
    bad = review[:90] + [{"place_id": p["place_id"], "verdict": "wrong_name"} for p in world[90:100]]
    assert not gates.g_precision(make_ctx(world, review=bad, name="c")).passed
    assert not gates.g_precision(make_ctx(world, review=review[:99] + [review[0]], name="d")).passed       # duplicate row


# ------------------------------------------------------------------------------ fail closed
def test_a_crashing_gate_becomes_a_failure(oracle, make_ctx):
    @gates.gate("G-BOOM")
    def boom(ctx):
        raise RuntimeError("kaboom")
    r = boom(make_ctx(oracle))
    assert not r.passed and "crashed: RuntimeError" in r.detail


def test_malformed_bundles_fail_every_relevant_gate_without_crashing(oracle, make_ctx):
    mutations = {
        "null id": lambda p: p.update(place_id=None),
        "kinds as strings": lambda p: p.update(kinds=["ruins"]),
        "string lat": lambda p: p.update(lat="x"),
        "tier None": lambda p: p.update(tier=None),
        "alias without key": lambda p: p.update(aliases=[{"nope": 1}]),
        "evidence not a list": lambda p: p.update(evidence="x"),
    }
    for label, mutate in mutations.items():
        bad = clone(oracle)
        mutate(bad[0])
        results = gates.run_all(make_ctx(bad, name=label.replace(" ", "_")))
        assert all(not r.detail.startswith("crashed") for r in results), (label, [r.detail for r in results if r.detail.startswith("crashed")])
        assert not next(r for r in results if r.gate == "G-SCHEMA").passed, label


def test_empty_bundle_passes_nothing_that_depends_on_it(make_ctx):
    results = {r.gate: r for r in gates.run_all(make_ctx([]))}
    passing = {g for g, r in results.items() if r.passed}
    assert passing <= {"G-GOLDEN", "G-CHURN"}, passing
