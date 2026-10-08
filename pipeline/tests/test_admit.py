import math

from atlas import admit as A

CFG = {"admission": {"r2_attention_sitelinks": 40, "r3_city_population": 100000, "r4_corroborated_sitelinks": 15,
                     "r5_country_floor": {"sovereign": 2}},
       "notability": {"recognition_cap": 1.5, "recognition": {"whs": 1.0, "national_top": 0.2}, "size_term_cap": 0.3,
                      "size_term_coefficient": 0.15, "size_term_reference_population": 100000},
       "tiers": {"icon": {"country_top_by_whs": [[9, 4], [30, 6], [None, 8]], "small_country_top": 1, "small_country_below": 10},
                 "major": {"global_percentile": 95, "country_next": 10, "small_country_next": 3},
                 "notable": {"global_percentile": 75, "country_top_share": 0.4}}}
TYPES = [{"class_qid": "Qsite", "label": "archaeological site", "place_type": "site", "kind_hint": "ruins", "place_like": "yes"},
         {"class_qid": "Qcity", "label": "city", "place_type": "settlement", "kind_hint": "", "place_like": "yes"}]


def cand(qid, sl, classes, **kw):
    return {"qid": qid, "iso3": "ITA", "lat": 41.0, "lon": 12.0, "label_en": qid, "sitelinks": sl,
            "classes": set(classes), "heritage": [], **kw}


def test_whole_properties_are_r1_but_serial_components_are_not():
    out = A.admit({"Q1": cand("Q1", 3, ["Qsite"], whs="91"), "Q2": cand("Q2", 3, ["Qsite"], whs="669-612")}, {}, TYPES, CFG)
    got = {c["qid"]: c["rules"] for c in out}
    assert got["Q1"] == ["R1"] and "R1" not in got.get("Q2", [])     # a component may still enter by the country floor


def test_r2_r3_r4_and_the_place_like_requirement():
    cs = {"A": cand("A", 50, ["Qsite"]), "B": cand("B", 10, ["Qcity"], population=250000),
          "C": cand("C", 16, ["Qsite"], heritage=["Qx"]), "D": cand("D", 16, ["Qsite"]),
          "E": cand("E", 90, ["Qunknown"])}
    got = {c["qid"]: c["rules"] for c in A.admit(cs, {}, TYPES, CFG)}
    assert got["A"] == ["R2"] and got["B"] == ["R3"] and got["C"] == ["R4"]
    assert "D" not in got or got["D"] == ["R5"]          # no independent signal: only the country floor can take it
    assert "E" not in got                                  # a class outside the table is not place-like (yet)


def test_mass_class_items_need_the_class_relative_rank():
    cs = {"A": cand("A", 60, ["Qcity"]), "B": cand("B", 60, ["Qcity"])}
    scores = {"A": {"D": 9.0, "pct": 99.0}, "B": {"D": 1.0, "pct": 40.0}}
    got = {c["qid"] for c in A.admit(cs, scores, TYPES, CFG, top_share=0.03) if "R2" in c["rules"]}
    assert got == {"A"}


def test_short_names_and_base_names():
    long = "Gulf of Porto: Calanche of Piana, Gulf of Girolata, Scandola Reserve, and more words to pass the limit of sixty"
    assert A.short_name(long, []) == "Gulf of Porto"
    assert A.short_name("Mosque of Ahmed Ibn Tulun, The", []) == "The Mosque of Ahmed Ibn Tulun"
    assert A.short_name("x" * 5, ["ab"]) == "xxxxx" and A.short_name("a  b", []) == "a b"
    assert A.base_name("Madrid city") == A.base_name("City of Madrid") == A.base_name("Madrid")


def test_duplicates_merge_into_the_most_cited_and_keep_the_other_key():
    a = {**cand("Q1", 100, ["Qcity"]), "name_en": "Madrid"}
    b = {**cand("Q2", 5, ["Qcity"]), "name_en": "Madrid city"}
    far = {**cand("Q3", 5, ["Qcity"]), "name_en": "Madrid", "lat": 50.0}
    out = A.merge_duplicates([a, b, far], 5.0)
    assert sorted(p["qid"] for p in out) == ["Q1", "Q3"] and a["alt_qids"] == ["Q2"]


def test_notability_and_tiers_follow_the_documented_rules():
    n = A.notability({"D": 99.0, "whs": "91", "heritage": ["Qx"], "population": 1_000_000}, CFG)
    assert math.isclose(n, math.log10(100) + 1.2 + 0.15, rel_tol=1e-9)
    ps = [{"iso3": "ITA", "name_en": f"P{i}", "_n": float(i)} for i in range(20)]
    A.assign_tiers(ps, CFG)
    tiers = {p["name_en"]: p["tier"] for p in ps}
    assert {tiers[f"P{i}"] for i in (19, 18, 17, 16)} == {"Icon"} and tiers["P15"] == "Major" and tiers["P0"] == "Local"


