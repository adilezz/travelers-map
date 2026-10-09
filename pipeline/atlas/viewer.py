"""A local viewer for the first bundle: browse, check, and label (document 3 sections 2.3 and 2.4).

    python -m atlas.viewer [--bundle build/first] [--port 8765]        # then open http://127.0.0.1:8765
    make viewer

What it shows: every place with its tier and the reason for it, its kinds with the rule and the evidence behind each,
the kinds that were cut and why, the places without a kind, what was absorbed into a place, what was left out as
context, and the golden row a place answers to. What it saves, to plain CSV files you commit:
  * data/golden/kind_labels.csv     your own kinds for the stratified sample (blind: the predicted kinds are hidden until
                                    you save, so the labels do not follow the rules);
  * data/review/precision_review.csv  right / wrong entity / wrong place / wrong name / should not exist, and whether the
                                    tier looks right, for a random sample of 100 places (gate G-PRECISION).
The samples are drawn once, with a fixed seed, and kept in data/golden/kind_sample.csv and data/review/precision_sample.csv, so
they do not move when the bundle is rebuilt. The server listens on 127.0.0.1 only and writes nothing else.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import random
import sys
import threading
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from atlas import golden as G
from atlas import kindrules as KR
from atlas import matching as M
from atlas.vocab import KIND_LABELS, KINDS

ROOT = Path(__file__).resolve().parents[2]
VERDICTS = ("right", "wrong entity", "wrong place", "wrong name", "should not exist")
TIER_VERDICTS = ("", "right", "too high", "too low")
KIND_LABEL_FIELDS = ["golden_id", "expected_name", "country", "place_id", "kinds", "annotator", "reason", "qid"]
VERDICT_FIELDS = ["place_id", "qid", "name", "verdict", "tier_verdict", "note", "reviewed_utc"]
PER_KIND, BLANK_SAMPLE, PRECISION_SAMPLE, SEED = 20, 20, 100, 20261009


def load_places(bundle: Path) -> list[dict]:
    out: list[dict] = []
    for f in sorted((bundle / "places").glob("*.json")):
        out += json.loads(f.read_text(encoding="utf-8"))["places"]
    return out


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def draw_samples(places: list[dict], seed: int = SEED, per_kind: int = PER_KIND, blank: int = BLANK_SAMPLE,
                 precision: int = PRECISION_SAMPLE) -> tuple[list[dict], list[dict]]:
    """(kind sample, precision sample): stratified by predicted kind plus places without one; a plain random draw for precision."""
    rng = random.Random(seed)
    ordered = sorted(places, key=lambda p: p["qid"])
    taken: set[str] = set()
    kind_rows: list[dict] = []
    for kind in KINDS:
        pool = [p for p in ordered if kind in {k["kind"] for k in p.get("kinds", [])} and p["qid"] not in taken]
        rng.shuffle(pool)
        for p in pool[:per_kind]:
            taken.add(p["qid"])
            kind_rows.append({"qid": p["qid"], "place_id": p["place_id"], "stratum": kind})
    pool = [p for p in ordered if not p.get("kinds") and p["qid"] not in taken]
    rng.shuffle(pool)
    kind_rows += [{"qid": p["qid"], "place_id": p["place_id"], "stratum": "no kind"} for p in pool[:blank]]
    rng = random.Random(seed + 1)
    pool = list(ordered)
    rng.shuffle(pool)
    prec_rows = [{"qid": p["qid"], "place_id": p["place_id"], "stratum": p["tier"]} for p in pool[:precision]]
    return kind_rows, prec_rows


class Store:
    """The bundle, the samples and the label files, behind one lock."""

    def __init__(self, bundle: Path, labels: Path, verdicts: Path, kind_sample: Path, prec_sample: Path, golden: Path | None = None):
        self.bundle, self.labels_path, self.verdicts_path = bundle, labels, verdicts
        self.kind_sample_path, self.prec_sample_path = kind_sample, prec_sample
        self.lock = threading.Lock()
        self.places = load_places(bundle)
        self.by_id = {p["place_id"]: p for p in self.places}
        self.manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8")) if (bundle / "manifest.json").is_file() else {}
        self.absorbed = read_csv(bundle / "absorbed.csv")
        self.context = read_csv(bundle / "context.csv")
        self.children: dict[str, list[dict]] = {}
        for r in self.absorbed:
            self.children.setdefault(r["parent"], []).append(r)
        self.golden: dict[str, dict] = {}
        if golden and golden.is_file():
            rows = G.load(golden)
            for gid, p in M.assign(rows, self.places).matched.items():
                r = next(x for x in rows if x.golden_id == gid)
                self.golden[p["place_id"]] = {"id": gid, "name": r.name, "kinds": list(r.kinds), "min_tier": r.min_tier, "max_tier": r.max_tier}
        if not kind_sample.is_file() or not prec_sample.is_file():
            k, p = draw_samples(self.places)
            write_csv(kind_sample, ["qid", "place_id", "stratum"], k)
            write_csv(prec_sample, ["qid", "place_id", "stratum"], p)
        self.kind_sample = {r["qid"]: r["stratum"] for r in read_csv(kind_sample)}
        self.prec_sample = {r["qid"]: r["stratum"] for r in read_csv(prec_sample)}
        self.labels = {r["qid"] or r["place_id"]: r for r in read_csv(labels)}
        self.verdicts = {r["qid"] or r["place_id"]: r for r in read_csv(verdicts)}

    # -- reads
    def meta(self) -> dict:
        n = len(self.places)
        return {"build_id": self.manifest.get("build_id", ""), "places": n, "kinds": [{"slug": k, "label": KIND_LABELS[k]} for k in KINDS],
                "tiers": ["Icon", "Major", "Notable", "Local"], "verdicts": list(VERDICTS), "tier_verdicts": list(TIER_VERDICTS),
                "countries": sorted({p["iso3"] for p in self.places}), "types": sorted({p["type"] for p in self.places}),
                "kind_sample": len(self.kind_sample), "precision_sample": len(self.prec_sample),
                "labelled": len(self.labels), "reviewed": len(self.verdicts),
                "missing": self.manifest.get("missing", []), "blank": sum(1 for p in self.places if not p.get("kinds")),
                "rules": {rid: {"kind": r["kind"], "test": r["test"], "strength": r["strength"], "role": r["role"]} for rid, r in KR.load_rules().items()}}

    def compact(self) -> list[dict]:
        rank = {"Icon": 0, "Major": 1, "Notable": 2, "Local": 3}
        rows = []
        for p in sorted(self.places, key=lambda p: (rank[p["tier"]], -p.get("sitelinks", 0), p["name_en"])):
            q = p["qid"]
            rows.append({"i": p["place_id"], "q": q, "n": p["name_en"], "c": p["iso3"], "t": p["type"], "r": p["tier"],
                         "k": [k["kind"] for k in p.get("kinds", [])], "s": p.get("sitelinks", 0),
                         "l": int(q in self.labels), "v": int(q in self.verdicts), "m": int(q in self.kind_sample),
                         "p": int(q in self.prec_sample), "o": int(hashlib.sha1(q.encode()).hexdigest()[:6], 16), "g": self.golden.get(p["place_id"], {}).get("id", ""),
                         "a": len(self.children.get(q, []))})
        return rows

    def place(self, place_id: str) -> dict | None:
        p = self.by_id.get(place_id)
        if p is None:
            return None
        q = p["qid"]
        return {"place": p, "golden": self.golden.get(place_id), "children": self.children.get(q, []),
                "label": self.labels.get(q), "verdict": self.verdicts.get(q), "kind_stratum": self.kind_sample.get(q),
                "precision_stratum": self.prec_sample.get(q)}

    def leftout(self) -> dict:
        return {"context": self.context, "absorbed": self.absorbed}

    # -- writes
    def save_label(self, body: dict) -> dict:
        p = self.by_id.get(body.get("place_id", ""))
        kinds = body.get("kinds")
        if p is None or not isinstance(kinds, list) or not all(k in KINDS for k in kinds) or len(set(kinds)) != len(kinds) or len(kinds) > 3:
            raise ValueError("a known place and 0 to 3 distinct kinds are required")
        g = self.golden.get(p["place_id"], {})
        row = {"golden_id": g.get("id", ""), "expected_name": p["name_en"], "country": p["iso3"], "place_id": p["place_id"],
               "kinds": "|".join(kinds), "annotator": "owner", "reason": str(body.get("reason", ""))[:500], "qid": p["qid"]}
        with self.lock:
            self.labels[p["qid"]] = row
            write_csv(self.labels_path, KIND_LABEL_FIELDS, list(self.labels.values()))
        return {"saved": True, "predicted": [k["kind"] for k in p.get("kinds", [])]}

    def save_verdict(self, body: dict) -> dict:
        p = self.by_id.get(body.get("place_id", ""))
        if p is None or body.get("verdict") not in VERDICTS or body.get("tier_verdict", "") not in TIER_VERDICTS:
            raise ValueError("a known place, a verdict and a tier verdict from the lists are required")
        row = {"place_id": p["place_id"], "qid": p["qid"], "name": p["name_en"], "verdict": body["verdict"],
               "tier_verdict": body.get("tier_verdict", ""), "note": str(body.get("note", ""))[:500],
               "reviewed_utc": datetime.now(UTC).isoformat(timespec="seconds")}
        with self.lock:
            self.verdicts[p["qid"]] = row
            write_csv(self.verdicts_path, VERDICT_FIELDS, list(self.verdicts.values()))
        return {"saved": True}


def make_handler(store: Store, html: bytes):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):                       # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/":
                self._send(200, html, "text/html; charset=utf-8")
            elif u.path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
            elif u.path == "/api/meta":
                self._json(store.meta())
            elif u.path == "/api/places":
                self._json(store.compact())
            elif u.path == "/api/place":
                r = store.place(q.get("id", [""])[0])
                self._json(r, 200) if r else self._json({"error": "unknown place"}, 404)
            elif u.path == "/api/leftout":
                self._json(store.leftout())
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 20_000:
                return self._json({"error": "too large"}, 413)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
                if self.path == "/api/label":
                    return self._json(store.save_label(body))
                if self.path == "/api/verdict":
                    return self._json(store.save_verdict(body))
            except (ValueError, KeyError) as e:
                return self._json({"error": str(e)}, 400)
            self._json({"error": "not found"}, 404)

    return Handler


def serve(store: Store, port: int, open_browser: bool = True) -> ThreadingHTTPServer:
    html = (Path(__file__).parent / "viewer.html").read_bytes()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store, html))
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    return server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", type=Path, default=ROOT / "build" / "first")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    if not (a.bundle / "places").is_dir():
        print(f"no bundle at {a.bundle}: run `make admit` first", file=sys.stderr)
        return 1
    store = Store(a.bundle, ROOT / "data" / "golden" / "kind_labels.csv", ROOT / "data" / "review" / "precision_review.csv",
                  ROOT / "data" / "golden" / "kind_sample.csv", ROOT / "data" / "review" / "precision_sample.csv",
                  ROOT / "data" / "golden" / "golden.csv")
    server = serve(store, a.port, not a.no_browser)
    print(f"viewer on http://127.0.0.1:{a.port}  ({len(store.places)} places; Ctrl+C to stop)")
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
