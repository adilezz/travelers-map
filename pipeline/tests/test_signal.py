from atlas import signal as S

COMMUNE = ["frwiki", "enwiki", "cebwiki", "svwiki"]            # what every ordinary commune has
FAMOUS = [*COMMUNE, "jawiki", "zhwiki", "arwiki", "kowiki", "hewiki"]


def town(i, famous=False):
    return (f"Q{i}", "FRA", ["Qcommune"]), (FAMOUS if famous else COMMUNE)


def build(n=100, famous=(7,)):
    items, profiles = [], {}
    for i in range(n):
        it, ws = town(i, i in famous)
        items.append(it)
        profiles[it[0]] = ws
    return items, profiles


def test_wiki_rates_and_discrimination():
    rates = S.wiki_rates([COMMUNE, COMMUNE, FAMOUS, COMMUNE])
    assert rates["frwiki"] == 1.0 and rates["jawiki"] == 0.25
    assert S.discrimination(COMMUNE, rates) == 0.0
    assert S.discrimination(FAMOUS, rates) == 5 * 0.75 and S.discrimination(["commonswiki"], rates) == 0.0


def test_mass_classes_and_their_members():
    items, profiles = build(100)
    assert S.mass_classes(items, mass_min=100) == {("FRA", "Qcommune"): 100}
    assert S.mass_classes(items, mass_min=101) == {}
    assert S.assign_class(["Qother", "Qcommune"], "FRA", {("FRA", "Qcommune"): 100}) == "Qcommune"
    assert S.assign_class(["Qother"], "FRA", {("FRA", "Qcommune"): 100}) is None


def test_only_the_top_share_of_a_mass_class_is_admitted_by_attention():
    items, profiles = build(100, famous=(7, 8))
    sc = S.scores(items, profiles, mass_min=50)
    assert sc["Q7"]["D"] > sc["Q0"]["D"] == 0.0
    assert S.admitted_by_attention(sc["Q7"]) and S.admitted_by_attention(sc["Q8"])
    assert not S.admitted_by_attention(sc["Q0"]) and not S.admitted_by_attention(sc["Q50"])
    assert sum(1 for v in sc.values() if S.admitted_by_attention(v)) == 2        # not the 98 ordinary ones


def test_items_outside_a_mass_class_are_left_to_the_plain_floors():
    items = [("Q1", "JOR", ["Qcastle"])]
    sc = S.scores(items, {"Q1": FAMOUS}, mass_min=1000)
    assert S.admitted_by_attention(sc["Q1"]) is None and sc["Q1"]["cls"] is None
