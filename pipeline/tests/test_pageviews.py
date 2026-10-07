import json
import urllib.error

import pytest

from atlas import admit as A
from atlas import pageviews as P


def fake(counts):
    def get(url, params):
        title = url.rsplit("/monthly/", 1)[0].rsplit("/", 1)[1]
        if title not in counts:
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        return {"items": [{"timestamp": f"{y}{m:02d}0100", "views": v} for (y, m), v in zip(P._months(), counts[title], strict=True)]}
    return get


def test_twelve_months_are_returned_in_order_and_gaps_are_zero():
    assert P._months()[0] == (2025, 10) and P._months()[-1] == (2026, 9) and len(P._months()) == 12
    got = P.fetch_views("Colosseum", fake({"Colosseum": list(range(12))}))
    assert got == list(range(12))
    partial = lambda url, params: {"items": [{"timestamp": "2026030100", "views": 7}]}      # noqa: E731
    assert P.fetch_views("X", partial)[5] == 7 and sum(P.fetch_views("X", partial)) == 7


def test_a_missing_article_is_none_not_an_error_and_titles_are_encoded():
    assert P.fetch_views("Nope", fake({})) is None
    seen = []
    P.fetch_views("Côte d'Azur/Nice", lambda url, params: seen.append(url) or {"items": []})
    assert seen[0].endswith("C%C3%B4te_d%27Azur%2FNice/monthly/2025100100/2026093000")


def test_run_is_resumable_records_zero_for_missing_and_keeps_going_after_a_failure(tmp_path):
    chosen = {"Q1": "A", "Q2": "B", "Q3": "Gone", "Q4": "Boom"}
    base = fake({"A": [1] * 12, "B": [2] * 12})

    def get(url, params):
        if "/Boom/" in url:
            raise RuntimeError("down")
        return base(url, params)
    res = P.run(chosen, tmp_path, get, delay=0, log=lambda s: None)
    assert res["fetched"] == 3 and res["failed"] == ["Q4"]
    rows = [json.loads(line) for line in (tmp_path / "pageviews.jsonl").read_text().splitlines()][1:]
    assert {r["qid"]: r["total"] for r in rows} == {"Q1": 12, "Q2": 24, "Q3": 0} and next(r for r in rows if r["qid"] == "Q3")["missing"]
    again = P.run(chosen, tmp_path, fake({"A": [1] * 12, "B": [2] * 12, "Boom": [3] * 12}), delay=0, log=lambda s: None)
    assert again["already"] == 3 and again["fetched"] == 1
    assert P.to_parquet(tmp_path) == 4 and P.load(tmp_path / "pageviews.parquet")["Q4"] == 36


def test_pageviews_enter_n_through_the_best_merged_item():
    cfg = {"notability": {"pageview_weight": 0.5, "recognition_cap": 1.5, "recognition": {"whs": 1.0, "national_top": 0.2},
                          "size_term_cap": 0.3, "size_term_coefficient": 0.15, "size_term_reference_population": 100000}}
    p = {"qid": "Q1", "alt_qids": ["Q2"], "sitelinks": 99}
    assert A.attach_pageviews([p], {"Q1": 1000, "Q2": 999_000}) == 1 and p["pv"] == 999_000
    base = A.notability({"sitelinks": 99}, cfg)
    assert A.notability(p, cfg) == pytest.approx(base + 0.5 * 3.0, abs=1e-3)
    q = {"qid": "Q9", "sitelinks": 99}
    assert A.attach_pageviews([q], {}) == 0 and q["pv"] is None and A.notability(q, cfg) == pytest.approx(base)
