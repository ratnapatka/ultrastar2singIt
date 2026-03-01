from __future__ import annotations

import os
import re
import sys
from html import escape
from pathlib import Path
from typing import List, Tuple

import markdown
import qdarktheme
import unicodedata
from PySide6 import QtCore
from PySide6.QtCore import Qt, QDateTime, QFileSystemWatcher
from PySide6.QtGui import QIcon, QRegularExpressionValidator
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QCheckBox, QTextEdit, QTableWidgetItem, QFileDialog, QGroupBox,
                               QGridLayout, QRadioButton, QAbstractItemView,
                               QAbstractButton, QDialog, QTextBrowser, QDialogButtonBox)

import GuiElement
from PreviewTable import PreviewTable

CORE_ID_DEFAULT_2022 = "0100CC30149B8000"
DLC_ID_DEFAULT_2022 = "0100CC30149B9011"
DLC_NAME_DEFAULT_2025 = "songs_fr"
DLC_ID_DEFAULT_2025 = "01001C101ED11002"
BROWSE = "Browse"

VIDEO_EXTENSIONS = ('.mp4', '.mpeg', '.avi', '.divx', '.mkv', '.webm')
AUDIO_EXTENSIONS = ('.mp3', '.ogg', '.aac', '.wav', '.flac')
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp')
TXT_EXTENSIONS = '.txt'

DEFAULT_INPUT_FOLDER_NAME = "My Songs"
DEFAULT_OUTPUT_FOLDER_NAME = "_Patch"

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

def set_element_enabled(element, is_enabled: bool):
    if not is_enabled and isinstance(element, QLineEdit):
        mark_field_valid(element, True)
    element.setEnabled(is_enabled)

def mark_field_valid(line_edit: QLineEdit, valid: bool) -> None:
    line_edit.setProperty("has_border", "true" if not valid else "false")
    # refresh style
    line_edit.style().unpolish(line_edit)
    line_edit.style().polish(line_edit)
    line_edit.update()

