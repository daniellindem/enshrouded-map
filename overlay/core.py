"""Plan interchange and north-up map registration. No game-process access."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import math
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import cv2
import numpy as np

ORIGIN = 32512 * 256
MAP_SIZE = 65536
DEFAULT_MPP = .356
TILE_URL = 'https://tiles.mapgenie.io/games/enshrouded/embervale/default-v7'
cv2.setNumThreads(2)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def read_plan(text: str) -> dict:
    """Accept the website's Share plan URL or an exported JSON file, never fetch a URL."""
    if len(text) > 100_000:
        raise ValueError('Plan is too large.')
    text = text.strip()
    if not text.startswith('{'):
        fragment = urlparse(text).fragment if '#' in text else text.lstrip('#')
        if not fragment.startswith('plan='):
            raise ValueError('Paste a Share plan link from Embervale Atlas, or open a plan JSON file.')
        encoded = unquote(fragment[5:])
        try:
            text = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode('utf-8')
        except (ValueError, UnicodeError) as exc:
            raise ValueError('This plan link could not be decoded.') from exc
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError('This is not valid plan JSON.') from exc
    if (not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1
            or not isinstance(data.get('altars'), list) or len(data['altars']) > 100):
        raise ValueError('Unsupported plan. Export a version 1 plan from the website.')
    ids = set()
    altars = []
    for a in data['altars']:
        if (not isinstance(a, dict) or not isinstance(a.get('id'), str) or not 1 <= len(a['id']) <= 80
                or a['id'] in ids or not isinstance(a.get('name'), str)
                or not all(number(a.get(k)) and 0 <= a[k] <= MAP_SIZE for k in ('x', 'y'))
                or type(a.get('level')) is not int or not 1 <= a['level'] <= 4):
            raise ValueError('Invalid altar in plan.')
        ids.add(a['id'])
        altars.append({k: a[k] for k in ('id', 'x', 'y', 'level')} |
                      {'name': a['name'][:60] or 'Unnamed altar', 'visible': a.get('visible') is not False})
    mpp = data.get('metersPerPixel', DEFAULT_MPP)
    if not number(mpp) or not .0001 <= mpp <= 1000:
        raise ValueError('Invalid map scale.')
    revision = data.get('scaleRevision', 1)
    if not number(revision):
        raise ValueError('Invalid scale revision.')
    if data.get('calibrated') is not True and revision < 2 and mpp == .5:
        mpp = DEFAULT_MPP
    data.update(altars=altars, metersPerPixel=mpp, scaleRevision=2)
    if not isinstance(data.get('selected'), str) or data['selected'] not in ids:
        data['selected'] = altars[0]['id'] if altars else None
    return data


def plan_link(plan):
    encoded = base64.urlsafe_b64encode(json.dumps(plan, separators=(',', ':'), ensure_ascii=False).encode()).decode().rstrip('=')
    return 'https://daniellindem.github.io/enshrouded-map/#plan=' + encoded


@dataclass
class Reference:
    image: np.ndarray  # BGR, source imagery mosaic
    x: float  # top left in website zoom-16 coordinates
    y: float
    factor: float  # website source pixels per mosaic pixel


@dataclass
class Alignment:
    # Reference mosaic pixels = game-image pixels * scale + (tx, ty).
    scale: float
    tx: float
    ty: float
    score: float
    error: float  # RMS in game-image pixels
    patches: int
    reference: Reference
    width: int
    height: int

    def source(self, point):
        return np.asarray(point) * (self.scale * self.reference.factor) + np.array([
            self.reference.x + self.tx * self.reference.factor,
            self.reference.y + self.ty * self.reference.factor])

    def screen(self, point):
        return (np.asarray(point) - np.array([self.reference.x, self.reference.y])) / self.reference.factor / self.scale - np.array([self.tx, self.ty]) / self.scale

    def side_pixels(self, level, mpp):
        return level * 40 / mpp / self.reference.factor / self.scale


