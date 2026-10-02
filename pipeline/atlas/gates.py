"""The gates of document 3 section 3. Each gate returns a GateResult and none only warns.

Principles (document 3 section 1): gates fail closed (a crash is a failure), read their
scope and exemptions from committed files and never from the bundle, report how many
things they checked (`n`) and how many checks they skipped, and treat a skip as a
failure unless the build is declared a prototype.
"""
from __future__ import annotations

import functools
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from atlas import golden as G
from atlas.bundle import Bundle, schema_problems
from atlas.geo import haversine_km, is_number, wilson_lower
from atlas.matching import assign, by_name_in_country, usable
from atlas.registry import Registry, place_keys
from atlas.vocab import KINDS, MAX_KINDS_PER_PLACE, MAX_NAME_LENGTH, PLACE_ID_RE, TIER_RANK

MIN_PLACES_FOR_SHARE = 100
MIN_HOLDOUT_ROWS = 100
MIN_PRECISION_ROWS = 100
REVIEW_VERDICTS = ("right", "wrong_entity", "wrong_place", "wrong_name", "should_not_exist")


@dataclass
class GateResult:
    gate: str
    passed: bool
    detail: str
    pending: bool = False
    n: int | None = None      # how many things the gate actually checked
    skipped: int = 0          # checks it could not run


@dataclass
class Context:
    bundle: Bundle
    golden: list[G.Row]
    registry: Registry | None = None
    previous: Bundle | None = None
    scope: dict | None = None            # data/scope.json, committed
    changelog: dict | None = None        # data/changelog.json, committed
    known_whs: set[str] | None = None
    holdout: list[G.Row] | None = None
    holdout_sha: str | None = None
    freeze: dict | None = None           # data/freeze.json, committed
    labels: list[dict] | None = None
    review: list[dict] | None = None
    strict: bool = True                  # a skipped check is a failure
    release: bool = False

    def places(self) -> list[dict]:
        return [p for p in self.bundle.active() if usable(p)]


def gate(name: str) -> Callable:
    """Register a gate and turn any exception into a failing result."""
    def deco(fn: Callable[[Context], GateResult]) -> Callable[[Context], GateResult]:
        @functools.wraps(fn)
        def wrapped(ctx: Context) -> GateResult:
            try:
                return fn(ctx)
            except Exception as e:  # noqa: BLE001 - fail closed on anything
                return GateResult(name, False, f"crashed: {type(e).__name__}: {e}")
        wrapped.gate_name = name  # type: ignore[attr-defined]
        return wrapped
    return deco


def _res(name: str, ok: bool, detail: str, **kw) -> GateResult:
    return GateResult(name, ok, detail, **kw)


def _first(items: list[str], k: int = 3) -> str:
    return "; ".join(items[:k]) + (f" (+{len(items) - k} more)" if len(items) > k else "")


# ------------------------------------------------------------------------------ structure
@gate("G-SCHEMA")
def g_schema(ctx: Context) -> GateResult:
    problems = schema_problems(ctx.bundle)
    n = len(ctx.bundle.places)
    if problems:
        return _res("G-SCHEMA", False, f"{len(problems)} problems: {_first(problems)}", n=n)
    return _res("G-SCHEMA", True, f"{n} places structurally valid", n=n)


@gate("G-GOLDEN")
def g_golden(ctx: Context) -> GateResult:
    problems = G.validate(ctx.golden, ctx.known_whs)
    if problems:
        return _res("G-GOLDEN", False, f"{len(problems)} problems: {_first(problems)}", n=len(ctx.golden))
    return _res("G-GOLDEN", True, f"{len(ctx.golden)} rows well formed", n=len(ctx.golden))


# ---------------------------------------------------------------------------- landmarks
def _shared_evidence(a: dict, b: dict) -> set[str]:
    def keys(p: dict) -> set[str]:
        out = {e.get("source_key") for e in p.get("evidence", []) if isinstance(e, dict)}
        out |= place_keys(p)
        if p.get("whs_id"):
            out.add(f"whs:{p['whs_id']}")
        return {k for k in out if isinstance(k, str) and re.match(r"^(whs|wdpa|qid|ramsar):", k)}
    return keys(a) & keys(b)


