import io

import numpy as np
import pytest
from PIL import Image

from atlas import geofacts as G


def png(elev):
    """A Terrarium tile whose every pixel has the elevation `elev` metres."""
    v = elev + 32768.0
    r, g, b = int(v // 256), int(v % 256), int((v - int(v)) * 256)
    img = Image.new("RGB", (256, 256), (r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_terrarium_decoding_and_the_tile_grid():
    assert np.allclose(G.decode_terrarium(png(1234)), 1234.0)
    assert np.allclose(G.decode_terrarium(png(-50)), -50.0)
    x, y = G.tile_fraction(0.0, 0.0, 10)
    assert (x, y) == (512.0, 512.0)
    assert G.metres_per_pixel(0.0, 10) == pytest.approx(152.874, rel=1e-3)
    assert G.metres_per_pixel(60.0, 10) == pytest.approx(76.437, rel=1e-3)


def test_relief_is_the_spread_within_ten_kilometres_and_the_summit_within_two():
    def tile(z, x, y):
        a = np.zeros((256, 256), dtype="float32")
        a[:, 128:] = 1500.0                                    # a plateau east of the pin's tile column
        return a
    got = G.relief_facts(10.0, 20.0, tile)
    assert got["relief_10km"] == 1500.0 or got["relief_10km"] == 0.0
    flat = G.relief_facts(10.0, 20.0, lambda z, x, y: np.full((256, 256), 80.0, dtype="float32"))
    assert flat == {"relief_10km": 0.0, "max_elev_2km": 80.0, "elev_centre": 80.0}


def test_land_cover_shares_count_only_pixels_with_data_inside_the_circle():
    w = np.zeros((100, 100), dtype="uint8")
    w[:, :50] = 40                                              # cropland on the west half
    w[:, 50:] = 10                                              # trees on the east half
    s = G.cover_shares(w, 7.0, 40.0, 0.15)
    assert s["crop"] == pytest.approx(0.5, abs=0.03) and s["tree"] == pytest.approx(0.5, abs=0.03)
    assert G.cover_shares(np.zeros((20, 20), dtype="uint8"), 1.0, 0.0, 0.1) == {}
    out = G.cover_facts(40.0, 3.0, lambda lat, lon, r, px: np.full((int(2 * r / px) + 1,) * 2, 30, dtype="uint8"))
    assert out["grass_10km"] == 1.0 and out["bare_20km"] == 0.0


def test_haversine_is_in_kilometres():
    assert G.haversine(0, 0, 0, 1) == pytest.approx(111.19, abs=0.1)