def load_reference(center, cache: Path, zoom=15) -> Reference:
    """Fetch only a 3x3 neighbourhood. Nothing is uploaded to the tile service."""
    if zoom not in (13, 14, 15, 16):
        raise ValueError('Reference zoom must be between 13 and 16.')
    factor = 2 ** (16 - zoom)
    tile_x, tile_y = [int((v + ORIGIN) / factor / 256) for v in center]
    minimum, maximum = 2 ** (zoom - 1) - 2 ** (zoom - 8), 2 ** (zoom - 1) - 1
    x0 = min(max(tile_x - 1, minimum), maximum - 2)
    y0 = min(max(tile_y - 1, minimum), maximum - 2)
    cache.mkdir(parents=True, exist_ok=True)
    canvas = np.zeros((768, 768, 3), dtype=np.uint8)
    for y in range(y0, y0 + 3):
        for x in range(x0, x0 + 3):
            path = cache / f'{zoom}-{y}-{x}.jpg'
            image = cv2.imread(str(path)) if path.exists() else None
            if image is None or image.shape != (256, 256, 3):
                req = Request(f'{TILE_URL}/{zoom}/{y}/{x}.jpg', headers={'User-Agent': 'EmbervaleAtlas/overlay-prototype'})
                try:
                    with urlopen(req, timeout=12) as response:
                        raw = response.read(2_000_000)
                    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                    if image is None or image.shape != (256, 256, 3):
                        raise ValueError('Invalid terrain tile.')
                    path.write_bytes(raw)
                except Exception as exc:
                    raise ValueError('Terrain tiles unavailable. Check your connection and try again.') from exc
            canvas[(y-y0)*256:(y-y0+1)*256, (x-x0)*256:(x-x0+1)*256] = image
    return Reference(canvas, x0 * 256 * factor - ORIGIN, y0 * 256 * factor - ORIGIN, factor)


def contours(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    gray = cv2.GaussianBlur(gray, (0, 0), .65).astype(np.float32)
    dx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=1)
    dy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=1)
    # Icons have much more contrast than terrain. Saturation clipping limits their influence.
    return np.minimum(cv2.magnitude(dx, dy), 7)


def frame_signature(image):
    return cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (384, 216), interpolation=cv2.INTER_LINEAR)


def same_view(a, b):
    """Cheap movement check between expensive matches; small marker animation is tolerated."""
    if a is None or b is None or a.shape != b.shape:
        return False
    difference = np.abs(a.astype(np.int16)-b.astype(np.int16))
    return float(difference.mean()) < .9 and float((difference > 5).mean()) < .022


def peak(target, template):
    if min(template.shape) < 12 or any(a > b for a, b in zip(template.shape, target.shape)) or template.std() < .04:
        return -1., (0, 0)
    result = cv2.matchTemplate(target, template, cv2.TM_CCOEFF_NORMED)
    # Float template matching can report 1.0 on nearly empty target windows.
    # Reject those windows explicitly, using double-precision local variance.
    h, w = template.shape
    sums, squares = cv2.integral2(target, sdepth=cv2.CV_64F, sqdepth=cv2.CV_64F)
    total = sums[h:, w:]-sums[:-h, w:]-sums[h:, :-w]+sums[:-h, :-w]
    total2 = squares[h:, w:]-squares[:-h, w:]-squares[h:, :-w]+squares[:-h, :-w]
    variance = total2/(h*w)-(total/(h*w))**2
    result[variance < .01] = -1
    result[~np.isfinite(result)] = -1
    _, score, _, position = cv2.minMaxLoc(result)
    return score, position


