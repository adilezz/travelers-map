"""Fixtures. The 'oracle bundle' is one perfect place per golden row, built from the golden
file itself. It proves the matcher and the golden set agree and gives the mutation tests
something to break; it says nothing about the pipeline, which has to earn its own bundle.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from atlas import golden as G
from atlas.bundle import Bundle
from atlas.gates import Context
from atlas.registry import Registry, place_keys

ROOT = Path(__file__).resolve().parents[2]
ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def pid(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).digest()
    return "pl_" + "".join(ALPHABET[b % 32] for b in h[:10])


def write_bundle(root: Path, places: list[dict], manifest_extra: dict | None = None) -> Path:
    (root / "places").mkdir(parents=True, exist_ok=True)
    by_iso: dict[str, list[dict]] = {}
    for p in places:
        by_iso.setdefault(p.get("iso3", "XXX") if isinstance(p, dict) else "XXX", []).append(p)
    for iso, ps in by_iso.items():
        (root / "places" / f"{iso}.json").write_text(
            json.dumps({"iso3": iso, "places": ps}, sort_keys=True), encoding="utf-8")
    hashes = {f.relative_to(root).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
              for f in sorted(root.rglob("*")) if f.is_file() and f.name != "manifest.json"}
    manifest = {"build_id": "test", "hashes": hashes,
                "counts": {"places": len(places), "per_country": {k: len(v) for k, v in by_iso.items()}}}
    manifest.update(manifest_extra or {})
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def oracle_places(rows) -> list[dict]:
    out = []
    for r in rows:
        if r.row_kind != "positive":
            continue
        n = int(r.golden_id[1:])
        out.append({
            "place_id": pid(r.golden_id), "type": r.type, "name_en": r.name,
            "aliases": r.raw["aliases"].split("|") if r.raw["aliases"] else [],
            "iso3": r.iso3, "lat": r.lat, "lon": r.lon, "tier": r.min_tier,
            "qid": f"Q{900000 + n}", "status": "active", "whs_id": r.whs_id,
            "kinds": [{"kind": k, "rule": "oracle", "evidence": ["a1"]} for k in r.kinds],
            "evidence": [{"asset_id": "a1", "source": "oracle", "url": "https://example.org/oracle",
                          "retrieved": "2026-10-01",
                          "source_key": f"whs:{r.whs_id}" if r.whs_id else "oracle"}],
        })
    return out


def registry_for(places: list[dict]) -> Registry:
    return Registry({p["place_id"]: {"place_id": p["place_id"], "status": "active", "keys": place_keys(p)}
                     for p in places if isinstance(p, dict) and isinstance(p.get("place_id"), str)})


SCOPE = {"sovereign": ["EGY", "ESP", "FRA", "ITA", "JOR", "MAR", "PER", "TUR", "TZA"], "dependencies": [], "exemptions": []}


@pytest.fixture(scope="session")
def golden_rows():
    return G.load(ROOT / "data" / "golden" / "golden.csv")


@pytest.fixture(scope="session")
def whs():
    return G.whs_ids(ROOT / "data" / "inputs" / "whs_properties.csv")


@pytest.fixture()
def oracle(tmp_path, golden_rows):
    return oracle_places(golden_rows)


@pytest.fixture()
def make_ctx(tmp_path, golden_rows, whs):
    """make_ctx(places, name='b', registry=..., **overrides) -> Context (lenient: strict=False)."""
    def _make(places, name="b", registry="auto", manifest_extra=None, **kw):
        bundle = Bundle.load(write_bundle(tmp_path / name, places, manifest_extra))
        reg = registry_for(places) if registry == "auto" else registry
        base = dict(bundle=bundle, golden=golden_rows, registry=reg, scope=SCOPE,
                    changelog={"causes": []}, known_whs=whs, strict=False)
        base.update(kw)
        return Context(**base)
    return _make