def _p(qid, n, ptype, **kw):
    return {"qid": qid, "_n": n, "label_en": qid, "_type": {"place_type": ptype}, "sitelinks": int(n * 100), "iso3": "XXX",
            "lat": 0.0, "lon": 0.0, **kw}


def test_absorption_follows_d25():
    rome, colosseum = _p("Rome", 3.0, "settlement"), _p("Colosseum", 2.0, "site", parents=["Rome"])
    pompeii = _p("Pompeii", 2.0, "site", whs="829", parents=["Village"])              # better documented than its commune: stays
    chateau = _p("Chateau", 2.5, "site", parents=["Village"])
    village = _p("Village", 1.0, "settlement")                                       # fewer sitelinks than the site: no absorption
    giza, saqqara = _p("Giza", 2.5, "site", whs="86"), _p("Saqqara", 2.0, "site", whs="86")
    camino, ponferrada = _p("Camino", 2.0, "site", whs="669"), _p("Ponferrada", 1.5, "site", whs="669-612")
    kept, log = A.absorb([rome, colosseum, pompeii, chateau, village, giza, saqqara, camino, ponferrada])
    assert {p["qid"] for p in kept} == {"Rome", "Pompeii", "Chateau", "Village", "Giza", "Camino"}
    assert rome["alt_qids"] == ["Colosseum"] and giza["alt_qids"] == ["Saqqara"] and camino["alt_qids"] == ["Ponferrada"]
    assert {e["child"] for e in log} == {"Colosseum", "Saqqara", "Ponferrada"}


def test_absorption_resolves_chains_to_the_final_parent():
    city, a, b = _p("City", 3.0, "settlement"), _p("A", 2.0, "site", parents=["City"]), _p("B", 1.0, "site", parents=["A"])
    kept, _ = A.absorb([city, a, b])
    assert [p["qid"] for p in kept] == ["City"] and sorted(city["alt_qids"]) == ["A", "B"]


def test_a_protected_area_and_its_mountain_are_one_destination():
    mount = _p("Mount", 2.0, "area", sitelinks=188, lat=-3.06, lon=37.36, iso3="TZA", label_en="Mount Kilimanjaro")
    park = _p("Park", 2.5, "area", sitelinks=47, lat=-3.07, lon=37.37, iso3="TZA", whs="403", label_en="Kilimanjaro National Park")
    kept, log = A.absorb([mount, park])
    assert [p["qid"] for p in kept] == ["Mount"] and mount["whs"] == "403" and log[0]["child"] == "Park"


def test_revised_inscriptions_are_whole_properties():
    assert A.norm_whs("173rev") == "173" and A.PROPERTY_ID.match(A.norm_whs("173rev")) and not A.PROPERTY_ID.match("874.594")


def test_owner_anchors_enter_by_r6_and_stay_labelled():
    cs = {"Q9": cand("Q9", 7, ["Qsite"])}
    out = A.admit(cs, {}, TYPES, CFG, anchors={"Q9": "anchored after miss"})
    assert out[0]["rules"] == ["R6"] and out[0]["anchor_note"] == "anchored after miss"


def test_owner_rulings_merge_and_keep_the_losers_kinds_and_property():
    town = _p("Town", 2.0, "settlement", whs="173", classes={"Qa"})
    city = _p("City", 2.5, "settlement", classes={"Qb"})
    kept, log = A.absorb([town, city], [{"loser_key": "qid:City", "survivor_key": "qid:Town", "reason": "one destination"}])
    assert [p["qid"] for p in kept] == ["Town"] and town["classes"] == {"Qa", "Qb"} and town["whs"] == "173"
    assert log[0]["reason"].startswith("owner ruling")


def test_a_site_inside_a_world_heritage_place_is_its_asset_even_if_better_cited():
    valley = _p("Valley", 2.0, "site", sitelinks=88, parents=["Thebes"])
    thebes = _p("Thebes", 1.9, "site", sitelinks=82, whs="87")
    kept, _ = A.absorb([valley, thebes])
    assert [p["qid"] for p in kept] == ["Thebes"]


def test_descriptors_do_not_make_a_second_name():
    assert A.base_name("Historic City of Toledo") == A.base_name("Toledo") and A.base_name("Konya Province") == "konya"
    assert A.base_name("Essaouira Ramparts") == "essaouira"


