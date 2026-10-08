from types import SimpleNamespace as NS

from atlas import tiercal as T


def row(gid, name, min_tier, max_tier="", kind="positive", relation="", targets=()):
    return NS(golden_id=gid, name=name, row_kind=kind, min_tier=min_tier, max_tier=max_tier, relation=relation, targets=tuple(targets))


def test_violations_count_min_max_and_not_above():
    rows = [row("G1", "Paris", "Icon"), row("G2", "Metz", "Notable", "Notable"), row("N1", "Metz2", "", kind="negative",
                                                                                      relation="not_above", targets=["G1"])]
    T.NEG["N1"] = ["Q2"]
    matched = {"G1": "Q1", "G2": "Q2"}
    assert T.violations(rows, matched, {"Q1": "Icon", "Q2": "Notable"}) == []
    bad = T.violations(rows, matched, {"Q1": "Major", "Q2": "Major"})
    assert len(bad) == 3 and any("needs Icon" in b for b in bad) and any("max Notable" in b for b in bad)
    T.NEG.clear()