def _relational(ctx: Context, assignment) -> list[str]:
    places = ctx.places()
    by_id = {r.golden_id: r for r in ctx.golden}
    out: list[str] = []
    for r in ctx.golden:
        if r.row_kind != "negative":
            continue
        country_places = [p for p in places if p["iso3"] == r.iso3]
        if not country_places:
            out.append(f"{r.golden_id} {r.name}: no places in {r.iso3}, relation cannot be checked")
            continue
        found = by_name_in_country(r, places)
        if r.relation == "component_of" and found:
            out.append(f"{r.golden_id} {r.name} exists as a separate place")
        elif r.relation == "not_credited":
            tgt = assignment.matched.get(r.targets[0]) if r.targets else None
            if tgt is None:
                out.append(f"{r.golden_id} {r.name}: target {by_id[r.targets[0]].name} unresolved")
                continue
            for p in found:
                shared = _shared_evidence(p, tgt)
                if shared:
                    out.append(f"{r.golden_id} {r.name} carries {by_id[r.targets[0]].name}'s evidence {sorted(shared)}")
    return out


@gate("G-LANDMARK")
def g_landmark(ctx: Context) -> GateResult:
    pos = [r for r in ctx.golden if r.row_kind == "positive"]
    if not pos:
        return _res("G-LANDMARK", False, "golden set has no positive rows", n=0)
    a = assign(ctx.golden, ctx.places())
    rate = len(a.matched) / len(pos)
    reg_missed = [r.golden_id for r in a.missed if r.regression]
    relational = _relational(ctx, a)
    parts = [f"{len(a.matched)}/{len(pos)} resolved ({rate:.1%})"]
    if a.missed:
        parts.append("missed " + _first([f"{r.golden_id} {r.name}" for r in a.missed], 5))
    if reg_missed:
        parts.append(f"REGRESSION rows missed: {reg_missed}")
    if a.duplicates:
        names = {r.golden_id: r.name for r in pos}
        parts.append("duplicates of " + _first([f"{g} {names[g]}" for g in a.duplicates]))
    if relational:
        parts.append("relational: " + _first(relational))
    ok = rate >= 0.95 and not reg_missed and not a.duplicates and not relational
    return _res("G-LANDMARK", ok, "; ".join(parts), n=len(pos))


@gate("G-TIER")
def g_tier(ctx: Context) -> GateResult:
    a = assign(ctx.golden, ctx.places())
    by_id = {r.golden_id: r for r in ctx.golden}
    bad: list[str] = []
    checked = 0
    for r in (x for x in ctx.golden if x.row_kind == "positive"):
        p = a.matched.get(r.golden_id)
        if p is None:
            continue
        checked += 1
        rank = TIER_RANK.get(p.get("tier"), -1)
        if rank < TIER_RANK[r.min_tier]:
            bad.append(f"{r.golden_id} {r.name} is {p.get('tier')}, needs {r.min_tier}+")
        if r.max_tier and rank > TIER_RANK[r.max_tier]:
            bad.append(f"{r.golden_id} {r.name} is {p.get('tier')}, max {r.max_tier}")
    for r in ctx.golden:
        if not (r.row_kind == "negative" and r.relation == "not_above"):
            continue
        for t in r.targets:
            tp = a.matched.get(t)
            if tp is None:
                bad.append(f"{r.golden_id} {r.name}: target {by_id[t].name} unresolved, ordering unchecked")
                continue
            for p in by_name_in_country(r, ctx.places()):
                if TIER_RANK.get(p.get("tier"), -1) >= TIER_RANK[tp["tier"]]:
                    bad.append(f"{r.golden_id} {r.name} ({p.get('tier')}) is not below {by_id[t].name} ({tp['tier']})")
    if checked == 0:
        return _res("G-TIER", False, "no golden row resolved, so no tier could be checked", n=0)
    return _res("G-TIER", not bad, f"{checked} tiers checked; " + (_first(bad) if bad else "all hold"), n=checked)


