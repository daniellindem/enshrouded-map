"""Qt desktop overlay. Run with python -m overlay.app from the repository root."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QShortcut, QKeySequence
from PySide6.QtMultimedia import QMediaCaptureSession, QScreenCapture, QVideoSink
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from .core import (Reference, detect_player, frame_signature, load_reference,
                   measure_edges, plan_link, read_plan, register, same_view)

COLORS = ['#ffffff', '#e8c78c', '#e0aa63', '#ed9153', '#d96d51']
EDGES = ['north', 'south', 'west', 'east']
ROOT = Path(__file__).resolve().parents[1]
STYLE = '''
QWidget { background: #16201c; color: #eee8d8; font-family: sans-serif; font-size: 13px; }
QMainWindow, QScrollArea { background: #101813; }
QGroupBox { border: 1px solid #3d493d; border-radius: 7px; margin-top: 15px; padding: 12px 8px 7px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #e8c78c; }
QPushButton { background: #304235; border: 1px solid #54634d; border-radius: 5px; padding: 8px 10px; }
QPushButton:hover { background: #42553d; border-color: #e8c78c; }
QPushButton:disabled { color: #899083; background: #242c25; border-color: #333d33; }
QLineEdit, QComboBox { background: #0f1712; border: 1px solid #52604e; border-radius: 4px; padding: 7px; }
QLabel#muted { color: #b0b9a8; font-size: 12px; }
QLabel#status { background: #25372b; padding: 10px; border-radius: 5px; }
QCheckBox { padding: 5px 0; }
QSplitter::handle { background: #3d493d; }
'''


def qimage(image):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()


def bgr(image):
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    data = np.frombuffer(rgba.bits(), np.uint8).reshape(rgba.height(), rgba.bytesPerLine())[:, :rgba.width()*4]
    return cv2.cvtColor(data.reshape(rgba.height(), rgba.width(), 4), cv2.COLOR_RGBA2BGR)


def paint_boundaries(painter, alignment, plan, compare=False):
    if alignment is None or not plan:
        return
    for altar in plan['altars']:
        if not altar.get('visible', True):
            continue
        x, y = alignment.screen([altar['x'], altar['y']])
        levels = [4, 3, 2, 1] if compare and altar['id'] == plan['selected'] else [altar['level']]
        for level in levels:
            size = alignment.side_pixels(level, plan['metersPerPixel'])
            color = QColor(COLORS[level])
            fill = QColor(color)
            fill.setAlpha(22 if level == altar['level'] else 6)
            painter.setBrush(fill)
            pen = QPen(color, 2)
            if level != altar['level']:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(QRectF(x-size/2, y-size/2, size, size))
            painter.drawText(QPointF(x-size/2+5, y-size/2-8), f'{level*40} m · altar {level}')
        painter.setPen(QPen(QColor('#fff3ce'), 2))
        painter.drawLine(QPointF(x-6, y), QPointF(x+6, y))
        painter.drawLine(QPointF(x, y-6), QPointF(x, y+6))
        painter.drawText(QPointF(x+12, y+5), altar['name'][:60])


class Preview(QWidget):
    regionSelected = Signal(object)
    pointSelected = Signal(object)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)
        self.image = None
        self.alignment = None
        self.plan = None
        self.roi = None
        self.player = None
        self.compare = False
        self.suppress = False
        self.mode = None
        self.start = self.end = None
        self.setStyleSheet('background: #0c120e;')

    def image_rect(self):
        if self.suppress or self.image is None:
            return QRectF()
        h, w = self.image.shape[:2]
        factor = min(self.width()/w, self.height()/h)
        return QRectF((self.width()-w*factor)/2, (self.height()-h*factor)/2, w*factor, h*factor)

    def image_point(self, point):
        rect = self.image_rect()
        if rect.isEmpty() or not rect.contains(point):
            return None
        return np.array([(point.x()-rect.x())*self.image.shape[1]/rect.width(),
                         (point.y()-rect.y())*self.image.shape[0]/rect.height()])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#0c120e'))
        if self.suppress:
            p.setPen(QColor('#b0b9a8'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       'Screen sharing active.\nReturn to this window to inspect the latest map.')
            return
        if self.image is None:
            p.setPen(QColor('#b0b9a8'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       'Import a Share plan, then load a game-map image\nor start screen sharing. Captures stay on this computer.')
            return
        rect = self.image_rect()
        p.drawImage(rect, qimage(self.image))
        p.translate(rect.x(), rect.y())
        p.scale(rect.width()/self.image.shape[1], rect.height()/self.image.shape[0])
        paint_boundaries(p, self.alignment, self.plan, self.compare)
        if self.player is not None:
            p.setPen(QPen(QColor('#85f5ce'), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            x, y = self.player
            p.drawEllipse(QPointF(x, y), 10, 10)
            p.drawLine(QPointF(x-18, y), QPointF(x+18, y))
            p.drawLine(QPointF(x, y-18), QPointF(x, y+18))
        if self.roi:
            x1, y1, x2, y2 = self.roi
            p.setPen(QPen(QColor('#85f5ce'), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(x1, y1, x2-x1, y2-y1))
        if self.start is not None and self.end is not None:
            a, b = self.start, self.end
            p.setPen(QPen(QColor('#85f5ce'), 2))
            p.setBrush(QColor(50, 200, 150, 30))
            p.drawRect(QRectF(QPointF(*a), QPointF(*b)).normalized())

    def mousePressEvent(self, event):
        point = self.image_point(event.position())
        if point is None or event.button() != Qt.MouseButton.LeftButton:
            return
        if self.mode == 'region':
            self.start = self.end = point
        elif self.mode in ('player', 'altar'):
            self.pointSelected.emit(point)

    def mouseMoveEvent(self, event):
        if self.start is not None:
            point = self.image_point(event.position())
            if point is not None:
                self.end = point
                self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None:
            return
        a, b = self.start, self.end
        self.start = self.end = None
        if np.linalg.norm(a-b) > 40:
            self.regionSelected.emit((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
        self.update()


class GameOverlay(QWidget):
    """A separate click-through OS window, never injected into the game."""
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowTitle('Embervale Atlas map overlay')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet('background: transparent;')
        self.alignment = None
        self.plan = None
        self.compare = False
        self.last_match = 0.
        self.expiry = QTimer(self)
        self.expiry.timeout.connect(self.expire)
        self.expiry.start(250)

    def expire(self):
        if time.monotonic()-self.last_match > 4:
            self.hide()

    def paintEvent(self, event):
        if self.alignment is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width()/self.alignment.width, self.height()/self.alignment.height)
        paint_boundaries(p, self.alignment, self.plan, self.compare)


class Signals(QObject):
    finished = Signal(object, object)


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()

    def run(self):
        try:
            self.signals.finished.emit(self.function(), None)
        except Exception as exc:
            self.signals.finished.emit(None, str(exc))


class MainWindow(QMainWindow):
    def __init__(self, cache=ROOT/'.overlay-cache'):
        super().__init__()
        self.setWindowTitle('Embervale Atlas · map overlay')
        self.resize(1220, 870)
        self.plan = None
        self.reference = None
        self.cache = Path(cache)
        self.edges = {}
        self.measurement = None
        self.busy = False
        self.job = None
        self.generation = 0
        self.last_capture = 0.
        self.last_signature_check = 0.
        self.latest_signature = None
        self.accepted_signature = None
        self.capture_received = 0.
        self.live_alignment = False
        self.source_kind = 'image'
        self.overlay = GameOverlay()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.session = QMediaCaptureSession(self)
        self.capture = QScreenCapture(self)
        self.sink = QVideoSink(self)
        self.session.setScreenCapture(self.capture)
        self.session.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.on_frame)
        self.capture.errorOccurred.connect(self.capture_error)
        self.capture.activeChanged.connect(self.capture_active_changed)
        self.preview = Preview()
        self.preview.regionSelected.connect(self.set_region)
        self.preview.pointSelected.connect(self.set_point)
        self.status = QLabel('Import a plan to choose the area to search. No game connection is used.')
        self.status.setObjectName('status')
        self.status.setWordWrap(True)
        self.quality = QLabel('No map alignment')
        self.quality.setObjectName('muted')
        self.quality.setWordWrap(True)
        self.build_ui()
        self.stale_timer = QTimer(self)
        self.stale_timer.timeout.connect(self.check_stale)
        self.stale_timer.start(1000)
        QShortcut(QKeySequence('Ctrl+O'), self).activated.connect(self.open_image)
        QShortcut(QKeySequence('Escape'), self).activated.connect(self.hide_overlay)

    def build_ui(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 10, 14, 14)
        title = QLabel('Embervale Atlas')
        title.setStyleSheet('font-size: 25px; color: #e8c78c; font-family: serif;')
        layout.addWidget(title)
        subtitle = QLabel('Map overlay · experimental')
        subtitle.setObjectName('muted')
        layout.addWidget(subtitle)
        layout.addWidget(self.status)
        plan_box = QGroupBox('1  Choose your plan')
        form = QVBoxLayout(plan_box)
        self.link = QLineEdit()
        self.link.setPlaceholderText('Paste the website’s Share plan link')
        self.link.returnPressed.connect(self.import_link)
        form.addWidget(self.link)
        row = QHBoxLayout()
        row.addWidget(self.button('Import link', self.import_link))
        row.addWidget(self.button('Open JSON', self.open_plan))
        form.addLayout(row)
        self.altar = QComboBox()
        self.altar.currentIndexChanged.connect(self.select_altar)
        form.addWidget(self.altar)
        self.zoom = QComboBox()
        for z, label in [(15, 'Nearby terrain · zoom 15'), (14, 'Wider area · zoom 14'), (13, 'Large area · zoom 13'), (16, 'Close detail · zoom 16')]:
            self.zoom.addItem(label, z)
        self.zoom.currentIndexChanged.connect(self.clear_reference)
        form.addWidget(self.zoom)
        form.addWidget(self.button('Load terrain near selected altar', self.fetch_reference))
        note = QLabel('Terrain imagery © MapGenie / respective owners. The plan gives an approximate location; matching determines map position and zoom.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        form.addWidget(note)
        layout.addWidget(plan_box)

        capture_box = QGroupBox('2  Align with the game map')
        form = QVBoxLayout(capture_box)
        row = QHBoxLayout()
        row.addWidget(self.button('Open map image…', self.open_image))
        self.align_button = self.button('Match terrain', self.match_image)
        row.addWidget(self.align_button)
        form.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.button('Select terrain region', lambda: self.set_mode('region')))
        row.addWidget(self.button('Reset region', lambda: self.set_region(None)))
        form.addLayout(row)
        self.screen = QComboBox()
        for i, screen in enumerate(QApplication.screens()):
            geo = screen.geometry()
            self.screen.addItem(f'{screen.name()} · {geo.width()} × {geo.height()}', i)
        self.screen.currentIndexChanged.connect(self.change_screen)
        form.addWidget(self.screen)
        note = QLabel('For live use, share the entire monitor selected above. Keep the game in a window or borderless mode. On Wayland, choose that monitor in the desktop sharing dialog too.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        form.addWidget(note)
        row = QHBoxLayout()
        self.share_button = self.button('Start screen sharing', self.start_capture)
        row.addWidget(self.share_button)
        row.addWidget(self.button('Stop', self.stop_capture))
        form.addLayout(row)
        self.show_overlay = QCheckBox('Show boundaries over the game map')
        self.show_overlay.toggled.connect(self.refresh_overlay)
        form.addWidget(self.show_overlay)
        self.compare = QCheckBox('Compare all four altar sizes')
        self.compare.toggled.connect(self.redraw)
        form.addWidget(self.compare)
        form.addWidget(self.button('Place selected altar at a point in preview', lambda: self.set_mode('altar')))
        form.addWidget(self.quality)
        layout.addWidget(capture_box)

        measure_box = QGroupBox('3  Measure the actual build area')
        form = QVBoxLayout(measure_box)
        note = QLabel('At the same altar, walk straight to each building boundary. Face north, open the map, then record the edge. Images can have different pans or zooms. Check the green player crosshair before applying.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        form.addWidget(note)
        row = QHBoxLayout()
        self.edge = QComboBox()
        for name in EDGES:
            self.edge.addItem(name.capitalize(), name)
        row.addWidget(self.edge)
        self.level = QComboBox()
        for i in range(1, 5):
            self.level.addItem(f'Altar {i} · {i*40} m side', i)
        self.level.currentIndexChanged.connect(self.update_measurement)
        row.addWidget(self.level)
        form.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.button('Load edge image…', self.open_edge))
        row.addWidget(self.button('Record current edge', self.record_edge))
        form.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.button('Mark player centre manually', lambda: self.set_mode('player')))
        row.addWidget(self.button('Clear edges', self.clear_edges))
        form.addLayout(row)
        self.edge_status = QLabel('North —  South —  West —  East —')
        self.edge_status.setWordWrap(True)
        form.addWidget(self.edge_status)
        self.measure_status = QLabel('Four edges provide the known distance. Terrain matching alone does not establish metres.')
        self.measure_status.setWordWrap(True)
        self.measure_status.setObjectName('muted')
        form.addWidget(self.measure_status)
        self.apply_button = self.button('Apply measured scale and altar centre', self.apply_measurement)
        self.apply_button.setEnabled(False)
        form.addWidget(self.apply_button)
        layout.addWidget(measure_box)
        row = QHBoxLayout()
        row.addWidget(self.button('Copy updated plan link', self.copy_plan))
        row.addWidget(self.button('Save plan JSON', self.save_plan))
        layout.addLayout(row)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setMinimumWidth(365)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.preview, 1)
        note = QLabel('Preview uses captured pixels. The desktop overlay shows boundaries only, stays click-through, and hides when terrain matching fails. Stop sharing hides it immediately. Esc hides it while this window is focused.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        right_layout.addWidget(note)
        split = QSplitter()
        split.addWidget(scroll)
        split.addWidget(right)
        split.setSizes([405, 815])
        self.setCentralWidget(split)

    @staticmethod
    def button(text, callback):
        b = QPushButton(text)
        b.clicked.connect(callback)
        return b

    def message(self, text):
        self.status.setText(text)

    def submit(self, function, done):
        if self.busy:
            self.message('Finishing the current match. Try again in a moment.')
            return False
        self.busy = True
        generation = self.generation
        self.job = Job(function)
        def finish(result, error):
            self.busy = False
            self.job = None
            if generation == self.generation:
                done(result, error)
        self.job.signals.finished.connect(finish)
        self.pool.start(self.job)
        return True

    def current_altar(self):
        if not self.plan:
            return None
        return next((a for a in self.plan['altars'] if a['id'] == self.plan['selected']), None)

    def set_plan(self, plan):
        self.stop_capture()
        self.plan = plan
        self.preview.plan = plan
        self.altar.blockSignals(True)
        self.altar.clear()
        for a in plan['altars']:
            self.altar.addItem(f'{a["name"]} · altar {a["level"]}', a['id'])
        self.altar.setCurrentIndex(max(0, self.altar.findData(plan['selected'])))
        self.altar.blockSignals(False)
        if self.current_altar():
            self.level.setCurrentIndex(self.current_altar()['level']-1)
        self.clear_reference()
        self.clear_edges()
        self.message('Plan imported. Load terrain near its selected altar, then capture the game map.')
        self.preview.update()

    def import_link(self):
        try:
            self.set_plan(read_plan(self.link.text()))
        except ValueError as exc:
            self.message(str(exc))

    def open_plan(self):
        name, _ = QFileDialog.getOpenFileName(self, 'Open plan', '', 'Plan JSON (*.json)')
        if name:
            try:
                self.set_plan(read_plan(Path(name).read_text(encoding='utf-8')))
            except (OSError, ValueError) as exc:
                self.message(str(exc))

    def select_altar(self):
        if self.plan and self.altar.currentData():
            self.plan['selected'] = self.altar.currentData()
            self.level.setCurrentIndex(self.current_altar()['level']-1)
            self.clear_reference()
            self.clear_edges()
            self.redraw()

    def clear_reference(self):
        self.generation += 1
        self.reference = None
        self.clear_alignment()

    def clear_alignment(self):
        self.live_alignment = False
        self.preview.alignment = None
        self.preview.player = None
        self.accepted_signature = None
        self.quality.setText('No map alignment')
        self.overlay.hide()
        self.preview.update()

    def fetch_reference(self):
        altar = self.current_altar()
        if altar is None:
            self.message('Import a plan containing at least one altar first.')
            return
        self.clear_alignment()
        zoom = self.zoom.currentData()
        center = [altar['x'], altar['y']]
        self.message('Loading nine terrain tiles near the selected altar…')
        def ready(result, error):
            if error:
                self.message(error)
                return
            self.reference = result
            self.message('Terrain loaded. Open a game-map image or start screen sharing.')
            if self.preview.image is not None:
                self.match_image()
        self.submit(lambda: load_reference(center, self.cache, zoom), ready)

    def load_image(self, path, record=None):
        try:
            raw = np.fromfile(path, dtype=np.uint8)
            image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if image is None or max(image.shape[:2]) > 12000:
                raise ValueError('Choose a PNG or JPEG map capture below 12,000 pixels per side.')
        except (ValueError, OSError) as exc:
            self.message(str(exc))
            return
        self.stop_capture()
        self.source_kind = 'image'
        self.preview.image = image
        self.preview.roi = None
        self.preview.update()
        self.message('Image loaded. Terrain matching uses the area near the selected plan altar.')
        if self.reference:
            self.match_image(record=record)
        else:
            self.message('Load terrain near the selected altar, then match this image.')

    def open_image(self):
        name, _ = QFileDialog.getOpenFileName(self, 'Open game-map image', '', 'Images (*.png *.jpg *.jpeg)')
        if name:
            self.load_image(name)

    def open_edge(self):
        if self.reference is None:
            self.message('Load terrain near the selected altar first.')
            return
        edge = self.edge.currentData()
        name, _ = QFileDialog.getOpenFileName(self, f'Open {edge} boundary image', '', 'Images (*.png *.jpg *.jpeg)')
        if name:
            self.load_image(name, record=edge)

    def set_mode(self, mode):
        if self.preview.image is None:
            self.message('Load a map capture first.')
            return
        if mode in ('altar', 'player') and self.preview.alignment is None:
            self.message('Match terrain before marking a point.')
            return
        if mode == 'player' and self.capture.isActive():
            self.stop_capture(keep_image=True)
            self.message('Sharing paused on this frame. Click the centre of the red player arrow.')
        else:
            self.message({'region': 'Drag a rectangle around clear terrain in the preview, avoiding HUD and fog.',
                          'altar': 'Click the exact altar centre in the preview.',
                          'player': 'Click the centre of the red player arrow in the preview.'}[mode])
        self.preview.mode = mode
        self.preview.setCursor(Qt.CursorShape.CrossCursor)

    def set_region(self, roi):
        self.generation += 1
        self.preview.mode = None
        self.preview.unsetCursor()
        self.preview.roi = roi
        self.clear_alignment()
        if not self.capture.isActive():
            self.match_image()

    def set_point(self, point):
        mode = self.preview.mode
        self.preview.mode = None
        self.preview.unsetCursor()
        if self.preview.alignment is None:
            return
        if mode == 'player':
            self.preview.player = point
            self.message('Player point marked. Record the selected edge to use it.')
        elif mode == 'altar':
            source = self.preview.alignment.source(point)
            if not all(0 <= v <= 65536 for v in source):
                self.message('That point lies outside the planner map.')
                return
            self.current_altar().update(x=float(source[0]), y=float(source[1]))
            self.clear_edges()
            self.message('Altar moved in this companion plan. Copy the updated link to bring it back to the website.')
        self.redraw()

    def match_image(self, checked=False, record=None):
        if self.preview.image is None or self.reference is None:
            self.message('Load terrain and a game-map capture first.')
            return
        if self.busy:
            return
        image, reference, roi = self.preview.image, self.reference, self.preview.roi
        previous = self.preview.alignment
        live = self.capture.isActive() and self.source_kind == 'live'
        signature = frame_signature(image) if live else None
        self.message('Matching terrain…')
        def ready(result, error):
            if live and not same_view(signature, self.latest_signature):
                self.clear_alignment()
                self.message('The map moved while matching. Waiting for a stable map view.')
                return
            if error:
                self.clear_alignment()
                self.message(error)
                return
            self.preview.image = image
            self.preview.alignment = result
            self.live_alignment = live and self.capture.isActive()
            self.accepted_signature = signature
            try:
                self.preview.player = detect_player(image)
            except ValueError:
                self.preview.player = None
            self.message('Map aligned. Boundaries follow the terrain. Review the player crosshair before recording an edge.')
            self.redraw()
            if record:
                self.record_edge(edge=record)
        self.submit(lambda: register(image, reference, roi, previous=previous), ready)

    def start_capture(self):
        if self.reference is None:
            self.message('Load terrain near the selected altar before sharing.')
            return
        if self.capture.isActive():
            return
        self.generation += 1
        self.clear_alignment()
        self.preview.roi = None
        self.source_kind = 'live'
        self.last_capture = 0.
        self.last_signature_check = 0.
        self.latest_signature = None
        self.capture_received = time.monotonic()
        # Wayland requires the system ScreenCast chooser. Qt ignores setScreen there.
        if os.environ.get('XDG_SESSION_TYPE') != 'wayland':
            self.capture.setScreen(QApplication.screens()[self.screen.currentIndex()])
        self.share_button.setEnabled(False)
        self.message('Choose the entire game monitor in the sharing dialog, then open the world map.')
        self.capture.start()

    def stop_capture(self, checked=False, keep_image=False):
        self.generation += 1
        self.capture.stop()
        self.share_button.setEnabled(True)
        self.live_alignment = False
        self.overlay.hide()
        if not keep_image:
            self.clear_alignment()
        self.source_kind = 'image'
        self.preview.suppress = False
        self.preview.update()

    def capture_error(self, error, message):
        self.stop_capture()
        self.message(f'Screen sharing stopped: {message}. You can still load map screenshots.')

    def capture_active_changed(self, active):
        self.share_button.setEnabled(not active)
        if not active:
            self.live_alignment = False
            self.overlay.hide()

    def change_screen(self):
        self.stop_capture()
        self.hide_overlay()
        self.message('Output monitor changed. Start sharing again and select the same monitor in the desktop chooser.')

    def on_frame(self, frame):
        if not self.capture.isActive() or not frame.isValid():
            return
        self.capture_received = time.monotonic()
        # Keep our own preview out of the live matching loop.
        if self.isActiveWindow():
            self.overlay.hide()
            return
        if self.capture_received-self.last_signature_check < .2:
            return
        self.last_signature_check = self.capture_received
        image = frame.toImage()
        if image.isNull():
            return
        captured = bgr(image)
        self.latest_signature = frame_signature(captured)
        if self.accepted_signature is not None and not same_view(self.accepted_signature, self.latest_signature):
            self.clear_alignment()
        if self.busy or self.capture_received-self.last_capture < 1.0:
            return
        self.last_capture = self.capture_received
        if self.preview.image is not None and self.preview.image.shape != captured.shape:
            self.clear_alignment()
            self.preview.roi = None
        self.preview.image = captured
        self.source_kind = 'live'
        self.match_image()

    def check_stale(self):
        if self.capture.isActive() and time.monotonic()-self.capture_received > 5:
            self.clear_alignment()
            self.message('Waiting for shared screen frames. Boundaries are hidden.')

    def refresh_overlay(self):
        if not (self.show_overlay.isChecked() and self.capture.isActive() and self.live_alignment
                and self.preview.alignment and not self.isActiveWindow()):
            self.overlay.hide()
            return
        self.overlay.alignment = self.preview.alignment
        self.overlay.plan = self.plan
        self.overlay.compare = self.compare.isChecked()
        self.overlay.last_match = time.monotonic()
        self.overlay.setGeometry(QApplication.screens()[self.screen.currentIndex()].geometry())
        self.overlay.show()
        self.overlay.update()

    def hide_overlay(self):
        self.show_overlay.setChecked(False)
        self.overlay.hide()

    def redraw(self):
        self.preview.compare = self.compare.isChecked()
        a = self.preview.alignment
        if a is not None and self.plan:
            self.quality.setText(f'{a.patches} terrain checks · {a.error:.1f} px fit residual · match {a.score:.2f}\nScale: {self.plan["metersPerPixel"]:.6f} m/source px. Residual is not absolute accuracy.')
        self.preview.update()
        self.refresh_overlay()

    def record_edge(self, checked=False, edge=None):
        if self.busy:
            self.message('Wait for terrain matching to finish before recording an edge.')
            return
        alignment, player = self.preview.alignment, self.preview.player
        if alignment is None or player is None:
            self.message('Match this map image, then mark the player centre if automatic detection missed it.')
            return
        edge = edge or self.edge.currentData()
        self.edges[edge] = alignment.source(player).tolist()
        self.update_measurement()
        self.message(f'{edge.capitalize()} edge recorded from the green crosshair. Choose the next edge or review the scale.')
        self.preview.update()

    def clear_edges(self):
        self.edges.clear()
        self.update_measurement()

    def update_measurement(self):
        self.measurement = None
        self.apply_button.setEnabled(False)
        self.edge_status.setText('   '.join(f'{k.capitalize()} {"✓" if k in self.edges else "—"}' for k in EDGES))
        if len(self.edges) < 4:
            self.measure_status.setText(f'{len(self.edges)}/4 edges recorded. Altar upgrade level determines the known side length; global Flame strength does not.')
            return
        try:
            self.measurement = measure_edges(self.edges, self.level.currentData())
            value = self.measurement
            self.measure_status.setText(f'Measured {value["metersPerPixel"]:.6f} m/source pixel.\nAxes differ by {value["axisDifference"]:.1%}. This is measurement agreement, not absolute accuracy.')
            self.apply_button.setEnabled(True)
        except ValueError as exc:
            self.measure_status.setText(str(exc))

    def apply_measurement(self):
        if not self.plan or self.measurement is None:
            return
        m = self.measurement
        if not all(0 <= v <= 65536 for v in m['center']):
            self.message('Measured altar centre is outside the planner map.')
            return
        self.plan.update(metersPerPixel=float(m['metersPerPixel']), scaleRevision=2, calibrated=True)
        a = self.current_altar()
        a.update(x=float(m['center'][0]), y=float(m['center'][1]), level=self.level.currentData())
        self.plan['center'] = {'x': a['x'], 'y': a['y']}
        self.message('Measured scale and altar centre applied. Copy the updated plan link or save JSON to keep this result.')
        self.redraw()

    def copy_plan(self):
        if self.plan:
            QApplication.clipboard().setText(plan_link(self.plan))
            self.message('Updated Share plan link copied. Opening it in the website imports these changes.')

    def save_plan(self):
        if not self.plan:
            return
        name, _ = QFileDialog.getSaveFileName(self, 'Save companion plan', 'embervale-plan.json', 'Plan JSON (*.json)')
        if name:
            try:
                Path(name).write_text(json.dumps(self.plan, indent=2, ensure_ascii=False), encoding='utf-8')
                self.message('Plan saved. Screenshots were not included.')
            except OSError as exc:
                self.message(str(exc))

    def closeEvent(self, event):
        self.stop_capture()
        self.overlay.close()
        self.pool.waitForDone()
        event.accept()

    def changeEvent(self, event):
        # An inactive companion must not display a terrain image that its own
        # full-monitor capture could mistake for the game map on the desktop.
        if event.type() == QEvent.Type.ActivationChange and hasattr(self, 'capture') and hasattr(self, 'preview'):
            self.preview.suppress = self.capture.isActive() and not self.isActiveWindow()
            self.preview.update()
            if self.isActiveWindow():
                self.overlay.hide()
        super().changeEvent(event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, help='Plan JSON or a file containing a Share plan URL')
    parser.add_argument('--image', type=Path, help='Load a game-map screenshot without screen sharing')
    parser.add_argument('--reference', type=Path, help='Local terrain mosaic for offline inspection')
    parser.add_argument('--origin', type=float, nargs=2, default=[0, 0], metavar=('X', 'Y'))
    parser.add_argument('--factor', type=float, default=2., help='Source zoom-16 pixels per reference image pixel')
    parser.add_argument('--render', type=Path, help='Write the initial UI to a PNG and exit; use QT_QPA_PLATFORM=offscreen for headless QA')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('Embervale Atlas')
    app.setStyleSheet(STYLE)
    window = MainWindow()
    try:
        if args.plan:
            window.set_plan(read_plan(args.plan.read_text(encoding='utf-8')))
        if args.reference:
            image = cv2.imread(str(args.reference))
            if image is None or not np.isfinite(args.factor) or args.factor <= 0:
                raise ValueError('Invalid local terrain reference or factor.')
            window.reference = Reference(image, *args.origin, args.factor)
        if args.image:
            window.load_image(str(args.image))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    window.show()
    if args.render:
        deadline = time.monotonic()+30
        def render():
            if window.busy and time.monotonic() < deadline:
                QTimer.singleShot(200, render)
                return
            window.grab().save(str(args.render))
            print(window.status.text(), flush=True)
            print(window.quality.text(), flush=True)
            window.close()
            app.quit()
        QTimer.singleShot(500, render)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
