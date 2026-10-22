# Map scale calibration

Measured on 22 October 2026 using the V7 terrain tiles and a level 1 altar northeast of Low Meadows Ancient Spire. The default scale is **0.356 metres per source pixel at zoom 16**. This is an estimate from a field test, not an official game coordinate conversion.

## In-game reference

The user captured eight game-map images at the same zoom and facing north: four positions next to the altar, and positions on each of its north, south, east, and west building boundaries. A level 1 altar has a 40 m horizontal side length. Opposite-edge spans provide the reference distance without assuming that a near-altar position is exactly at the centre.

Every image was registered to the first capture using two separate terrain patches. Both patches produced the same integer translation in all eight images. Screen cropping and map panning therefore do not change the measured distances.

The player arrow was separated from the altar icon by connected components. Using all red pixels together would mix the arrow with the red-orange flame and underestimate movement.

| Measurement | Span in original game-image pixels | Reference distance |
| --- | ---: | ---: |
| West boundary to east boundary, marker bounding-box centres | 170.0 | 40 m |
| North boundary to south boundary, marker bounding-box centres | 170.0 | 40 m |
| West to east, independent arrow-component centroid check | 171.1 | 40 m |
| North to south, independent arrow-component centroid check | 169.9 | 40 m |

This gives about 4.25 game-image pixels per metre. The centroid check differs between axes by about 0.7%. This is agreement between measurements, not a claim of 0.7% absolute accuracy. The four near-altar positions are roughly a metre from the centre inferred from opposing edges.

## Match to website imagery

The matching terrain lies within zoom-15 tiles with x indices 16316–16318 and y indices 16333–16335. That mosaic begins at source-zoom-16 coordinates x = 30720, y = 39424 in the app's local coordinate system.

Five distinct patches were matched: the northern outcrop, the western ring-shaped feature, the small southwestern rock, and the western and eastern cliffs. Fitting one uniform scale and a translation to their centres gives:

- Zoom-15 tile pixels per game-image pixel: approximately 0.33072.
- Root-mean-square feature-fit residual: approximately 0.28 zoom-15 pixels across the coordinate components.
- Estimated altar centre in app coordinates: x = 31295.3, y = 39941.5.

The conversion is:

```text
40 m / (170 game pixels × 0.33072 tile pixels/game pixel × 2 source pixels/tile pixel)
≈ 0.35573 m per source-zoom-16 pixel
```

The application rounds this to **0.356**. A 40 m side is therefore about 112.4 source pixels, compared with 80 source pixels under the original 0.5 assumption. The displayed width increases by approximately 40.4% at a fixed zoom.

## Limits and plan compatibility

Standing at the visual boundary, player-marker animation, raster compression, and terrain-feature matching introduce uncertainty. This sample supports equal scale on both axes locally. Additional locations would provide a stronger check that the conversion applies throughout the map. Terrain height and building-placement restrictions are not represented by a top-down footprint.

The initial 0.5 value and the earlier rough 0.4 screenshot estimate are superseded by this tile-matched measurement. A user can still apply a manual local calibration with the ruler.

Scale revision 2 migrates older uncalibrated plans that used 0.5. It preserves altar coordinates, levels, and manual calibrations. The same rule applies to saved plans and shared links. Default plans remain labelled as an estimate in the interface.

The user's screenshots are not included in the repository or public site. This record contains the derived measurements only.
