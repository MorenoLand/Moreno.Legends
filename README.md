# Cross-platform Mega Man Legends 2 port

The goal is to port Mega Man Legends 2 to Godot/Redot for Linux, Windows, macOS and WebAssembly, with mobile support as a possible additional target. The client should extract its required assets from the user's disc files rather than distribute exported game data.

The current implementation loads extracted ST0F areas with the original textured and animated Mega Man player, geometry collision and arm-cannon projectiles. The full game and automatic client-side disc import are still in development.

Open this folder with Redot 26.2 or a compatible Godot 4 editor and run the main scene. WASD moves relative to the camera; mouse movement or Q/E orbits it, Space jumps, left mouse fires, right mouse holds shoulder aim, Esc releases the mouse, and F respawns. Aiming reduces movement speed and limits how quickly Mega Man turns; camera and shots collide with level geometry.

The disc extraction helpers are in `tools/`. After extracting `DAT` and `COMMON` into `build/disc-assets`, run `python tools/export_maps.py --stage ST0F`, `python tools/export_player.py`, and `python tools/export_hud.py`. Generated assets and local dependencies are ignored by Git.

The player contains the original buster-equipped mesh, palettes, skeleton and 81 recovered control clips at the traced player-to-level scale. Standing, running, jumping and firing use observed motion mappings; the manifest records unresolved controls. The HUD is provisional while the original gameplay gauges are traced. Collision comes from rendered meshes rather than the original collision tables. Enemies, damage sources and scripted room transitions are not implemented.

Runtime code uses GDScript and the Compatibility renderer. The Web export preset includes asset manifests and disables threads; browser mouse capture begins on a canvas click. Native gameplay has been exercised; a browser export has not been verified.