def register(image: np.ndarray, reference: Reference, roi=None, previous: Alignment | None = None) -> Alignment:
    """Coarse scale search followed by spatially separate contour checks and a uniform fit.

    A plan supplies the approximate area; this is deliberately not a whole-world search.
    HUD/fog can be excluded with a region drawn in the preview.
    """
    h, w = image.shape[:2]
    if min(h, w) < 100:
        raise ValueError('Map capture is too small.')
    x1, y1, x2, y2 = roi or (int(w*.16), int(h*.10), int(w*.84), int(h*.80))
    x1, y1, x2, y2 = max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))
    if x2-x1 < 100 or y2-y1 < 100:
        raise ValueError('Select a larger terrain region, at least 100 pixels per side.')
    patch = image[y1:y2, x1:x2]
    target = contours(reference.image)
    max_scale = min(2., (target.shape[1]-4)/patch.shape[1], (target.shape[0]-4)/patch.shape[0])
    min_scale = max(.025, 112/min(patch.shape[:2]))
    if min_scale >= max_scale:
        raise ValueError('Select a smaller terrain region or a wider reference area.')
    if previous and previous.width == w and previous.height == h:
        lo, hi = max(min_scale, previous.scale*.82), min(max_scale, previous.scale*1.22)
        scales = np.geomspace(lo, hi, 24) if lo < hi else np.geomspace(min_scale, max_scale, 64)
    else:
        scales = np.geomspace(min_scale, max_scale, 64)
    candidates = []
    def consider(scale):
        resized = cv2.resize(patch, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        score, position = peak(target, contours(resized))
        candidates.append((score, float(scale), position))
    for scale in scales:
        consider(float(scale))
    # Refine several distinct peaks; a small repetitive contour must not win by itself.
    seeds = []
    for item in sorted(candidates, reverse=True):
        if all(abs(math.log(item[1]/seed[1])) > .045 for seed in seeds):
            seeds.append(item)
        if len(seeds) == 5:
            break
    for _, seed, _ in seeds:
        for scale in np.linspace(max(min_scale, seed*.96), min(max_scale, seed*1.04), 25):
            consider(float(scale))
    best = []
    for item in sorted(candidates, reverse=True):
        if all(abs(math.log(item[1]/other[1])) > .018 for other in best):
            best.append(item)
        if len(best) == 10:
            break
    for score, scale, position in best:
        if score < .20:
            break
        tx, ty = position[0]-x1*scale, position[1]-y1*scale
        source_points, target_points, patch_scores = [], [], []
        # 3x3 non-overlapping local checks establish scale and translation independently.
        for row in range(3):
            for col in range(3):
                bx = x1 + col*(x2-x1)//3
                by = y1 + row*(y2-y1)//3
                bw, bh = (x2-x1)//3, (y2-y1)//3
                small = image[by:by+bh, bx:bx+bw]
                template = contours(cv2.resize(small, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR))
                th, tw = template.shape
                px, py = bx*scale+tx, by*scale+ty
                radius = max(5, int(scale*9))
                left, top = max(0, round(px)-radius), max(0, round(py)-radius)
                right, bottom = min(target.shape[1], round(px)+tw+radius), min(target.shape[0], round(py)+th+radius)
                local_score, pos = peak(target[top:bottom, left:right], template)
                if local_score >= .32:
                    source_points.append((bx+bw/2, by+bh/2))
                    target_points.append((left+pos[0]+tw/2, top+pos[1]+th/2))
                    patch_scores.append(local_score)
        if len(source_points) < 4:
            continue
        a, b = np.array(source_points), np.array(target_points)
        # Uniform scale, no rotation or shear. The game's world map is north-up.
        ac, bc = a-a.mean(0), b-b.mean(0)
        fitted = float(np.sum(ac*bc)/np.sum(ac*ac))
        offset = b.mean(0)-fitted*a.mean(0)
        residuals = np.linalg.norm(a*fitted+offset-b, axis=1)/fitted if fitted > 0 else np.full(len(a), np.inf)
        keep = residuals < 5
        if keep.sum() < 4:
            continue
        a, b = a[keep], b[keep]
        ac, bc = a-a.mean(0), b-b.mean(0)
        fitted = float(np.sum(ac*bc)/np.sum(ac*ac))
        offset = b.mean(0)-fitted*a.mean(0)
        error = float(np.sqrt(np.mean(np.sum((a*fitted+offset-b)**2, axis=1)))/fitted)
        if (error > 3.5 or abs(fitted/scale-1) > .04 or
                np.ptp(a[:, 0]) < (x2-x1)*.30 or np.ptp(a[:, 1]) < (y2-y1)*.30):
            continue
        return Alignment(fitted, *offset, score, error, len(a), reference, w, h)
    raise ValueError('No reliable terrain match. Open the world map near the selected altar; select clear terrain or change the reference zoom.')


def detect_player(image):
    """Find the north-facing red player arrow, excluding the orange altar flame."""
    b, g, r = cv2.split(image.astype(np.int16))
    mask = ((r-g > 115) & (r > 180) & (g < 125) & (r-b > 130)).astype(np.uint8)
    h, w = mask.shape
    mask[:int(h*.08)] = 0
    mask[int(h*.88):] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    candidates = []
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if area >= 35 and 8 <= bw <= w*.08 and 12 <= bh <= h*.10 and .30 <= bw/bh <= 1.8:
            candidates.append((area, i))
    if not candidates:
        raise ValueError('Player arrow not found. Face north and click the arrow centre in the preview.')
    candidates.sort(reverse=True)
    if len(candidates) > 1 and candidates[1][0] > candidates[0][0]*.65:
        raise ValueError('More than one possible player marker. Click the arrow centre in the preview.')
    _, index = candidates[0]
    x, y, bw, bh, area = stats[index]
    # The arrow's detached tail is included in its bounding box.
    right, bottom = x+bw-1, y+bh-1
    for i in range(1, count):
        sx, sy, sw, sh, sa = stats[i]
        if (i != index and sa >= 10 and abs(sx+sw/2-(x+bw/2)) < bw*.35
                and sy >= y+bh*.7 and -bh*.25 <= sy-bottom <= max(12, bh*.35)):
            bottom = max(bottom, sy+sh-1)
    return np.array([(x+right)/2, (y+bottom)/2], dtype=float)


def measure_edges(points, level):
    """Four cardinal boundary positions in website source coordinates -> metre scale."""
    if set(points) != {'north', 'south', 'east', 'west'} or type(level) is not int or not 1 <= level <= 4:
        raise ValueError('Capture all four edges and choose the altar upgrade level.')
    n, s, e, w = [np.asarray(points[k], dtype=float) for k in ('north', 'south', 'east', 'west')]
    if any(p.shape != (2,) or not np.isfinite(p).all() for p in (n, s, e, w)):
        raise ValueError('Invalid edge position.')
    width, height = e[0]-w[0], s[1]-n[1]
    if min(width, height) < 10:
        raise ValueError('Opposite edges are too close, reversed, or labelled incorrectly.')
    disagreement = abs(width-height)/((width+height)/2)
    if disagreement > .08:
        raise ValueError(f'Axis measurements differ by {disagreement:.1%}. Recapture the edges before applying this scale.')
    if abs(e[1]-w[1])/height > .15 or abs(s[0]-n[0])/width > .15:
        raise ValueError('Walk directly north/south and east/west from the same altar. These points are not on its centre lines.')
    center_x, center_y = (e[0]+w[0])/2, (s[1]+n[1])/2
    if (abs((n[0]+s[0])/2-center_x)/width > .12 or
            abs((e[1]+w[1])/2-center_y)/height > .12):
        raise ValueError('The edge pairs do not share an altar centre. Recapture along its centre lines.')
    return {'metersPerPixel': level*40/((width+height)/2), 'center': [center_x, center_y],
            'axisDifference': disagreement, 'width': width, 'height': height}
