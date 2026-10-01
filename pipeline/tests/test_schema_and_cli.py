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
    assert "G-LANDMARK" in r.stdout and "PEND" in r.stdout and "[n=97]" in r.stdout
    results = json.loads((tmp_path / "out.json").read_text())
    assert {x["gate"] for x in results if x["pending"]} == {"G-DETERMINISM", "G-REGION", "G-DISPUTE", "G-PRINT"}


def test_registry_parquet_is_readable_and_empty():
    from atlas.registry import Registry
    assert Registry.load(ROOT / "data" / "registry" / "place_registry.parquet").rows == {}


def test_committed_data_files_are_valid():
    scope = json.loads((ROOT / "data" / "scope.json").read_text(encoding="utf-8"))
    assert scope["sovereign"] == ["EGY", "ITA", "JOR", "PER", "TZA"]
    cfg = json.loads((ROOT / "data" / "rules" / "tiers.json").read_text(encoding="utf-8"))
    assert cfg["admission"]["r5_country_floor"] == {"sovereign": 5, "dependency": 2}
    m = json.loads((ROOT / "data" / "inputs" / "MANIFEST.json").read_text(encoding="utf-8"))
    ids = {s["source_id"] for s in m["sources"]}
    assert {"wikidata", "wikipedia_pageviews", "wikivoyage", "unesco_whs", "wdpa", "ramsar", "geonames", "osm", "natural_earth"} <= ids
    assert all(s["licence"] and "restricted" in s for s in m["sources"])
    assert json.loads((ROOT / "data" / "changelog.json").read_text(encoding="utf-8"))["causes"] == []