# ---------------------------------------------------------------------------------- identity
_REG_STATUS = re.compile(r"^(active|retired|merged_into:\S+|split_from:\S+)$")


@gate("G-ID")
def g_id(ctx: Context) -> GateResult:
    places = [p for p in ctx.bundle.places if isinstance(p, dict)]
    ids = [p.get("place_id") for p in places]
    n = len(ids)
    if n == 0:
        return _res("G-ID", False, "no places", n=0)
    bad_fmt = [i for i in ids if not (isinstance(i, str) and PLACE_ID_RE.match(i))]
    dup = [i for i, c in Counter(ids).items() if c > 1]
    if bad_fmt or dup:
        return _res("G-ID", False, f"{len(bad_fmt)} malformed ids {bad_fmt[:2]}, {len(dup)} duplicates {dup[:2]}", n=n)
    reg = ctx.registry
    if reg is None:
        return _res("G-ID", False, "no registry supplied (data/registry/place_registry.parquet)", n=n)
    problems: list[str] = []
    bad_status = [i for i, r in reg.rows.items() if not _REG_STATUS.match((r.get("status") or "").strip())]
    if bad_status:
        problems.append(f"{len(bad_status)} registry rows with a missing or invalid status, e.g. {bad_status[:2]}")
    unknown = [i for i in ids if i not in reg.rows]
    if unknown:
        problems.append(f"{len(unknown)} ids missing from the registry, e.g. {unknown[:2]}")
    for p in places:
        i = p["place_id"]
        if i not in reg.rows:
            continue
        st = reg.status(i)
        if p.get("status", "active") == "active" and not (st == "active" or st.startswith("split_from:")):
            problems.append(f"{i} is active in the bundle but '{st}' in the registry")
        extra = place_keys(p) - reg.rows[i]["keys"]
        if extra:
            problems.append(f"{i} carries keys the registry does not hold for it: {sorted(extra)[:2]}")
        for k in place_keys(p):
            owners = reg.key_index().get(k, set())
            if owners and i not in owners:
                problems.append(f"{i} carries {k}, registered to {sorted(owners)[:2]}")
    conflicts = reg.key_conflicts()
    if conflicts:
        problems.append(f"{len(conflicts)} keys registered to more than one id, e.g. {sorted(conflicts)[:2]}")
    if ctx.previous is not None:
        prev_ids = {p.get("place_id") for p in ctx.previous.places if isinstance(p, dict)}
        unexplained = [i for i in prev_ids - set(ids) if reg.status(i) in ("", "active")]
        if unexplained:
            problems.append(f"{len(unexplained)} ids lost without a registry status, e.g. {unexplained[:2]}")
    return _res("G-ID", not problems, _first(problems) if problems else f"{n} ids unique, well formed, registered with their keys", n=n)


@gate("G-IDENT")
def g_ident(ctx: Context) -> GateResult:
    active = ctx.bundle.active()
    if not active:
        return _res("G-IDENT", False, "no places", n=0)
    qids = Counter(p.get("qid") for p in active if p.get("qid"))
    dup = [q for q, c in qids.items() if c > 1]
    if dup:
        return _res("G-IDENT", False, f"{len(dup)} QIDs on more than one active place, e.g. {dup[:3]}", n=len(active))
    if ctx.registry is None:
        return _res("G-IDENT", False, "no registry supplied", n=len(active))
    broken = [i for i in ctx.registry.rows
              if ctx.registry.status(i).startswith("merged_into:") and ctx.registry.resolve(i) is None]
    if broken:
        return _res("G-IDENT", False, f"{len(broken)} merged_into chains do not resolve, e.g. {broken[:2]}", n=len(active))
    return _res("G-IDENT", True, "no shared QIDs; merge chains resolve", n=len(active))


_BAD_NAME = re.compile(r"(^[QPL]\d+$)|<|>|&#?\w+;|[\x00-\x1f\x7f-\x9f�]|Ã.|Â.")


