import json
from pathlib import Path

import pytest

from atlas import snapshot

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def manifest(tmp_path):
    m = json.loads((ROOT / "data" / "inputs" / "MANIFEST.json").read_text(encoding="utf-8"))
    for src in m["sources"]:                       # a clean copy: the real manifest pins real files
        src.pop("files", None)
        src["snapshot"] = None
    p = tmp_path / "MANIFEST.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


def test_pin_then_check_passes_and_detects_changes(tmp_path, manifest):
    raw = tmp_path / "raw"
    raw.mkdir()
    f = raw / "wdpa.csv"
    f.write_text("id,name\n1,x\n", encoding="utf-8")
    e = snapshot.pin("wdpa", f, raw, "2026-10-01", manifest)
    assert e["path"] == "wdpa.csv" and len(e["sha256"]) == 64
    assert snapshot.check(raw, manifest) == []
    f.write_text("id,name\n1,y\n", encoding="utf-8")                  # same size, different content
    assert any("hash differs" in p for p in snapshot.check(raw, manifest))
    f.write_text("longer", encoding="utf-8")
    assert any("changed size" in p for p in snapshot.check(raw, manifest))
    f.unlink()
    assert any("missing" in p for p in snapshot.check(raw, manifest))


def test_required_sources_must_be_pinned_with_a_snapshot(tmp_path, manifest):
    problems = snapshot.check(tmp_path, manifest, required={"wikidata", "nonsense"})
    assert any("wikidata: required but not pinned" in p for p in problems)
    assert any("nonsense: not a source" in p for p in problems)


def test_pin_rejects_unknown_sources_and_repins_replace(tmp_path, manifest):
    f = tmp_path / "a.csv"
    f.write_text("1", encoding="utf-8")
    with pytest.raises(KeyError):
        snapshot.pin("nope", f, tmp_path, None, manifest)
    snapshot.pin("ramsar", f, tmp_path, "2026-10-01", manifest)
    f.write_text("22", encoding="utf-8")
    snapshot.pin("ramsar", f, tmp_path, None, manifest)
    src = next(s for s in json.loads(manifest.read_text())["sources"] if s["source_id"] == "ramsar")
    assert len(src["files"]) == 1 and src["files"][0]["bytes"] == 2 and src["snapshot"] == "2026-10-01"
