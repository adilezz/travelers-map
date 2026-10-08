"""S2b: which states each place is or was the capital of, read from the state side (property P36).

    python -m atlas.capitals run     [--bundle build/first]    # about 12 SPARQL requests, resumable
    python -m atlas.capitals parquet
    python -m atlas.capitals pin

Wikidata records a capital on the state (P36) far more often than on the city (P1376), so Venice, Florence, Siena,
Naples, Chan Chan and Thebes are missing from the city-side statements the kind rules first used. For every place of
the bundle (and its merged items) this asks: which states list it as a capital, with what end date, and what are those
states (their classes decide "sovereign state" against "duchy")."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from atlas.extract import http_run
from atlas.geofacts import load_places

ROOT = Path(__file__).resolve().parents[2]
BATCH = 150


def query(qids: list[str]) -> str:
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""SELECT ?cap ?state (GROUP_CONCAT(DISTINCT ?cls; separator="|") AS ?classes) (SAMPLE(?ended) AS ?ended) WHERE {{
  VALUES ?cap {{ {values} }}
  ?state p:P36 ?st . ?st ps:P36 ?cap .
  OPTIONAL {{ ?st pq:P582 ?end }}
  BIND(BOUND(?end) AS ?ended)
  OPTIONAL {{ ?state wdt:P31 ?cls }}
}} GROUP BY ?cap ?state"""


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def parse(b: dict) -> dict:
    classes = [qid(x) for x in b.get("classes", {}).get("value", "").split("|") if x]
    return {"cap": qid(b["cap"]["value"]), "state": qid(b["state"]["value"]), "classes": classes,
            "ended": b.get("ended", {}).get("value") in ("true", "1")}


def targets(bundle: Path) -> list[str]:
    out: set[str] = set()
    for p in load_places(bundle):
        out |= {p["qid"]} | {k[4:] for k in p.get("keys", []) if k.startswith("qid:")}
    return sorted(out)


def run(qids: list[str], out: Path, run_query: Callable[[str], list[dict]] = http_run, delay: float = 1.0,
        log: Callable[[str], None] = print) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "capitals.jsonl"
    done: set[str] = set()
    if path.is_file():
        done = {json.loads(line)["batch"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    failed = []
    batches = [qids[i:i + BATCH] for i in range(0, len(qids), BATCH)]
    with open(path, "a", encoding="utf-8") as fh:
        for n, b in enumerate(batches):
            key = f"{b[0]}-{b[-1]}"
            if key in done:
                continue
            try:
                rows = [parse(x) for x in run_query(query(b))]
            except Exception as e:
                failed.append(key)
                log(f"batch {n + 1}/{len(batches)} failed: {type(e).__name__} {str(e)[:80]}")
                continue
            fh.write(json.dumps({"batch": key, "rows": rows}, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
            log(f"batch {n + 1}/{len(batches)}: {len(rows)} capital statements")
            time.sleep(delay)
    return {"batches": len(batches), "already": len(done), "failed": failed}


def to_parquet(out: Path) -> int:
    import duckdb
    rows = out / "capitals.rows.jsonl"
    with open(out / "capitals.jsonl", encoding="utf-8") as fh, open(rows, "w", encoding="utf-8") as w:
        for line in fh:
            if line.strip():
                for r in json.loads(line)["rows"]:
                    w.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    dest = out / "capitals.parquet"
    con = duckdb.connect()
    con.execute(f"COPY (SELECT cap, state, classes, ended FROM read_json_auto('{rows.as_posix()}', sample_size=-1) ORDER BY cap, state) "
                f"TO '{dest.as_posix()}' (FORMAT PARQUET)")
    n = con.execute(f"SELECT count(*) FROM read_parquet('{dest.as_posix()}')").fetchone()[0]
    rows.unlink()
    return n


def load(path: Path) -> dict[str, list[dict]]:
    """cap QID -> [{qid, ended, classes}]; empty when S2b has not been run."""
    if not path.is_file():
        return {}
    import duckdb
    out: dict[str, list[dict]] = {}
    for cap, state, classes, ended in duckdb.connect().execute(f"SELECT cap, state, classes, ended FROM read_parquet('{path.as_posix()}')").fetchall():
        out.setdefault(cap, []).append({"qid": state, "ended": bool(ended), "classes": list(classes or [])})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "parquet", "pin"])
    ap.add_argument("--bundle", type=Path, default=ROOT / "build" / "first")
    ap.add_argument("--snapshot", default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1].name)
    a = ap.parse_args(argv)
    out = ROOT / "data" / "raw" / "wikidata" / a.snapshot
    if a.cmd == "run":
        res = run(targets(a.bundle), out)
        print(res["batches"], "batches,", res["already"], "already done,", len(res["failed"]), "failed")
        return 1 if res["failed"] else 0
    if a.cmd == "parquet":
        print(to_parquet(out), "capital statements")
        return 0
    from atlas import snapshot
    snapshot.pin("wikidata_sparql", out / "capitals.parquet", ROOT / "data" / "raw", a.snapshot)
    print("pinned capitals.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
