"""Try the tile subdivision on real borders and the golden places.

Needs shapely and matplotlib (not dependencies of the pipeline yet):
    pip install shapely matplotlib
    PYTHONPATH=pipeline python3 pipeline/scripts/tiles_demo.py COUNTRIES.geojson OUT.png [ISO3 ...]

COUNTRIES.geojson: any GeoJSON of country borders with an `iso3` property (the v1 file works).
This is an exploration: it clips each rectangle to the country and reports what the stop
rule produces; it is not the M4 builder.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import box, shape
from shapely.ops import polylabel, transform

from atlas.tiles import TileParams, partition, project_mm

ROOT = Path(__file__).resolve().parents[2]


def country_geom(path: str, iso3: str):
    for f in json.load(open(path, encoding="utf-8"))["features"]:
        if f["properties"].get("iso3") == iso3:
            g = shape(f["geometry"])
            return transform(lambda xs, ys, zs=None: tuple(zip(*(project_mm(y, x) for x, y in zip(xs, ys, strict=True)), strict=True)), g)
    raise KeyError(iso3)


def golden_points(iso3: str):
    with open(ROOT / "data" / "golden" / "golden.csv", encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["iso3"] == iso3 and r["row_kind"] == "positive"]
    return [(r["golden_id"], *project_mm(float(r["lat"]), float(r["lon"]))) for r in rows]


def pieces(geom):
    return list(geom.geoms) if hasattr(geom, "geoms") else [geom]


def run(path: str, iso3: str, params: TileParams, by_landmass: bool = True):
    """Partition one country. With `by_landmass`, each separate landmass is tiled on its own,
    so a tile is always one connected piece; landmasses with no place get no tile."""
    from shapely.geometry import Point

    land = country_geom(path, iso3)
    pts = golden_points(iso3)
    regions = [p for p in pieces(land) if p.area >= 4.0] if by_landmass else [land]
    owned = {i: [] for i in range(len(regions))}
    for q in pts:                                    # a place belongs to the nearest landmass
        pt = Point(q[1], q[2])
        owned[min(range(len(regions)), key=lambda i: regions[i].distance(pt))].append(q)
    tiles = []
    for i, region in enumerate(regions):
        if not owned[i]:
            continue
        for lf in partition(owned[i], region.bounds, params):
            clipped = region.intersection(box(*lf.bbox))
            parts = [p for p in pieces(clipped) if p.area > 1.0]
            diam = max((2 * polylabel(p, tolerance=0.1).distance(p.exterior) for p in parts if p.geom_type == "Polygon"), default=0)
            tiles.append({"leaf": lf, "geom": clipped, "parts": len(parts), "diam": diam})
    return land, pts, tiles


def summary(tiles):
    d = [t["diam"] for t in tiles]
    return {"tiles": len(tiles), "disconnected": sum(1 for t in tiles if t["parts"] > 1),
            "unsplit": sum(1 for t in tiles if t["leaf"].stop != "small_enough"),
            "min_diam_mm": round(min(d), 1), "median_diam_mm": round(statistics.median(d), 1),
            "under_12mm": sum(1 for x in d if x < 12.0)}


def main() -> int:
    path, out, isos = sys.argv[1], sys.argv[2], sys.argv[3:] or ["ITA", "EGY", "PER"]
    base = TileParams(balance_slack=2)
    fig, axes = plt.subplots(1, len(isos), figsize=(6 * len(isos), 7))
    for ax, iso in zip(axes if len(isos) > 1 else [axes], isos, strict=True):
        land, pts, tiles = run(path, iso, base)
        cmap = plt.get_cmap("Pastel1")
        for i, t in enumerate(tiles):
            for p in pieces(t["geom"]):
                if p.geom_type == "Polygon" and p.area > 1:
                    xs, ys = p.exterior.xy
                    ax.fill(xs, ys, color=cmap(i % 9), ec="#444", lw=1.2)
            c = t["geom"].representative_point()
            ax.text(c.x, c.y, str(len(t["leaf"].ids)), ha="center", va="center", fontsize=9, color="#222", weight="bold")
        ax.scatter([p[1] for p in pts], [p[2] for p in pts], s=10, c="#b3261e", zorder=5)
        ax.set_aspect("equal")
        s = summary(tiles)
        ax.set_title(f"{iso}: {len(pts)} places, {s['tiles']} tiles\nnumbers = holes per tile; red = places (mm on the wall)", fontsize=10)
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print("rendered", out)
    print(f"{'country':8s} {'max':>3s} {'margin':>6s} {'slack':>6s} | tiles disc unsplit  min/median inscribed mm  <12mm")
    print("\nvariants: landmass-first on; slack = places a cut may be off an even split")
    for iso in isos:
        for mp, mg, sl in [(6, 3.0, 0), (6, 3.0, 1), (6, 3.0, 2), (6, 2.0, 2), (8, 3.0, 2)]:
            _, _, tiles = run(path, iso, TileParams(max_places=mp, edge_margin_mm=mg, balance_slack=sl))
            s_ = summary(tiles)
            print(f"{iso:8s} {mp:3d} {mg:6.1f} {sl:6d} | {s_['tiles']:5d} {s_['disconnected']:4d} {s_['unsplit']:7d}  {s_['min_diam_mm']:6.1f} / {s_['median_diam_mm']:6.1f}      {s_['under_12mm']:3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