@gate("G-NAMES")
def g_names(ctx: Context) -> GateResult:
    places = [p for p in ctx.bundle.places if isinstance(p, dict)]
    if not places:
        return _res("G-NAMES", False, "no places", n=0)
    bad = []
    for p in places:
        n = p.get("name_en")
        if not isinstance(n, str) or not n or len(n) > MAX_NAME_LENGTH or _BAD_NAME.search(n):
            bad.append(f"{p.get('place_id')}:{str(n)[:30]!r}")
    detail = f"{len(bad)} bad names, e.g. {bad[:3]}" if bad else f"{len(places)} names clean"
    # name_local presence needs the country script table (M2): reported as skipped, not as passed.
    ok = not bad and not ctx.strict  # strict builds cannot pass while a check is skipped
    return _res("G-NAMES", ok, detail + " (name_local presence: skipped until M2)", n=len(places), skipped=1)


@gate("G-COUNT")
def g_count(ctx: Context) -> GateResult:
    counts = ctx.bundle.manifest.get("counts")
    places = [p for p in ctx.bundle.places if isinstance(p, dict)]
    if not isinstance(counts, dict) or not isinstance(counts.get("places"), int):
        return _res("G-COUNT", False, "manifest has no counts.places", n=len(places))
    per = counts.get("per_country")
    if not isinstance(per, dict) or not per:
        return _res("G-COUNT", False, "manifest has no counts.per_country", n=len(places))
    actual = Counter(p.get("iso3") for p in places)
    if counts["places"] != len(places) or dict(actual) != per or not places:
        return _res("G-COUNT", False, f"manifest {counts['places']}, files {len(places)}; per-country differs: "
                    f"{sorted(set(actual.items()) ^ set(per.items()))[:3]}", n=len(places))
    return _res("G-COUNT", True, f"{len(places)} places agree in manifest, files and per-country counts", n=len(places))


# ------------------------------------------------------------------------------------ kinds
@gate("G-KIND")
def g_kind(ctx: Context) -> GateResult:
    places = ctx.bundle.active()
    if not places:
        return _res("G-KIND", False, "no places", n=0)
    problems: list[str] = []
    counts: Counter[str] = Counter()
    for p in places:
        ks = p.get("kinds")
        if not isinstance(ks, list) or not 1 <= len(ks) <= MAX_KINDS_PER_PLACE:
            problems.append(f"{p.get('place_id')} has {len(ks) if isinstance(ks, list) else 'no'} kinds")
            continue
        names = [k.get("kind") if isinstance(k, dict) else None for k in ks]
        if len(set(names)) != len(names):
            problems.append(f"{p.get('place_id')} repeats a kind")
        for k in ks:
            kind = k.get("kind") if isinstance(k, dict) else None
            if kind not in KINDS:
                problems.append(f"{p.get('place_id')} unknown kind {kind!r}")
            elif not k.get("rule") or not k.get("evidence"):
                problems.append(f"{p.get('place_id')} kind {kind} lacks rule or evidence")
            else:
                counts[kind] += 1
    missing = [k for k in KINDS if counts[k] == 0]
    if missing:
        problems.append(f"kinds absent from the world: {missing}")
    skipped = 0
    if len(places) >= MIN_PLACES_FOR_SHARE:
        for k in KINDS:
            share = counts[k] / len(places)
            if counts[k] and (share > 0.25 or share < 0.01):
                problems.append(f"kind {k} on {share:.1%} of places")
    else:
        skipped = 1
        if ctx.strict:
            problems.append(f"share bounds skipped (n={len(places)} < {MIN_PLACES_FOR_SHARE}); "
                            "accepted only for a declared prototype build (--prototype)")
    return _res("G-KIND", not problems, _first(problems) if problems else f"{len(places)} places, all kinds present",
                n=len(places), skipped=skipped)


