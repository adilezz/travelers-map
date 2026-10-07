import math

from atlas import admit as A

CFG = {"admission": {"r2_attention_sitelinks": 40, "r3_city_population": 100000, "r4_corroborated_sitelinks": 15,
                     "r5_country_floor": {"sovereign": 2}},
       "notability": {"recognition_cap": 1.5, "recognition": {"whs": 1.0, "national_top": 0.2}, "size_term_cap": 0.3,
                      "size_term_coefficient": 0.15, "size_term_reference_population": 100000},
       "tiers": {"icon": {"global_percentile": 99, "country_top": 3, "small_country_top": 1, "small_country_below": 10},
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
    assert tiers["P19"] == tiers["P18"] == tiers["P17"] == "Icon" and tiers["P16"] == "Major" and tiers["P0"] == "Local"


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
    mount, park = _p("Mount", 2.0, "area", sitelinks=188, lat=-3.06, lon=37.36, iso3="TZA"), \
        _p("Park", 2.5, "area", sitelinks=47, lat=-3.07, lon=37.37, iso3="TZA", whs="403")
    kept, log = A.absorb([mount, park])
    assert [p["qid"] for p in kept] == ["Mount"] and mount["whs"] == "403" and log[0]["child"] == "Park"
