# Tier calibration against the golden set

176 golden rows resolve to a place; the gate needs zero violations of `min_tier`, `max_tier` and `not_above`. Parameters are searched on the golden set only, never on H1.

`tiers.json` before D37 (8 Oct): **45 violations**; tier shares (1.1351233355162629, 4.147566033617114, 34.92687186203886).

- G003 Luxor (Thebes): Notable, needs Icon+
- G004 Abu Simbel: Major, needs Icon+
- G005 Aswan: Notable, needs Major+
- G008 Siwa Oasis: Notable, needs Major+
- G009 White Desert: Local, needs Notable+
- G010 Sharm el-Sheikh: Notable, needs Major+
- G013 Wadi Al-Hitan: Major, max Notable
- G015 Cusco: Major, needs Icon+
- G016 Sacred Valley (Ollantaytambo): Notable, needs Major+
- G019 Colca Canyon: Local, needs Major+
- G020 Arequipa: Notable, needs Major+
- G028 Florence: Major, needs Icon+
- G033 Siena: Notable, needs Major+
- G037 Lake Como: Notable, needs Major+
- G047 Jerash: Notable, needs Major+
- G049 Aqaba: Notable, needs Major+
- G052 Dana Biosphere Reserve: Local, needs Notable+
- G056 Ngorongoro Crater: Major, needs Icon+
- G060 Nyerere National Park (Selous): Local, needs Notable+
- G061 Tarangire National Park: Local, needs Notable+
- G062 Lake Manyara National Park: Local, needs Notable+
- G063 Mount Meru (Arusha National Park): Local, needs Notable+
- G067 Ruaha National Park: Local, needs Notable+
- G073 Wadi El Rayan: Local, needs Notable+
- G081 Gran Paradiso National Park: Local, needs Notable+
- G086 Mujib Nature Reserve: Local, needs Notable+
- G088 Ajloun: Local, needs Notable+
- G094 Mwanza: Notable, needs Major+
- G095 Katavi National Park: Local, needs Notable+
- G097 Mikumi National Park: Local, needs Notable+
- G100 Fez: Major, needs Icon+
- G103 Chefchaouen: Notable, needs Major+
- G104 Erg Chebbi (Merzouga): Local, needs Major+
- G108 Toubkal: Local, needs Major+
- G113 Ouzoud Falls: Local, needs Notable+
- G130 Picos de Europa: Notable, needs Major+
- G136 Timanfaya National Park: Notable, needs Major+
- G147 Loire Valley: Notable, needs Major+
- G148 Chamonix and Mont Blanc: Notable, needs Major+
- G149 Provence (Luberon): Notable, needs Major+
- G150 French Riviera: Notable, needs Major+
- G153 Lourdes: Notable, needs Major+
- G155 Alsace Wine Route: Local, needs Notable+
- G158 Calanques National Park: Local, needs Notable+
- G176 Bodrum: Notable, needs Major+

## Lowest violations (ties by the smallest Icon plus Major share)

| violations | Icon % | Major % | Notable % | protected R | pageview weight | icon p | major p | icon top | major next | notable p |
|---|---|---|---|---|---|---|---|---|---|---|
| 13 | 2.4 | 10.4 | 33.8 | 0.4 | 1.0 | 99.5 | 90 | 12 | 30 | 60 |
| 13 | 2.4 | 10.3 | 33.8 | 0.4 | 1.0 | 99 | 90 | 12 | 30 | 60 |
| 14 | 2.4 | 10.3 | 33.7 | 0.4 | 0.5 | 99 | 90 | 12 | 30 | 60 |
| 14 | 2.4 | 10.3 | 33.7 | 0.4 | 0.5 | 99.5 | 90 | 12 | 30 | 60 |
| 15 | 2.4 | 9.2 | 34.6 | 0.4 | 1.0 | 99 | 90 | 12 | 20 | 60 |
| 15 | 2.4 | 9.3 | 34.6 | 0.4 | 1.0 | 99.5 | 90 | 12 | 20 | 60 |
| 15 | 1.7 | 10.6 | 34.1 | 0.4 | 1.0 | 99 | 90 | 8 | 30 | 60 |
| 15 | 1.6 | 10.7 | 34.1 | 0.4 | 1.0 | 99.5 | 90 | 8 | 30 | 60 |
| 15 | 2.4 | 10.3 | 28.3 | 0.4 | 0.5 | 99 | 90 | 12 | 30 | 75 |
| 15 | 2.4 | 10.3 | 28.3 | 0.4 | 0.5 | 99.5 | 90 | 12 | 30 | 75 |
| 15 | 2.4 | 10.4 | 28.2 | 0.4 | 1.0 | 99.5 | 90 | 12 | 30 | 75 |
| 15 | 2.4 | 10.3 | 28.2 | 0.4 | 1.0 | 99 | 90 | 12 | 30 | 75 |
| 16 | 2.4 | 8.3 | 35.5 | 0.4 | 0.5 | 99 | 90 | 12 | 10 | 60 |
| 16 | 2.4 | 8.3 | 35.5 | 0.4 | 0.5 | 99.5 | 90 | 12 | 10 | 60 |
| 16 | 1.7 | 9.5 | 35.0 | 0.4 | 1.0 | 99 | 90 | 8 | 20 | 60 |

## Violations against the cost in Icon and Major places (cheapest setting per violation count)

| violations | Icon % | Major % | protected R | pageview weight | icon top | major next |
|---|---|---|---|---|---|---|
| 13 | 2.4 | 10.4 | 0.4 | 1.0 | 12 | 30 |
| 14 | 2.4 | 10.3 | 0.4 | 0.5 | 12 | 30 |
| 15 | 2.4 | 9.2 | 0.4 | 1.0 | 12 | 20 |
| 16 | 2.4 | 8.3 | 0.4 | 0.5 | 12 | 10 |
| 17 | 2.4 | 6.4 | 0.4 | 1.0 | 12 | 30 |
| 18 | 1.7 | 8.6 | 0.4 | 1.0 | 8 | 10 |
| 19 | 1.7 | 6.5 | 0.4 | 1.0 | 8 | 30 |
| 20 | 2.4 | 5.0 | 0.4 | 1.0 | 12 | 20 |
| 21 | 1.6 | 5.3 | 0.4 | 1.0 | 8 | 20 |
| 22 | 2.4 | 5.0 | 0.4 | 0.5 | 12 | 20 |
| 23 | 1.3 | 6.5 | 0.4 | 0.5 | 5 | 30 |
| 24 | 2.4 | 3.8 | 0.4 | 1.0 | 12 | 10 |
| 25 | 1.7 | 4.1 | 0.4 | 1.0 | 8 | 10 |
| 26 | 1.3 | 5.2 | 0.4 | 0.5 | 5 | 20 |
