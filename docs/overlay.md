# Desktop map overlay

The local companion draws your altar boundaries over Enshrouded's **world map** in a transparent, click-through desktop window. It also previews boundaries on saved game-map images. It does not draw a 3D fence in the game world.

This is an experimental companion, not a Keen-approved integration. It uses captured screen pixels and the same terrain tiles as the website. It does not access the game process, inspect memory, inject code, modify game files, or automate gameplay. Keen's [current terms](https://enshrouded.com/en-US/eula) do not explicitly approve this kind of overlay.

## Run it

Use Python 3.10 or newer. From the repository directory on Linux:

```sh
./scripts/run_overlay.sh
```

The launcher creates `.venv-overlay` and installs PySide6, NumPy and headless OpenCV on first use. That installation needs internet access. It does not require administrator privileges. If your distribution separates `venv` into another package, install that Python component first.

The equivalent commands, also useful on other desktop platforms, are:

```sh
python3 -m venv .venv-overlay
.venv-overlay/bin/python -m pip install -r overlay/requirements.txt
.venv-overlay/bin/python -m overlay.app
```

On Windows, use `py -m venv .venv-overlay`, then `.venv-overlay\Scripts\python.exe` in place of `.venv-overlay/bin/python`. The screenshot workflow is platform-independent; the live overlay has not yet been verified in an actual game session on Windows or KDE.

## First alignment

1. In the website, place an altar near the one you want to test. Click **Share plan**, then paste that link into the companion and click **Import link**. The website's browser storage is separate from this application.
2. Select the altar and click **Load terrain near selected altar**. This loads nine nearby source tiles, not the entire map. Keep the default zoom 15 initially.
3. Click **Open map image** and choose an in-game world-map screenshot, or use live sharing below. Terrain matching determines the capture's position and zoom automatically.
4. Check that the square and centre cross line up. If the altar's initial position is approximate, use **Place selected altar at a point in preview** and click its centre. That edit updates the companion's plan.

Matching requires visible contour detail. If it fails, drag a **terrain region** around clear map features, excluding menus and unexplored fog. If the image covers much more terrain, select the wider reference zoom and load terrain again. Pan the in-game map near the selected altar. Matching does not search all of Embervale and does not rotate the map.

## Live use on KDE / Wayland

Select the output monitor in the companion, then click **Start screen sharing**. In the desktop's permission dialog, select that **entire monitor**, rather than an application window or a crop. Qt uses the system ScreenCast portal and PipeWire on Wayland. See [Qt's Linux capture requirements](https://doc.qt.io/qt-6/qtmultimedia-linux.html).

Enable **Show boundaries over the game map**, then switch focus back to the game and open its map. Keep Enshrouded in windowed or borderless mode. The compositor controls stacking; exclusive fullscreen may prevent a separate window from appearing above the game. Some Wayland desktops may need an always-on-top window rule for `Embervale Atlas map overlay`.

The monitor selected in the desktop sharing chooser must match the output monitor selected in the companion. Captured physical pixels are mapped to that monitor's logical dimensions, including display scaling. Changing monitor layout, capture source, or resolution requires stopping and starting sharing again.

The companion matches a frame at a time in a background worker, with no queued backlog. A cheaper image-change check hides boundaries while the view moves, and results are discarded if the view changed during matching. Failed matches hide the overlay. Matching is intentionally conservative; pausing briefly after panning or zooming helps it reacquire the map. If the capture backend stops emitting frames for several seconds, the overlay also hides until new frames arrive.

The control window pauses live matching while focused. Its preview is blank while it is in the background, so full-screen capture cannot match its own preview. Return to the control window to inspect the last matched frame, record an edge, or stop capture.

The overlay never takes mouse input. **Stop** immediately hides it and ends screen sharing. **Esc** hides it when the control window has keyboard focus; it is not a global game shortcut. Use Alt+Tab to reach the control window from the game. Closing the companion also stops capture.

## Measure metres from the game

Terrain matching gives the relationship between game-map pixels and website pixels. It cannot infer a real-world distance from map contours alone. The four-edge workflow supplies a known distance using an altar's build boundary.

1. Choose the **altar upgrade level**, independently of global Flame strength. The side lengths are 40, 80, 120 and 160 metres.
2. From the altar, walk straight north to the building boundary. Face north and open the game map. Select **North** in the companion, then use **Record current edge**, or load a saved capture with **Load edge image**.
3. Repeat at the south, west and east boundaries. Each capture is registered independently, so cropping, panning and zoom can differ. Keep the same altar and upgrade level throughout.
4. Review the green crosshair on the player arrow in each capture. Automatic red-arrow detection can be confused by other markers or an altar icon covering the player. **Mark player centre manually** lets you correct it. Live sharing pauses on the captured frame while you mark it; click **Record current edge** afterward.
5. Once all four edges are recorded, review the calculated scale and axis disagreement. Badly inconsistent spans, reversed labels and points away from the centre lines are rejected. You can replace an individual edge by recording it again.
6. Click **Apply measured scale and altar centre**, then **Copy updated plan link** or **Save plan JSON**. Importing that Share plan link into the website carries back the scale, altar location and upgrade level.

Measurements are kept in memory until exported. Closing the application discards changes that have not been copied or saved. Applying the measurement changes the companion's plan, not the website's saved plan automatically.

The fit residual measures agreement between matched terrain patches. Axis disagreement measures agreement between two distance measurements. Neither proves absolute positional accuracy. Standing at the visible build boundary and estimating the arrow's centre still introduce uncertainty. This does not validate terrain restrictions or the vertical build volume.

## Data and network use

Captured images and shared frames are processed locally in memory. They are not uploaded, automatically written to disk, or included in exported plans. The application contacts MapGenie's tile service to load the selected neighbourhood and caches those tiles under the ignored `.overlay-cache/` directory. The usual network metadata and requested tile indices are visible to that service. Existing map attribution and imagery permissions still apply. No local web server or network control endpoint is opened.

## Verification

```sh
QT_QPA_PLATFORM=offscreen .venv-overlay/bin/python -m unittest discover -s tests -v
```

Offline tests cover plan interchange and old-scale migration, malformed inputs, terrain registration under zoom/translation/brightness changes, rejection of flat and unrelated frames, movement detection, arrow detection, measurement validation, transparent click-through window flags, stale background result rejection, and applying/exporting measurements through the Qt UI.

Additional local checks used the eight supplied screenshots from the Low Meadows test area. All eight registered automatically. Recording the four cardinal edges through the GUI produced approximately **0.35544 m per source-zoom-16 pixel**, with **1.3%** difference between the two axes. That is consistent with the earlier manual estimate of 0.356. The supplied 3D gameplay frame was rejected. User screenshots and downloaded imagery are not included in the repository.

GUI rendering was checked with Qt's offscreen backend. Actual game window stacking, monitor selection and the Wayland permission flow still need a live desktop trial.
