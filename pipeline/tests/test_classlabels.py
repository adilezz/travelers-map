import csv

import pytest

from atlas import classlabels as C


def test_fetch_reads_labels_descriptions_and_parents_and_skips_missing():
    def get(url, params):
        assert params["props"] == "labels|descriptions|claims" and params["languages"] == "en"
        return {"entities": {
            "Q23413": {"labels": {"en": {"value": "castle"}}, "descriptions": {"en": {"value": "fortified building"}},
                       "claims": {"P279": [{"mainsnak": {"datavalue": {"value": {"id": "Q57821"}}}}]}},
            "Qx": {"missing": ""}}}
    out = C.fetch(["Q23413", "Qx"], get)
    assert out == {"Q23413": {"label_en": "castle", "description_en": "fortified building", "subclass_of": ["Q57821"]}}


def test_frequent_classes_counts_items_once_and_write_round_trips(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('Q1', 50, ['Qa','Qb']), ('Q1', 50, ['Qa','Qb']), "
                "('Q2', 20, ['Qa']), ('Q3', 3, ['Qc'])) v(qid, sitelinks, instance_of)")
    con.execute(f"COPY t TO '{(tmp_path / 'attention.parquet').as_posix()}' (FORMAT PARQUET)")
    rows = C.frequent_classes(tmp_path, top=5)
    assert rows[0] == ("Qa", 2) and ("Qb", 1) in rows and all(q != "Qc" for q, _ in rows)
    out = tmp_path / "labels.csv"
    C.write(rows, {"Qa": {"label_en": "alpha", "description_en": "", "subclass_of": ["Qp", "Qq"]}}, out)
    got = list(csv.DictReader(out.open(encoding="utf-8")))
    assert got[0]["label_en"] == "alpha" and got[0]["subclass_of"] == "Qp|Qq" and got[1]["label_en"] == ""
