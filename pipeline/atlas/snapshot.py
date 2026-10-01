"""Stage 0: pin raw inputs by hash and refuse to build from anything that changed
(document 2 section 2.1).

    python -m atlas.snapshot pin   <source_id> <file> [--snapshot 2026-10-01]
    python -m atlas.snapshot check [--root data/raw]

A source's manifest entry lists its pinned files. Raw files live outside git; only the
manifest (paths, sizes, hashes, snapshot dates) is committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "inputs" / "MANIFEST.json"


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def load(manifest_path: Path = MANIFEST) -> dict:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def pin(source_id: str, file: str | Path, root: Path, snapshot: str | None = None,
        manifest_path: Path = MANIFEST) -> dict:
    """Record a file under a source: path relative to `root`, size and SHA-256."""
    m = load(manifest_path)
    src = next((s for s in m["sources"] if s["source_id"] == source_id), None)
    if src is None:
        raise KeyError(f"unknown source {source_id!r}")
    file = Path(file).resolve()
    rel = file.relative_to(Path(root).resolve()).as_posix()
    entry = {"path": rel, "bytes": file.stat().st_size, "sha256": sha256_file(file)}
    files = [f for f in src.get("files", []) if f["path"] != rel] + [entry]
    src["files"] = sorted(files, key=lambda f: f["path"])
    src["snapshot"] = snapshot or src.get("snapshot") or date.today().isoformat()
    manifest_path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry


def check(root: Path, manifest_path: Path = MANIFEST, required: set[str] | None = None) -> list[str]:
    """Problems with the pinned inputs; empty means every pinned file is present and unchanged.

    `required` names the sources the build uses: each must be pinned (a null hash is a
    failure, not a pass). Sources outside `required` are checked only if they have files.
    """
    problems: list[str] = []
    m = load(manifest_path)
    seen = set()
    for src in m["sources"]:
        sid = src["source_id"]
        seen.add(sid)
        files = src.get("files") or []
        if required and sid in required and not files:
            problems.append(f"{sid}: required but not pinned")
        if required and sid in required and not src.get("snapshot"):
            problems.append(f"{sid}: pinned without a snapshot date")
        for f in files:
            p = Path(root) / f["path"]
            if not p.is_file():
                problems.append(f"{sid}: {f['path']} is missing")
            elif p.stat().st_size != f["bytes"]:
                problems.append(f"{sid}: {f['path']} changed size")
            elif sha256_file(p) != f["sha256"]:
                problems.append(f"{sid}: {f['path']} hash differs from the pinned one")
    if required:
        problems += [f"{r}: not a source in the manifest" for r in sorted(required - seen)]
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("pin")
    p1.add_argument("source_id")
    p1.add_argument("file", type=Path)
    p1.add_argument("--root", type=Path, default=ROOT / "data" / "raw")
    p1.add_argument("--snapshot")
    p2 = sub.add_parser("check")
    p2.add_argument("--root", type=Path, default=ROOT / "data" / "raw")
    p2.add_argument("--require", nargs="*", default=[])
    a = ap.parse_args(argv)
    if a.cmd == "pin":
        e = pin(a.source_id, a.file, a.root, a.snapshot)
        print(f"pinned {e['path']} ({e['bytes']} bytes) sha256 {e['sha256'][:12]}…")
        return 0
    problems = check(a.root, required=set(a.require) or None)
    for p in problems:
        print("FAIL", p)
    print("inputs ok" if not problems else f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
