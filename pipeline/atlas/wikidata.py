"""A small Wikidata client (standard library only) for the tools the owner runs locally.

The Claude sandbox cannot reach Wikidata, so everything that uses this client is tested
against recorded responses; the live run is done on the owner's machine. Wikimedia asks
clients to send an identifying User-Agent and to go slowly; both are done here.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

API = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "TravelersMap/2.0 (personal research project; github.com/adilezz/travelers-map)"


def http_get(url: str, params: dict, retries: int = 3) -> dict:
    q = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(q, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(float(e.headers.get("Retry-After") or 5 * (attempt + 1)))
                continue
            raise
    raise RuntimeError("unreachable")


def qid_of(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


class Client:
    def __init__(self, fetch: Callable[[str, dict], dict] | None = None, delay: float = 0.25):
        self._fetch = fetch or http_get
        self._delay = delay

    def _get(self, url: str, params: dict) -> dict:
        data = self._fetch(url, params)
        if self._delay:
            time.sleep(self._delay)
        return data

    def search(self, text: str, lang: str = "en", limit: int = 7) -> list[dict]:
        d = self._get(API, {"action": "wbsearchentities", "search": text, "language": lang,
                            "type": "item", "limit": limit, "format": "json"})
        return d.get("search", [])

    def entities(self, qids: list[str]) -> dict[str, dict]:
        """label, description, coordinate, sitelink count and instance-of for each item."""
        out: dict[str, dict] = {}
        for i in range(0, len(qids), 50):
            batch = qids[i:i + 50]
            d = self._get(API, {"action": "wbgetentities", "ids": "|".join(batch), "format": "json",
                                "props": "labels|descriptions|claims|sitelinks", "languages": "en"})
            for qid, e in d.get("entities", {}).items():
                if "missing" in e:
                    continue
                coord = None
                for c in e.get("claims", {}).get("P625", []):
                    v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                    if v:
                        coord = (v["latitude"], v["longitude"])
                        break
                inst = [c["mainsnak"]["datavalue"]["value"]["id"] for c in e.get("claims", {}).get("P31", [])
                        if c.get("mainsnak", {}).get("datavalue")]
                out[qid] = {
                    "label": e.get("labels", {}).get("en", {}).get("value", ""),
                    "description": e.get("descriptions", {}).get("en", {}).get("value", ""),
                    "coord": coord, "sitelinks": len(e.get("sitelinks", {})), "instance_of": inst,
                }
        return out

    def labels(self, qids: list[str]) -> dict[str, str]:
        return {q: e["label"] for q, e in self.entities(qids).items()}

    def sparql(self, query: str) -> list[dict]:
        d = self._get(SPARQL, {"query": query, "format": "json"})
        return d.get("results", {}).get("bindings", [])

    def items_with_whs_id(self, whs_id: str) -> list[str]:
        """Items carrying the UNESCO World Heritage Site ID (P757)."""
        rows = self.sparql(f'SELECT ?item WHERE {{ ?item wdt:P757 "{whs_id}" . }}')
        return [qid_of(r["item"]["value"]) for r in rows]
