import csv

import pytest

from atlas import golden as G
from atlas import recall as R

duckdb = pytest.importorskip("duckdb")


def make_raw(tmp_path, qids):
    con = duckdb.connect()
    values = ",".join("('" + q + "', 50)" for q in qids)
    con.execute(f"CREATE TABLE t AS SELECT * FROM (VALUES {values}) v(qid, sitelinks)")
    con.execute(f"COPY t TO '{(tmp_path / 'attention.parquet').as_posix()}' (FORMAT PARQUET)")


def golden_file(tmp_path, qids):
    p = tmp_path / "g.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=G.COLUMNS, lineterminator="\n")
        w.writeheader()
        for i, q in enumerate(qids, 1):
            w.writerow({**dict.fromkeys(G.COLUMNS, ""), "golden_id": f"G{i:03d}", "country": "Italy", "iso3": "ITA",
                        "expected_name": f"P{i}", "row_kind": "positive", "qid": q, "type": "site"})
    return p


def test_recall_counts_found_and_missed_and_reports_them(tmp_path):
    make_raw(tmp_path, ["Q1", "Q2", "Q3"])
    res = R.recall(tmp_path, golden_file(tmp_path, ["Q1", "Q2", "Q9"]))
    assert res["n"] == 3 and res["found"] == 2 and [r.qid for r in res["missed"]] == ["Q9"]
    assert res["by_iso"] == {"ITA": [2, 3]}
    text = R.report(res, tmp_path)
    assert "2 of 3 golden QIDs" in text and "| G003 | P3 | Q9 | ITA |" in text


def test_main_fails_below_the_95_percent_floor(tmp_path, capsys):
    make_raw(tmp_path, ["Q1"])
    g = golden_file(tmp_path, ["Q1", "Q2"])
    assert R.main(["--raw", str(tmp_path), "--golden", str(g)]) == 1
    make_raw(tmp_path, ["Q1", "Q2"])
    assert R.main(["--raw", str(tmp_path), "--golden", str(g)]) == 0
