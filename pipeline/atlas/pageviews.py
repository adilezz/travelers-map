"""S4: twelve months of English-Wikipedia pageviews for the places in the bundle (document 1 section 6.1).

    python -m atlas.pageviews select  [--bundle build/first]    # which titles, how many requests
    python -m atlas.pageviews run     [--bundle build/first]    # fetch, resumable
    python -m atlas.pageviews parquet
    python -m atlas.pageviews pin

One request per article (Wikimedia REST, per-article, monthly, human users, all access), about ten per
second, so a bundle of 5,500 places takes ten to fifteen minutes. A place carries the most-viewed of the
articles of its merged items (Giza's pyramid complex and its Great Pyramid are one place). Only the English
article is asked: this is a known bias toward English-language attention, documented in document 1
section 6.1 and audited in M3. An article that does not exist or has no views is recorded as zero, not
dropped, so "no data" and "no attention" are not confused.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from atlas.wikidata import http_get

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
START, END = "2025100100", "2026093000"        # twelve full months before the 5 October 2026 snapshot
MONTHS = 12


def load_titles(raw: Path) -> dict[str, str]:
    import duckdb
    p = raw / "details.parquet"
    if not p.is_file():
        return {}
    con = duckdb.connect()
    return {q: t for q, t in con.execute(
        f"SELECT qid, wikipedia_en FROM read_parquet('{p.as_posix()}') WHERE wikipedia_en IS NOT NULL").fetchall()}


def bundle_qids(bundle: Path) -> set[str]:
    out: set[str] = set()
    for f in sorted((bundle / "places").glob("*.json")):
        for p in json.loads(f.read_text(encoding="utf-8"))["places"]:
            out |= {k[4:] for k in p.get("keys", []) if k.startswith("qid:")} | {p["qid"]}
    return out


def select(raw: Path, bundle: Path) -> dict[str, str]:
    """QID -> English title, for every item of every place in the bundle that has an article."""
    titles = load_titles(raw)
    return {q: titles[q] for q in sorted(bundle_qids(bundle)) if q in titles}


def fetch_views(title: str, get: Callable[[str, dict], dict] = http_get) -> list[int] | None:
    """Twelve monthly counts, or None when Wikimedia has no record of the article (404)."""
    url = f"{BASE}/{urllib.parse.quote(title.replace(' ', '_'), safe='')}/monthly/{START}/{END}"
    try:
        d = get(url, {})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    by_month = {i["timestamp"][:6]: int(i["views"]) for i in d.get("items", [])}
    return [by_month.get(f"{y}{m:02d}", 0) for y, m in _months()]


def _months() -> list[tuple[int, int]]:
    y, m = int(START[:4]), int(START[4:6])
    out = []
    for _ in range(MONTHS):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def run(chosen: dict[str, str], out: Path, get: Callable[[str, dict], dict] = http_get, delay: float = 0.1,
        log: Callable[[str], None] = print) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "pageviews.jsonl"
    done: set[str] = set()
    if path.is_file():
        with open(path, encoding="utf-8") as fh:
            done = {json.loads(line)["qid"] for line in fh if line.strip() and not line.startswith('{"_meta"')}
    todo = [q for q in sorted(chosen) if q not in done]
    failed: list[str] = []
    with open(path, "a", encoding="utf-8") as fh:
        if not done:
            fh.write(json.dumps({"_meta": {"run_utc": datetime.now(UTC).isoformat(timespec="seconds"), "start": START,
                                           "end": END, "project": "en.wikipedia", "agent": "user"}}) + "\n")
        for i, q in enumerate(todo):
            try:
                v = fetch_views(chosen[q], get)
            except Exception as e:                                       # one bad title must not stop the run
                failed.append(q)
                log(f"{q} {chosen[q]!r}: failed ({type(e).__name__}: {str(e)[:60]})")
                continue
            row = {"qid": q, "title": chosen[q], "views": v or [0] * MONTHS, "total": sum(v or []), "missing": v is None}
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            if i % 200 == 0:
                fh.flush()
                log(f"{i}/{len(todo)}")
            time.sleep(delay)
    return {"selected": len(chosen), "already": len(done), "fetched": len(todo) - len(failed), "failed": failed}


def to_parquet(out: Path) -> int:
    import duckdb
    rows = out / "pageviews.rows.jsonl"
    with open(out / "pageviews.jsonl", encoding="utf-8") as fh, open(rows, "w", encoding="utf-8") as w:
        for line in fh:
            if line.strip() and not line.startswith('{"_meta"'):
                w.write(line)
    dest = out / "pageviews.parquet"
    con = duckdb.connect()
    con.execute(f"COPY (SELECT qid, title, views, total, missing FROM read_json_auto('{rows.as_posix()}', sample_size=-1) "
                f"ORDER BY qid) TO '{dest.as_posix()}' (FORMAT PARQUET)")
    n = con.execute(f"SELECT count(*) FROM read_parquet('{dest.as_posix()}')").fetchone()[0]
    rows.unlink()
    return n


def load(path: Path) -> dict[str, int]:
    """QID -> twelve-month total; empty when S4 has not been run."""
    if not path.is_file():
        return {}
    import duckdb
    return dict(duckdb.connect().execute(f"SELECT qid, total FROM read_parquet('{path.as_posix()}')").fetchall())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["select", "run", "parquet", "pin"])
    ap.add_argument("--raw", type=Path, default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1])
    ap.add_argument("--bundle", type=Path, default=ROOT / "build" / "first")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--delay", type=float, default=0.1)
    a = ap.parse_args(argv)
    out = a.out or ROOT / "data" / "raw" / "pageviews" / a.raw.name
    if a.cmd == "select":
        chosen = select(a.raw, a.bundle)
        print(f"{len(chosen)} articles to fetch, about {len(chosen) * (a.delay + 0.15) / 60:.0f} minutes")
        return 0
    if a.cmd == "run":
        res = run(select(a.raw, a.bundle), out, delay=a.delay)
        print(res["selected"], "selected,", res["already"], "already done,", res["fetched"], "fetched,", len(res["failed"]), "failed")
        return 1 if res["failed"] else 0
    if a.cmd == "parquet":
        print(to_parquet(out), "rows")
        return 0
    from atlas import snapshot
    snapshot.pin("wikipedia_pageviews", out / "pageviews.parquet", ROOT / "data" / "raw", a.raw.name)
    print("pinned pageviews.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
