import json

from atlas import capitals as C


def row(cap, state, classes, ended):
    return {"cap": {"value": f"http://www.wikidata.org/entity/{cap}"}, "state": {"value": f"http://www.wikidata.org/entity/{state}"},
            "classes": {"value": "|".join(f"http://www.wikidata.org/entity/{c}" for c in classes)}, "ended": {"value": "true" if ended else "false"}}


def test_query_lists_the_places_and_parse_reads_the_bindings():
    q = C.query(["Q1", "Q2"])
    assert "wd:Q1 wd:Q2" in q and "p:P36" in q and "pq:P582" in q
    assert C.parse(row("Q2044", "Q1", ["Q3024240", "Q6256"], True)) == {"cap": "Q2044", "state": "Q1", "classes": ["Q3024240", "Q6256"], "ended": True}


def test_run_is_resumable_and_the_parquet_loads_by_capital(tmp_path):
    calls = []

    def fake(query):
        calls.append(query)
        return [row("Q2044", "Q1", ["Q3024240"], True)]
    qids = [f"Q{i}" for i in range(1, 321)]
    res = C.run(qids, tmp_path, fake, delay=0, log=lambda s: None)
    assert res["batches"] == 3 and len(calls) == 3 and not res["failed"]
    C.run(qids, tmp_path, fake, delay=0, log=lambda s: None)
    assert len(calls) == 3                                                       # nothing is asked twice
    assert C.to_parquet(tmp_path) == 3
    got = C.load(tmp_path / "capitals.parquet")
    assert got["Q2044"][0] == {"qid": "Q1", "ended": True, "classes": ["Q3024240"]}
    assert json.loads((tmp_path / "capitals.jsonl").read_text().splitlines()[0])["rows"]
