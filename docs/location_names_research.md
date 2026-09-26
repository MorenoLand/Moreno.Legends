# Room names

Room names come from the game's own text in `SLES_035.56`:
- Location strings start at `0x60B05` (main names, sub-names, "Floor B1" to "Floor B8").
- Four-byte records `(stage, area, sub-name, main-name)` start at `0x611A0`.

`tools/location_text.py` reads both and writes `tools/location_names.json`. Rooms that share a label in one stage are numbered ("Floor B2 - Room 3"). The numbering is the port's own, not game text.

`tools/world.py` reads the JSON through `location_name()` when it writes the manifests, so a normal import does not need the generator or the disc. Areas the game gives no sub-name stay "Area NN".
