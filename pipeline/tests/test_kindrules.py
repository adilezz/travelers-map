from atlas import kindrules as KR
from atlas import kinds as K

RULES, SETS, PARAMS = KR.load_rules(), KR.load_class_sets(), KR.load_params()
PAIRS = K.load_pairs(KR.ROOT / "data" / "rules" / "kind_pairs.csv")


def ctx(geo=None, wdpa=None, states=None, near=False):
    return KR.Context(RULES, SETS, PARAMS, states or {}, wdpa or {}, geo or {}, lambda c, km, pop: near)


def place(qid="Q1", classes=(), pop=0, ptype="settlement", **kw):
    return {"qid": qid, "classes": set(classes), "population": pop, "_type": {"place_type": ptype}, "lat": 0.0, "lon": 0.0, **kw}


def kinds(c, x):
    sel, hits = KR.kinds_for(c, x, PAIRS)
    return sel.kinds(), hits


def test_every_rule_that_is_evaluated_exists_in_the_rule_table():
    for rid in ("R01", "R02", "R03", "R05", "R07", "R10", "R12", "R12b", "R13", "R13b", "R14", "R14b", "R15", "R16", "R17", "R18",
                "R19", "R20", "R21"):
        assert rid in RULES
    assert set(SETS) <= set(RULES) and set(RULES) >= KR.NOT_EVALUATED


def test_current_and_former_capitals_need_a_state():
    states = {"Q79": {"Q3624078"}, "Q12560": {"Q48349", "Q3024240"}, "Q154547": {"Q154547x"}}
    cairo = place("Q85", capital_of=[{"qid": "Q79", "ended": False}], pop=9_800_000)
    got, _ = kinds(cairo, ctx(states=states))
    assert "capital" in got and "metropolis" in got
    cusco = place("Q2", capital_of=[{"qid": "Q12560", "ended": True}], pop=400_000)
    assert "capital" in kinds(cusco, ctx(states=states))[0]
    seat = place("Q3", capital_of=[{"qid": "Q154547", "ended": False}], pop=20_000)
    assert "capital" not in kinds(seat, ctx(states=states))[0]


def test_geometry_facts_make_mountain_forest_desert_and_rural():
    assert "mountain" in kinds(place(), ctx({"Q1": {"relief_10km": 1600.0}}))[0]
    assert "mountain" in kinds(place(), ctx({"Q1": {"max_elev_2km": 2600.0}}))[0]
    assert "forest" in kinds(place(), ctx({"Q1": {"tree_10km": 0.8}}))[0]
    assert "desert" in kinds(place(), ctx({"Q1": {"bare_20km": 0.8}}))[0]
    got, hits = kinds(place(), ctx({"Q1": {"crop_10km": 0.6, "grass_10km": 0.2}}))
    assert got == ["rural"] and hits["R20"] == ["geo:Q1"]
    assert kinds(place(), ctx({"Q1": {"crop_10km": 0.6, "grass_10km": 0.2}}, near=True))[0] == []      # a city within 10 km: not countryside


def test_classes_of_merged_items_support_but_cannot_create_a_kind_alone():
    ruins = place("Q9", classes={"Q839954"})
    assert kinds(ruins, ctx())[0] == ["ruins"]
    city = place("Q8", classes={"Q515"}, pop=500_000, members={"Q7": {"classes": {"Q839954"}}})
    got, hits = kinds(city, ctx())
    assert "ruins" in got and hits["R07"] == ["wd:Q7"]                       # the merged item is the evidence


def test_a_big_port_needs_the_sea_nearby_and_a_living_faith_is_sacred_not_ruins():
    port = place("Q4", classes={"Q44782"}, pop=300_000)
    assert "maritime" not in kinds(port, ctx({"Q4": {"coast_km": 40.0}}))[0]
    assert "maritime" in kinds(port, ctx({"Q4": {"coast_km": 1.0}}))[0]
    monastery = place("Q5", classes={"Q44613", "Q839954"}, ptype="site")
    assert "ruins" in kinds(monastery, ctx())[0]                              # a dead faith as well: ruins wins by the pair rule
    living = place("Q6", classes={"Q44613"}, ptype="site")
    assert kinds(living, ctx())[0] == ["sacred"]


def test_iucn_categories_and_the_fallback_for_ordinary_cities():
    park = place("Q10", ptype="area", wdpa="555")
    assert "wildlife" in kinds(park, ctx(wdpa={"555": {"iucn_cat": "II", "area_km2": 900.0}}))[0]
    assert "wildlife" not in kinds(park, ctx(wdpa={"555": {"iucn_cat": "VI", "area_km2": 900.0}}))[0]
    lille = place("Q11", classes={"Q515"}, pop=230_000)
    sel, hits = KR.kinds_for(lille, ctx(), PAIRS)
    assert sel.kinds() == ["metropolis"] and "R21" in hits


def test_a_nested_asset_supports_a_kind_but_only_a_dominant_one_creates_it():
    cairo = place("Q85", classes={"Q515"}, pop=9_000_000, sitelinks=261,
                  members={"Q1": {"classes": {"Q32815"}, "nested": True, "sitelinks": 30}})
    assert "sacred" not in kinds(cairo, ctx())[0]                                  # one mosque of many
    lourdes = place("Q86", classes={"Q515"}, sitelinks=87, members={"Q2": {"classes": {"Q1370598"}, "nested": True, "sitelinks": 40}})
    assert "sacred" in kinds(lourdes, ctx())[0]                                    # the sanctuary carries the town
    thebes = place("Q87", classes={"Q515"}, sitelinks=100, members={"Q3": {"classes": {"Q839954"}, "nested": False, "sitelinks": 1}})
    assert "ruins" in kinds(thebes, ctx())[0]                                      # an identity merge always counts


def test_old_town_from_the_unesco_title_and_the_state_side_capitals():
    titles = {"174": "Historic Centre of Florence", "86": "Memphis and its Necropolis", "1": "Kondoa Rock-Art Sites"}
    x = KR.Context(RULES, SETS, PARAMS, {}, {}, {}, lambda c, km, pop: False, titles,
                   {"Q2044": [{"qid": "Q1", "ended": True, "classes": ["Q3024240"]}, {"qid": "Q2", "ended": False, "classes": ["Q154547"]}]})
    florence = place("Q2044", whs="174", sitelinks=214)
    got, hits = kinds(florence, x)
    assert "old_town" in got and "capital" in got and hits["R17"] == ["whs:174"]   # a former capital of a historical country; a duchy does not count
    assert "old_town" not in kinds(place("Q9", whs="86"), x)[0]
