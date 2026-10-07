"""S3b: reduce the owner-downloaded WDPA tables to the three facts rule R1 needs.

The WDPA download (protectedplanet.net, terms accepted by the owner) is several GB of polygons and is restricted;
only a small table is kept: WDPA id, IUCN management category, reported area. The December 2026 files use SITE_ID and PRNT_ISO3 (older ones WDPAID, ISO3); both are read. Usage:
    python -m atlas.wdpa reduce <WDPA_*_csv.csv ...> --out data/raw/wdpa/wdpa_reduced.csv
The CSV files of the download (one per part) already carry the attribute columns, so no GIS software is needed.
"""
import argparse
import csv
from pathlib import Path

from atlas.extract import COUNTRIES

STRICT = {"Ia", "Ib", "II"}


def reduce_files(paths: list[Path], isos: set[str]) -> list[dict]:
    rows: dict[str, dict] = {}
    for p in paths:
        with open(p, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                iso = r.get("PRNT_ISO3") or r.get("PARENT_ISO3") or r.get("ISO3") or ""
                if not isos.intersection(iso.split(";")) or (r.get("STATUS") or "Designated") != "Designated":
                    continue
                area = r.get("GIS_AREA") or r.get("REP_AREA") or "0"
                wid = r.get("SITE_ID") or r["WDPAID"]
                rows[wid] = {"wdpaid": wid, "iucn_cat": r.get("IUCN_CAT", ""), "area_km2": float(area or 0)}
    return sorted(rows.values(), key=lambda r: int(r["wdpaid"]))


def load(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["wdpaid"]: {"iucn_cat": r["iucn_cat"], "area_km2": float(r["area_km2"])} for r in csv.DictReader(fh)}


def strict_and_large(entry: dict | None, min_km2: float) -> bool:
    return bool(entry) and entry["iucn_cat"] in STRICT and entry["area_km2"] >= min_km2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["reduce"])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/raw/wdpa/wdpa_reduced.csv"))
    a = ap.parse_args()
    rows = reduce_files(a.files, set(COUNTRIES))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["wdpaid", "iucn_cat", "area_km2"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} protected areas -> {a.out}")


if __name__ == "__main__":
    main()
