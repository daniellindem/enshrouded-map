"""Offline checks. No user screenshots, network access or game installation needed."""
import copy
import json
import unittest

import cv2
import numpy as np

from overlay.core import (Alignment, Reference, DEFAULT_MPP, detect_player, measure_edges,
                          frame_signature, same_view, plan_link, read_plan, register)


def plan():
    return {'version': 1, 'altars': [{'id': 'a', 'name': 'A & Æ', 'x': 31295.3, 'y': 39941.5,
            'level': 1, 'visible': True}], 'selected': 'a', 'metersPerPixel': .356, 'scaleRevision': 2}


def terrain():
    rng = np.random.default_rng(5)
    image = np.full((768, 768, 3), (143, 153, 156), np.uint8)
    for i in range(65):
        centre = rng.integers(25, 740, 2)
        radii = rng.integers(8, 65, 2)
        cv2.ellipse(image, tuple(centre), tuple(radii), int(rng.integers(0, 180)), 0, 360,
                    (110, 119, 122), 1, cv2.LINE_AA)
    return image


class Plans(unittest.TestCase):
    def test_round_trip_preserves_unicode_and_scale(self):
        self.assertEqual(read_plan(plan_link(plan()))['altars'], plan()['altars'])
        self.assertEqual(read_plan(json.dumps(plan()))['metersPerPixel'], .356)

    def test_migrates_only_old_estimate(self):
        data = plan() | {'metersPerPixel': .5, 'scaleRevision': 1}
        self.assertEqual(read_plan(json.dumps(data))['metersPerPixel'], DEFAULT_MPP)
        data['calibrated'] = True
        self.assertEqual(read_plan(json.dumps(data))['metersPerPixel'], .5)

    def test_rejects_bad_coordinates_duplicates_and_malformed_links(self):
        for field, value in [('x', float('nan')), ('level', True), ('y', -1)]:
            data = plan()
            data['altars'][0][field] = value
            with self.assertRaises(ValueError):
                read_plan(json.dumps(data))
        data = plan()
        data['altars'].append(copy.deepcopy(data['altars'][0]))
        with self.assertRaises(ValueError):
            read_plan(json.dumps(data))
        for invalid in ['https://example.com/', '#plan=***', '[]', '{"version":1,"altars":false}']:
            with self.assertRaises(ValueError):
                read_plan(invalid)


class Registration(unittest.TestCase):
    def test_view_guard_detects_pan_and_allows_small_marker_changes(self):
        image = cv2.resize(terrain(), (1200, 900))
        pan = cv2.warpAffine(image, np.float32([[1, 0, 15], [0, 1, 0]]), (1200, 900), borderMode=cv2.BORDER_REPLICATE)
        self.assertFalse(same_view(frame_signature(image), frame_signature(pan)))
        marked = image.copy()
        cv2.circle(marked, (600, 450), 10, (25, 40, 255), -1)
        self.assertTrue(same_view(frame_signature(image), frame_signature(marked)))

    def test_map_translation_zoom_and_brightness(self):
        source = terrain()
        crop = source[140:500, 120:520]
        game = cv2.resize(crop, (800, 720), interpolation=cv2.INTER_CUBIC)
        game = cv2.convertScaleAbs(game, alpha=.8, beta=12)
        game = cv2.copyMakeBorder(game, 30, 50, 50, 70, cv2.BORDER_CONSTANT, value=(45, 45, 45))
        # A bright marker occludes part of the map, as the actual altar icon does.
        cv2.rectangle(game, (410, 380), (450, 420), (20, 220, 255), -1)
        ref = Reference(source, 30000, 39000, 2)
        result = register(game, ref)
        expected = np.array([30000, 39000]) + np.array([120, 140])*2
        np.testing.assert_allclose(result.source([50, 30]), expected, atol=4)
        self.assertAlmostEqual(result.scale, .5, delta=.008)
        np.testing.assert_allclose(result.screen(result.source([532, 321])), [532, 321], atol=1e-6)
        self.assertAlmostEqual(result.side_pixels(1, .4), 100, delta=2)
        self.assertGreaterEqual(result.patches, 4)

    def test_flat_and_unrelated_frames_are_rejected(self):
        ref = Reference(terrain(), 0, 0, 2)
        for image in [np.full((700, 900, 3), 150, np.uint8),
                      np.random.default_rng(44).integers(0, 255, (700, 900, 3), dtype=np.uint8)]:
            with self.assertRaises(ValueError):
                register(image, ref)

    def test_arrow_and_detached_tail_not_orange_flame(self):
        image = np.full((700, 900, 3), 150, np.uint8)
        cv2.fillPoly(image, [np.array([[440, 300], [420, 343], [440, 335], [460, 343]])], (45, 65, 245))
        cv2.fillPoly(image, [np.array([[440, 342], [425, 351], [455, 351]])], (45, 65, 245))
        cv2.circle(image, (400, 280), 20, (5, 160, 255), -1)
        np.testing.assert_allclose(detect_player(image), [440, 325.5], atol=1)
        image[:] = 150
        with self.assertRaises(ValueError):
            detect_player(image)


class Measurements(unittest.TestCase):
    def edges(self):
        return {'north': [500, 400], 'south': [500, 600], 'west': [400, 500], 'east': [600, 500]}

    def test_known_side_not_radius_and_not_global_flame(self):
        measurement = measure_edges(self.edges(), 1)
        self.assertEqual(measurement['metersPerPixel'], .2)
        np.testing.assert_equal(measurement['center'], [500, 500])
        self.assertEqual(measure_edges(self.edges(), 4)['metersPerPixel'], .8)

    def test_rejects_bad_axes_and_wrong_centre_lines(self):
        for edge, point in [('north', [500, 200]), ('east', [400, 500]),
                            ('south', [550, 600]), ('north', [550, 400])]:
            edges = self.edges()
            edges[edge] = point
            with self.assertRaises(ValueError):
                measure_edges(edges, 1)


if __name__ == '__main__':
    unittest.main()