def test_a_living_big_city_is_a_settlement_even_with_an_archaeological_class():
    types = [{"class_qid": "Qarch", "label": "archaeological site", "place_type": "site", "kind_hint": "ruins", "place_like": "yes"},
             {"class_qid": "Q1549591", "label": "big city", "place_type": "settlement", "kind_hint": "metropolis", "place_like": "yes"}]
    assert A.classify(["Qarch", "Q1549591"], types)["place_type"] == "settlement"
    assert A.kind_hints(["Qarch", "Q1549591"], types) == ["metropolis"]
    assert A.classify(["Qarch"], types)["place_type"] == "site"


def test_a_province_record_folds_into_its_seat_and_a_park_does_not_fold_into_its_island():
    seat = {**_p("Izmit", 2.0, "settlement", classes=set()), "lat": 40.77, "lon": 29.94, "sitelinks": 90}
    prov = {**_p("Kocaeli", 1.9, "settlement", classes={"Qprov"}), "lat": 40.76, "lon": 29.93, "sitelinks": 80}
    kept, log = A.absorb([seat, prov], admin={"Qprov"})
    assert [p["qid"] for p in kept] == ["Izmit"] and "province" in log[0]["reason"]
    island = {**_p("Isle", 2.0, "area", whs="380", label_en="La Gomera"), "sitelinks": 40}
    park = {**_p("Park", 2.0, "area", label_en="Garajonay National Park"), "sitelinks": 90}
    assert len(A.absorb([island, park])[0]) == 2


def test_recognition_terms_for_protected_areas_do_not_stack():
    cfg = {**CFG, "notability": {**CFG["notability"], "recognition": {"whs": 1.0, "national_top": 0.2, "iucn_ia_ii": 0.4,
                                                                     "protected_designation": 0.2}}}
    base = A.notability({"sitelinks": 9}, cfg)
    assert A.notability({"sitelinks": 9, "classes": {"Q46169"}}, cfg) == base + 0.2
    assert A.notability({"sitelinks": 9, "classes": {"Q46169"}, "iucn": True}, cfg) == base + 0.4
    table = {"1": {"iucn_cat": "II", "area_km2": 500.0}}
    out = A.admit({"Q1": cand("Q1", 7, ["Qsite"], wdpa="1")}, {}, TYPES, CFG, wdpa=table)
    assert out[0]["iucn"] is True and out[0]["rules"] == ["R1"]


def test_icon_count_grows_with_world_heritage_properties():
    t = CFG["tiers"]
    assert [A.icon_count(n, t) for n in (0, 9, 10, 30, 31, 61)] == [4, 4, 6, 6, 8, 8]
    ps = [{"iso3": "ITA", "name_en": f"P{i}", "_n": float(i), "whs": str(i + 1), "_type": {}} for i in range(40)]
    ps = [{**p, "lat": 0, "lon": 0} for p in ps]
    A.assign_tiers(ps, CFG)
    assert sum(1 for p in ps if p["tier"] == "Icon") == 8                       # 40 places hold a whole property each: over 30 gives 8


def test_world_heritage_ids_are_checked_against_the_unesco_list():
    assert A.norm_whs("1133bis") == "1133bis" and A.norm_whs("9999") == "" and A.norm_whs("not an id") == ""
    assert A.norm_whs("№395 в списке (en)") == "395" and A.norm_whs("874.594") == "874.594"
    assert A.better_whs("91-001", "91") == "91" and A.better_whs("91", "91-001") == "91" and A.better_whs(None, "91-001") == "91-001"


def test_context_is_not_a_destination_but_a_wadi_or_a_park_is():
    t = []
    river = {"classes": {"Q4022"}, "sitelinks": 200, "rules": ["R2"], "_type": {"place_type": "area"}}
    wadi = {"classes": {"Q4022", "Q187971"}, "sitelinks": 60, "rules": ["R2"], "_type": {"place_type": "area"}}
    region = {"classes": {"Q82794"}, "sitelinks": 200, "rules": ["R2"], "_type": {"place_type": "area"}, "population": 371_000_000}
    sahara = {"classes": {"Q8514"}, "sitelinks": 225, "rules": ["R2"], "_type": {"place_type": "area"}}
    assert A.is_context(river, t) and A.is_context(region, t) and A.is_context(sahara, t)
    assert not A.is_context(wadi, t) and not A.is_context({**river, "whs": "87"}, t)


def test_a_city_takes_the_record_of_its_historic_centre():
    rome = {**_p("Rome", 4.0, "settlement"), "sitelinks": 344, "label_en": "Rome", "lat": 41.89, "lon": 12.48, "iso3": "ITA", "whs": "91-003"}
    rec = {**_p("Rec", 1.0, "settlement"), "sitelinks": 21, "label_en": "Historic Centre of Rome", "lat": 41.90, "lon": 12.47, "iso3": "ITA",
           "whs": "91"}
    kept, log = A.absorb([rome, rec])
    assert [p["qid"] for p in kept] == ["Rome"] and rome["whs"] == "91"