def apply_theme_change(theme, app):
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_labels()
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

        self.watched_dir: str | None = None

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
            self.ffmpeg_input: self.ffmpeg_input_fv,
            self.rad_input: self.rad_input_fv,
            self.input_input: self.input_input_fv,
            self.max_video_size: self.max_video_size_fv,
            self.output_input: self.output_input_fv,
            self.name_txt_input: self.name_txt_input_fv,
            self.songs_dlc_input: self.songs_dlc_input_fv,
            self.songs_json_input: self.songs_json_input_fv,
        }
        self.set_defaults()


    def create_left_panel(self):
        """Create left panel with Game Info, Tools, and Tweaks"""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        ## Game Info Section
        game_info_group = QGroupBox("Game Info")
        game_info_layout = QGridLayout()

        # game version radio buttons
        game_info_layout.addWidget(QLabel("Let's Sing:"), 0, 0)
        game_version_layout = QHBoxLayout()
        self.game_version_2022 = QRadioButton("2022")
        self.game_version_2025 = QRadioButton("2025")
        self.game_version_2022.setToolTip("Choose which game version to convert the files to.")
        self.game_version_2025.setToolTip("Choose which game version to convert the files to.")
        self.game_version_2025.setChecked(True)
        self.game_version = '2025'
        self.game_version_2022.clicked.connect(self.game_version_radio_toggle)
        self.game_version_2025.clicked.connect(self.game_version_radio_toggle)
        game_version_layout.addWidget(self.game_version_2022)
        game_version_layout.addWidget(self.game_version_2025)
        game_version_layout.addStretch()
        game_info_layout.addLayout(game_version_layout, 0, 1)

        game_info_layout.addWidget(self.core_id_label, 1, 0)
        self.core_id_input = QLineEdit()
        self.core_id_input.setToolTip("The TitleID of the base game (e.g., 0100CC30149B8000 for 2022), not used for 2025.")
        game_info_layout.addWidget(self.core_id_input, 1, 1)

        game_info_layout.addWidget(self.dlc_id_label, 2, 0)
        self.dlc_id_input = QLineEdit()
        self.dlc_id_input.setToolTip("The TitleID of the dlc (e.g., 0100CC30149B9011 for 2022).")
        game_info_layout.addWidget(self.dlc_id_input, 2, 1)

        game_info_layout.addWidget(self.dlc_name_label, 3, 0)
        self.dlc_name_input = QLineEdit()
        self.dlc_name_input.setToolTip(
            "The name of the DLC (e.g., songs_fr for the French Hits DLC for Let's Sign 2025), not used in Let's Sign 2022."
            "\n\nThis name can be found in the name.txt file located in [DLC TITLEID]/romfs/name.txt")
        game_info_layout.addWidget(self.dlc_name_input, 3, 1)

        game_info_group.setLayout(game_info_layout)
        left_layout.addWidget(game_info_group)

        # Tools Section
        tools_group = QGroupBox("Conversion tools")
        tools_layout = QGridLayout()

        # FFMPEG
        tools_layout.addWidget(self.ffmpeg_label, 0, 0)
        self.ffmpeg_input = QLineEdit()
        self.ffmpeg_input.setToolTip("Path to the FFmpeg release. Used for converting videos/audio/images to the format required by Let's Sing.")
        self.ffmpeg_input.editingFinished.connect(self.ffmpeg_input_fv)
        tools_layout.addWidget(self.ffmpeg_input, 0, 1)
        self.ffmpeg_browse = QPushButton(BROWSE)
        self.ffmpeg_browse.clicked.connect(lambda: self.browse_file(self.ffmpeg_input, "ffmpeg (*.exe)"))
        tools_layout.addWidget(self.ffmpeg_browse, 0, 2)

        # RAD
        tools_layout.addWidget(self.rad_label, 1, 0)
        self.rad_input = QLineEdit()
        self.rad_input.setToolTip("Path to RAD Video Tools. Used for converting videos to bk2 format for Let's Sing 2025.")
        self.rad_input.editingFinished.connect(self.rad_input_fv)
        tools_layout.addWidget(self.rad_input, 1, 1)
        self.rad_browse = QPushButton(BROWSE)
        self.rad_browse.clicked.connect(lambda: self.browse_file(self.rad_input, "radvideo64 (*.exe)"))
        tools_layout.addWidget(self.rad_browse, 1, 2)

        tools_group.setLayout(tools_layout)
        left_layout.addWidget(tools_group)

        input_output_group = QGroupBox("Input and Output folders")
        input_output_layout = QGridLayout()

        # Input
        input_output_layout.addWidget(self.input_label, 2, 0)
        self.input_input = QLineEdit()
        self.input_input.setToolTip(
            "Path to the folder containing the UltraStar song folders."
            "\nSong folders should be named as 'Artist - Song Title' and contain the txt and media files."
            "\n\nNote: The program will cache the converted files in these song folders.")
        self.input_input.editingFinished.connect(self.input_input_fv)
        input_output_layout.addWidget(self.input_input, 2, 1)
        self.input_input_browse = QPushButton(BROWSE)
        self.input_input_browse.clicked.connect(lambda: self.browse_folder(self.input_input))
        input_output_layout.addWidget(self.input_input_browse, 2, 2)

        # Output
        input_output_layout.addWidget(self.output_label, 3, 0)
        self.output_input = QLineEdit()
        self.output_input.setToolTip("Path to the output folder where the converted files will be saved.")
        warning_action = self.output_input.addAction(
            GuiElement.Icon.ALERT_TRIANGLE.get_icon(),
            QLineEdit.TrailingPosition)
        warning_action.setToolTip("Warning: The selected folder, if it exists, will be deleted prior to starting the conversion.")
        self.output_input.editingFinished.connect(self.output_input_fv)
        input_output_layout.addWidget(self.output_input, 3, 1)
        self.output_browse = QPushButton(BROWSE)
        self.output_browse.clicked.connect(lambda: self.browse_folder(self.output_input))
        input_output_layout.addWidget(self.output_browse, 3, 2)

        input_output_group.setLayout(input_output_layout)
        left_layout.addWidget(input_output_group)

        # Tweaks Section
        tweaks_group = QGroupBox("Conversion tweaks")
        tweaks_layout = QVBoxLayout()

        # Include DLC songs checkbox
        self.include_dlc_checkbox = QCheckBox("Include songs from the DLC")
        self.include_dlc_checkbox.setToolTip("If left unchecked, the songs from the DLC will not be accessible in the game.")
        self.include_dlc_checkbox.clicked.connect(self.include_dlc_checkbox_refresh)
        tweaks_layout.addWidget(self.include_dlc_checkbox)

        # Name.txt
        name_layout = QHBoxLayout()
        name_layout.addWidget(self.name_txt_label)
        self.name_txt_input = QLineEdit()
        self.name_txt_input.setToolTip(
            "Path to the name.txt file from the DLC. This file contains either a list of the included song IDs (2022) or just the name of the DLC (2025)."
            "\n\nThe file is located in [DLC TITLEID]/romfs/name.txt")
        self.name_txt_input.editingFinished.connect(self.name_txt_input_fv)
        name_layout.addWidget(self.name_txt_input)
        self.name_txt_browse = QPushButton(BROWSE)
        self.name_txt_browse.clicked.connect(lambda: self.browse_file(self.name_txt_input, "name (*.txt)"))
        name_layout.addWidget(self.name_txt_browse)
        tweaks_layout.addLayout(name_layout)

        # SongsDLC.tsv
        songs_dlc_layout = QHBoxLayout()
        songs_dlc_layout.addWidget(self.songs_dlc_label)
        self.songs_dlc_input = QLineEdit()
        self.songs_dlc_input.setToolTip("Path to the SongsDLC.tsv file from the DLC. This file contains metadata about the songs included in the DLC (only used for Let's Sing 2022). "
                                        "\n\nThe file is located in [CORE TITLEID]/romfs/Data/StreamingAssets/SongsDLC.tsv")
        self.songs_dlc_input.editingFinished.connect(self.songs_dlc_input_fv)
        songs_dlc_layout.addWidget(self.songs_dlc_input)
        self.songs_dlc_browse = QPushButton(BROWSE)
        self.songs_dlc_browse.clicked.connect(lambda: self.browse_file(self.songs_dlc_input, "SongsDLC (*.tsv)"))
        songs_dlc_layout.addWidget(self.songs_dlc_browse)
        tweaks_layout.addLayout(songs_dlc_layout)

        # Songs_xx.json
        songs_json_layout = QHBoxLayout()
        songs_json_layout.addWidget(self.songs_json_label)
        self.songs_json_input = QLineEdit()
        self.songs_json_input.setToolTip(
            "Path to the songs_xx.json file from the DLC. This file contains metadata about the songs included in the DLC (only used for Let's Sing 2025)."
            "\n\nThe file is located in [DLC TITLEID]/romfs/songs_xx.json")
        self.songs_json_input.editingFinished.connect(self.songs_json_input_fv)
        songs_json_layout.addWidget(self.songs_json_input)
        self.songs_json_browse = QPushButton(BROWSE)
        self.songs_json_browse.clicked.connect(lambda: self.browse_file(self.songs_json_input, "songs_xx (*.json)"))
        songs_json_layout.addWidget(self.songs_json_browse)
        tweaks_layout.addLayout(songs_json_layout)

        # Slow/Accurate pitch correction
        self.pitch_correction_checkbox = QCheckBox("Analyze song vocals for pitch correction (~10s per song)")
        self.pitch_correction_checkbox.setToolTip(
            "UltraStar files often have lower pitch values than Let's Sing expects so some form of pitch correction is required."
            "\n\nIf left unchecked, quick maths will be employed for correcting the pitch.")
        tweaks_layout.addWidget(self.pitch_correction_checkbox)

        # Max video size
        max_video_layout = QHBoxLayout()
        max_video_layout.addWidget(self.max_video_label)
        self.max_video_size = QLineEdit()
        self.max_video_size.setToolTip("Set a maximum size for the converted video files. Lowering this value can help reduce the overall size of the converted files, but may result in lower video quality.")
        self.max_video_size.setValidator(self.int_validator)
        self.max_video_size.setText("50")
        self.max_video_size.editingFinished.connect(self.max_video_size_fv)
        max_video_layout.addWidget(self.max_video_size)
        max_video_layout.addStretch()
        tweaks_layout.addLayout(max_video_layout)

        # Ignore medley checkbox
        self.ignore_medley_checkbox = QCheckBox("Ignore the UltraStar medley tags for finding chorus sections")
        self.ignore_medley_checkbox.setToolTip(
            "UltraStar medley tags in the lyrics txt file, if they exist, are sometimes incorrect and can lead to a non-chorus sections being marked as choruses."
            "\n\nCheck this box if you wish to ignore the tags and fully rely on the backup chorus lookup methods instead.")
        self.ignore_medley_checkbox.setChecked(False)
        tweaks_layout.addWidget(self.ignore_medley_checkbox)

        # tweaks_group.setLayout(tweaks_layout)
        tweaks_content = QWidget()
        tweaks_content.setLayout(tweaks_layout)
        tweaks_outer_layout = QVBoxLayout()
        tweaks_outer_layout.addWidget(tweaks_content)
        tweaks_group.setLayout(tweaks_outer_layout)
        tweaks_group.toggled.connect(tweaks_content.setVisible)
        tweaks_group.setCheckable(True)
        tweaks_group.setChecked(False)

        left_layout.addWidget(tweaks_group)
        left_layout.addStretch()

        # Help button
        help_button_layout = QHBoxLayout()
        self.help_button = QPushButton(" Help")
        self.help_button.setIcon(GuiElement.Icon.INFO_SQUARE_ROUNDED.get_icon())
        self.help_button.setToolTip("Show instructions on what this program does and how to use it.")
        self.help_button.clicked.connect(self.show_help)
        help_button_layout.addWidget(self.help_button)
        help_button_layout.addStretch()
        left_layout.addLayout(help_button_layout)
        return left_widget

    def create_right_panel(self):
        """Create right panel with Logs and Preview"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.logs_text = QTextEdit()
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
        self.clear_logs_button = QPushButton(" Clear logs")
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
        self.preview_table = PreviewTable(checkbox_column=0)
        self.preview_table.checkboxStateChanged.connect(self.update_clear_cache_enabled)

        preview_layout.addWidget(self.preview_table)
        preview_layout.addWidget(self.build_preview_legend())

        # Preview buttons
        preview_buttons_layout = QHBoxLayout()
        self.refresh_button = QPushButton(" Refresh")
        self.refresh_button.setToolTip("Refresh the input song folders preview.")
        self.refresh_button.setIcon(GuiElement.Icon.REFRESH.get_icon())
        self.refresh_button.clicked.connect(self.refresh_preview)
        preview_buttons_layout.addWidget(self.refresh_button)

        self.clear_cache_button = QPushButton(" Clear cache")
        self.clear_cache_button.setToolTip("Delete the previously converted files from the selected input song's folder, base files won't be deleted.")
        self.clear_cache_button.setIcon(GuiElement.Icon.FILE_X.get_icon())
        self.clear_cache_button.clicked.connect(self.clear_cache)
        preview_buttons_layout.addWidget(self.clear_cache_button)

        preview_buttons_layout.addStretch()

        self.stop_button = QPushButton(" Stop")
        self.stop_button.setToolTip("Stop the conversion process, all the files converted so far will be cached.")
        self.stop_button.setIcon(GuiElement.Icon.STOP.get_icon())
        self.stop_button.setIconSize(QtCore.QSize(GuiElement.ICON_SIZE, GuiElement.ICON_SIZE))
        self.stop_button.clicked.connect(self.stop_conversion)

        self.start_button = QPushButton(" Start conversion")
        self.start_button.setToolTip("Start the conversion process, cached videos, audio and images will not be converted again.")
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

    def game_version_radio_toggle(self):
        """Enable/disable fields based on selected game version"""
        if self.game_version_2022.isChecked():
            self.game_version = '2022'
            set_element_enabled(self.core_id_label, True)
            set_element_enabled(self.core_id_input, True)
            set_element_enabled(self.dlc_name_label, False)
            set_element_enabled(self.dlc_name_input, False)
            set_element_enabled(self.rad_label, False)
            set_element_enabled(self.rad_input, False)
            set_element_enabled(self.rad_browse, False)
            if self.include_dlc_checkbox.isChecked():
                set_element_enabled(self.name_txt_label, True)
                set_element_enabled(self.name_txt_input, True)
                set_element_enabled(self.name_txt_browse, True)
                set_element_enabled(self.songs_dlc_label, True)
                set_element_enabled(self.songs_dlc_input, True)
                set_element_enabled(self.songs_dlc_browse, True)
                set_element_enabled(self.songs_json_label, False)
                set_element_enabled(self.songs_json_input, False)
                set_element_enabled(self.songs_json_browse, False)

            self.core_id_input.setText(CORE_ID_DEFAULT_2022) if not self.core_id_input.text() else None
            self.dlc_id_input.setText(DLC_ID_DEFAULT_2022) if self.dlc_id_input.text() in ("", DLC_ID_DEFAULT_2025) else None
            self.dlc_name_input.setText("") if self.dlc_name_input.text() == DLC_NAME_DEFAULT_2025 else None

        else:  # 2025 is checked
            self.game_version = '2025'
            set_element_enabled(self.core_id_label, False)
            set_element_enabled(self.core_id_input, False)
            set_element_enabled(self.dlc_name_label, True)
            set_element_enabled(self.dlc_name_input, True)
            set_element_enabled(self.rad_label, True)
            set_element_enabled(self.rad_input, True)
            set_element_enabled(self.rad_browse, True)
            if self.include_dlc_checkbox.isChecked():
                set_element_enabled(self.name_txt_label, False)
                set_element_enabled(self.name_txt_input, False)
                set_element_enabled(self.name_txt_browse, False)
                set_element_enabled(self.songs_dlc_label, False)
                set_element_enabled(self.songs_dlc_input, False)
                set_element_enabled(self.songs_dlc_browse, False)
                set_element_enabled(self.songs_json_label, True)
                set_element_enabled(self.songs_json_input, True)
                set_element_enabled(self.songs_json_browse, True)

            self.core_id_input.setText("") if self.core_id_input.text() == CORE_ID_DEFAULT_2022 else None
            self.dlc_id_input.setText(DLC_ID_DEFAULT_2025) if self.dlc_id_input.text() in ("", DLC_ID_DEFAULT_2022) else None
            self.dlc_name_input.setText(DLC_NAME_DEFAULT_2025) if not self.dlc_name_input.text() else None
        mark_field_valid(self.core_id_input, True)
        mark_field_valid(self.dlc_id_input, True)
        mark_field_valid(self.dlc_name_input, True)
        self.refresh_preview()

    def ffmpeg_input_fv(self) -> bool:
        path = self.ffmpeg_input.text().strip()
        valid = path and os.path.isfile(path) and path.lower().endswith('ffmpeg.exe')
        mark_field_valid(self.ffmpeg_input, valid)
        return valid

    def rad_input_fv(self) -> bool:
        path = self.rad_input.text().strip()
        valid = path and os.path.isfile(path) and path.lower().endswith('radvideo64.exe')
        mark_field_valid(self.rad_input, valid)
        return valid

    def output_input_fv(self) -> bool:
        path = self.output_input.text().strip()

        if not path:
            mark_field_valid(self.output_input, False)
            return False
        if os.path.isdir(path):
            for file_or_folder in os.listdir(path):
                if os.path.isfile(file_or_folder) or not re.search(r'^[0-9A-F]{16}', file_or_folder):
                    #chosen folder contains unknown files or folders, append _Patch subfolder to path and approve
                    self.output_input.setText(os.path.join(path, DEFAULT_OUTPUT_FOLDER_NAME))
                    break
        mark_field_valid(self.output_input, True)
        return True

    def input_input_fv(self) -> bool:
        path = self.input_input.text().strip()
        if path and os.path.isdir(path):
            for folder in os.listdir(path):
                # the input folder should contain at least one "Artist Name - Song Title" folder
                if os.path.isdir(os.path.join(path, folder)) and re.search(r'^((?:.*\S)?)\s-\s(\S(?:.*\S)?)$', folder):
                    mark_field_valid(self.input_input, True)
                    self.sync_watched_folders(path)
                    self.scan_input_folder()
                    return True
        mark_field_valid(self.input_input, False)
        self.clear_preview()
        return False

    def name_txt_input_fv(self) -> bool:
        path = self.name_txt_input.text().strip()
        valid = path and os.path.isfile(path) and path.lower().endswith('name.txt')
        mark_field_valid(self.name_txt_input, valid)
        return valid

    def songs_dlc_input_fv(self) -> bool:
        path = self.songs_dlc_input.text().strip()
        valid = path and os.path.isfile(path) and path.lower().endswith('SongsDLC.tsv')
        mark_field_valid(self.songs_dlc_input, valid)
        return valid

    def songs_json_input_fv(self) -> bool:
        path = self.songs_json_input.text().strip()
        valid = path and os.path.isfile(path) and re.search(r'songs_[a-z]{2,3}\.json', path)
        mark_field_valid(self.songs_json_input, valid)
        return valid

    def max_video_size_fv(self) -> bool:
        self.max_video_size.setText(str(max(10, min(int(self.max_video_size.text() or 50), 200))))
        return True

    def include_dlc_checkbox_refresh(self):
        """Enable/disable DLC related fields based on checkbox"""
        if self.include_dlc_checkbox.isChecked():
            if self.game_version_2022.isChecked():
                set_element_enabled(self.name_txt_label, True)
                set_element_enabled(self.name_txt_input, True)
                set_element_enabled(self.name_txt_browse, True)
                set_element_enabled(self.songs_dlc_label, True)
                set_element_enabled(self.songs_dlc_input, True)
                set_element_enabled(self.songs_dlc_browse, True)
            else:
                set_element_enabled(self.songs_json_label, True)
                set_element_enabled(self.songs_json_input, True)
                set_element_enabled(self.songs_json_browse, True)
        else:
            set_element_enabled(self.name_txt_label, False)
            set_element_enabled(self.name_txt_input, False)
            set_element_enabled(self.name_txt_browse, False)
            set_element_enabled(self.songs_dlc_label, False)
            set_element_enabled(self.songs_dlc_input, False)
            set_element_enabled(self.songs_dlc_browse, False)
            set_element_enabled(self.songs_json_label, False)
            set_element_enabled(self.songs_json_input, False)
            set_element_enabled(self.songs_json_browse, False)

    def toggle_row_checkbox(self, row: int, column: int):
        """Toggle the checkbox in column 0 when any cell in the row is clicked."""
        item = self.preview_table.item(row, 0)
        if item is None:
            return
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def set_defaults(self):
        """Set default values for inputs"""
        self.dlc_id_input.setText(DLC_ID_DEFAULT_2025)
        self.dlc_name_input.setText(DLC_NAME_DEFAULT_2025)

        self.prefill_ffmpeg_path()
        self.prefill_rad_path()
        self.prefill_input_output_paths()
        self.game_version_radio_toggle()
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

    def prefill_ffmpeg_path(self):
        """Prefill FFMPEG path if installed at expected location"""
        root_path = os.path.abspath(os.path.dirname(__file__))
        if os.path.exists(os.path.join(root_path, "ffmpeg", "bin", "ffmpeg.exe")):
            self.ffmpeg_input.setText(os.path.join(root_path, "ffmpeg", "bin"))
            return

        common_install_location = r"C:\ffmpeg\bin\ffmpeg.exe"
        if os.path.exists(common_install_location):
            self.ffmpeg_input.setText(common_install_location)

    def prefill_rad_path(self):
        """Prefill RAD tools path if installed at expected location"""
        expected_path = r"C:\Program Files (x86)\RADVideo\radvideo64.exe"
        if os.path.exists(expected_path):
            self.rad_input.setText(expected_path)

    def prefill_input_output_paths(self):
        """Prefill input and output paths to root"""
        root_path = os.path.abspath(os.path.dirname(__file__))
        default_input_path = os.path.join(root_path, DEFAULT_INPUT_FOLDER_NAME)
        default_output_path = os.path.join(root_path, DEFAULT_OUTPUT_FOLDER_NAME)

        self.input_input.setText(default_input_path if default_input_path else root_path)
        self.output_input.setText(default_output_path)
        self.sync_watched_folders(root_path)

    def scan_input_folder(self):
        """Scan input folder for song directories and populate preview table"""
        input_path = os.path.normpath(self.input_input.text().strip())
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
                if self.game_version == '2025':
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

    def browse_file(self, line_edit, file_filter="All Files (*)"):
        """Open file browser and set the selected file path"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)
        if file_path:
            file_path = os.path.normpath(file_path)
            line_edit.setText(file_path)
            validator = self.field_validators.get(line_edit)
            if validator:
                validator()

    def browse_folder(self, line_edit):
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
        self.sync_watched_folders(self.input_input.text())
        self.scan_input_folder()

    def log(self, message):
        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")

        for line in str(message).splitlines() or [""]:
            self.logs_text.append(
                f"<span style='color:#888888;'>[{ts}]</span> {escape(line)}"
            )

    def clear_logs(self):
        self.logs_text.clear()

    def refresh_preview(self):
        self.log("Input folder preview refreshed.")
        self.scan_input_folder()

    def clear_cache(self):
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
        req(self.dlc_name_input, "DLC Name")

        req(self.ffmpeg_input, "FFmpeg")
        req(self.rad_input, "RAD Video Tools")
        req(self.output_input, "Output folder")
        req(self.input_input, "Input folder")

        req(self.name_txt_input, "name.txt")
        req(self.songs_dlc_input, "SongsDLC.tsv")
        req(self.songs_json_input, "songs_xx.json")
        req(self.max_video_size, "Max video size")

        return missing, invalid

    def set_controls_enabled(self, enabled: bool) -> None:
        """Enable/disable interactive controls for conversion run."""
        for w in self.findChildren(QLineEdit):
            w.setEnabled(enabled)
        for w in self.findChildren(QAbstractButton):
            w.setEnabled(enabled)

        self.stop_button.setEnabled(not enabled)
        self.clear_logs_button.setEnabled(True)
        self.preview_table.header.setEnabled(enabled)

        if enabled:
            self.preview_table.setSelectionMode(QAbstractItemView.SingleSelection)
            for row in range(self.preview_table.rowCount()):
                item = self.preview_table.item(row, 0)
                if item:
                    item.setFlags(item.flags() | Qt.ItemIsEnabled)
            self.game_version_radio_toggle()
            self.include_dlc_checkbox_refresh()
        else:
            self.preview_table.setSelectionMode(QAbstractItemView.NoSelection)
            for row in range(self.preview_table.rowCount()):
                item = self.preview_table.item(row, 0)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)

    def start_conversion(self):
        """Start the conversion process (validate + lock UI)."""
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

        self.log("Starting conversion...")
        self.log(f"Game Version: {self.game_version}")
        self.log(f"Core ID: {self.core_id_input.text()}")
        self.log(f"DLC ID: {self.dlc_id_input.text()}")
        self.log(f"DLC Name: {self.dlc_name_input.text()}")

        # TODO: start your actual conversion task/thread here
        # If you start a worker thread, make sure it calls a "finished" handler
        # that sets conversion_running False and re-enables controls.

    def stop_conversion(self):
        """Stop the conversion process (unlock UI)."""
        if not self.conversion_running:
            return

        self.log("Stopping conversion...")
        # TODO: stop your actual conversion task/thread here

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

    def init_labels(self):
        self.lets_sing_label = QLabel("Let's Sing:")
        self.core_id_label = QLabel('Core TitleID:')
        self.dlc_id_label = QLabel('DLC TitleID:')
        self.dlc_name_label = QLabel('DLC Name:')
        self.ffmpeg_label = QLabel('FFmpeg:')
        self.rad_label = QLabel('RAD Video Tools:')
        self.input_label = QLabel('Input folder:')
        self.output_label = QLabel('Output folder:')
        self.name_txt_label = QLabel('name.txt:')
        self.songs_dlc_label = QLabel('SongsDLC.tsv:')
        self.songs_json_label = QLabel('songs_xx.json:')
        self.max_video_label = QLabel('Max video size (MB):')


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
