from __future__ import annotations

import os
import re
import sys
import threading
from html import escape
from pathlib import Path
from typing import List, Tuple

import markdown
import qdarktheme
import unicodedata
import yaml
from PySide6 import QtCore
from PySide6.QtCore import Qt, QDateTime, QFileSystemWatcher, QThread, Signal
from PySide6.QtGui import QIcon, QRegularExpressionValidator
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QCheckBox, QTextEdit, QTableWidgetItem, QFileDialog, QGroupBox,
                               QGridLayout, QAbstractItemView,
                               QAbstractButton, QDialog, QTextBrowser, QDialogButtonBox, QComboBox)

import GuiElement
import data.repository.DlcRepository as repository
from PreviewTable import PreviewTable
from config_loader import load_config

JSON = "json"
XML = "xml"

BROWSE = "Browse"

VIDEO_EXTENSIONS = ('.mp4', '.mpeg', '.avi', '.divx', '.mkv', '.webm')
AUDIO_EXTENSIONS = ('.mp3', '.ogg', '.aac', '.wav', '.flac')
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp')
TXT_EXTENSIONS = '.txt'

DEFAULT_INPUT_FOLDER_NAME = "My Songs"
DEFAULT_OUTPUT_FOLDER_NAME = "_Patch"

class ConversionWorker(QThread):
    log_message = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, cfg, stop_event):
        super().__init__()
        self.cfg = cfg
        self.stop_event = stop_event

    def run(self):
        try:
            import ConvertFiles
            ConvertFiles.main(self.cfg, stop_event=self.stop_event)
        except Exception as e:
            self.error.emit(str(e))
            return
        self.finished.emit()


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')

def construct_name_id_from_directory_name(dir_long_name) -> str:
    split_dir_name = dir_long_name.split(' - ')
    artist_dir_name = strip_accents(split_dir_name[0])
    title_dir_name = strip_accents(split_dir_name[1])
    artist_caps = [word[0].upper() for word in artist_dir_name.split()]
    artist_cap = ''.join(artist_caps)
    title_lower = ''.join(e.lower() for e in title_dir_name if e.isalnum())
    return artist_cap + title_lower

def set_element_enabled(element, is_enabled: bool) -> None:
    if not is_enabled and isinstance(element, QLineEdit):
        mark_field_valid(element, True)
    element.setEnabled(is_enabled)

def mark_field_valid(line_edit: QLineEdit, valid: bool) -> None:
    line_edit.setProperty("has_border", "true" if not valid else "false")
    # refresh style
    line_edit.style().unpolish(line_edit)
    line_edit.style().polish(line_edit)
    line_edit.update()

def apply_theme_change(theme, app) -> None:
    if theme.name == 'Dark':
        tooltip_style = """ QToolTip {
                color: #ffffff;
                background-color: #2d2d2d;
                border: 1px solid #555555;
                padding: 4px;
            }"""
    else:
        tooltip_style = """ QToolTip {
                color: #000000;
                background-color: #f5f5f0;
                border: 1px solid #aaaaaa;
                padding: 4px;
            }"""
    current = app.styleSheet()
    app.setStyleSheet(current + tooltip_style)

