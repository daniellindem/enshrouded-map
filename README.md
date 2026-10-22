# Embervale Atlas

A static HTML map for planning Enshrouded bases. Open the portable **`embervale-atlas.html`** directly in a browser. It bundles the interface, styles, scripts, and landmarks in one file. Terrain imagery still needs an internet connection.

For development, open `index.html` or run:

```sh
python3 -m http.server 5173
```

Then visit http://localhost:5173. No install or build is required.

## GitHub Pages

The site publishes from `main` with the `Publish GitHub Pages` workflow. In the repository's Pages settings, the publishing source is **GitHub Actions**. The repository stays private; the published website is public so anyone with its URL can try it.

The workflow packages an explicit list of website assets. Repository documentation, plans, and workflow files are not included in the published site. To produce the same package locally:

```sh
python3 scripts/build_site.py
```

The output is `_site/`, including a freshly generated portable HTML file. The build uses Python's standard library only. Private-repository Pages hosting requires a supported GitHub plan.

Place and drag flame altars, choose each altar's level, compare the four building footprints, and toggle landmarks or a 10-metre building grid. Plans save locally in the browser. Share plan copies a URL containing the plan, including its scale. Undo restores altar edits, removal, and calibration changes. Touch supports map panning and pinch zoom.

## Map scale

The default scale is **approximate**: 0.5 metres per imagery pixel at source zoom 16. It is not a verified game coordinate conversion. Use the ruler control, mark two points with a known horizontal in-game distance, and enter that distance to calibrate all overlays. Calibration is saved with the plan. Do not use the default estimate for precise placement.

Building footprints are 40, 80, 120, and 160 metres per side for altar levels 1 through 4. These are full side lengths, not radii. The map shows the horizontal footprint of the cubic building volume. Global Flame strength is a separate progression system. Dimensions: [Official Enshrouded Wiki](https://enshrouded.wiki.gg/wiki/Flame_Altar).

## Files and external resources

- `index.html`: interface and dialogs.
- `styles.css`: responsive layout and styling.
- `app.js`: tile renderer, world coordinates, interaction, calibration, and plan storage.
- `locations.js`: settlement and ancient spire positions from the reference map.
- `embervale-atlas.html`: portable single-file version of the site.

Terrain tiles load directly from MapGenie's public Embervale tile service, with visible attribution and a link to the [source map](https://mapgenie.io/enshrouded/maps/embervale). Internet access and continued availability of that service are required. There is no offline imagery bundle. Imagery and game assets belong to their respective owners. Obtain the appropriate permissions or supply your own tile service for a public deployment. Fonts load from Google Fonts with local fallbacks. All planning controls use native browser APIs without external JavaScript libraries.

This is an unofficial fan tool and does not connect to the game or validate terrain restrictions.

## Deferred work

Website issue reporting is planned separately in [plans/issue-tracker.md](plans/issue-tracker.md). It has not been implemented.