@gate("G-KIND-PRECISION")
def g_kind_precision(ctx: Context, floor: float = 0.85) -> GateResult:
    if not ctx.labels:
        return _res("G-KIND-PRECISION", False, "no hand-labelled sample (data/golden/kind_labels.csv)", n=0)
    by_id = {p.get("place_id"): p for p in ctx.bundle.active()}
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    seen = 0
    for lab in ctx.labels:
        p = by_id.get(lab.get("place_id"))
        if p is None:
            continue
        seen += 1
        truth = {k for k in (lab.get("kinds") or "").split("|") if k}
        for k in (x.get("kind") for x in p.get("kinds", []) if isinstance(x, dict)):
            (tp if k in truth else fp)[k] += 1
    if seen == 0:
        return _res("G-KIND-PRECISION", False, "no labelled place appears in the bundle", n=0)
    weak = [f"{k} {tp[k]}/{tp[k] + fp[k]}" for k in KINDS
            if tp[k] + fp[k] == 0 or wilson_lower(tp[k], tp[k] + fp[k]) < floor]
    return _res("G-KIND-PRECISION", not weak,
                f"lower bound below {floor} or unlabelled: {weak}" if weak else "every kind above the floor", n=seen)


@gate("G-COVER")
def g_cover(ctx: Context) -> GateResult:
    scope = ctx.scope
    if not isinstance(scope, dict) or not (scope.get("sovereign") or scope.get("dependencies")):
        return _res("G-COVER", False, "no committed scope (data/scope.json)", n=0)
    states, deps = set(scope.get("sovereign", [])), set(scope.get("dependencies", []))
    exempt = set(scope.get("exemptions", []))
    count = Counter(p["iso3"] for p in ctx.places())
    short = [f"{c} {count[c]}<5" for c in sorted(states) if count[c] < 5 and c not in exempt]
    short += [f"{c} {count[c]}<2" for c in sorted(deps) if count[c] < 2 and c not in exempt]
    outside = sorted(set(count) - states - deps)
    if outside:
        short.append(f"places in countries outside the committed scope: {outside}")
    return _res("G-COVER", not short, _first(short) if short else "every country in scope meets its floor",
                n=len(states | deps))


@gate("G-EVIDENCE")
def g_evidence(ctx: Context) -> GateResult:
    if not ctx.bundle.places:
        return _res("G-EVIDENCE", False, "no places", n=0)
    bad = [p for p in schema_problems(ctx.bundle) if "evidence" in p]
    return _res("G-EVIDENCE", not bad, f"{len(bad)} evidence problems: {_first(bad)}" if bad
                else "every place and kind has provenance", n=len(ctx.bundle.places))


@gate("G-INTEGRITY")
def g_integrity(ctx: Context) -> GateResult:
    """Files match the hashes the build recorded. This detects corruption and tampering after
    the build; it does NOT prove the build is reproducible (that is G-DETERMINISM, M2)."""
    recorded = ctx.bundle.manifest.get("hashes")
    if not isinstance(recorded, dict) or not recorded:
        return _res("G-INTEGRITY", False, "manifest records no file hashes", n=0)
    actual = ctx.bundle.file_hashes()
    diff = [f for f in sorted(set(recorded) | set(actual)) if recorded.get(f) != actual.get(f)]
    return _res("G-INTEGRITY", not diff, f"{len(diff)} files differ from the manifest, e.g. {diff[:3]}" if diff
                else f"{len(actual)} file hashes match", n=len(actual))


@gate("G-CHURN")
def g_churn(ctx: Context, limit: float = 0.02) -> GateResult:
    prev = ctx.previous
    if prev is None:
        return _res("G-CHURN", True, "first build: nothing to compare", n=0)
    old = {p["place_id"]: p for p in prev.places if isinstance(p, dict) and "place_id" in p}
    new = {p["place_id"]: p for p in ctx.bundle.places if isinstance(p, dict) and "place_id" in p}
    changed = 0
    for i, p in old.items():
        q = new.get(i)
        if (q is None or q.get("tier") != p.get("tier") or q.get("name_en") != p.get("name_en")
                or (is_number(q.get("lat")) and is_number(p.get("lat"))
                    and haversine_km(p["lat"], p["lon"], q["lat"], q["lon"]) > 1.0)):
            changed += 1
    share = changed / max(1, len(old))
    if share <= limit:
        return _res("G-CHURN", True, f"{share:.1%} changed (limit {limit:.0%})", n=len(old))
    cause = ctx.bundle.manifest.get("recorded_cause")
    causes = {c.get("id") for c in (ctx.changelog or {}).get("causes", []) if isinstance(c, dict)}
    if isinstance(cause, str) and cause in causes:
        return _res("G-CHURN", True, f"{share:.1%} changed, explained by committed cause '{cause}'", n=len(old))
    return _res("G-CHURN", False, f"{share:.1%} of places changed id, tier, name or position (limit {limit:.0%}) "
                "with no cause listed in data/changelog.json", n=len(old))


