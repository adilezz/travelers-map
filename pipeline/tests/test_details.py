"""S2 details, against recorded wbgetentities responses (the sandbox cannot reach Wikidata)."""
import json

import pytest

from atlas import details as D


def claim(value, rank="normal", end=False):
    c = {"mainsnak": {"datavalue": {"value": value}}, "rank": rank}
    if end:
        c["qualifiers"] = {"P582": [{}]}
    return c


ROME = {"id": "Q220",
        "labels": {"en": {"value": "Rome"}, "it": {"value": "Roma"}},
        "aliases": {"en": [{"value": "Eternal City"}], "it": [{"value": "Urbe"}]},
        "descriptions": {"en": {"value": "capital of Italy"}},
        "claims": {"P31": [claim({"id": "Q1549591"}), claim({"id": "Q747074"}, rank="deprecated")],
                   "P131": [claim({"id": "Q1282"})],
                   "P1376": [claim({"id": "Q38"}), claim({"id": "Q172579"}, end=True)],
                   "P571": [claim({"time": "-0753-04-21T00:00:00Z"})],
                   "P856": [claim("https://www.comune.roma.it")]},
        "sitelinks": {"enwiki": {"title": "Rome"}, "itwiki": {"title": "Roma"}}}
MERGED = {"id": "Q220", "labels": {"en": {"value": "Rome"}}, "claims": {}, "sitelinks": {}}


def test_parse_keeps_what_wikidata_said_and_drops_deprecated_claims():
    r = D.parse_entity("Q220", ROME, ["en", "it"])
    assert r["label_en"] == "Rome" and r["label_loc"] == "Roma" and r["aliases_loc"] == ["Urbe"]
    assert r["description_en"] == "capital of Italy" and r["instance_of"] == ["Q1549591"]
    assert r["located_in"] == ["Q1282"] and r["inception"] == -753 and r["official_url"].startswith("https://")
    assert r["capital_of"] == [{"qid": "Q38", "ended": False}, {"qid": "Q172579", "ended": True}]
    assert r["wikipedia_en"] == "Rome" and "redirected_to" not in r


def test_a_redirected_qid_is_recorded_with_its_target_and_a_missing_one_is_flagged():
    def get(url, params):
        return {"entities": {"Q999": MERGED, "Q404": {"id": "Q404", "missing": ""}}}
    rows = D.fetch_batch(["Q999", "Q404"], ["en"], get)
    assert rows[0]["qid"] == "Q999" and rows[0]["redirected_to"] == "Q220"
    assert rows[1] == {"qid": "Q404", "missing": True}


def test_fetch_asks_for_the_right_languages_and_sitelinks():
    seen = {}

    def get(url, params):
        seen.update(params)
        return {"entities": {}}
    D.fetch_batch(["Q1"], ["en", "it"], get)
    assert seen["languages"] == "en|it" and seen["sitefilter"] == "enwiki|itwiki" and seen["redirects"] == "yes"


def test_run_is_resumable_and_reports_failed_batches(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "BATCH", 2)
    chosen = {f"Q{i}": {"sitelinks"} for i in range(1, 6)}
    calls = []

    def get(url, params):
        calls.append(params["ids"])
        if len(calls) == 2:
            raise OSError("timeout")
        return {"entities": {q: {"id": q, "labels": {"en": {"value": q}}, "claims": {}, "sitelinks": {}}
                             for q in params["ids"].split("|")}}
    res = D.run(chosen, tmp_path, get, delay=0, log=lambda s: None)
    assert res["failed"] == ["Q3", "Q4"] and res["fetched"] == 3
    res2 = D.run(chosen, tmp_path, get, delay=0, log=lambda s: None)
    assert res2["already"] == 3 and res2["fetched"] == 2 and res2["failed"] == []
    rows = [json.loads(line) for line in (tmp_path / "details.jsonl").read_text().splitlines()[1:]]
    assert sorted(r["qid"] for r in rows) == ["Q1", "Q2", "Q3", "Q4", "Q5"] and rows[0]["why"] == ["sitelinks"]


def test_select_applies_the_floors_and_adds_golden(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('Q1', 50, NULL, NULL), ('Q2', 3, NULL, NULL), "
                "('Q3', 3, 200000, NULL), ('Q4', 2, NULL, '91')) v(qid, sitelinks, population, whs)")
    con.execute(f"COPY t TO '{(tmp_path / 'attention.parquet').as_posix()}' (FORMAT PARQUET)")
    g = tmp_path / "g.csv"
    g.write_text("golden_id,qid\nG1,Q2\nG2,\n", encoding="utf-8")
    chosen = D.select(tmp_path, g)
    assert chosen == {"Q1": {"sitelinks"}, "Q3": {"population"}, "Q4": {"whs"}, "Q2": {"golden"}}


def test_parquet_round_trip(tmp_path):
    pytest.importorskip("duckdb")
    D.run({"Q1": {"golden"}}, tmp_path, lambda u, p: {"entities": {"Q1": {"id": "Q1", "labels": {"en": {"value": "x"}},
                                                                          "claims": {}, "sitelinks": {}}}}, delay=0,
          log=lambda s: None)
    assert D.to_parquet(tmp_path) == 1 and (tmp_path / "details.parquet").is_file()


def test_profile_lists_the_wikis_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "BATCH", 2)
    calls = []

    def get(url, params):
        calls.append(params["ids"])
        assert params["props"] == "sitelinks"
        if len(calls) == 2:
            raise OSError("timeout")
        return {"entities": {q: {"id": q, "sitelinks": {"enwiki": {}, "cebwiki": {}}} for q in params["ids"].split("|")}}
    res = D.run_profiles(["Q1", "Q2", "Q3", "Q4", "Q5"], tmp_path, get, delay=0, log=lambda s: None)
    assert res["failed"] == ["Q3", "Q4"] and res["fetched"] == 3
    res2 = D.run_profiles(["Q1", "Q2", "Q3", "Q4", "Q5"], tmp_path, get, delay=0, log=lambda s: None)
    assert res2["already"] == 3 and res2["failed"] == []
    rows = [json.loads(line) for line in (tmp_path / "profile.jsonl").read_text().splitlines()]
    assert sorted(r["qid"] for r in rows) == ["Q1", "Q2", "Q3", "Q4", "Q5"] and rows[0]["wikis"] == ["cebwiki", "enwiki"]
