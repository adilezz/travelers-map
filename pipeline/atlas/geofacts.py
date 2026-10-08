"""Geometry facts for the kind rules: relief, land cover and distance to the sea (document 1 section 7.2).

    python -m atlas.geofacts run     [--bundle build/first]    # sample the rasters, resumable, about 20 minutes
    python -m atlas.geofacts parquet                           # write and pin data/raw/geofacts/<snapshot>/geofacts.parquet
    python -m atlas.geofacts selftest                          # one place, to see that the sources answer

Three open sources, all public and keyless:
  * relief: Mapzen/AWS Terrain Tiles (Terrarium PNG, zoom 10, about 110 m a pixel; built from SRTM, Copernicus and others);
  * land cover: ESA WorldCover 2021 v200 (10 m, CC BY 4.0), read as small decimated windows from the cloud-optimised GeoTIFFs;
  * the sea: Natural Earth 10 m coastline (public domain).
The facts are numbers about a circle around the place's pin, never about its name. They need numpy, pillow,
rasterio, shapely and pyshp (`pip install numpy pillow rasterio shapely pyshp`); the rest of the pipeline does not.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERRAIN = "https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png"
WORLDCOVER = ("/vsicurl/https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
              "ESA_WorldCover_10m_2021_v200_{ns}{lat:02d}{ew}{lon:03d}_Map.tif")
COASTLINE = "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_coastline.zip"
ZOOM = 10
USER_AGENT = "TravelersMap/2.0 (personal research project; github.com/adilezz/travelers-map)"
WC = {10: "tree", 20: "shrub", 30: "grass", 40: "crop", 50: "built", 60: "bare", 70: "snow", 80: "water", 90: "wetland", 95: "mangrove", 100: "moss"}


# ------------------------------------------------------------------ relief
def tile_fraction(lat: float, lon: float, z: int = ZOOM) -> tuple[float, float]:
    """Web-Mercator tile coordinates (fractional) of a point."""
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def metres_per_pixel(lat: float, z: int = ZOOM) -> float:
    return 156543.03392 * math.cos(math.radians(lat)) / 2 ** z


def decode_terrarium(png: bytes):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype="float32")
    return a[..., 0] * 256.0 + a[..., 1] + a[..., 2] / 256.0 - 32768.0


def circle_mask(shape: tuple[int, int], cy: float, cx: float, radius_px: float):
    import numpy as np
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= radius_px ** 2


def relief_facts(lat: float, lon: float, get_tile, radii_km: tuple[float, float] = (10.0, 2.0)) -> dict:
    """`get_tile(z, x, y)` returns a 256 x 256 array of metres. Gives the relief (max - min) within 10 km and the highest
    point within 2 km."""
    import numpy as np
    z = ZOOM
    mpp = metres_per_pixel(lat, z)
    px, py = tile_fraction(lat, lon, z)
    rbig = radii_km[0] * 1000.0 / mpp
    x0, x1 = int(math.floor(px - rbig / 256.0)), int(math.floor(px + rbig / 256.0))
    y0, y1 = int(math.floor(py - rbig / 256.0)), int(math.floor(py + rbig / 256.0))
    rows = [np.concatenate([get_tile(z, x, y) for x in range(x0, x1 + 1)], axis=1) for y in range(y0, y1 + 1)]
    mosaic = np.concatenate(rows, axis=0)
    cx, cy = (px - x0) * 256.0, (py - y0) * 256.0
    out = {}
    big = mosaic[circle_mask(mosaic.shape, cy, cx, rbig)]
    small = mosaic[circle_mask(mosaic.shape, cy, cx, radii_km[1] * 1000.0 / mpp)]
    out["relief_10km"] = round(float(big.max() - big.min()), 1)
    out["max_elev_2km"] = round(float(small.max()), 1)
    out["elev_centre"] = round(float(mosaic[int(round(cy)), int(round(cx))]), 1)
    return out


# ------------------------------------------------------------------ land cover
def cover_shares(window, radius_km: float, lat: float, pixel_km: float) -> dict:
    """Shares of each WorldCover class inside the circle (pixels with no data are left out)."""
    import numpy as np
    h, w = window.shape
    mask = circle_mask(window.shape, (h - 1) / 2.0, (w - 1) / 2.0, radius_km / pixel_km)
    vals = window[mask]
    vals = vals[vals > 0]
    if vals.size == 0:
        return {}
    counts = {name: float(np.count_nonzero(vals == code)) / vals.size for code, name in WC.items()}
    return {k: round(v, 4) for k, v in counts.items()}


def cover_facts(lat: float, lon: float, read_window) -> dict:
    """`read_window(lat, lon, radius_km, pixel_km)` returns a 2-d uint8 array centred on the point.
    Tree, crop and grass within 10 km; bare ground within 20 km; built-up within 10 km."""
    near = cover_shares(read_window(lat, lon, 10.0, 0.15), 10.0, lat, 0.15)
    far = cover_shares(read_window(lat, lon, 20.0, 0.30), 20.0, lat, 0.30)
    out = {}
    if near:
        out.update(tree_10km=near["tree"], crop_10km=near["crop"], grass_10km=near["grass"], built_10km=near["built"],
                   water_10km=near["water"], wetland_10km=near["wetland"])
    if far:
        out.update(bare_20km=far["bare"], tree_20km=far["tree"])
    return out


class WorldCoverReader:
    """Reads small decimated windows around a point from the cloud-optimised GeoTIFFs, one dataset per thread and tile."""

    def __init__(self):
        self.local = threading.local()

    def _dataset(self, lat: float, lon: float):
        import rasterio
        la, lo = int(math.floor(lat / 3.0)) * 3, int(math.floor(lon / 3.0)) * 3
        cache = self.local.__dict__.setdefault("ds", {})
        key = (la, lo)
        if key not in cache:
            url = WORLDCOVER.format(ns="N" if la >= 0 else "S", lat=abs(la), ew="E" if lo >= 0 else "W", lon=abs(lo))
            try:
                cache[key] = rasterio.open(url)
            except Exception:                                    # ocean-only tiles do not exist
                cache[key] = None
        return cache[key]

    def __call__(self, lat: float, lon: float, radius_km: float, pixel_km: float):
        import numpy as np
        from rasterio.windows import Window
        ds = self._dataset(lat, lon)
        n = max(8, int(math.ceil(2.0 * radius_km / pixel_km)))
        if ds is None:
            return np.zeros((n, n), dtype="uint8")
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * max(0.05, math.cos(math.radians(lat))))
        w = ds.window(lon - dlon, lat - dlat, lon + dlon, lat + dlat)
        return ds.read(1, window=Window(w.col_off, w.row_off, w.width, w.height), out_shape=(n, n), boundless=True, fill_value=0)


# ------------------------------------------------------------------ the sea
class Coast:
    def __init__(self, cache: Path):
        import shapefile
        from shapely.geometry import LineString
        from shapely.strtree import STRtree
        cache.mkdir(parents=True, exist_ok=True)
        zip_path = cache / "ne_10m_coastline.zip"
        if not zip_path.is_file():
            req = urllib.request.Request(COASTLINE, headers={"User-Agent": USER_AGENT})
            zip_path.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        with zipfile.ZipFile(zip_path) as z:
            reader = shapefile.Reader(shp=io.BytesIO(z.read("ne_10m_coastline.shp")), dbf=io.BytesIO(z.read("ne_10m_coastline.dbf")))
            self.lines = []
            for shp in reader.shapes():
                parts = list(shp.parts) + [len(shp.points)]
                for a, b in zip(parts, parts[1:], strict=False):
                    if b - a >= 2:
                        self.lines.append(LineString(shp.points[a:b]))
        self.tree = STRtree(self.lines)

    def distance_km(self, lat: float, lon: float) -> float:
        from shapely.geometry import Point
        from shapely.ops import nearest_points
        p = Point(lon, lat)
        i = self.tree.nearest(p)
        q = nearest_points(p, self.lines[int(i)])[1]
        return round(haversine(lat, lon, q.y, q.x), 2)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


# ------------------------------------------------------------------ the run
class TileCache:
    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.mem: dict[tuple, object] = {}
        self.lock = threading.Lock()

    def __call__(self, z: int, x: int, y: int):
        import numpy as np
        key = (z, x, y)
        with self.lock:
            if key in self.mem:
                return self.mem[key]
        path = self.folder / f"{z}_{x}_{y}.png"
        if not path.is_file():
            req = urllib.request.Request(TERRAIN.format(z=z, x=x % (2 ** z), y=y), headers={"User-Agent": USER_AGENT})
            for attempt in range(4):
                try:
                    path.write_bytes(urllib.request.urlopen(req, timeout=60).read())
                    break
                except Exception:
                    if attempt == 3:
                        return np.zeros((256, 256), dtype="float32")
                    time.sleep(2 * (attempt + 1))
        arr = decode_terrarium(path.read_bytes())
        with self.lock:
            if len(self.mem) < 400:
                self.mem[key] = arr
        return arr


def facts_for(place: dict, tiles, reader, coast) -> dict:
    lat, lon = place["lat"], place["lon"]
    out = {"qid": place["qid"], "lat": lat, "lon": lon}
    out.update(relief_facts(lat, lon, tiles))
    out.update(cover_facts(lat, lon, reader))
    out["coast_km"] = coast.distance_km(lat, lon)
    return out


def load_places(bundle: Path) -> list[dict]:
    return [p for f in sorted((bundle / "places").glob("*.json")) for p in json.loads(f.read_text(encoding="utf-8"))["places"]]


def run(bundle: Path, out: Path, cache: Path, workers: int = 8, log=print) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "geofacts.jsonl"
    done: set[str] = set()
    if path.is_file():
        done = {json.loads(line)["qid"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    todo = [p for p in load_places(bundle) if p["qid"] not in done]
    tiles, reader, coast = TileCache(cache / "terrain"), WorldCoverReader(), Coast(cache)
    failed: list[str] = []
    lock = threading.Lock()
    count = [0]

    def work(p: dict):
        try:
            row = facts_for(p, tiles, reader, coast)
        except Exception as e:                                   # one place must not stop the run
            with lock:
                failed.append(p["qid"])
                log(f"{p['qid']} {p.get('name_en')}: {type(e).__name__}: {str(e)[:80]}")
            return
        with lock:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            count[0] += 1
            if count[0] % 100 == 0:
                fh.flush()
                log(f"{count[0]}/{len(todo)}")

    with open(path, "a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    return {"places": len(todo) + len(done), "already": len(done), "fetched": len(todo) - len(failed), "failed": failed}


def to_parquet(out: Path) -> int:
    import duckdb
    src, dest = out / "geofacts.jsonl", out / "geofacts.parquet"
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM read_json_auto('{src.as_posix()}', sample_size=-1) ORDER BY qid) TO '{dest.as_posix()}' (FORMAT PARQUET)")
    return con.execute(f"SELECT count(*) FROM read_parquet('{dest.as_posix()}')").fetchone()[0]


def load(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    import duckdb
    con = duckdb.connect()
    cur = con.execute(f"SELECT * FROM read_parquet('{path.as_posix()}')")
    names = [d[0] for d in cur.description]
    rows = [{k: v for k, v in zip(names, r, strict=True) if v is not None} for r in cur.fetchall()]
    return {r["qid"]: r for r in rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "parquet", "pin", "selftest"])
    ap.add_argument("--bundle", type=Path, default=ROOT / "build" / "first")
    ap.add_argument("--snapshot", default=sorted((ROOT / "data" / "raw" / "wikidata").glob("*"))[-1].name)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    out = ROOT / "data" / "raw" / "geofacts" / a.snapshot
    cache = ROOT / "build" / "geo"
    if a.cmd == "selftest":
        p = {"qid": "Q0", "lat": 29.9792, "lon": 31.1342, "name_en": "Giza"}
        t = time.time()
        print(facts_for(p, TileCache(cache / "terrain"), WorldCoverReader(), Coast(cache)), f"{time.time() - t:.1f} s")
        return 0
    if a.cmd == "run":
        res = run(a.bundle, out, cache, a.workers)
        print(res["places"], "places,", res["already"], "already done,", res["fetched"], "fetched,", len(res["failed"]), "failed")
        return 1 if res["failed"] else 0
    if a.cmd == "parquet":
        print(to_parquet(out), "rows")
        return 0
    from atlas import snapshot
    snapshot.pin("geofacts", out / "geofacts.parquet", ROOT / "data" / "raw", a.snapshot)
    print("pinned geofacts.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
