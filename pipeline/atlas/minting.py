"""Minting, reusing, retiring, merging and splitting place ids (document 2 section 3.2).

The registry is the only source of identity. Rules enforced here:
1. a candidate is matched by its keys (QID first, then WDPA, GeoNames, OSM); a hit reuses the id;
2. a place that falls below a threshold keeps its id (retired) and is reactivated, not re-minted;
3. a merge points the loser at the survivor; any key of the loser still resolves, through the chain;
4. a split mints a new id for the new part; the original keeps its id;
5. an id is never reused, and a key never moves to another id;
6. nothing is committed to disk unless the landmark gate passed on real QIDs.
"""
from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path

from atlas.registry import Registry
from atlas.vocab import PLACE_ID_RE

ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
KEY_PRIORITY = ("qid", "wdpa", "geonames", "osm")


class MintingError(Exception):
    """A rule of the registry would be broken."""


def new_id(reg: Registry, rng: random.Random | None = None) -> str:
    rng = rng or random.SystemRandom()
    for _ in range(1000):
        pid = "pl_" + "".join(rng.choice(ALPHABET) for _ in range(10))
        if pid not in reg.rows and PLACE_ID_RE.match(pid):
            return pid
    raise MintingError("could not mint an unused id")


def _scheme(key: str) -> str:
    return key.split(":", 1)[0]


def ordered(keys: Iterable[str]) -> list[str]:
    return sorted(set(keys), key=lambda k: (KEY_PRIORITY.index(_scheme(k)) if _scheme(k) in KEY_PRIORITY else 99, k))


def lookup(reg: Registry, keys: Iterable[str]) -> str | None:
    """The current id for a candidate's keys, following merge chains. Raises if the keys point
    at two different places: the pipeline must resolve that explicitly (merge or split)."""
    idx = reg.key_index()
    found: set[str] = set()
    for k in keys:
        for pid in idx.get(k, ()):
            cur = reg.resolve(pid)
            if cur is None:
                raise MintingError(f"{k} resolves through a broken merge chain from {pid}")
            found.add(cur)
    if len(found) > 1:
        raise MintingError(f"keys {sorted(keys)} identify {len(found)} different places: {sorted(found)}")
    return next(iter(found), None)


def mint_or_reuse(reg: Registry, keys: Iterable[str], build: str,
                  rng: random.Random | None = None) -> str:
    keys = ordered(keys)
    if not keys:
        raise MintingError("a place needs at least one identity key")
    pid = lookup(reg, keys)
    if pid is None:
        pid = new_id(reg, rng)
        reg.rows[pid] = {"place_id": pid, "keys": set(keys), "status": "active",
                         "minted_build": build, "last_seen_build": build, "tombstone_reason": ""}
        return pid
    row = reg.rows[pid]
    idx = reg.key_index()
    for k in keys:
        owners = idx.get(k, set())
        if owners and pid not in {reg.resolve(o) for o in owners}:
            raise MintingError(f"{k} already belongs to another place")
    row["keys"] |= set(keys)                 # adding a key is allowed; moving one is not
    row["last_seen_build"] = build
    if row["status"] == "retired":           # reactivate, never re-mint
        row["status"], row["tombstone_reason"] = "active", ""
    return pid


def retire(reg: Registry, place_id: str, build: str, reason: str) -> None:
    row = reg.rows[place_id]
    if row["status"] != "active":
        raise MintingError(f"{place_id} is {row['status']}, not active")
    row.update(status="retired", last_seen_build=build, tombstone_reason=reason)


def merge(reg: Registry, loser: str, survivor: str, build: str) -> None:
    if loser == survivor:
        raise MintingError("cannot merge a place into itself")
    for pid in (loser, survivor):
        if pid not in reg.rows:
            raise MintingError(f"unknown place {pid}")
    if reg.resolve(survivor) == loser:
        raise MintingError("merge would create a cycle")
    reg.rows[loser].update(status=f"merged_into:{survivor}", last_seen_build=build)


def split(reg: Registry, place_id: str, new_keys: Iterable[str], build: str,
          rng: random.Random | None = None) -> str:
    keys = ordered(new_keys)
    if not keys:
        raise MintingError("the new part needs its own keys")
    if lookup(reg, keys) is not None:
        raise MintingError("a split needs keys no place already holds")
    pid = new_id(reg, rng)
    reg.rows[pid] = {"place_id": pid, "keys": set(keys), "status": f"split_from:{place_id}",
                     "minted_build": build, "last_seen_build": build, "tombstone_reason": ""}
    return pid


def save(reg: Registry, path: str | Path) -> None:
    """Write the registry as Parquet, sorted by id so diffs and hashes are stable."""
    import duckdb

    con = duckdb.connect()
    con.execute("create table r(place_id varchar, keys varchar[], status varchar, minted_build varchar,"
                " last_seen_build varchar, tombstone_reason varchar)")
    for pid in sorted(reg.rows):
        r = reg.rows[pid]
        con.execute("insert into r values (?,?,?,?,?,?)",
                    [pid, sorted(r["keys"]), r["status"], r.get("minted_build"),
                     r.get("last_seen_build"), r.get("tombstone_reason") or None])
    con.execute("copy (select * from r order by place_id) to ? (format parquet)", [str(path)])


def commit(reg: Registry, path: str | Path, gate_results: list, golden: list) -> None:
    """Rule 6: ids are permanent, so nothing is written until G-LANDMARK has passed AND every
    golden place carries a real, resolved QID (matching on names alone is the v1 failure)."""
    landmark = next((g for g in gate_results if g.gate == "G-LANDMARK"), None)
    if landmark is None or not landmark.passed:
        raise MintingError("refusing to commit the registry: G-LANDMARK has not passed")
    blank = [r.golden_id for r in golden if r.row_kind == "positive" and not r.qid]
    if blank:
        raise MintingError(f"refusing to commit the registry: {len(blank)} golden rows have no QID, e.g. {blank[:3]}")
    save(reg, path)
