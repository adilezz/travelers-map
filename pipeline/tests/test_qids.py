"""The QID tools, tested against recorded Wikidata responses (the sandbox cannot reach Wikidata)."""
import csv

import pytest

from atlas import golden as G
from atlas import qids
from atlas.wikidata import Client, qid_of

# Recorded in the shapes the real API returns.
SEARCH = {"Petra": {"search": [{"id": "Q5788", "label": "Petra", "description": "archaeological city in Jordan"},
                               {"id": "Q42", "label": "Petra", "description": "a given name"}]},
          "Obscure": {"search": []}}
ENTITIES = {
    "Q5788": {"labels": {"en": {"value": "Petra"}}, "descriptions": {"en": {"value": "archaeological city in Jordan"}},
              "claims": {"P625": [{"mainsnak": {"datavalue": {"value": {"latitude": 30.3285, "longitude": 35.4444}}}}],
                         "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q839954"}}}}]},
              "sitelinks": {f"w{i}wiki": {} for i in range(80)}},
    "Q42": {"labels": {"en": {"value": "Petra"}}, "descriptions": {"en": {"value": "a given name"}},
            "claims": {}, "sitelinks": {f"w{i}wiki": {} for i in range(30)}},
    "Q8502": {"labels": {"en": {"value": "mountain"}}, "claims": {}, "sitelinks": {}},
    "Q7": {"labels": {"en": {"value": "something else"}}, "claims": {}, "sitelinks": {}},
    "Qgone": {"missing": ""},
}


def fake_fetch(url, params):
    if params.get("action") == "wbsearchentities":
        return SEARCH.get(params["search"], {"search": []})
    if params.get("action") == "wbgetentities":
        return {"entities": {q: ENTITIES[q] for q in params["ids"].split("|") if q in ENTITIES}}
    if "sparql" in url:
        return {"results": {"bindings": [{"item": {"value": "http://www.wikidata.org/entity/Q5788"}}]}} if '"326"' in params["query"] \
            else {"results": {"bindings": []}}
    raise AssertionError(params)


@pytest.fixture()
def client():
    return Client(fake_fetch, delay=0)


def row(golden_rows, name):
    return next(r for r in golden_rows if r.name == name)


def test_client_parses_entities_and_sparql(client):
    e = client.entities(["Q5788", "Qgone"])
    assert list(e) == ["Q5788"] and e["Q5788"]["coord"] == (30.3285, 35.4444)
    assert e["Q5788"]["sitelinks"] == 80 and e["Q5788"]["instance_of"] == ["Q839954"]
    assert client.items_with_whs_id("326") == ["Q5788"] and client.items_with_whs_id("1") == []
    assert qid_of("http://www.wikidata.org/entity/Q5788") == "Q5788"


def test_resolve_finds_petra_uniquely_and_marks_the_namesake_far(client, golden_rows):
    out = qids.candidates_for(client, row(golden_rows, "Petra"))
    top = out[0]
    assert top["candidate_qid"] == "Q5788" and top["status"] == "unique" and top["found_by"] == "whs"
    assert top["distance_km"] < 1 and top["name_match"] == "yes"
    other = next(c for c in out if c["candidate_qid"] == "Q42")
    assert other["status"] == "far"                          # a given name with no coordinate is never proposed


def test_resolve_reports_none_and_skips_resolved_and_relational_rows(client, golden_rows):
    negatives = [r for r in golden_rows if r.row_kind == "negative"]
    fake = G.Row(raw={**row(golden_rows, "Petra").raw, "expected_name": "Obscure", "aliases": ""}, golden_id="GX",
                 iso3="JOR", name="Obscure", names={"obscure"}, type="site", lat=30.0, lon=35.0, tol_km=5, whs_id="")
    out = qids.resolve(client, [fake])
    assert out[0]["status"] == "none"
    done = G.Row(**{**row(golden_rows, "Petra").__dict__, "qid": "Q5788"})
    assert qids.resolve(client, [done, *negatives]) == []


