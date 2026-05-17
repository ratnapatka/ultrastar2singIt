from __future__ import annotations

from enum import Enum
from io import BytesIO

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from pytablericons import TablerIcons, OutlineIcon, FilledIcon

ICON_SIZE = 16

class Color(Enum):
    BLUE = '#005f73'
    GREEN = '#0a9396'
    RED = '#ae2012'
    ORANGE = '#ca6702'

class Icon(Enum):
    START = TablerIcons.load(OutlineIcon.STATUS_CHANGE, color=Color.GREEN.value, stroke_width=2.5)
    STOP = TablerIcons.load(FilledIcon.PLAYER_STOP, color=Color.RED.value, stroke_width=2.5)
    CHECK = TablerIcons.load(OutlineIcon.CHECK, color=Color.GREEN.value, stroke_width=2.5)
    X = TablerIcons.load(OutlineIcon.X, color=Color.RED.value, stroke_width=2.5)
    FILE_CHECK = TablerIcons.load(OutlineIcon.FILE_CHECK, color=Color.BLUE.value, stroke_width=2.5)
    REFRESH = TablerIcons.load(OutlineIcon.REFRESH, color=Color.GREEN.value, stroke_width=2.5)
    FILE_X = TablerIcons.load(OutlineIcon.FILE_X, color=Color.RED.value, stroke_width=2.5)
    TRASH = TablerIcons.load(OutlineIcon.TRASH, color=Color.RED.value, stroke_width=2.5)
    ALERT_TRIANGLE = TablerIcons.load(OutlineIcon.ALERT_TRIANGLE, color=Color.ORANGE.value, stroke_width=2.5)
    INFO_SQUARE_ROUNDED = TablerIcons.load(OutlineIcon.INFO_SQUARE_ROUNDED, color=Color.BLUE.value, stroke_width=2.5)

    def get_icon(self: Icon) -> QIcon:
        try:
            return self._cached_icon
        except AttributeError:
            pass
        buffer = BytesIO()
        self.value.save(buffer, format='PNG')
        buffer.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.read())
        icon = QIcon(pixmap)
        self._cached_icon = icon  # type: ignore[attr-defined]
        return icon

_combined_cache: dict[tuple, QIcon] = {}

def combine_icons(icon1, icon2, size=ICON_SIZE):
    key = (id(icon1), id(icon2), size)
    cached = _combined_cache.get(key)
    if cached is not None:
        return cached
    pixmap = QPixmap(size * 2, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    icon1.paint(painter, 0, 0, size, size)
    icon2.paint(painter, size, 0, size, size)
    painter.end()
    icon = QIcon(pixmap)
    _combined_cache[key] = icon
    return icon
