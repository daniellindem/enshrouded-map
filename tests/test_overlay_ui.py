"""Headless Qt integration checks. No screen-sharing session is started."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import json
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from overlay.app import MainWindow, STYLE, bgr, qimage
from overlay.core import Alignment, Reference, plan_link, read_plan
from test_overlay_core import plan


class Companion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.window = MainWindow(Path(self.temp.name))
        self.window.set_plan(plan())
        self.ref = Reference(np.zeros((768, 768, 3), np.uint8), 30000, 39000, 2)
        self.alignment = Alignment(.5, 0, 0, .8, 1., 6, self.ref, 1000, 1000)
        self.window.preview.image = np.zeros((1000, 1000, 3), np.uint8)
        self.window.preview.alignment = self.alignment
        self.window.reference = self.ref

    def tearDown(self):
        self.window.close()
        self.temp.cleanup()

    def test_measure_apply_and_round_trip_back_to_website(self):
        self.window.edges = {'north': [31295, 39885], 'south': [31295, 39997],
                             'west': [31239, 39941], 'east': [31351, 39941]}
        self.window.update_measurement()
        self.assertTrue(self.window.apply_button.isEnabled())
        self.window.apply_measurement()
        exported = read_plan(plan_link(self.window.plan))
        self.assertTrue(exported['calibrated'])
        self.assertAlmostEqual(exported['metersPerPixel'], 40/112)
        self.assertEqual(exported['altars'][0]['x'], 31295)
        self.assertEqual(exported['altars'][0]['y'], 39941)
        self.assertEqual(exported['altars'][0]['level'], 1)
        self.assertIn(f'{40/112:.6f}', self.window.quality.text())

    def test_background_preview_does_not_paint_captured_terrain(self):
        preview = self.window.preview
        preview.image[:] = (100, 150, 200)
        preview.resize(800, 600)
        preview.suppress = True
        self.assertTrue(preview.image_rect().isEmpty())
        image = preview.grab().toImage()
        self.assertEqual(image.pixelColor(30, 30).name(), '#0c120e')
        preview.suppress = False
        self.assertFalse(preview.image_rect().isEmpty())

    def test_record_edge_uses_the_registered_frame(self):
        self.window.preview.player = np.array([622.5, 470.5])
        self.window.record_edge(edge='north')
        np.testing.assert_allclose(self.window.edges['north'], [30622.5, 39470.5])
        self.window.busy = True
        self.window.record_edge(edge='east')
        self.assertNotIn('east', self.window.edges)

    def test_overlay_is_transparent_and_click_through(self):
        overlay = self.window.overlay
        overlay.resize(1000, 1000)
        overlay.alignment = self.alignment
        overlay.plan = self.window.plan
        self.assertTrue(overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        image = overlay.grab().toImage()
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.window.show_overlay.setChecked(True)
        self.window.refresh_overlay()
        self.assertFalse(overlay.isVisible(), 'Image-file matches must never enable the desktop overlay')

    def test_old_background_result_cannot_restore_cleared_alignment(self):
        results = []
        self.window.submit(lambda: 123, lambda value, error: results.append(value))
        self.window.clear_reference()
        deadline = time.monotonic()+4
        while self.window.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertFalse(self.window.busy)
        self.assertEqual(results, [])
        self.assertIsNone(self.window.preview.alignment)

    def test_qimage_color_and_padding_round_trip(self):
        image = np.random.default_rng(23).integers(0, 255, (71, 103, 3), dtype=np.uint8)
        np.testing.assert_equal(bgr(qimage(image)), image)


if __name__ == '__main__':
    unittest.main()
