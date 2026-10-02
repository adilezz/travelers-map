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


def test_optional_rows_are_not_negative(golden_rows):
    optional = {r.name for r in golden_rows if r.row_kind == "optional"}
    assert optional == {"Colosseum", "Uffizi Gallery", "Sagrada Familia", "Prado Museum", "Mezquita of Cordoba", "Hagia Sophia"}


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
