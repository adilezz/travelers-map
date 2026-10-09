import json
import threading
import urllib.error
import urllib.request

import pytest

from atlas import viewer as V


def place(i, name, tier="Notable", kinds=("mountain",), iso="ITA", typ="settlement"):
    return {"place_id": f"pl_{i:010d}", "qid": f"Q{i}", "name_en": name, "iso3": iso, "type": typ, "tier": tier, "tier_reason": "x",
            "lat": 1.0, "lon": 2.0, "keys": [f"qid:Q{i}"], "aliases": [], "rules": ["R2"], "sitelinks": 50 - i % 40,
            "evidence": [{"asset_id": f"wd:Q{i}", "source": "wikidata", "url": "https://www.wikidata.org/wiki/Q1", "retrieved": "2026-10-05"}],
            "kinds": [{"kind": k, "rule": "R14", "strength": 0.8, "evidence": [f"wd:Q{i}"]} for k in kinds]}


@pytest.fixture()
def store(tmp_path):
    b = tmp_path / "bundle"
    (b / "places").mkdir(parents=True)
    ks = ["mountain", "seaside", "ruins", "sacred"]
    ps = [place(i, f"Place {i}", kinds=(ks[i % 4],) if i % 7 else ()) for i in range(1, 200)]
    (b / "places" / "ITA.json").write_text(json.dumps({"iso3": "ITA", "places": ps}))
    (b / "manifest.json").write_text(json.dumps({"build_id": "t"}))
    (b / "absorbed.csv").write_text("child,child_name,parent,parent_name,reason\nQ5,Place 5,Q1,Place 1,located in or part of Q1\n")
    return V.Store(b, tmp_path / "labels.csv", tmp_path / "verdicts.csv", tmp_path / "ks.csv", tmp_path / "ps.csv")


def test_samples_are_stratified_seeded_and_frozen(store, tmp_path):
    k, p = V.draw_samples(store.places, per_kind=5, blank=3, precision=10)
    k2, p2 = V.draw_samples(store.places, per_kind=5, blank=3, precision=10)
    assert k == k2 and p == p2                                                 # the same seed gives the same sample
    strata = {r["stratum"] for r in k}
    assert {"mountain", "seaside", "ruins", "sacred", "no kind"} <= strata and len({r["qid"] for r in k}) == len(k)
    first = (tmp_path / "ks.csv").read_text()
    again = V.Store(store.bundle, tmp_path / "labels.csv", tmp_path / "verdicts.csv", tmp_path / "ks.csv", tmp_path / "ps.csv")
    assert (tmp_path / "ks.csv").read_text() == first and again.kind_sample == store.kind_sample    # kept, not redrawn


def test_labels_and_verdicts_are_validated_and_saved_as_csv(store, tmp_path):
    pid = store.places[0]["place_id"]
    r = store.save_label({"place_id": pid, "kinds": ["ruins", "sacred"], "reason": "a temple"})
    assert r["saved"] and r["predicted"]
    row = V.read_csv(tmp_path / "labels.csv")[0]
    assert row["kinds"] == "ruins|sacred" and row["annotator"] == "owner" and row["place_id"] == pid and row["qid"] == store.places[0]["qid"]
    for bad in ({"place_id": pid, "kinds": ["ruins", "ruins"]}, {"place_id": pid, "kinds": ["a", "b"]}, {"place_id": pid, "kinds": list(V.KINDS[:4])},
                {"place_id": "nope", "kinds": []}):
        with pytest.raises(ValueError):
            store.save_label(bad)
    store.save_label({"place_id": pid, "kinds": []})                            # "no kind" is an answer
    assert len(V.read_csv(tmp_path / "labels.csv")) == 1                       # the same place is overwritten, not duplicated
    store.save_verdict({"place_id": pid, "verdict": "right", "tier_verdict": "too high", "note": "n"})
    assert V.read_csv(tmp_path / "verdicts.csv")[0]["tier_verdict"] == "too high"
    with pytest.raises(ValueError):
        store.save_verdict({"place_id": pid, "verdict": "great"})


def test_the_http_api_serves_places_details_and_accepts_labels(store):
    server = V.serve(store, 0, open_browser=False)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        assert b"Atlas viewer" in urllib.request.urlopen(base + "/").read()
        meta = json.loads(urllib.request.urlopen(base + "/api/meta").read())
        assert meta["places"] == 199 and meta["blank"] > 0 and "R14" in meta["rules"]
        rows = json.loads(urllib.request.urlopen(base + "/api/places").read())
        assert rows[0]["r"] == "Notable" and {"i", "q", "n", "k", "m", "p", "o"} <= set(rows[0])
        d = json.loads(urllib.request.urlopen(f"{base}/api/place?id={rows[0]['i']}").read())
        assert d["place"]["name_en"] and "children" in d
        req = urllib.request.Request(base + "/api/label", data=json.dumps({"place_id": rows[0]["i"], "kinds": ["ruins"]}).encode(),
                                     headers={"Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(req).read())["saved"]
        bad = urllib.request.Request(base + "/api/label", data=b'{"place_id": "x", "kinds": []}')
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(bad)
        assert e.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/place?id=none")
        assert e.value.code == 404
    finally:
        server.shutdown()
