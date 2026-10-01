"""The published bundle (document 2 section 6): loading and structural validation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from atlas.geo import is_number
from atlas.vocab import ISO3_RE, KEY_RE, PLACE_TYPES, STATUSES, TIERS


class BundleError(Exception):
    """The bundle cannot be read at all."""


@dataclass
class Bundle:
    root: Path
    manifest: dict
    places: list  # raw records; may be malformed, see schema_problems

    @classmethod
    def load(cls, root: str | Path) -> Bundle:
        root = Path(root)
        mpath = root / "manifest.json"
        if not mpath.is_file():
            raise BundleError(f"no manifest.json in {root}")
        try:
            manifest = json.loads(mpath.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise BundleError(f"manifest.json unreadable: {e}") from e
        if not isinstance(manifest, dict):
            raise BundleError("manifest.json is not an object")
        places: list = []
        pdir = root / "places"
        for f in sorted(pdir.glob("*.json")) if pdir.is_dir() else []:
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise BundleError(f"{f.name} unreadable: {e}") from e
            if not isinstance(doc, dict) or not isinstance(doc.get("places"), list):
                raise BundleError(f"{f.name}: expected an object with a 'places' list")
            for p in doc["places"]:
                if isinstance(p, dict):
                    p.setdefault("iso3", doc.get("iso3", f.stem))
                places.append(p)
        return cls(root, manifest, places)

    def active(self) -> list[dict]:
        return [p for p in self.places if isinstance(p, dict) and p.get("status", "active") == "active"]

    def file_hashes(self) -> dict[str, str]:
        out = {}
        for f in sorted(self.root.rglob("*")):
            if f.is_file() and f.name != "manifest.json":
                out[f.relative_to(self.root).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
        return out


def _alias_ok(a: object) -> bool:
    if isinstance(a, str):
        return True
    return isinstance(a, dict) and isinstance(a.get("alias"), str)


def schema_problems(bundle: Bundle) -> list[str]:
    """Structural problems that would make a gate crash or pass vacuously.

    Gates run only on records that pass this check; a bundle that fails it is not published.
    """
    out: list[str] = []
    if not bundle.places:
        return ["bundle has no places"]
    for i, p in enumerate(bundle.places):
        tag = f"place[{i}]"
        if not isinstance(p, dict):
            out.append(f"{tag}: not an object")
            continue
        pid = p.get("place_id")
        tag = f"{pid if isinstance(pid, str) else tag}"
        if not isinstance(pid, str) or not pid:
            out.append(f"{tag}: place_id missing or not a string")
        if p.get("type") not in PLACE_TYPES:
            out.append(f"{tag}: bad type {p.get('type')!r}")
        if not isinstance(p.get("name_en"), str):
            out.append(f"{tag}: name_en missing or not a string")
        iso = p.get("iso3")
        if not (isinstance(iso, str) and ISO3_RE.match(iso)):
            out.append(f"{tag}: bad iso3 {iso!r}")
        lat, lon = p.get("lat"), p.get("lon")
        if not (is_number(lat) and is_number(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            out.append(f"{tag}: bad coordinates {lat!r}, {lon!r}")
        if p.get("tier") not in TIERS:
            out.append(f"{tag}: bad tier {p.get('tier')!r}")
        status = p.get("status", "active")
        if status not in STATUSES:
            out.append(f"{tag}: bad status {status!r}")
        aliases = p.get("aliases", [])
        if not isinstance(aliases, list) or not all(_alias_ok(a) for a in aliases):
            out.append(f"{tag}: aliases must be strings or objects with an 'alias' string")
        keys = p.get("keys", [])
        if not isinstance(keys, list) or not all(isinstance(k, str) and KEY_RE.match(k) for k in keys):
            out.append(f"{tag}: keys must be 'qid:…', 'wdpa:…', 'geonames:…' or 'osm:…'")
        evidence = p.get("evidence")
        ev_ids: set = set()
        if not isinstance(evidence, list) or not evidence:
            out.append(f"{tag}: evidence missing or empty")
        else:
            for e in evidence:
                if not isinstance(e, dict):
                    out.append(f"{tag}: evidence entry is not an object")
                    continue
                if not (isinstance(e.get("asset_id"), str) and e["asset_id"]):
                    out.append(f"{tag}: evidence without a string asset_id")
                else:
                    ev_ids.add(e["asset_id"])
                for f in ("source", "url", "retrieved"):
                    if not (isinstance(e.get(f), str) and e[f]):
                        out.append(f"{tag}: evidence missing {f}")
        kinds = p.get("kinds")
        if not isinstance(kinds, list):
            out.append(f"{tag}: kinds must be a list")
        else:
            for k in kinds:
                if not isinstance(k, dict) or not isinstance(k.get("kind"), str):
                    out.append(f"{tag}: kind entries must be objects with a 'kind' string")
                    continue
                if not (isinstance(k.get("rule"), str) and k["rule"]):
                    out.append(f"{tag}: kind {k['kind']} has no rule")
                ev = k.get("evidence")
                if not (isinstance(ev, list) and ev and all(isinstance(x, str) and x for x in ev)):
                    out.append(f"{tag}: kind {k['kind']} has no evidence ids")
                elif set(ev) - ev_ids:
                    out.append(f"{tag}: kind {k['kind']} cites evidence the place does not carry")
    return out
