import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest
from conftest import write_bundle

from atlas.vocab import KINDS, PLACE_TYPES, TIERS

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "pipeline"
SCHEMA = (PIPELINE / "atlas" / "schema.sql").read_text(encoding="utf-8")


def test_schema_loads_and_matches_the_vocabulary():
    con = duckdb.connect()
    con.execute(SCHEMA)
    tables = {r[0] for r in con.execute("show tables").fetchall()}
    assert {"asset", "place", "place_asset", "place_kind", "place_alias", "territory", "piece",
            "print_selection", "merge_log", "split_log", "review_queue", "build"} <= tables
    for name in (*KINDS, *PLACE_TYPES, *TIERS):
        assert f"'{name}'" in SCHEMA


def test_schema_rejects_bad_rows():
    con = duckdb.connect()
    con.execute(SCHEMA)
    ok = "insert into place values ('pl_0000000001','site','Petra',null,'JOR',null,30.3,35.4,null,'Icon',null,null,'rich',null,null,null,null,null,null,null,null,'active','b1')"
    con.execute(ok)
    with pytest.raises(duckdb.Error):
        con.execute(ok.replace("'pl_0000000001','site'", "'pl_0000000002','castle'"))
    with pytest.raises(duckdb.Error):
        con.execute("insert into place_kind values ('pl_0000000001','archaeological','r',1.0,['a'])")
    with pytest.raises(duckdb.Error):
        con.execute("insert into place_kind values ('pl_0000000001','ruins','r',1.0,[])")


def test_reserved_tables_exist_and_enforce_their_constraints():
    con = duckdb.connect()
    con.execute(SCHEMA)
    tables = {r[0] for r in con.execute("show tables").fetchall()}
    assert {"place_crossref", "place_text", "place_season", "travel_effort", "place_stay",
            "place_edge", "node", "place_node", "place_link"} <= tables
    cols = {r[0] for r in con.execute("describe place_metric").fetchall()}
    assert "pageviews_monthly" in cols
    assert "redistributable" in {r[0] for r in con.execute("describe source").fetchall()}
    assert "snapshot" in {r[0] for r in con.execute("describe asset").fetchall()}
    con.execute("insert into place values ('pl_0000000001','site','Petra',null,'JOR',null,30.3,35.4,null,'Icon',null,null,'rich',null,null,null,null,null,null,null,null,'active','b1')")
    with pytest.raises(duckdb.Error):
        con.execute("insert into place_season values ('pl_0000000001', 13, 0.5, 'x')")
    with pytest.raises(duckdb.Error):
        con.execute("insert into place_text values ('pl_0000000001','en','review','great!',null,null,null)")


OWNER_SCHEMA = (PIPELINE / "atlas" / "owner_schema.sql").read_text(encoding="utf-8")


def test_owner_store_is_separate_and_enforces_its_constraints():
    assert "REFERENCES" not in OWNER_SCHEMA.upper().replace("-- THE OWNER'S OWN STATE", "")  # no keys into the shared schema
    con = duckdb.connect()
    con.execute(OWNER_SCHEMA)
    con.execute("insert into visit (visit_id, place_id, date_from, precision, rating) values ('v1','pl_0000000001','2014-07-01','season',2)")
    with pytest.raises(duckdb.Error):
        con.execute("insert into visit (visit_id, place_id, precision) values ('v2','pl_0000000001','sometime')")
    with pytest.raises(duckdb.Error):
        con.execute("insert into visit (visit_id, place_id, rating) values ('v3','pl_0000000001',9)")
    with pytest.raises(duckdb.Error):
        con.execute("insert into visit (visit_id, place_id, date_from, date_to) values ('v4','pl_0000000001','2020-02-01','2020-01-01')")
    con.execute("insert into visit (visit_id, place_id) values ('v5','pl_0000000001')")   # many visits per place
    assert con.execute("select count(*) from visit where place_id='pl_0000000001'").fetchone()[0] == 2
    with pytest.raises(duckdb.Error):
        con.execute("insert into visit_candidate (candidate_id, place_id, evidence, confidence) values ('c1','pl_0000000001','{}',1.5)")


def run(*args):
    return subprocess.run([sys.executable, "-m", "atlas.verify", *args], cwd=ROOT, capture_output=True,
                          text=True, env={"PYTHONPATH": str(PIPELINE), "PATH": "/usr/bin:/bin"})


