import random

from atlas.tiles import Leaf, TileParams, best_cut, partition, project_mm


def pts(coords):
    return [(f"p{i}", x, y) for i, (x, y) in enumerate(coords)]


BOX = (0.0, 0.0, 100.0, 100.0)


def test_projection_matches_the_printed_map_dimensions():
    x180, _ = project_mm(0, 180)
    x_180, _ = project_mm(0, -180)
    _, ytop = project_mm(90, 0)
    _, ybot = project_mm(-90, 0)
    assert round(x180 - x_180) == 3000 and round(ytop - ybot) == 1460      # 3.00 x 1.46 m (document 4 section 3)


def test_a_small_tile_is_not_split():
    leaves = partition(pts([(10, 10), (20, 20), (30, 30)]), BOX)
    assert len(leaves) == 1 and leaves[0].stop == "small_enough" and leaves[0].cuts == []


def test_cuts_fall_in_gaps_and_balance_the_count():
    cols = [(5 + i * 4, 50) for i in range(6)] + [(70 + i * 4, 50) for i in range(6)]    # two clusters
    leaves = partition(pts(cols), BOX, TileParams(max_places=6))
    assert len(leaves) == 2 and [len(x.ids) for x in leaves] == [6, 6]
    cut = leaves[0].cuts[0]
    assert cut[0] == "x" and 21 < cut[1] < 70                       # inside the empty gap, not on a place
    assert cut[1] == (25 + 70) / 2                                  # exactly midway between the neighbours


def test_every_place_lies_at_least_the_margin_from_every_cut_edge():
    rng = random.Random(3)
    cloud = pts([(rng.uniform(2, 98), rng.uniform(2, 98)) for _ in range(40)])
    p = TileParams(max_places=6, edge_margin_mm=2.0, min_extent_mm=5.0)
    xy = {c[0]: (c[1], c[2]) for c in cloud}
    for leaf in partition(cloud, BOX, p):
        x0, y0, x1, y1 = leaf.bbox
        for pid in leaf.ids:
            x, y = xy[pid]
            assert x0 <= x <= x1 and y0 <= y <= y1
            if x0 > BOX[0]:
                assert x - x0 >= p.edge_margin_mm - 1e-9
            if x1 < BOX[2]:
                assert x1 - x >= p.edge_margin_mm - 1e-9
            if y0 > BOX[1]:
                assert y - y0 >= p.edge_margin_mm - 1e-9
            if y1 < BOX[3]:
                assert y1 - y >= p.edge_margin_mm - 1e-9


def test_each_side_of_a_cut_keeps_the_minimum_number_of_places():
    rng = random.Random(9)
    cloud = pts([(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(60)])
    leaves = partition(cloud, BOX, TileParams(max_places=6, min_places=3, edge_margin_mm=0.5, min_extent_mm=2.0))
    assert all(len(x.ids) >= 3 for x in leaves) and sum(len(x.ids) for x in leaves) == 60


def test_tiles_never_get_smaller_than_the_minimum_extent():
    cloud = pts([(i * 3.0, 50 + (i % 2)) for i in range(30)])
    p = TileParams(max_places=4, min_extent_mm=12.0, edge_margin_mm=1.0)
    leaves = partition(cloud, (0, 0, 100, 100), p)
    assert len(leaves) > 1
    for leaf in leaves:
        assert leaf.bbox[2] - leaf.bbox[0] >= 12.0 - 1e-9 and leaf.bbox[3] - leaf.bbox[1] >= 12.0 - 1e-9


def test_a_dense_cluster_is_reported_not_forced():
    """Seven places all within 1 mm: no cut is possible. The tile is kept and says why."""
    leaves = partition(pts([(50 + i * 0.1, 50) for i in range(7)]), BOX, TileParams(max_places=6))
    assert len(leaves) == 1 and leaves[0].stop.startswith("cannot_split") and len(leaves[0].ids) == 7


def test_deterministic_and_independent_of_input_order():
    rng = random.Random(1)
    cloud = pts([(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(35)])
    p = TileParams(max_places=5, edge_margin_mm=1.0, min_extent_mm=4.0)
    base = [(sorted(x.ids), x.bbox) for x in partition(cloud, BOX, p)]
    for _ in range(10):
        shuffled = cloud[:]
        rng.shuffle(shuffled)
        assert [(sorted(x.ids), x.bbox) for x in partition(shuffled, BOX, p)] == base


def test_the_longer_side_is_cut_first_and_the_other_axis_is_tried_when_blocked():
    wide = pts([(i * 10.0, 50) for i in range(8)])                     # a row of places: only x can split
    leaves = partition(wide, (0, 0, 100, 40), TileParams(max_places=4, edge_margin_mm=2.0, min_extent_mm=5.0))
    assert len(leaves) == 2 and all(c[0] == "x" for x in leaves for c in x.cuts)
    best, why = best_cut(pts([(1, 1), (2, 2)]), BOX, "x", TileParams())
    assert best is None and why == "too_few_places"


def test_a_ceiling_on_tile_size_forces_a_split_only_when_it_can_be_done():
    p = TileParams(max_places=6, max_extent_mm=60.0, edge_margin_mm=2.0, min_extent_mm=5.0)
    cloud = pts([(10, 50), (12, 52), (14, 48), (80, 50), (82, 52), (84, 48)])
    leaves = partition(cloud, BOX, p)
    assert len(leaves) == 2 and all(isinstance(x, Leaf) for x in leaves)


def test_slack_lets_a_wider_gap_win_over_a_perfectly_even_split():
    # 8 places: an even split (4|4) falls in a 3 mm gap; a 5|3 split falls in a 20 mm gap
    xs = [10, 12, 14, 16, 19, 39, 41, 43]
    cloud = pts([(x, 50) for x in xs])
    p = TileParams(max_places=4, min_places=3, edge_margin_mm=1.0, min_extent_mm=4.0)
    even = partition(cloud, BOX, p)
    slack = partition(cloud, BOX, TileParams(max_places=5, min_places=3, edge_margin_mm=1.0, min_extent_mm=4.0, balance_slack=1))
    assert even[0].cuts[0][1] == 17.5 and slack[0].cuts[0][1] == 29.0
