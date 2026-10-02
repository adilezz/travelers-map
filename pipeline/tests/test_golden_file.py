"""The golden set must be well formed before it is used to judge anything."""
import copy
from collections import Counter

from atlas import golden as G
from atlas.vocab import KINDS


def test_file_validates(golden_rows, whs):
    assert G.validate(golden_rows, whs) == []


def test_validation_requires_the_unesco_list(golden_rows):
    assert any("UNESCO" in p for p in G.validate(golden_rows, None))


def test_every_prototype_country_is_covered(golden_rows):
    countries = Counter(r.iso3 for r in golden_rows if r.row_kind == "positive")
    assert set(countries) == {"EGY", "ESP", "FRA", "ITA", "JOR", "MAR", "PER", "TUR", "TZA"}
    assert all(n >= 15 for n in countries.values())


def test_every_kind_is_represented(golden_rows):
    assert {k for r in golden_rows for k in r.kinds} == set(KINDS)


def test_regression_rows_are_present(golden_rows):
    reg = {r.name for r in golden_rows if r.regression}
    assert {"Machu Picchu", "Petra", "Cairo", "Wadi Rum", "Mount Kilimanjaro", "Florence"} <= reg


def test_relational_rows_have_the_intended_targets(golden_rows):
    by = {r.golden_id: r for r in golden_rows}
    nine = next(r for r in golden_rows if r.name == "Yusuf as-Siddiq")
    assert {by[t].name for t in nine.targets} == {"Giza Pyramids", "Cairo", "Luxor (Thebes)", "Abu Simbel"}


def test_nested_monuments_are_negative_component_rows(golden_rows):
    assert not [r for r in golden_rows if r.row_kind == "optional"]
    comps = {r.name for r in golden_rows if r.row_kind == "negative" and r.relation == "component_of"}
    assert {"Colosseum", "Uffizi Gallery", "Saqqara", "Hagia Sophia"} <= comps


def test_validator_catches_broken_rows(golden_rows, whs):
    rows = copy.deepcopy(golden_rows)
    rows[0].kinds = ()
    rows[1].tol_km = 500
    rows[2].min_tier = "Legendary"
    rows[3].iso3 = "egypt"
    rows[4].whs_id = "99999"
    assert len(G.validate(rows, whs)) >= 5


def test_loading_tolerates_non_numeric_values(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text(",".join(G.COLUMNS) + "\nG1,Egypt,EGY,X,,positive,site,abc,,,Icon,,ruins,,,,,,,,\n", encoding="utf-8")
    rows = G.load(p)
    assert rows[0].lat is None and any("coordinates" in x for x in G.validate(rows, set()))


def test_structure_table_is_well_formed(golden_rows):
    import csv
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "data" / "golden" / "structure.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    ids = {r.golden_id for r in golden_rows}
    retired = {"G011"}                       # Saqqara, absorbed into Giza (D25)
    assert len({r["row_id"] for r in rows}) == len(rows)
    for r in rows:
        assert r["row_type"] in {"edge", "node", "stay"}, r["row_id"]
        assert r["status"] in {"confirmed", "rejected"}, r["row_id"]
        if r["row_type"] == "edge":
            assert r["relation"] in {"part_of", "gateway_of", "day_trip_from", "near"}, r["row_id"]
        if r["row_type"] == "node":
            assert r["relation"] in {"in", "serves"} and r["mode"] in {"air", "rail", "sea", "road"}, r["row_id"]
        if r["row_type"] == "stay":
            assert r["stay_bucket"] in {"hours", "half_day", "day", "multi_day"}, r["row_id"]
        for ref in (r["subject"], r["object"]):
            if len(ref) == 4 and ref[0] in "GN" and ref[1:].isdigit():
                assert ref in ids | retired or ref in {"N002", "N003", "N004"}, (r["row_id"], ref)
