"""The extraction runner, tested against recorded WDQS-shaped responses (the sandbox cannot reach Wikidata)."""
import json

import pytest

from atlas import extract as X


def b(item, wkt="Point(12.4922 41.8902)", sl="140", **more):
    d = {"item": {"value": f"http://www.wikidata.org/entity/{item}"}, "coord": {"value": wkt},
         "sl": {"value": sl}, "country": {"value": "http://www.wikidata.org/entity/Q38"},
         "label_en": {"value": "Colosseum"}}
    d.update({k: {"value": v} for k, v in more.items()})
    return d


def test_point_is_lon_lat_and_parse_keeps_what_wikidata_said():
    assert X.point("Point(12.4922 41.8902)") == (41.8902, 12.4922)
    assert X.point("") is None and X.point("nonsense") is None
    r = X.parse(b("Q10285", pop="2800000.0", whs="91"))
    assert r["qid"] == "Q10285" and r["lat"] == 41.8902 and r["lon"] == 12.4922
    assert r["sitelinks"] == 140 and r["population"] == 2800000 and r["whs"] == "91" and r["country_qid"] == "Q38"


def test_western_sahara_items_carry_the_disputed_marker_under_morocco():
    row = X.parse({"item": {"value": "http://www.wikidata.org/entity/Q1"},
                   "country": {"value": "http://www.wikidata.org/entity/Q6250"}}, X.COUNTRIES["MAR"]["disputed"])
    assert row["disputed"] == "ESH" and row["lat"] is None


def test_plan_covers_every_country_class_band_and_extra_family():
    todo = X.jobs(class_qids=["Q515", "Q8502"])
    per_country = 2 * len(X.BANDS) + 2 + len(X.NODE_CLASSES)
    assert len(todo) == 9 * per_country
    assert len({j.filename for j in todo}) == len(todo)                        # no two jobs share a file
    q = [j for j in todo if j.country == "MAR"][0].query(0)
    assert "wd:Q1028 wd:Q6250" in q and "LIMIT 5000 OFFSET 0" in q and "ORDER BY ?item" in q
    top = [j for j in todo if j.country == "ITA" and j.family.endswith("40-up")][0].query(0)
    assert "FILTER(?sl >= 40)" in top and "<=" not in top
    mid = [j for j in todo if j.country == "ITA" and j.family.endswith("15-39")][0].query(0)
    assert "FILTER(?sl >= 15 && ?sl <= 39)" in mid


def test_the_real_class_table_expands_to_all_its_classes():
    assert len(X.jobs(["ITA"])) == len(X.classes()) * len(X.BANDS) + 2 + len(X.NODE_CLASSES)


def test_run_pages_writes_a_self_describing_file_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(X, "PAGE", 2)
    asked = []

    def run(q):
        asked.append(q)
        offset = int(q.rsplit("OFFSET", 1)[1])
        return [b("Q1"), b("Q2")] if offset == 0 else [b("Q3")]

    job = X.jobs(["ITA"], ["Q515"])[0]
    r = X.run_job(job, tmp_path, run, delay=0)
    assert r["status"] == "ok" and r["rows"] == 3 and len(asked) == 2
    meta = X.read_meta(tmp_path / job.filename)
    assert meta["complete"] and meta["rows"] == 3 and "wd:Q515" in meta["query"] and meta["run_utc"]
    assert [x["qid"] for x in X.iter_rows(tmp_path / job.filename)] == ["Q1", "Q2", "Q3"]
    again = X.run_job(job, tmp_path, run, delay=0)
    assert again["status"] == "skipped" and len(asked) == 2                     # resumable: nothing re-asked


def test_a_failed_query_is_reported_and_does_not_stop_the_rest(tmp_path, monkeypatch):
    todo = X.jobs(["ITA"], ["Q515"])[:3]
    calls = []

    def run(q):
        calls.append(q)
        if len(calls) == 2:
            raise OSError("timeout")
        return [b("Q1")]

    res = X.run_all(todo, tmp_path, run, delay=0, log=lambda s: None)
    assert [r["status"] for r in res] == ["ok", "failed", "ok"]
    assert X.check(tmp_path, todo) == [f"{todo[1].filename}: missing or incomplete"]
    assert not list(tmp_path.glob("*.tmp"))


def test_preflight_rejects_a_wrong_country_qid():
    good = {q: X.COUNTRIES[i]["name"] for i in X.COUNTRIES for q in X.COUNTRIES[i]["qids"][:1]}
    assert X.preflight(lambda qs: good) == []
    bad = dict(good, Q38="France")
    assert X.preflight(lambda qs: bad) == ["Q38: expected 'Italy', Wikidata says 'France'"]


def test_parquet_groups_by_family(tmp_path):
    pytest.importorskip("duckdb")
    for job, rows in ((X.jobs(["ITA"], ["Q515"])[0], [b("Q1"), b("Q2")]), (X.jobs(["FRA"], ["Q515"])[0], [b("Q3")])):
        X.run_job(job, tmp_path, lambda q, r=rows: r, delay=0)
    counts = X.to_parquet(tmp_path)
    assert counts == {"class": 3}
    assert (tmp_path / "class.parquet").is_file() and not list(tmp_path.glob("*.rows.jsonl"))
    assert json.loads(json.dumps(counts)) == counts