def test_ambiguous_when_two_strong_candidates_are_near(client, golden_rows):
    ENTITIES["Q99"] = {"labels": {"en": {"value": "Petra Archaeological Park"}}, "claims": {
        "P625": [{"mainsnak": {"datavalue": {"value": {"latitude": 30.33, "longitude": 35.45}}}}]},
        "sitelinks": {f"w{i}wiki": {} for i in range(40)}}
    SEARCH["Petra"]["search"].append({"id": "Q99", "label": "x", "description": ""})
    try:
        out = qids.candidates_for(client, row(golden_rows, "Petra"))
        assert {c["status"] for c in out[:2]} == {"ambiguous"}
    finally:
        del ENTITIES["Q99"]
        SEARCH["Petra"]["search"].pop()


def test_apply_decisions_sets_qids_and_refuses_duplicates_and_bad_values(tmp_path, golden_rows):
    import shutil
    from pathlib import Path
    gp = tmp_path / "golden.csv"
    shutil.copy(Path(G.__file__).resolve().parents[2] / "data" / "golden" / "golden.csv", gp)
    blanked = [dict(r, qid="", qid_status="to_resolve") for r in csv.DictReader(gp.open(encoding="utf-8"))]
    with open(gp, "w", encoding="utf-8", newline="") as fh:      # the real file now carries QIDs; test from a blank copy
        w0 = csv.DictWriter(fh, fieldnames=list(blanked[0].keys()), lineterminator="\n")
        w0.writeheader()
        w0.writerows(blanked)
    petra = row(golden_rows, "Petra").golden_id
    rum = row(golden_rows, "Wadi Rum").golden_id
    dp = tmp_path / "d.csv"

    def write(rows):
        with open(dp, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=qids.DECISION_COLUMNS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    write([{"golden_id": petra, "qid": "Q5788", "decision": "accept", "note": ""},
           {"golden_id": rum, "qid": "Q1", "decision": "reject", "note": "wrong"}])
    assert qids.apply_decisions(gp, dp, "2026-10-02") == 1
    back = {r.golden_id: r for r in G.load(gp)}
    assert back[petra].qid == "Q5788" and back[rum].qid == ""
    assert back[petra].raw["qid_status"] == "resolved 2026-10-02"
    write([{"golden_id": rum, "qid": "Q5788", "decision": "accept", "note": ""}])
    with pytest.raises(ValueError, match="both"):
        qids.apply_decisions(gp, dp)
    write([{"golden_id": rum, "qid": "5788", "decision": "accept", "note": ""}])
    with pytest.raises(ValueError, match="not a QID"):
        qids.apply_decisions(gp, dp)
    write([{"golden_id": "N001", "qid": "Q9", "decision": "accept", "note": ""}])
    with pytest.raises(ValueError, match="not a positive"):
        qids.apply_decisions(gp, dp)


def test_class_table_check_catches_a_wrong_qid(client, tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("class_qid,expected_label,place_type,kind_hint,verified,note\n"
                 "Q8502,mountain,area,mountain,no,\nQ7,volcano,area,volcanic,no,\nQ404,lake,area,water,no,\n", encoding="utf-8")
    problems = qids.check_classes(client, p)
    assert len(problems) == 2 and any("Q7" in x and "something else" in x for x in problems) and any("not found" in x for x in problems)


def test_the_committed_class_table_is_well_formed():
    from pathlib import Path

    from atlas.vocab import KINDS, PLACE_TYPES
    path = Path(G.__file__).resolve().parents[2] / "data" / "rules" / "classes.csv"
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 20 and len({r["class_qid"] for r in rows}) == len(rows)
    assert all(r["class_qid"].startswith("Q") and r["place_type"] in PLACE_TYPES for r in rows)
    assert all(r["kind_hint"] in KINDS or r["kind_hint"] == "" for r in rows)
    assert all(r["verified"] == "no" for r in rows)       # none verified until the owner runs `qids classes`
