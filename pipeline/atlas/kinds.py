"""Choosing a place's kinds from the rules that fired (document 1 section 7.3).

Deterministic and auditable: the same fired rules always give the same kinds, in the same
order, and every dropped kind records why. Rules, their strengths and the pair rules are
data (`data/rules/kinds.csv`, `kind_pairs.csv`), not code; only the closed set of conditions
below lives here.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from atlas.vocab import KIND_PRIORITY, KINDS, MAX_KINDS_PER_PLACE

MIN_STRENGTH = 0.50   # a kind needs at least this combined strength...
CAP = 0.95            # ...and never claims more than this, however many rules agree
BUCKET = 0.05         # strengths closer than this are treated as equal, then evidence decides


@dataclass(frozen=True)
class Fired:
    rule_id: str
    kind: str
    source: str            # wikidata, unesco, iucn, osm, landcover, relief, coast, pop, footprint
    strength: float        # the rule's estimated precision, 0..1
    role: str = "core"     # 'support' adds strength but cannot create a kind alone; 'fallback' applies only if no kind survives
    excludes: tuple[str, ...] = ()


@dataclass
class Choice:
    kind: str
    strength: float
    sources: int
    rule_ids: tuple[str, ...]


@dataclass
class Selection:
    kept: list[Choice] = field(default_factory=list)
    cut: list[dict] = field(default_factory=list)   # {"kind", "strength", "reason"}
    crowded: bool = False                            # the 4th kind was nearly as strong as the 3rd

    def kinds(self) -> list[str]:
        return [c.kind for c in self.kept]


# --- the closed set of pair-rule conditions, each over simple facts about the place ---------
CONDITIONS: dict[str, Callable[[dict], bool]] = {
    "always": lambda f: True,
    # the place ITSELF is a living place of worship or pilgrimage site (not a city that contains one)
    "living_worship": lambda f: bool(f.get("living_worship")),
    "not_living_worship": lambda f: not f.get("living_worship"),
    # a real port city (200k+) with no beach within 2 km
    "large_port_no_beach": lambda f: f.get("population", 0) >= 200_000 and not f.get("beach_within_2km"),
    # a strict protected area covers at least half the footprint and farmland under 30 %
    "protected_dominant": lambda f: f.get("protected_overlap", 0.0) >= 0.5 and f.get("cropland_share", 0.0) < 0.3,
    "tree_dominant": lambda f: f.get("tree_cover", 0.0) >= 0.5,
    # the water is sea, lagoon or brackish: that is `seaside`, not `water`
    "marine_water": lambda f: bool(f.get("water_is_marine")),
}


@dataclass(frozen=True)
class Pair:
    keep: str
    drop: str
    condition: str
    rationale: str = ""


def load_pairs(path: str | Path) -> list[Pair]:
    pairs = []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            p = Pair(row["keep"], row["drop"], row["condition"], row.get("rationale", ""))
            if p.keep not in KINDS or p.drop not in KINDS:
                raise ValueError(f"unknown kind in pair rule {p}")
            if p.condition not in CONDITIONS:
                raise ValueError(f"unknown condition {p.condition!r} in pair rule {p}")
            pairs.append(p)
    return pairs


def _bucket(strength: float) -> int:
    return round(strength / BUCKET)


def combine(fired: list[Fired]) -> dict[str, Choice]:
    """Per kind: noisy-or over distinct sources (only the best rule per source counts, so
    correlated rules cannot inflate a kind), capped; a kind needs a core rule."""
    by_kind: dict[str, list[Fired]] = defaultdict(list)
    for f in fired:
        by_kind[f.kind].append(f)
    out: dict[str, Choice] = {}
    for kind, rules in by_kind.items():
        best: dict[str, float] = {}
        for r in rules:
            best[r.source] = max(best.get(r.source, 0.0), r.strength)
        s = min(CAP, 1.0 - math.prod(1.0 - v for v in best.values()))
        out[kind] = Choice(kind, round(s, 4), len(best), tuple(sorted(r.rule_id for r in rules)))
    return out


def select_kinds(fired: list[Fired], facts: dict | None = None,
                 pairs: list[Pair] | None = None) -> Selection:
    facts = facts or {}
    pairs = pairs or []
    sel = Selection()
    fallback = [f for f in fired if f.role == "fallback"]   # D26: used only when nothing else survives
    fired = [f for f in fired if f.role != "fallback"]
    choices = combine(fired)
    core_kinds = {f.kind for f in fired if f.role == "core"}
    live: dict[str, Choice] = {}
    for kind, c in choices.items():
        if kind not in core_kinds:
            sel.cut.append({"kind": kind, "strength": c.strength, "reason": "no_core_rule"})
        elif c.strength < MIN_STRENGTH:
            sel.cut.append({"kind": kind, "strength": c.strength, "reason": "below_threshold"})
        else:
            live[kind] = c
    for f in sorted(fired, key=lambda f: f.rule_id):
        for x in f.excludes:
            if x in live and f.kind in live:
                sel.cut.append({"kind": x, "strength": live.pop(x).strength, "reason": f"excluded_by:{f.rule_id}"})
    for p in pairs:
        if p.keep in live and p.drop in live and CONDITIONS[p.condition](facts):
            sel.cut.append({"kind": p.drop, "strength": live.pop(p.drop).strength,
                            "reason": f"pair:{p.keep}>{p.drop}:{p.condition}"})
    order = sorted(live.values(), key=lambda c: (-_bucket(c.strength), -c.sources,
                                                 KIND_PRIORITY.index(c.kind), c.kind))
    if not order and fallback:
        order = sorted(combine(fallback).values(), key=lambda c: (-_bucket(c.strength), KIND_PRIORITY.index(c.kind)))
        order = [c for c in order if c.strength >= MIN_STRENGTH]
    sel.kept = order[:MAX_KINDS_PER_PLACE]
    for c in order[MAX_KINDS_PER_PLACE:]:
        sel.cut.append({"kind": c.kind, "strength": c.strength, "reason": "cap"})
    if len(order) > MAX_KINDS_PER_PLACE:
        third, fourth = order[MAX_KINDS_PER_PLACE - 1], order[MAX_KINDS_PER_PLACE]
        sel.crowded = _bucket(fourth.strength) >= _bucket(third.strength) - 2
    return sel
