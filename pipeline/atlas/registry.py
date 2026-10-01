"""The identity registry (document 2 section 3.2)."""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REGISTRY_COLUMNS = (
    "place_id", "keys", "status", "minted_build", "last_seen_build", "tombstone_reason",
)


def place_keys(p: dict) -> set[str]:
    """Identity keys a place record carries, in registry form.

    A World Heritage id is deliberately not an identity key: it names a *property*, and a
    serial property can back several places (Giza and Saqqara are both parts of property 86).
    It stays on the place as an evidence link.
    """
    keys = set(p.get("keys") or [])
    for field_name, prefix in (("qid", "qid"), ("wdpa_id", "wdpa"),
                               ("geonames_id", "geonames"), ("osm_id", "osm")):
        v = p.get(field_name)
        if v:
            keys.add(f"{prefix}:{v}")
    return keys


@dataclass
class Registry:
    rows: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> Registry:
        path = Path(path)
        rows: dict[str, dict] = {}
        if path.suffix == ".parquet":
            import duckdb

            cur = duckdb.connect().execute("select * from read_parquet(?)", [str(path)])
            cols = [d[0] for d in cur.description]
            for rec in cur.fetchall():
                row = dict(zip(cols, rec, strict=True))
                row["keys"] = set(row.get("keys") or [])
                rows[row["place_id"]] = row
        else:
            with open(path, encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    row["keys"] = {k for k in (row.get("keys") or "").split("|") if k}
                    rows[row["place_id"]] = row
        return cls(rows)

    def status(self, place_id: str) -> str:
        return (self.rows.get(place_id, {}).get("status") or "").strip()

    def resolve(self, place_id: str) -> str | None:
        """Follow merged_into chains; None on a dangling or cyclic chain."""
        seen: set[str] = set()
        cur = place_id
        while cur in self.rows:
            if cur in seen:
                return None
            seen.add(cur)
            st = self.status(cur)
            if not st.startswith("merged_into:"):
                return cur
            cur = st.split(":", 1)[1]
        return None

    def key_index(self) -> dict[str, set[str]]:
        idx: dict[str, set[str]] = defaultdict(set)
        for pid, row in self.rows.items():
            for k in row.get("keys", ()):
                idx[k].add(pid)
        return idx

    def key_conflicts(self) -> dict[str, set[str]]:
        """Keys registered to more than one place_id (document 2 section 3.2, rule 5)."""
        return {k: ids for k, ids in self.key_index().items() if len(ids) > 1}