def test_verify_fails_without_a_bundle():
    r = run()
    assert r.returncode == 1 and "no bundle" in r.stdout


def test_verify_fails_on_an_unreadable_bundle(tmp_path):
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    r = run("--bundle", str(tmp_path))
    assert r.returncode == 1 and "G-BUNDLE" in r.stdout


def test_verify_never_goes_green_on_the_oracle_and_reports_n(oracle, tmp_path):
    d = write_bundle(tmp_path / "b", oracle)
    r = run("--bundle", str(d), "--prototype", "--json", str(tmp_path / "out.json"))
    assert r.returncode == 1
    assert "G-LANDMARK" in r.stdout and "PEND" in r.stdout and "[n=185]" in r.stdout
    results = json.loads((tmp_path / "out.json").read_text())
    assert {x["gate"] for x in results if x["pending"]} == {"G-DETERMINISM", "G-STRUCT", "G-REGION", "G-DISPUTE", "G-PRINT"}


def test_registry_parquet_is_readable_and_empty():
    from atlas.registry import Registry
    assert Registry.load(ROOT / "data" / "registry" / "place_registry.parquet").rows == {}


def test_committed_data_files_are_valid():
    scope = json.loads((ROOT / "data" / "scope.json").read_text(encoding="utf-8"))
    assert scope["sovereign"] == ["EGY", "ESP", "FRA", "ITA", "JOR", "MAR", "PER", "TUR", "TZA"]
    cfg = json.loads((ROOT / "data" / "rules" / "tiers.json").read_text(encoding="utf-8"))
    assert cfg["admission"]["r5_country_floor"] == {"sovereign": 5, "dependency": 2}
    m = json.loads((ROOT / "data" / "inputs" / "MANIFEST.json").read_text(encoding="utf-8"))
    ids = {s["source_id"] for s in m["sources"]}
    assert {"wikidata", "wikipedia_pageviews", "wikivoyage", "unesco_whs", "wdpa", "ramsar", "geonames", "osm", "natural_earth"} <= ids
    assert all(s["licence"] and "restricted" in s for s in m["sources"])
    assert json.loads((ROOT / "data" / "changelog.json").read_text(encoding="utf-8"))["causes"] == []


def test_structure_layer_enforces_its_constraints():
    con = duckdb.connect()
    con.execute(SCHEMA)
    for pid, name in (("pl_0000000001", "Rome"), ("pl_0000000002", "Colosseum")):
        con.execute(f"insert into place values ('{pid}','site','{name}',null,'ITA',null,41.9,12.5,null,'Icon',null,null,'rich',null,null,null,null,null,null,null,null,'active','b1')")
    ins = "insert into place_edge values ('pl_0000000002','pl_0000000001','{rel}','wikidata',0.9,null,false,null,null)"
    con.execute(ins.format(rel="part_of"))
    with pytest.raises(duckdb.Error):
        con.execute(ins.format(rel="contains"))           # relations are a closed vocabulary
    with pytest.raises(duckdb.Error):
        con.execute("insert into place_edge values ('pl_0000000001','pl_0000000001','near','rule',0.5,null,false,null,null)")
    node = "insert into node values ('{nid}','airport','Fiumicino','ITA',41.8,12.25,'FCO','LIRF',null,null,null,'international','active',false,null,null)"
    con.execute(node.format(nid="nd_0000000001"))
    with pytest.raises(duckdb.Error):
        con.execute(node.format(nid="pl_0000000001"))      # nodes carry their own id family
    con.execute("insert into place_node values ('pl_0000000001','nd_0000000001','serves','air',30.0,'wikidata',0.9,false)")
    with pytest.raises(duckdb.Error):
        con.execute("insert into place_node values ('pl_0000000001','nd_0000000001','nearest','air',30.0,'wikidata',0.9,false)")
    with pytest.raises(duckdb.Error):                      # minutes are not stored, only buckets
        con.execute("insert into place_stay values ('pl_0000000001','three_hours',null,null,'owner','high','x',null)")
    with pytest.raises(duckdb.Error):
        con.execute("insert into place_stay values ('pl_0000000001','day',9,3,'owner','high','x',null)")
    con.execute("insert into place_stay values ('pl_0000000001','multi_day',24,72,'source_text','medium','wikivoyage',null)")