# -------------------------------------------------------------------------- release-only gates
@gate("G-HOLDOUT")
def g_holdout(ctx: Context, floor: float = 0.85) -> GateResult:
    pos = [r for r in (ctx.holdout or []) if r.row_kind == "positive"]
    if len(pos) < MIN_HOLDOUT_ROWS:
        return _res("G-HOLDOUT", False, f"holdout has {len(pos)} rows, needs {MIN_HOLDOUT_ROWS} (data/holdout/H1.csv)", n=len(pos))
    frozen = (ctx.freeze or {}).get("holdout_sha256")
    if not frozen or frozen != ctx.holdout_sha:
        return _res("G-HOLDOUT", False, "holdout is not frozen, or changed since it was frozen (data/freeze.json)", n=len(pos))
    gold = [r for r in ctx.golden if r.row_kind == "positive"]
    overlap = [h.name for h in pos for g in gold if h.iso3 == g.iso3 and (
        h.names & g.names or (h.type == g.type and None not in (h.lat, g.lat)
                              and haversine_km(h.lat, h.lon, g.lat, g.lon) < 1.0))]
    if overlap:
        return _res("G-HOLDOUT", False, f"{len(overlap)} holdout rows duplicate golden rows: {overlap[:3]}", n=len(pos))
    a = assign(pos, ctx.places())
    lb = wilson_lower(len(a.matched), len(pos))
    return _res("G-HOLDOUT", lb >= floor, f"recall {len(a.matched)}/{len(pos)}, Wilson lower bound {lb:.2f} (floor {floor})", n=len(pos))


@gate("G-PRECISION")
def g_precision(ctx: Context, floor: float = 0.95) -> GateResult:
    rows = ctx.review or []
    ids = {p.get("place_id") for p in ctx.bundle.active()}
    seen = [r.get("place_id") for r in rows]
    if len(rows) < MIN_PRECISION_ROWS:
        return _res("G-PRECISION", False, f"review has {len(rows)} rows, needs {MIN_PRECISION_ROWS}", n=len(rows))
    if len(set(seen)) != len(seen) or not set(seen) <= ids:
        return _res("G-PRECISION", False, "review rows must be unique and refer to places in this bundle", n=len(rows))
    if any(r.get("verdict") not in REVIEW_VERDICTS for r in rows):
        return _res("G-PRECISION", False, f"verdicts must be one of {REVIEW_VERDICTS}", n=len(rows))
    right = sum(1 for r in rows if r["verdict"] == "right")
    return _res("G-PRECISION", right / len(rows) >= floor, f"{right}/{len(rows)} right ({right / len(rows):.1%})", n=len(rows))


# ------------------------------------------------------------------------------- pending
def pending_gates() -> list[GateResult]:
    return [
        GateResult("G-DETERMINISM", False, "pending: a rebuild from the same manifest must reproduce every hash; built in M2", True),
        GateResult("G-STRUCT", False, "pending: parent chains, serving nodes and stay buckets against data/golden/structure.csv; built in M2", True),
        GateResult("G-REGION", False, "pending: needs geometry; built in M4", True),
        GateResult("G-DISPUTE", False, "pending: needs territories; built in M4", True),
        GateResult("G-PRINT", False, "pending: needs the print selection; built in M4", True),
    ]


CORE_GATES = (g_schema, g_golden, g_landmark, g_tier, g_id, g_ident, g_names, g_count, g_kind,
              g_kind_precision, g_cover, g_evidence, g_integrity, g_churn)
RELEASE_GATES = (g_holdout, g_precision)


def run_all(ctx: Context) -> list[GateResult]:
    out = [g(ctx) for g in CORE_GATES]
    if ctx.release:
        out += [g(ctx) for g in RELEASE_GATES]
    return out + pending_gates()
