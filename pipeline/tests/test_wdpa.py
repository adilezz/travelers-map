import csv

from atlas import admit as A
from atlas import wdpa as W
from tests.test_admit import CFG, TYPES, cand


def test_reduce_keeps_designated_areas_of_the_scope(tmp_path):
    f = tmp_path / "w.csv"
    with open(f, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["WDPAID", "ISO3", "STATUS", "IUCN_CAT", "GIS_AREA"])
        w.writeheader()
        w.writerows([{"WDPAID": "1", "ISO3": "TZA", "STATUS": "Designated", "IUCN_CAT": "II", "GIS_AREA": "30000"},
                     {"WDPAID": "2", "ISO3": "TZA", "STATUS": "Proposed", "IUCN_CAT": "II", "GIS_AREA": "5"},
                     {"WDPAID": "3", "ISO3": "USA", "STATUS": "Designated", "IUCN_CAT": "II", "GIS_AREA": "5"}])
    assert [r["wdpaid"] for r in W.reduce_files([f], {"TZA"})] == ["1"]


def test_strict_category_and_size_make_a_protected_area_r1():
    table = {"1": {"iucn_cat": "II", "area_km2": 30000.0}, "2": {"iucn_cat": "IV", "area_km2": 900.0},
             "3": {"iucn_cat": "Ia", "area_km2": 12.0}}
    cs = {q: cand(q, 7, ["Qsite"], wdpa=q) for q in "123"}
    got = {c["qid"]: c["rules"] for c in A.admit(cs, {}, TYPES, CFG, wdpa=table)}
    assert got["1"] == ["R1"] and "R1" not in got.get("2", []) and "R1" not in got.get("3", [])


def test_reduce_reads_the_new_column_names(tmp_path):
    f = tmp_path / "n.csv"
    with open(f, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["SITE_ID", "PRNT_ISO3", "STATUS", "IUCN_CAT", "GIS_AREA"])
        w.writeheader()
        w.writerow({"SITE_ID": "9", "PRNT_ISO3": "PER", "STATUS": "Designated", "IUCN_CAT": "II", "GIS_AREA": "1800"})
    assert W.reduce_files([f], {"PER"}) == [{"wdpaid": "9", "iucn_cat": "II", "area_km2": 1800.0}]