def make_legend_item(icon: QIcon, text: str) -> QWidget:
    """Small (icon + text) widget for the legend."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(2, 0, 0, 0)
    lay.setSpacing(0)

    icon_lbl = QLabel()
    icon_lbl.setPixmap(icon.pixmap(14, 14))
    icon_lbl.setFixedSize(16, 16)

    text_lbl = QLabel(text)
    text_lbl.setStyleSheet("color: #666666;")

    lay.addWidget(icon_lbl)
    lay.addWidget(text_lbl)
    return w

def is_blank(s) -> bool:
    return not (s and not str(s).isspace())

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.game_format = JSON
        self.init_elements()
        self.setStyleSheet(f"""
            QLineEdit {{ height: 18px; }}
            QLineEdit[has_border="true"] {{ border: 1px solid #b0534c; }}
        """)
        self.int_validator = QRegularExpressionValidator('(^[0-9]+$|^$)')

        self.setWindowTitle("Let's Sing DLC Patcher")
        self.setWindowIcon(GuiElement.Icon.MICROPHONE.get_icon())
        self.setGeometry(100, 100, 1400, 800)
        self.conversion_running = False

        self.folder_watcher = QFileSystemWatcher(self)
        self.folder_watcher.directoryChanged.connect(self.refresh_preview_from_watcher)
        self.folder_watcher.fileChanged.connect(self.refresh_preview_from_watcher)

        # Central widget with main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Create left and right panels
        left_panel = self.create_left_panel()
        right_panel = self.create_right_panel()

        # Add panels to main layout
        main_layout.addWidget(left_panel, stretch=2)
        main_layout.addWidget(right_panel, stretch=3)

        self.field_validators = {
            self.core_id_input: self.core_id_input_fv,
            self.dlc_id_input: self.dlc_id_input_fv,
            self.dlc_json_name_input: self.dlc_json_name_input_fv,
            self.ffmpeg_path: self.ffmpeg_path_fv,
            self.rad_path: self.rad_path_fv,
            self.input_path: self.input_path_fv,
            self.max_video_size: self.max_video_size_fv,
            self.output_path: self.output_path_fv,
            self.dlc_name_txt_path: self.dlc_name_txt_path_fv,
            self.dlc_tsv_path: self.dlc_tsv_path_fv,
            self.dlc_json_path: self.dlc_json_path_fv,
        }
        self.cfg = load_config()
        self.set_defaults()

    def core_id_input_fv(self) -> bool:
        text = self.core_id_input.text().strip()
        valid = text and re.search(r'[0-F]{16}', text) is not None
        mark_field_valid(self.core_id_input, valid)
        return valid

    def dlc_id_input_fv(self) -> bool:
        text = self.dlc_id_input.text().strip()
        valid = text and re.search(r'[0-F]{16}', text) is not None
        mark_field_valid(self.dlc_id_input, valid)
        return valid

    def dlc_json_name_input_fv(self) -> bool:
        mark_field_valid(self.dlc_json_name_input, True)
        self.game_format = JSON if self.dlc_json_name_input.text() != '' else XML
        self.include_dlc_checkbox_refresh()
        set_element_enabled(self.rad_label, True if self.game_format == JSON else False)
        set_element_enabled(self.rad_path, True if self.game_format == JSON else False)
        set_element_enabled(self.rad_browse, True if self.game_format == JSON else False)
        return True

    def core_edition_combo_fv(self, edition: str) -> None:
        core_data = self.core_edition_combo.currentData()
        self.core_id_input.setText(core_data["core_id"] if core_data else "")
        self.dlc_name_combo.clear()
        if edition == "other":
            set_element_enabled(self.core_id_label, True)
            set_element_enabled(self.core_id_input, True)
        else:
            set_element_enabled(self.core_id_label, False)
            set_element_enabled(self.core_id_input, False)
            dlcs = repository.get_by_core_edition(edition)
            for dlc in dlcs:
                self.dlc_name_combo.addItem(dlc.dlc_name, userData = {"dlc_id": dlc.dlc_id, "dlc_json_name": dlc.dlc_json_name})
        self.dlc_name_combo.addItem("other", userData={"dlc_id": None, "dlc_json_name": None})

    def dlc_name_combo_fv(self, dlc_name: str) -> None:
        if dlc_name == "other":
            set_element_enabled(self.dlc_id_label, True)
            set_element_enabled(self.dlc_id_input, True)
            set_element_enabled(self.dlc_json_name_label, True)
            set_element_enabled(self.dlc_json_name_input, True)
        else:
            set_element_enabled(self.dlc_id_label, False)
            set_element_enabled(self.dlc_id_input, False)
            set_element_enabled(self.dlc_json_name_label, False)
            set_element_enabled(self.dlc_json_name_input, False)
        dlc_data = self.dlc_name_combo.currentData()
        self.dlc_id_input.setText(dlc_data["dlc_id"] if dlc_data else "")
        self.dlc_json_name_input.setText(dlc_data["dlc_json_name"] if dlc_data else "")
        self.dlc_json_name_input_fv()

    def create_left_panel(self) -> QWidget:
        """Create left panel with Game Info, Tools, and Tweaks"""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        ## Game Info Section
        game_info_group = QGroupBox("Game Info")
        game_info_layout = QGridLayout()

        # game and DLC version
        self.core_id_input.editingFinished.connect(self.core_id_input_fv)
        self.dlc_id_input.editingFinished.connect(self.dlc_id_input_fv)
        self.dlc_json_name_input.editingFinished.connect(self.dlc_json_name_input_fv)

        self.core_edition_combo.currentTextChanged.connect(self.core_edition_combo_fv)
        self.dlc_name_combo.currentTextChanged.connect(self.dlc_name_combo_fv)
        for core in repository.get_core_editions():
            self.core_edition_combo.addItem(core.core_edition, userData={"core_id": core.core_id})
        self.core_edition_combo.addItem("other", userData={"core_id": None})

        game_info_layout.addWidget(self.lets_sing_label, 0, 0)
        game_info_layout.addWidget(self.core_edition_combo, 0, 1)
        game_info_layout.addWidget(self.core_id_label, 1, 0)
        game_info_layout.addWidget(self.core_id_input, 1, 1)

        game_info_layout.addWidget(self.dlc_name_label, 2, 0)
        game_info_layout.addWidget(self.dlc_name_combo, 2, 1)
        game_info_layout.addWidget(self.dlc_id_label, 3, 0)
        game_info_layout.addWidget(self.dlc_id_input, 3, 1)
        game_info_layout.addWidget(self.dlc_json_name_label, 4, 0)
        game_info_layout.addWidget(self.dlc_json_name_input, 4, 1)

        game_info_group.setLayout(game_info_layout)
        left_layout.addWidget(game_info_group)

        # Tools Section
        tools_group = QGroupBox("Conversion tools")
        tools_layout = QGridLayout()

        # FFMPEG
        tools_layout.addWidget(self.ffmpeg_label, 0, 0)
        self.ffmpeg_path.editingFinished.connect(self.ffmpeg_path_fv)
        tools_layout.addWidget(self.ffmpeg_path, 0, 1)
        self.ffmpeg_browse.clicked.connect(lambda: self.browse_file(self.ffmpeg_path, "ffmpeg (*.exe)"))
        tools_layout.addWidget(self.ffmpeg_browse, 0, 2)

        # RAD
        tools_layout.addWidget(self.rad_label, 1, 0)
        self.rad_path.editingFinished.connect(self.rad_path_fv)
        tools_layout.addWidget(self.rad_path, 1, 1)
        self.rad_browse.clicked.connect(lambda: self.browse_file(self.rad_path, "radvideo64 (*.exe)"))
        tools_layout.addWidget(self.rad_browse, 1, 2)

        tools_group.setLayout(tools_layout)
        left_layout.addWidget(tools_group)

        input_output_group = QGroupBox("Input and Output folders")
        input_output_layout = QGridLayout()

        # Input
        input_output_layout.addWidget(self.input_label, 2, 0)
        self.input_path.editingFinished.connect(self.input_path_fv)
        input_output_layout.addWidget(self.input_path, 2, 1)
        self.input_input_browse.clicked.connect(lambda: self.browse_folder(self.input_path))
        input_output_layout.addWidget(self.input_input_browse, 2, 2)

        # Output
        input_output_layout.addWidget(self.output_label, 3, 0)
        self.output_path.editingFinished.connect(self.output_path_fv)
        input_output_layout.addWidget(self.output_path, 3, 1)
        self.output_browse.clicked.connect(lambda: self.browse_folder(self.output_path))
        input_output_layout.addWidget(self.output_browse, 3, 2)

        input_output_group.setLayout(input_output_layout)
        left_layout.addWidget(input_output_group)

        # Tweaks Section
        self.tweaks_group = QGroupBox("Conversion tweaks")
        tweaks_layout = QVBoxLayout()

        # Include DLC songs checkbox
        self.include_dlc_checkbox.clicked.connect(self.include_dlc_checkbox_refresh)
        tweaks_layout.addWidget(self.include_dlc_checkbox)

        # Name.txt
        name_layout = QHBoxLayout()
        name_layout.addWidget(self.name_txt_label)
        self.dlc_name_txt_path.editingFinished.connect(self.dlc_name_txt_path_fv)
        name_layout.addWidget(self.dlc_name_txt_path)
        self.name_txt_browse.clicked.connect(lambda: self.browse_file(self.dlc_name_txt_path, "name (*.txt)"))
        name_layout.addWidget(self.name_txt_browse)
        tweaks_layout.addLayout(name_layout)

        # SongsDLC.tsv
        songs_dlc_layout = QHBoxLayout()
        songs_dlc_layout.addWidget(self.songs_dlc_label)
        self.dlc_tsv_path.editingFinished.connect(self.dlc_tsv_path_fv)
        songs_dlc_layout.addWidget(self.dlc_tsv_path)
        self.songs_dlc_browse.clicked.connect(lambda: self.browse_file(self.dlc_tsv_path, "SongsDLC (*.tsv)"))
        songs_dlc_layout.addWidget(self.songs_dlc_browse)
        tweaks_layout.addLayout(songs_dlc_layout)

        # Songs_xx.json
        songs_json_layout = QHBoxLayout()
        songs_json_layout.addWidget(self.songs_json_label)
        self.dlc_json_path.editingFinished.connect(self.dlc_json_path_fv)
        songs_json_layout.addWidget(self.dlc_json_path)
        self.songs_json_browse.clicked.connect(lambda: self.browse_file(self.dlc_json_path, "songs_xx (*.json)"))
        songs_json_layout.addWidget(self.songs_json_browse)
        tweaks_layout.addLayout(songs_json_layout)

        # Slow/Accurate pitch correction
        tweaks_layout.addWidget(self.pitch_correction_checkbox)

        # Still video
        tweaks_layout.addWidget(self.still_video_checkbox)

        # Max video size
        max_video_layout = QHBoxLayout()
        max_video_layout.addWidget(self.max_video_label)
        self.max_video_size.setValidator(self.int_validator)
        self.max_video_size.editingFinished.connect(self.max_video_size_fv)
        max_video_layout.addWidget(self.max_video_size)
        max_video_layout.addStretch()
        tweaks_layout.addLayout(max_video_layout)

        # Ignore medley checkbox
        tweaks_layout.addWidget(self.ignore_medley_checkbox)

        tweaks_content = QWidget()
        tweaks_content.setLayout(tweaks_layout)
        tweaks_outer_layout = QVBoxLayout()
        tweaks_outer_layout.addWidget(tweaks_content)
        self.tweaks_group.setLayout(tweaks_outer_layout)
        self.tweaks_group.toggled.connect(tweaks_content.setVisible)
        self.tweaks_group.setCheckable(True)
        self.tweaks_group.setChecked(False)

        left_layout.addWidget(self.tweaks_group)
        left_layout.addStretch()

        # Help button
        help_button_layout = QHBoxLayout()
        self.help_button.setIcon(GuiElement.Icon.INFO_SQUARE_ROUNDED.get_icon())
        self.help_button.clicked.connect(self.show_help)
        help_button_layout.addWidget(self.help_button)
        help_button_layout.addStretch()
        left_layout.addLayout(help_button_layout)
        return left_widget

    def create_right_panel(self) -> QWidget:
        """Create right panel with Logs and Preview"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.logs_text.setReadOnly(True)
        self.logs_text.setFixedHeight(150)

        # Preview Section
        preview_group = self.create_preview_table()
        right_layout.addWidget(preview_group, stretch=5)

        # Logs Section
        logs_group = QGroupBox("Logs")
        logs_layout = QVBoxLayout()


        logs_layout.addWidget(self.logs_text)

        logs_buttons_layout = QHBoxLayout()
        logs_buttons_layout.addStretch()
        self.clear_logs_button.setIcon(GuiElement.Icon.TRASH.get_icon())
        self.clear_logs_button.clicked.connect(self.clear_logs)
        logs_buttons_layout.addWidget(self.clear_logs_button)
        logs_layout.addLayout(logs_buttons_layout)

        logs_group.setLayout(logs_layout)
        right_layout.addWidget(logs_group)

        return right_widget

    def create_preview_table(self) -> QGroupBox:
        preview_group = QGroupBox("Input folder preview")
        preview_layout = QVBoxLayout()

        # Song preview table
        self.preview_table.checkboxStateChanged.connect(self.update_clear_cache_enabled)

        preview_layout.addWidget(self.preview_table)
        preview_layout.addWidget(self.build_preview_legend())

        # Preview buttons
        preview_buttons_layout = QHBoxLayout()
        self.refresh_button.setIcon(GuiElement.Icon.REFRESH.get_icon())
        self.refresh_button.clicked.connect(self.refresh_preview)
        preview_buttons_layout.addWidget(self.refresh_button)

        self.clear_cache_button.setIcon(GuiElement.Icon.FILE_X.get_icon())
        self.clear_cache_button.clicked.connect(self.clear_cache)
        preview_buttons_layout.addWidget(self.clear_cache_button)

        preview_buttons_layout.addStretch()

        self.stop_button.setIcon(GuiElement.Icon.STOP.get_icon())
        self.stop_button.setIconSize(QtCore.QSize(GuiElement.ICON_SIZE, GuiElement.ICON_SIZE))
        self.stop_button.clicked.connect(self.stop_conversion)

        self.start_button.setIcon(GuiElement.Icon.START.get_icon())
        self.start_button.setIconSize(QtCore.QSize(GuiElement.ICON_SIZE, GuiElement.ICON_SIZE))
        self.start_button.clicked.connect(self.start_conversion)

        preview_buttons_layout.addWidget(self.stop_button)
        preview_buttons_layout.addWidget(self.start_button)

        preview_layout.addLayout(preview_buttons_layout)

        preview_group.setLayout(preview_layout)
        return preview_group

    def build_preview_legend(self) -> QWidget:
        """Legend shown under the preview table."""
        legend = QWidget()
        lay = QHBoxLayout(legend)
        lay.setContentsMargins(0, 0, 0, 0)

        lay.addStretch()
        lay.addWidget(make_legend_item(GuiElement.Icon.CHECK.get_icon(), "Input file exists"))
        lay.addWidget(make_legend_item(GuiElement.Icon.X.get_icon(), "Input file missing"))
        lay.addWidget(
            make_legend_item(GuiElement.Icon.FILE_CHECK.get_icon(), "Converted file cached"))
        lay.addStretch()
        return legend

    def ffmpeg_path_fv(self) -> bool:
        path = self.ffmpeg_path.text().strip()
        valid = path and os.path.isfile(path) and path.lower().endswith('ffmpeg.exe')
        mark_field_valid(self.ffmpeg_path, valid)
        return valid

    def rad_path_fv(self) -> bool:
        path = self.rad_path.text().strip()
        valid = path and os.path.isfile(path) and path.lower().endswith('radvideo64.exe')
        mark_field_valid(self.rad_path, valid)
        return valid

    def output_path_fv(self) -> bool:
        path = self.output_path.text().strip()

        if not path:
            mark_field_valid(self.output_path, False)
            return False
        if os.path.isdir(path):
            for file_or_folder in os.listdir(path):
                if os.path.isfile(file_or_folder) or not re.search(r'^[0-9A-F]{16}', file_or_folder):
                    #chosen folder contains unknown files or folders, append _Patch subfolder to path and approve
                    self.output_path.setText(os.path.join(path, DEFAULT_OUTPUT_FOLDER_NAME))
                    break
        mark_field_valid(self.output_path, True)
        return True

    def input_path_fv(self) -> bool:
        path = self.input_path.text().strip()
        if path and os.path.isdir(path):
            for folder in os.listdir(path):
                # the input folder should contain at least one "Artist Name - Song Title" folder
                if os.path.isdir(os.path.join(path, folder)) and re.search(r'^((?:.*\S)?)\s-\s(\S(?:.*\S)?)$', folder):
                    mark_field_valid(self.input_path, True)
                    self.sync_watched_folders(path)
                    self.scan_input_folder()
                    return True
        mark_field_valid(self.input_path, False)
        self.clear_preview()
        return False

    def dlc_name_txt_path_fv(self) -> bool:
        path = self.dlc_name_txt_path.text().strip()
        valid = path and os.path.isfile(path) and path.endswith('name.txt')
        mark_field_valid(self.dlc_name_txt_path, valid)
        return valid

    def dlc_tsv_path_fv(self) -> bool:
        path = self.dlc_tsv_path.text().strip()
        valid = path and os.path.isfile(path) and path.endswith('SongsDLC.tsv')
        mark_field_valid(self.dlc_tsv_path, valid)
        return valid

    def dlc_json_path_fv(self) -> bool:
        path = self.dlc_json_path.text().strip()
        valid = path and os.path.isfile(path)
        mark_field_valid(self.dlc_json_path, valid)
        return valid

    def still_video_checkbox_fv(self) -> None:
        set_element_enabled(self.max_video_label, not self.still_video_checkbox.isChecked())
        set_element_enabled(self.max_video_size, not self.still_video_checkbox.isChecked())

    def max_video_size_fv(self) -> bool:
        self.max_video_size.setText(str(max(10, min(int(self.max_video_size.text() or 50), 200))))
        return True

    def include_dlc_checkbox_refresh(self) -> None:
        """Enable/disable DLC related fields based on checkbox"""
        if self.include_dlc_checkbox.isChecked():
            if self.game_format == XML:
                set_element_enabled(self.name_txt_label, True)
                set_element_enabled(self.dlc_name_txt_path, True)
                set_element_enabled(self.name_txt_browse, True)
                set_element_enabled(self.songs_dlc_label, True)
                set_element_enabled(self.dlc_tsv_path, True)
                set_element_enabled(self.songs_dlc_browse, True)
                set_element_enabled(self.songs_json_label, False)
                set_element_enabled(self.dlc_json_path, False)
                set_element_enabled(self.songs_json_browse, False)
            elif self.game_format == JSON:
                set_element_enabled(self.name_txt_label, False)
                set_element_enabled(self.dlc_name_txt_path, False)
                set_element_enabled(self.name_txt_browse, False)
                set_element_enabled(self.songs_dlc_label, False)
                set_element_enabled(self.dlc_tsv_path, False)
                set_element_enabled(self.songs_dlc_browse, False)
                set_element_enabled(self.songs_json_label, True)
                set_element_enabled(self.dlc_json_path, True)
                set_element_enabled(self.songs_json_browse, True)
        else:
            set_element_enabled(self.name_txt_label, False)
            set_element_enabled(self.dlc_name_txt_path, False)
            set_element_enabled(self.name_txt_browse, False)
            set_element_enabled(self.songs_dlc_label, False)
            set_element_enabled(self.dlc_tsv_path, False)
            set_element_enabled(self.songs_dlc_browse, False)
            set_element_enabled(self.songs_json_label, False)
            set_element_enabled(self.dlc_json_path, False)
            set_element_enabled(self.songs_json_browse, False)

    def set_defaults(self) -> None:
        """Set default values for inputs from config"""
        dlc_entity = repository.get_by_dlc_id(str(self.cfg.dlc.id))
        if dlc_entity is not None:
            self.core_edition_combo.setCurrentText(dlc_entity.core_edition)
            self.core_id_input.setText(dlc_entity.core_id)
            self.dlc_name_combo.setCurrentText(dlc_entity.dlc_name)
            self.dlc_id_input.setText(dlc_entity.dlc_id)
            self.dlc_json_name_input.setText(dlc_entity.dlc_json_name)
        else:
            edition_entity = repository.get_edition_by_core_id(str(self.cfg.core.id))
            self.core_edition_combo.setCurrentText(edition_entity)
            self.core_id_input.setText(str(self.cfg.core.id))
            self.dlc_name_combo.setCurrentText('other')
            self.dlc_id_input.setText(str(self.cfg.dlc.id))
            if not is_blank(self.cfg.dlc.json_name):
                self.dlc_json_name_input.setText(str(self.cfg.dlc.json_name))

        self.core_id_input_fv()
        self.dlc_id_input_fv()
        self.dlc_json_name_input_fv()
        self.prefill_ffmpeg_path()
        self.prefill_rad_path()
        self.prefill_input_output_paths()

        self.tweaks_group.setChecked(self.cfg.conversion_tweaks.enable)
        self.include_dlc_checkbox.setChecked(self.cfg.conversion_tweaks.dlc_songs.include)
        if not is_blank(self.cfg.conversion_tweaks.dlc_songs.name_txt_path):
            self.dlc_name_txt_path.setText(str(self.cfg.conversion_tweaks.dlc_songs.name_txt_path))
            self.dlc_name_txt_path_fv()
        if not is_blank(self.cfg.conversion_tweaks.dlc_songs.songs_json_path):
            self.dlc_json_path.setText(str(self.cfg.conversion_tweaks.dlc_songs.songs_json_path))
            self.dlc_json_path_fv()
        if not is_blank(self.cfg.conversion_tweaks.dlc_songs.songs_dlc_tsv_path):
            self.dlc_tsv_path.setText(str(self.cfg.conversion_tweaks.dlc_songs.songs_dlc_tsv_path))
            self.dlc_tsv_path_fv()

        self.pitch_correction_checkbox.setChecked(True if self.cfg.conversion_tweaks.pitch_correction.lower() == 'slow' else False)
        self.max_video_size.setText(str(self.cfg.conversion_tweaks.max_video_size))
        self.max_video_size_fv()
        self.ignore_medley_checkbox.setChecked(self.cfg.conversion_tweaks.no_medley)
        self.still_video_checkbox.clicked.connect(self.still_video_checkbox_fv)
        self.still_video_checkbox.setChecked(self.cfg.conversion_tweaks.still_video)
        self.still_video_checkbox_fv()

        self.include_dlc_checkbox_refresh()
        self.stop_button.setEnabled(False)
        self.clear_cache_button.setEnabled(False)

    def update_clear_cache_enabled(self, *_args) -> None:
        """Enable Clear cache only if any checkbox in column 0 is checked."""
        # If conversion is running, keep it protected with the rest of the UI.
        self.clear_cache_button.setEnabled(self.any_preview_row_checked())

    def any_preview_row_checked(self) -> bool:
        for row in range(self.preview_table.rowCount()):
            item = self.preview_table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                return True
        return False

    def prefill_ffmpeg_path(self) -> None:
        if not is_blank(self.cfg.tools.ffmpeg_path):
            self.ffmpeg_path.setText(self.cfg.tools.ffmpeg_path)
            return
        root_path = os.path.abspath(os.path.dirname(__file__))
        if os.path.exists(os.path.join(root_path, "ffmpeg", "bin", "ffmpeg.exe")):
            self.ffmpeg_path.setText(os.path.join(root_path, "ffmpeg", "bin"))
            return

        common_install_location = r"C:\ffmpeg\bin\ffmpeg.exe"
        if os.path.exists(common_install_location):
            self.ffmpeg_path.setText(common_install_location)

    def prefill_rad_path(self) -> None:
        if not is_blank(self.cfg.tools.rad_path):
            self.rad_path.setText(self.cfg.tools.rad_path)
        expected_path = r"C:\Program Files (x86)\RADVideo\radvideo64.exe"
        if os.path.exists(expected_path):
            self.rad_path.setText(expected_path)

    def prefill_input_output_paths(self) -> None:
        root_path = os.path.abspath(os.path.dirname(__file__))
        if not is_blank(self.cfg.folders.input):
            self.input_path.setText(self.cfg.folders.input)
            input_path = os.path.abspath(self.cfg.folders.input)
        else:
            input_path = os.path.join(root_path, DEFAULT_INPUT_FOLDER_NAME)
        if not is_blank(self.cfg.folders.output):
            self.output_path.setText(self.cfg.folders.output)
            output_path = os.path.abspath(self.cfg.folders.output)
        else:
            output_path = os.path.join(root_path, DEFAULT_OUTPUT_FOLDER_NAME)

        self.input_path.setText(input_path)
        self.output_path.setText(output_path)
        self.output_path_fv()
        self.sync_watched_folders(input_path)
        self.refresh_preview()

    def scan_input_folder(self) -> None:
        """Scan input folder for song directories and populate preview table"""
        input_path = os.path.normpath(self.input_path.text().strip())
        if not input_path or input_path == "." or not os.path.exists(input_path):
            self.clear_watches()
            self.clear_preview()
            return
        self.sync_watched_folders(input_path)

        songs = []
        try:
            for directory in os.listdir(input_path):
                directory_path = os.path.join(input_path, directory)
                if not os.path.isdir(directory_path) or " - " not in directory:
                    continue

                name_id = construct_name_id_from_directory_name(directory)
                if self.dlc_json_name_input is not None:
                    output_video_name = name_id + '.bk2'
                    png_in_game_file_name = "yoyoyo"
                    png_long_file_name = "yoyoyo"
                    png_result_file_name = "yoyoyo"
                else :
                    png_in_game_file_name = name_id + '_InGameLoading.png'
                    png_long_file_name = name_id + '_long.png'
                    png_result_file_name = name_id + '_Result.png'
                    output_video_name = name_id + '.mp4'
                output_image_name = name_id + '.png'
                output_audio_name = name_id + '.ogg'
                output_audio_preview_name = name_id + '_preview.ogg'
                output_txt_name = name_id + '.vxla'

                has_video = GuiElement.Icon.X.get_icon()
                has_audio = GuiElement.Icon.X.get_icon()
                has_image = GuiElement.Icon.X.get_icon()
                has_txt = GuiElement.Icon.X.get_icon()

                all_files = os.listdir(directory_path)
                for file in all_files:
                    file_lower = file.lower()
                    if directory != Path(file).stem:
                        continue
                    if file_lower.endswith(VIDEO_EXTENSIONS):
                        has_video = GuiElement.Icon.CHECK.get_icon()
                    elif file_lower.endswith(AUDIO_EXTENSIONS):
                        has_audio = GuiElement.Icon.CHECK.get_icon()
                    elif file_lower.endswith(IMAGE_EXTENSIONS):
                        has_image = GuiElement.Icon.CHECK.get_icon()
                    elif file_lower.endswith(TXT_EXTENSIONS):
                        has_txt = GuiElement.Icon.CHECK.get_icon()

                cached_video = output_video_name in all_files
                cached_audio = output_audio_name in all_files
                cached_image = output_image_name in all_files
                cached_txt = output_txt_name in all_files

                if cached_video:
                    has_video = GuiElement.combine_icons(has_video, GuiElement.Icon.FILE_CHECK.get_icon())
                if cached_audio:
                    has_audio = GuiElement.combine_icons(has_audio, GuiElement.Icon.FILE_CHECK.get_icon())
                if cached_image:
                    has_image = GuiElement.combine_icons(has_image, GuiElement.Icon.FILE_CHECK.get_icon())
                if cached_txt:
                    has_txt = GuiElement.combine_icons(has_txt, GuiElement.Icon.FILE_CHECK.get_icon())

                songs.append({
                    "directory": directory,
                    "directory_path": directory_path,
                    "icons": [has_video, has_audio, has_image, has_txt],
                    "outputs": [output_video_name, output_audio_name, output_audio_preview_name,
                                output_image_name, png_in_game_file_name, png_long_file_name,
                                png_result_file_name, output_txt_name],
                    "is_cached": cached_video or cached_audio or cached_image or cached_txt,
                })

        except Exception as e:
            self.log(f"Error scanning input folder: {e}")
            return

        # Populate preview table
        self.preview_table.setRowCount(len(songs))
        for row, song in enumerate(songs):
            # Checkbox column (0)
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags((checkbox_item.flags()
                                    | Qt.ItemIsUserCheckable
                                    | Qt.ItemIsEnabled
                                    | Qt.ItemIsSelectable)
                                   & ~Qt.ItemIsEditable)
            checkbox_item.setCheckState(Qt.Unchecked)
            checkbox_item.setTextAlignment(Qt.AlignCenter)
            # Store deletion info on the checkbox item
            checkbox_item.setData(Qt.UserRole, {"directory_path": song["directory_path"], "outputs": song["outputs"]})
            self.preview_table.setItem(row, 0, checkbox_item)

            # Song name column (1)
            song_item = QTableWidgetItem(song["directory"])
            song_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            song_item.setFlags(song_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 1, song_item)

            # Icon columns (2..5)
            for i, icon in enumerate(song["icons"], start=2):
                icon_item = QTableWidgetItem()
                icon_item.setIcon(icon)
                icon_item.setTextAlignment(Qt.AlignCenter)
                icon_item.setFlags(icon_item.flags() & ~Qt.ItemIsEditable)
                self.preview_table.setItem(row, i, icon_item)

    def browse_file(self, line_edit, file_filter="All Files (*)") -> None:
        """Open file browser and set the selected file path"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)
        if file_path:
            file_path = os.path.normpath(file_path)
            line_edit.setText(file_path)
            validator = self.field_validators.get(line_edit)
            if validator:
                validator()

    def browse_folder(self, line_edit) -> None:
        """Open folder browser and set the selected folder path"""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            folder_path = os.path.normpath(folder_path)
            line_edit.setText(folder_path)
            validator = self.field_validators.get(line_edit)
            if validator:
                validator()

    def clear_preview(self) -> None:
        """Clear preview table contents."""
        self.preview_table.setRowCount(0)
        self.preview_table.clearContents()
        self.update_clear_cache_enabled()

    def clear_watches(self) -> None:
        for p in self.folder_watcher.directories():
            self.folder_watcher.removePath(p)
        for p in self.folder_watcher.files():
            self.folder_watcher.removePath(p)

    def sync_watched_folders(self, root: str) -> None:
        """Watch root + all qualifying immediate subfolders."""
        root = os.path.normpath(root.strip())
        if not root or not os.path.isdir(root):
            self.clear_watches()
            return

        # Build desired watch list
        desired: set[str] = {root}
        try:
            for name in os.listdir(root):
                sub = os.path.join(root, name)
                if os.path.isdir(sub) and " - " in name:
                    desired.add(sub)
        except Exception:
            # If listing fails, still keep root watched
            pass

        current = set(self.folder_watcher.directories())

        for p in sorted(current - desired):
            self.folder_watcher.removePath(p)
        to_add = sorted(desired - current)
        if to_add:
            self.folder_watcher.addPaths(to_add)

    def refresh_preview_from_watcher(self) -> None:
        if not self.isVisible():
            return
        self.sync_watched_folders(self.input_path.text())
        self.scan_input_folder()

    def log(self, message) -> None:
        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")

        for line in str(message).splitlines() or [""]:
            self.logs_text.append(
                f"<span style='color:#888888;'>[{ts}]</span> {escape(line)}"
            )

    def clear_logs(self) -> None:
        self.logs_text.clear()

    def refresh_preview(self) -> None:
        self.log("Input folder preview refreshed.")
        self.scan_input_folder()

    def clear_cache(self) -> None:
        """Delete cached output files for rows whose checkbox (col 0) is checked."""
        deleted_files = 0
        affected_songs = 0

        checked_rows = []
        for row in range(self.preview_table.rowCount()):
            item = self.preview_table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                checked_rows.append(row)

        if not checked_rows:
            self.log("Clear cache: no rows checked.")
            return

        for row in checked_rows:
            checkbox_item = self.preview_table.item(row, 0)
            if checkbox_item is None:
                continue

            payload = checkbox_item.data(Qt.UserRole) or {}
            directory_path = payload.get("directory_path")
            outputs = payload.get("outputs") or []

            if not directory_path or not os.path.isdir(directory_path):
                continue

            any_deleted = False
            for name in outputs:
                file_path = os.path.join(directory_path, name)
                if not os.path.exists(file_path):
                    continue
                try:
                    os.remove(file_path)
                    deleted_files += 1
                    any_deleted = True
                except Exception as e:
                    self.log(f"Failed to delete: {file_path} ({str(e)})")

            if any_deleted:
                affected_songs += 1

        self.log(f"Clear cache done. Deleted files: {deleted_files}, songs affected: {affected_songs}")
        self.refresh_preview()
        self.update_clear_cache_enabled()

    def required_fields_missing(self) -> Tuple[List[str], List[str]]:
        missing: List[str] = []
        invalid: List[str] = []

        def req(line_edit: QLineEdit, label: str):
            if not line_edit.isEnabled():
                mark_field_valid(line_edit, True)
                return
            if not line_edit.text().strip():
                missing.append(label)
                mark_field_valid(line_edit, False)
            else:
                validator = self.field_validators.get(line_edit)
                if validator and not validator():
                    invalid.append(label)

        req(self.core_id_input, "Core ID")
        req(self.dlc_id_input, "DLC ID")
        # req(self.dlc_json_name_input, "DLC JSON Name")

        req(self.ffmpeg_path, "FFmpeg")
        req(self.rad_path, "RAD Video Tools")
        req(self.output_path, "Output folder")
        req(self.input_path, "Input folder")

        req(self.dlc_name_txt_path, "name.txt")
        req(self.dlc_tsv_path, "SongsDLC.tsv")
        req(self.dlc_json_path, "songs_xx.json")
        req(self.max_video_size, "Max video size")

        return missing, invalid

    def set_controls_enabled(self, enabled: bool) -> None:
        """Enable/disable interactive controls for conversion run."""
        for w in self.findChildren(QLineEdit):
            w.setEnabled(enabled)
        for w in self.findChildren(QAbstractButton):
            w.setEnabled(enabled)
        for w in self.findChildren(QComboBox):
            w.setEnabled(enabled)

        self.stop_button.setEnabled(not enabled)
        self.clear_logs_button.setEnabled(True)
        self.preview_table.header.setEnabled(enabled)
        set_element_enabled(self.tweaks_group, enabled)

        if enabled:
            self.preview_table.setSelectionMode(QAbstractItemView.SingleSelection)
            for row in range(self.preview_table.rowCount()):
                item = self.preview_table.item(row, 0)
                if item:
                    item.setFlags(item.flags() | Qt.ItemIsEnabled)

            if self.core_edition_combo.currentText() != "other":
                set_element_enabled(self.core_id_label, False)
                set_element_enabled(self.core_id_input, False)

            if self.dlc_name_combo.currentText() != "other":
                set_element_enabled(self.dlc_id_label, False)
                set_element_enabled(self.dlc_id_input, False)
                set_element_enabled(self.dlc_json_name_label, False)
                set_element_enabled(self.dlc_json_name_input, False)
            self.still_video_checkbox_fv()
            self.include_dlc_checkbox_refresh()
            self.dlc_json_name_input_fv()
        else:
            self.preview_table.setSelectionMode(QAbstractItemView.NoSelection)
            for row in range(self.preview_table.rowCount()):
                item = self.preview_table.item(row, 0)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)

    def start_conversion(self) -> None:
        self.preview_table.clearSelection()
        missing, invalid = self.required_fields_missing()
        if missing or invalid:
            if missing:
                self.log("Cannot start conversion. Fill required fields:\n- " + "\n- ".join(missing))
            if invalid:
                self.log("Cannot start conversion. Invalid values for fields:\n- " + "\n- ".join(invalid))
            return

        self.conversion_running = True
        self.set_controls_enabled(False)
        self.save_config()

        self.log("Saved config.")
        self.log("Starting conversion...")

        self._stop_event = threading.Event()
        self._worker = ConversionWorker(self.cfg, self._stop_event)
        self._worker.log_message.connect(self.log)
        self._worker.finished.connect(self._on_conversion_finished)
        self._worker.error.connect(self._on_conversion_error)
        self._worker.start()


    def _on_conversion_finished(self) -> None:
        self.conversion_running = False
        self.set_controls_enabled(True)
        self.refresh_preview()

    def _on_conversion_error(self, error_msg: str) -> None:
        self.log(f"Conversion failed: {error_msg}")
        self.conversion_running = False
        self.set_controls_enabled(True)
        self.refresh_preview()

    def stop_conversion(self) -> None:
        if not self.conversion_running:
            return

        self.log("Stopping conversion...")
        self._stop_event.set()

        self.conversion_running = False
        self.set_controls_enabled(True)

    def show_help(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Help – Let's Sing DLC Patcher")
        dlg.setWindowIcon(GuiElement.Icon.INFO_SQUARE_ROUNDED.get_icon())
        dlg.setModal(True)
        dlg.resize(1200, 1000)

        layout = QVBoxLayout(dlg)

        help_modal = QTextBrowser(dlg)
        help_modal.setOpenExternalLinks(True)

        help_modal.setHtml(self.help_html())
        layout.addWidget(help_modal)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, dlg)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        dlg.exec()

    def help_html(self) -> str:
        readme_path = Path(__file__).resolve().parent / "Help.md"
        md_text = readme_path.read_text(encoding="utf-8", errors="replace")

        body = markdown.markdown(
            md_text,
            extensions=["extra", "sane_lists", "nl2br"],
            output_format="html",
        )

        return f"<html><head></head><body>{body}</body></html>"

    def init_elements(self):
        self.init_labels()
        self.core_edition_combo = QComboBox()
        self.dlc_name_combo = QComboBox()

        self.core_id_input = QLineEdit()
        self.core_id_input.setMaxLength(16)
        self.dlc_id_input = QLineEdit()
        self.dlc_id_input.setMaxLength(16)
        self.dlc_json_name_input = QLineEdit()
        self.dlc_json_name_input.setMaxLength(32)
        self.rad_path = QLineEdit()
        self.rad_path.setMaxLength(256)
        self.ffmpeg_path = QLineEdit()
        self.ffmpeg_path.setMaxLength(256)
        self.input_path = QLineEdit()
        self.input_path.setMaxLength(256)
        self.output_path = QLineEdit()
        self.output_path.setMaxLength(256)
        self.warning_action = self.output_path.addAction(
            GuiElement.Icon.ALERT_TRIANGLE.get_icon(), QLineEdit.TrailingPosition)
        self.dlc_name_txt_path = QLineEdit()
        self.dlc_name_txt_path.setMaxLength(256)
        self.dlc_tsv_path = QLineEdit()
        self.dlc_tsv_path.setMaxLength(256)
        self.dlc_json_path = QLineEdit()
        self.dlc_json_path.setMaxLength(256)
        self.max_video_size = QLineEdit()
        self.max_video_size.setMaxLength(8)


        self.rad_browse = QPushButton(BROWSE)
        self.ffmpeg_browse = QPushButton(BROWSE)
        self.input_input_browse = QPushButton(BROWSE)
        self.output_browse = QPushButton(BROWSE)
        self.name_txt_browse = QPushButton(BROWSE)
        self.songs_dlc_browse = QPushButton(BROWSE)
        self.songs_json_browse = QPushButton(BROWSE)
        self.help_button = QPushButton(" Help")
        self.clear_logs_button = QPushButton(" Clear logs")
        self.refresh_button = QPushButton(" Refresh")
        self.clear_cache_button = QPushButton(" Clear cache")
        self.stop_button = QPushButton(" Stop")
        self.start_button = QPushButton(" Start conversion")

        self.preview_table = PreviewTable(checkbox_column=0)
        self.logs_text = QTextEdit()

        self.include_dlc_checkbox = QCheckBox("Include songs from the DLC")
        self.still_video_checkbox = QCheckBox("Use cover image instead of video (very fast)")
        self.pitch_correction_checkbox = QCheckBox("Analyze song vocals for pitch correction (~10s per song)")
        self.ignore_medley_checkbox = QCheckBox("Ignore the UltraStar medley tags for finding chorus sections")
        self.set_tooltips()

    def init_labels(self) -> None:
        self.lets_sing_label = QLabel("Let's Sing:")
        self.core_id_label = QLabel('Core TitleID:')
        self.dlc_name_label = QLabel('DLC Name:')
        self.dlc_id_label = QLabel('DLC TitleID:')
        self.dlc_json_name_label = QLabel('DLC JSON Name:')
        self.ffmpeg_label = QLabel('FFmpeg:')
        self.rad_label = QLabel('RAD Video Tools:')
        self.input_label = QLabel('Input folder:')
        self.output_label = QLabel('Output folder:')
        self.name_txt_label = QLabel('name.txt:')
        self.songs_dlc_label = QLabel('SongsDLC.tsv:')
        self.songs_json_label = QLabel('songs_xx.json:')
        self.max_video_label = QLabel('Max video size (MB):')

    def set_tooltips(self):
        self.core_id_input.setToolTip("The unique TitleID of the base game (e.g., 0100CC30149B8000 for Let's Sing 2022).")
        self.dlc_id_input.setToolTip("The unique TitleID of the dlc which will be patched (e.g., 0100CC30149B9011 for Let's Sing 2022).")
        self.dlc_json_name_input.setToolTip(
            "The name of the DLC metadata file in JSON format, used for Let's Sing 2024 and onward (e.g., songs_fr for the French Hits DLC for Let's Sign 2025)."
            "\n\nThis name can be found in the name.txt file located in [DLC TITLEID]/romfs/name.txt")
        self.ffmpeg_path.setToolTip("Path to the FFmpeg release. Used for converting videos/audio/images to the format required by Let's Sing.")
        self.rad_path.setToolTip("Path to RAD Video Tools. Required for Let's Sing 2024 and onward for converting videos to bk2 format.")
        self.input_path.setToolTip(
            "Path to the folder containing the UltraStar song folders."
            "\nSong folders should be named as 'Artist - Song Title' and contain the txt and media files."
            "\n\nNote: The program will cache the converted files in these song folders.")
        self.output_path.setToolTip("Path to the output folder where the converted files will be saved.")
        self.warning_action.setToolTip("Warning: The selected folder, if it exists, will be deleted prior to starting the conversion.")
        self.include_dlc_checkbox.setToolTip("If left unchecked, the songs from the DLC will not be accessible in the game.")
        self.dlc_name_txt_path.setToolTip(
            "Path to the name.txt file from the DLC. This file contains either a list of the included song IDs "
            "(prior to Let's Sing 2024) or just the name of the DLC metadata JSON file (Let's Sing 2024 and onward)."
            "\n\nThe file is located in [DLC TITLEID]/romfs/name.txt")
        self.dlc_tsv_path.setToolTip("Path to the SongsDLC.tsv file from the DLC. This file contains metadata about the songs included in the DLC (prior to Let's Sing 2024). "
                                        "\n\nThe file is located in [CORE TITLEID]/romfs/Data/StreamingAssets/SongsDLC.tsv")
        self.dlc_json_path.setToolTip(
            "Path to the songs_xx.json file from the DLC. This file contains metadata about the songs included in the DLC (used for Let's Sing 2024 and onward)."
            "\n\nThe file is located in [DLC TITLEID]/romfs/songs_xx.json")
        self.pitch_correction_checkbox.setToolTip(
            "UltraStar files often have lower pitch values than Let's Sing expects so some form of pitch correction is required."
            "\n\nIf left unchecked, quick maths will be employed for correcting the pitch.")
        self.still_video_checkbox.setToolTip("Check this box to skip encoding of music videos to the game's format, "
            "the cover image will be used to create a static video instead. This will dramatically speed up the conversion "
            "and reduce the final size of the patch.")
        self.max_video_size.setToolTip("Set a maximum size for the converted video files. Lowering this value can help reduce the overall size of the converted files, but may result in lower video quality.")
        self.ignore_medley_checkbox.setToolTip(
            "UltraStar medley tags in the lyrics txt file, if they exist, are sometimes incorrect and can lead to a non-chorus sections being marked as choruses."
            "\n\nCheck this box if you wish to ignore the tags and fully rely on the backup chorus lookup methods instead.")
        self.help_button.setToolTip("Show instructions on what this program does and how to use it.")
        self.refresh_button.setToolTip("Refresh the input song folders preview.")
        self.clear_cache_button.setToolTip("Delete the previously converted files from the selected input song's folder, base files won't be deleted.")
        self.stop_button.setToolTip("Stop the conversion process, all the files converted so far will be cached.")
        self.start_button.setToolTip("Start the conversion process, cached videos, audio and images will not be converted again.")

    def save_config(self) -> None:
        dlc_id = self.dlc_id_input.text().strip()
        dlc_entity = repository.get_by_dlc_id(dlc_id)

        dlc_section = {"id": dlc_id}
        if dlc_entity:
            core_section = None
        else:
            dlc_json_name = self.dlc_json_name_input.text().strip()
            if not is_blank(dlc_json_name):
                dlc_section["json_name"] = dlc_json_name
            core_section = {"id": self.core_id_input.text().strip()}
        config_dict = {"dlc": dlc_section}

        if core_section is not None:
            config_dict["core"] = core_section

        tools_section = {"ffmpeg_path": self.ffmpeg_path.text().strip()}
        if not is_blank(self.rad_path.text()):
            tools_section["rad_path"] = self.rad_path.text().strip()
        config_dict["tools"] = tools_section

        config_dict["folders"] = {
            "input": self.input_path.text().strip(),
            "output": self.output_path.text().strip(),
        }

        dlc_songs_section = {"include": self.include_dlc_checkbox.isChecked()}
        if not is_blank(self.dlc_name_txt_path.text()):
            dlc_songs_section["name_txt_path"] = self.dlc_name_txt_path.text().strip()
        if not is_blank(self.dlc_json_path.text()):
            dlc_songs_section["songs_json_path"] = self.dlc_json_path.text().strip()
        if not is_blank(self.dlc_tsv_path.text()):
            dlc_songs_section["songs_dlc_tsv_path"] = self.dlc_tsv_path.text().strip()

        config_dict["conversion_tweaks"] = {
            "enable": self.tweaks_group.isChecked(),
            "dlc_songs": dlc_songs_section,
            "pitch_correction": "slow" if self.pitch_correction_checkbox.isChecked() else "fast",
            "max_video_size": int(self.max_video_size.text()) if self.max_video_size.text().strip().isdigit() else None,
            "no_medley": self.ignore_medley_checkbox.isChecked(),
            "still_video": self.still_video_checkbox.isChecked(),
        }

        user_path = Path('.') / 'config.yml'
        with open(user_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)


def main():
    app = QApplication(sys.argv)
    qdarktheme.setup_theme("auto")
    apply_theme_change(app.styleHints().colorScheme(), app)
    app.styleHints().colorSchemeChanged.connect(lambda scheme: apply_theme_change(scheme, app))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
