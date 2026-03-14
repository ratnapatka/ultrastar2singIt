import json
import logging
import os
import re
import shutil
import subprocess
import xml.etree.cElementTree as Et
from pathlib import Path
from xml.dom import minidom

import pandas as pd
import unicodedata
from tqdm import tqdm

import PitchAnalyzer
import UltrastarToSingit
import data.repository.DlcRepository as repository
from config_loader import load_config

XML_FORMAT = 'xml'   # Let's Sing 2022 / 2023 (no DLC JSON name)
JSON_FORMAT = 'json'  # Let's Sing 2024+ (DLC JSON name present)

SLOW = "slow"
FAST = "fast"

PITCH_MIN = 43
PITCH_MAX = 81

SONG_DLC_FILE = 'SongsDLC.tsv'
NAME_TXT_FILE = 'name.txt'

MUSIC_GENRE_LIST = ['Pop', 'Rap', 'Rock', 'Ballad', 'Electro']

logging.basicConfig(
    filename='error.log',
    filemode='a',
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.ERROR
)
logger = logging.getLogger(__name__)

_ffmpeg_path = 'ffmpeg'
_ffprobe_path = 'ffprobe'
_rad_path = None
_output_dir = ''
_input_dir = ''


def _init_paths(cfg) -> None:
    """Set module-level tool / folder paths from the resolved config."""
    global _ffmpeg_path, _ffprobe_path, _rad_path, _output_dir, _input_dir

    # ffmpeg / ffprobe
    if cfg.tools.ffmpeg_path:
        _ffmpeg_path = str(cfg.tools.ffmpeg_path)
        candidate = str(Path(_ffmpeg_path).parent / 'ffprobe.exe')
        _ffprobe_path = candidate if os.path.isfile(candidate) else 'ffprobe'
    else:
        _ffmpeg_path = 'ffmpeg'
        _ffprobe_path = 'ffprobe'

    # RAD Video Tools
    _rad_path = str(cfg.tools.rad_path) if cfg.tools.rad_path else None

    # Folders
    _input_dir = str(cfg.folders.input) if cfg.folders.input else os.getcwd()
    _output_dir = str(cfg.folders.output) if cfg.folders.output else os.path.join(os.getcwd(), '_Patch')
    if os.path.isdir(_output_dir):
        for file_or_folder in os.listdir(_output_dir):
            if os.path.isfile(file_or_folder) or not re.search(r'^[0-9A-F]{16}', file_or_folder):
                # chosen folder contains unknown files or folders, append _Patch subfolder to path and approve
                _output_dir = os.path.join(_output_dir, "_Patch")
                break


def resolve_config(cfg):
    """Fill in missing values from the DLC database where possible."""
    dlc_id = str(cfg.dlc.id) if cfg.dlc.id else None
    if dlc_id:
        dlc_entity = repository.get_by_dlc_id(dlc_id)
        if dlc_entity:
            cfg.core.id = dlc_entity.core_id
            cfg.dlc.json_name = dlc_entity.dlc_json_name
    return cfg


def get_output_format(cfg) -> str:
    """JSON_FORMAT when dlc.json_name is set, else XML_FORMAT."""
    return JSON_FORMAT if cfg.dlc.json_name else XML_FORMAT


def _is_blank(value) -> bool:
    return not (value and not str(value).isspace())


def sanitize_name(name):
    name = ''.join(c for c in unicodedata.normalize('NFD', name)
                  if unicodedata.category(c) != 'Mn')
    name = name.replace('...', '')
    name = name.replace('…', '')
    name = re.sub(r"[!?#$%'\"\u2018\u2019\u00B4`\u201C\u201D()\[\]]", '', name)
    return ' '.join(name.split()).strip()


def rename_folders_physically():
    tqdm.write("Sanitizing folder names...")
    input_path = Path(_input_dir)
    current_dirs = [x for x in input_path.iterdir() if x.is_dir()]

    for folder in current_dirs:
        old_name = folder.name
        if old_name.startswith(('_', '.')):
            continue

        new_name = sanitize_name(old_name)

        if old_name != new_name:
            try:
                folder.rename(folder.parent / new_name)
                tqdm.write(f"Folder renamed: '{old_name}' -> '{new_name}'")
            except Exception as e:
                tqdm.write(f"Error while trying to rename {old_name}: {e}")


def construct_name_id_from_directory_name(dir_long_name) -> str:
    split_dir_name = dir_long_name.split(' - ')
    artist_dir_name = strip_accents(split_dir_name[0])
    title_dir_name = strip_accents(split_dir_name[1])
    artist_caps = [word[0].upper() for word in artist_dir_name.split()]
    artist_cap = ''.join(artist_caps)
    title_lower = ''.join(e.lower() for e in title_dir_name if e.isalnum())
    return artist_cap + title_lower


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


def find_folders_to_convert():
    input_path = Path(_input_dir)
    dir_to_convert = [x.name for x in input_path.iterdir() if x.is_dir()]
    dir_to_convert = [x for x in dir_to_convert if not x.startswith(('_', '.'))]
    return dir_to_convert


def delete_output_folder():
    try:
        if os.path.exists(_output_dir):
            tqdm.write(f"Removing existing output directory: {_output_dir}")
            shutil.rmtree(_output_dir)
            tqdm.write("Output directory successfully removed")
    except PermissionError:
        tqdm.write("Error: Could not delete output folder - permission denied")
    except Exception as e:
        tqdm.write(f"Error deleting output folder: {e}")


def get_duration(path_to_song):
    result = subprocess.run(
        [_ffprobe_path, '-v', 'error', '-show_entries',
         'format=duration', '-of',
         'default=noprint_wrappers=1:nokey=1', path_to_song],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )
    return float(result.stdout)


def is_video_still_image(file):
    duration = get_duration(file)
    cmd = [
        _ffmpeg_path, '-i', file,
        '-vf', 'freezedetect=n=0.01:d=0.1',
        '-map', '0:v:0', '-f', 'null', '-'
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    stderr = result.stderr

    freeze_starts = [float(m.group(1)) for m in re.finditer(r'freeze_start: ([\d.]+)', stderr)]
    freeze_ends = [float(m.group(1)) for m in re.finditer(r'freeze_end: ([\d.]+)', stderr)]

    if freeze_starts and (len(freeze_ends) < len(freeze_starts)):
        freeze_ends.append(duration)

    # Calculate total freeze duration
    total_freeze = sum(e - s for s, e in zip(freeze_starts, freeze_ends))
    # If freeze covers >95% of the video, treat as still image
    return total_freeze / duration > 0.95


def create_still_video_from_cover_image(files_jpg, files_txt, list_in_dir, output_mp4_file_name, song_duration, txt_data):
    tqdm.write('creating static video: ' + output_mp4_file_name)
    file = txt_data.get('COVER', None)
    if file:
        file = os.path.join(os.path.dirname(os.fspath(files_txt[-1])), txt_data.get('COVER', None))
    else:
        file = files_jpg[0]
    target_size_mb = 10
    target_bitrate_kbps = int((target_size_mb * 8192) / song_duration)
    complex_filter = (
        "split[bg][fg];"
        "[bg]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,gblur=sigma=10[bg_blurred];"
        "[fg]scale='if(gt(iw/ih,1280/720),min(iw,1280),-1)':'if(gt(iw/ih,1280/720),-1,min(ih,720))':force_original_aspect_ratio=decrease[fg_scaled];"
        "[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2,fps=25"
    )
    ffmpeg_cmd = [_ffmpeg_path, '-y', '-loop', '1',
                 '-i', os.fspath(file), '-c:v', 'libx264', '-t', str(song_duration),
                 '-preset', 'medium', '-tune', 'stillimage',
                 '-b:v', f'{target_bitrate_kbps}k',
                 '-vf', complex_filter,
                 '-pix_fmt', 'yuv420p',
                 '-an', os.fspath(list_in_dir / output_mp4_file_name)]
    subprocess.run(ffmpeg_cmd)


def create_in_game_loading_picture(files_jpg, list_in_dir, png_in_game_file_name):
    file = files_jpg[0]
    ffmpeg_cmd = [_ffmpeg_path, '-i', os.fspath(file), '-vf',
                 'scale=512:512:force_original_aspect_ratio=increase,crop=512:512',
                 os.fspath(list_in_dir / png_in_game_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + png_in_game_file_name)


def create_cover_long(files_jpg, list_in_dir, png_long_file_name):
    file = files_jpg[0]
    ffmpeg_cmd = [_ffmpeg_path, '-i', os.fspath(file), '-vf',
                 'scale=191:396:force_original_aspect_ratio=increase,crop=191:396',
                 os.fspath(list_in_dir / png_long_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + png_long_file_name)


def create_cover(files_jpg, list_in_dir, png_file_name):
    file = files_jpg[0]
    ffmpeg_cmd = [_ffmpeg_path, '-i', os.fspath(file), '-vf',
                 'scale=256:256:force_original_aspect_ratio=increase,crop=256:256',
                  os.fspath(list_in_dir / png_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + png_file_name)


def create_audio_preview(files_avi, files_mp3, list_in_dir, ogg_preview_file_name, txt_data):
    if files_mp3:
        file = files_mp3[0]
    else:
        file = files_avi[0]
    preview_start_time = 60
    preview_duration_time = 30
    if 'MEDLEYSTARTBEAT' in txt_data and 'MEDLEYENDBEAT' in txt_data:
        preview_start_beat = int(txt_data['MEDLEYSTARTBEAT'])
        preview_end_beat = int(txt_data['MEDLEYENDBEAT'])
        bpm = float(txt_data["BPM"].replace(',', '.'))
        gap = float(txt_data["GAP"].replace(',', '.')) / 1000
        preview_start_time = (preview_start_beat * 60 / bpm / 4) + gap
        preview_duration_time = ((preview_end_beat - preview_start_beat) * 60 / bpm / 4)
    elif 'PREVIEWSTART' in txt_data:
        preview_start_time = float(txt_data['PREVIEWSTART'].replace(',', '.'))
    ffmpeg_cmd = [_ffmpeg_path, '-ss', str(preview_start_time), '-i', os.fspath(file),
                 '-vn',
                 '-t', str(preview_duration_time), '-ar', '48000',
                 '-af', 'loudnorm=I=-16:LRA=11:TP=-1.5',
                 os.fspath(list_in_dir / ogg_preview_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + ogg_preview_file_name)


def create_audio(files_avi, files_mp3, list_in_dir, ogg_file_name, video_gap):
    if files_mp3:
        file = files_mp3[0]
    else:
        file = files_avi[0]
    filter_cmd = ''
    if video_gap < 0:
        # Negative gap: trim the beginning of the audio
        # Remove the first |video_gap| seconds
        filter_cmd = f'atrim=start={abs(video_gap)},'
    elif video_gap > 0:
        # Positive gap: add silence to the beginning
        # Insert video_gap seconds of silence before the audio
        filter_cmd = f'adelay={int(video_gap * 1000)}|{int(video_gap * 1000)},'
    filter_cmd += 'loudnorm=I=-16:LRA=11:TP=-1.5'
    ffmpeg_cmd = [_ffmpeg_path, '-i', os.fspath(file), '-vn', '-ar', '48000',
                 '-af', filter_cmd,
                 os.fspath(list_in_dir / ogg_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + ogg_file_name)


def create_video(file, list_in_dir, output_video_file_name, target_bitrate_kbps):
    # First pass to analyze video
    ffmpeg_cmd = [_ffmpeg_path, '-y', '-i', os.fspath(file),
                 '-c:v', 'libx264', '-preset', 'medium', '-b:v', f'{target_bitrate_kbps}k',
                 '-pass', '1', '-an', '-vf',
                 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=25',
                 '-f', 'null', os.devnull]
    subprocess.run(ffmpeg_cmd)
    # Second pass to create final file
    ffmpeg_cmd = [_ffmpeg_path, '-y', '-i', os.fspath(file),
                 '-c:v', 'libx264', '-preset', 'medium', '-b:v', f'{target_bitrate_kbps}k',
                 '-pass', '2', '-an', '-vf',
                 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=25',
                  os.fspath(list_in_dir / output_video_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + output_video_file_name)
    # Clean up FFmpeg passlog files
    for log_file in Path('.').glob('ffmpeg2pass*'):
        os.remove(log_file)


def create_video_bink(file, list_in_dir, output_video_file_name, compression_percentage, quality):
    if not _rad_path:
        tqdm.write("ERROR: RAD Video Tools path not configured - cannot create .bk2 video")
        return
    file_format = '/V' + str(200)
    remove_sound = '/L-1'
    bink_args = [_rad_path, 'binkc', file, os.fspath(list_in_dir / output_video_file_name), file_format,
                    '/(1280', '/)720', remove_sound]
    if compression_percentage:
        data_rate_switch = '/D' + str(compression_percentage)
        bink_args.append(data_rate_switch)
    if quality:
        quality_switch = '/Q' + str(quality)
        bink_args.append(quality_switch)
    bink_args.append('/#')
    tqdm.write(f"Converting video {file} to {output_video_file_name} with args: {bink_args}")
    subprocess.run(bink_args, capture_output=True, text=True)


def match_genre(txt_data):
    genre_raw = txt_data.get('GENRE', '').lower()
    for g in MUSIC_GENRE_LIST:
        if g.lower() in genre_raw:
            return g
    return 'Pop'


def handle_xml_or_json(dlc_id, core_id, json_file_name, list_in_dir, txt_data,
                       name_id, output_format, xml_file_name, cfg):
    title = txt_data.get('TITLE', 'title')
    artist = txt_data.get('ARTIST', 'artist')
    year = txt_data.get('YEAR', '2000')
    genre = match_genre(txt_data)

    if output_format == XML_FORMAT:
        uid = add_data_to_songsdlc_tsv(core_id, artist, name_id, title, year, cfg)
        create_meta_xml(uid, artist, genre, list_in_dir, name_id, title, xml_file_name, year)
    elif output_format == JSON_FORMAT:
        song_data = {
            "id": name_id,
            "artist": artist,
            "title": title,
            "gender": "Both",
            "year": int(year),
            "timeless": "",
            "genre": genre,
            "theme": "Love, Deep, Party",
            "difficulty": "VeryEasy",
            "coopfriendly": "Coop"
        }
        add_song_to_json(dlc_id, json_file_name, song_data, cfg)


def create_meta_xml(UID, artist, genre, list_in_dir, name_id, title, xml_file_name, year):
    root = Et.Element("DLCSong")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
    Et.SubElement(root, "Genre").text = genre
    Et.SubElement(root, "Id").text = name_id
    Et.SubElement(root, "Uid").text = str(UID)
    Et.SubElement(root, "Artist").text = artist
    Et.SubElement(root, "Title").text = title
    Et.SubElement(root, "Year").text = year
    Et.SubElement(root, "Ratio").text = "Ratio_16_9"
    Et.SubElement(root, "Difficulty").text = "Difficulty0"
    Et.SubElement(root, "Feat")
    Et.SubElement(root, "Line1").text = artist
    Et.SubElement(root, "Line2")
    xmlstr = minidom.parseString(Et.tostring(root)).toprettyxml(
        encoding="utf-8", indent="   ").decode('utf-8')
    xmlbin = xmlstr.replace('\n', '\r\n').encode('utf-8-sig')
    with open(os.fspath(list_in_dir / xml_file_name), "wb") as f:
        f.write(xmlbin)


def add_song_to_json(dlc_id, json_file_name, song_data, cfg):
    include_dlc = bool(cfg.conversion_tweaks.dlc_songs.include)
    source_json = str(cfg.conversion_tweaks.dlc_songs.songs_json_path) if not _is_blank(cfg.conversion_tweaks.dlc_songs.songs_json_path) else None

    dlc_romfs_dir = os.path.join(_output_dir, dlc_id, 'romfs')
    os.makedirs(dlc_romfs_dir, exist_ok=True)
    dest_json_file = os.path.join(dlc_romfs_dir, json_file_name)

    if os.path.exists(dest_json_file):
        with open(dest_json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        if include_dlc and source_json and os.path.exists(source_json):
            shutil.copy2(source_json, dest_json_file)
            with open(dest_json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {"name": json_file_name.split('_')[1].split('.')[0], "songs": []}

    data['songs'].append(song_data)
    with open(dest_json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def add_data_to_songsdlc_tsv(core_id, artist, name_id, title, year, cfg):
    core_assets_dir = os.path.join(_output_dir, core_id, 'romfs/Data/StreamingAssets')
    os.makedirs(core_assets_dir, exist_ok=True)
    dest_songs_dlc = os.path.join(core_assets_dir, SONG_DLC_FILE)

    if not os.path.exists(dest_songs_dlc):
        include_dlc = bool(cfg.conversion_tweaks.dlc_songs.include)
        source_tsv = str(cfg.conversion_tweaks.dlc_songs.songs_dlc_tsv_path) if not _is_blank(
            cfg.conversion_tweaks.dlc_songs.songs_dlc_tsv_path) else None

        if include_dlc and source_tsv and os.path.exists(source_tsv):
            shutil.copy2(source_tsv, dest_songs_dlc)
        else:
            with open(dest_songs_dlc, 'w') as outfile:
                outfile.write("ENABLED\tUID\tID\tARTIST\tTITLE\tYEAR\tDIFFICULTY\tSKU_INT\tSKU_FR\tSKU_SPA\tSKU_GER"
                              "\tDLC_INDEX\tVIDEO_RATIO\tGENRE_POP_UNLOCKED\tGENRE_RAP\tGENRE_BALLAD\tGENRE_ROCK"
                              "\tGENRE_HAPPY_UNLOCKED\tGENRE_FIESTA\tGENRE_LOVE\tGENRE_SAD\tGENRE_OLD_UNLOCKED"
                              "\tGENRE_2000\tGENRE_RECENT\tGENRE_RANDOM_UNLOCKED"
                              "\tGENRE_VO\tGENRE_WOMEN\tGENRE_ENGLISH\tGENRE_MEN\n")

    songs_xls = pd.read_csv(dest_songs_dlc, sep='\t', index_col=0)
    if songs_xls.empty:
        uid = 200
        new_row = {
            'UID': uid,
            'ID': name_id,
            'ARTIST': artist,
            'TITLE': title,
            'YEAR': int(year),
            'DIFFICULTY': '0',
            'SKU_INT': 'x',
            'SKU_FR': 'x',
            'SKU_SPA': 'x',
            'SKU_GER': 'x',
            'DLC_INDEX': '1',
            'VIDEO_RATIO': 'RATIO_16_9',
            'GENRE_RANDOM_UNLOCKED': 'x',
            'GENRE_ENGLISH': 'x',
        }
        for col in songs_xls.columns:
            if col not in new_row:
                new_row[col] = ''
        songs_xls.loc[0] = new_row
        songs_xls.index = ['x']
    else:
        highest_current_uid = max(songs_xls['UID'].values)
        uid = 200 if highest_current_uid < 200 else highest_current_uid + 1
        new_row = len(songs_xls.index)
        original_index = songs_xls.index.copy()
        songs_xls.loc[new_row] = songs_xls.iloc[-1].copy()
        songs_xls.loc[new_row, 'UID'] = uid
        songs_xls.loc[new_row, 'ID'] = name_id
        songs_xls.loc[new_row, 'ARTIST'] = artist
        songs_xls.loc[new_row, 'TITLE'] = title
        songs_xls.loc[new_row, 'YEAR'] = int(year)
        new_index = list(original_index) + ['x']
        songs_xls.index = new_index

    songs_xls.to_csv(dest_songs_dlc, sep='\t', index_label='ENABLED')
    return uid


def add_data_to_name_txt(dlc_id, name_id, output_format, dlc_json_name, cfg):
    include_dlc = bool(cfg.conversion_tweaks.dlc_songs.include)
    source_name_txt = str(cfg.conversion_tweaks.dlc_songs.name_txt_path) if not _is_blank(cfg.conversion_tweaks.dlc_songs.name_txt_path) else None

    dlc_romfs_dir = os.path.join(_output_dir, dlc_id, 'romfs')
    os.makedirs(dlc_romfs_dir, exist_ok=True)
    dest_name_txt = os.path.join(dlc_romfs_dir, NAME_TXT_FILE)

    if not os.path.exists(dest_name_txt):
        if include_dlc and source_name_txt and os.path.exists(source_name_txt):
            shutil.copy2(source_name_txt, dest_name_txt)
        else:
            if output_format == XML_FORMAT:
                open(dest_name_txt, 'w').close()
            elif output_format == JSON_FORMAT:
                with open(dest_name_txt, 'w') as outfile:
                    outfile.write(dlc_json_name + '\n')
    # Append song ID for XML format
    if output_format == XML_FORMAT:
        with open(dest_name_txt, 'a') as outfile:
            outfile.write(name_id + '\n')


def convert_files(dirs_to_convert, cfg):
    dlc_id = str(cfg.dlc.id)
    core_id = str(cfg.core.id) if cfg.core.id else None
    output_format = get_output_format(cfg)
    dlc_json_name = str(cfg.dlc.json_name) if cfg.dlc.json_name else None
    target_size_mb = float(cfg.conversion_tweaks.max_video_size or 50)
    pitch_correction_method = str(cfg.conversion_tweaks.pitch_correction or FAST).lower()
    ignore_medley = bool(cfg.conversion_tweaks.no_medley)
    ignore_video = bool(cfg.conversion_tweaks.still_video)

    # Map output_format to UltrastarToSingit OLD/NEW constants
    vxla_output_type = UltrastarToSingit.NEW if output_format == JSON_FORMAT else UltrastarToSingit.OLD

    json_file_name = (dlc_json_name + '.json') if dlc_json_name else None

    for dir_long_name in tqdm(dirs_to_convert, desc="Converting folders"):
        try:
            if ' - ' not in dir_long_name:
                continue

            name_id = construct_name_id_from_directory_name(dir_long_name)
            tqdm.write(name_id)

            list_in_dir = Path(_input_dir) / dir_long_name
            files_all = [os.fspath(x.name) for x in list_in_dir.iterdir()]
            files_txt = [x for x in list_in_dir.iterdir() if x.suffix.lower() == '.txt']
            files_avi = [x for x in list_in_dir.iterdir() if x.suffix.lower() in ('.avi', '.divx', '.mp4', '.flv', '.mkv', '.webm')]
            files_mp3 = [x for x in list_in_dir.iterdir() if x.suffix.lower() in ('.mp3', '.ogg', '.wav', '.flac', '.aac', '.m4a', '.opus')]
            files_jpg = [x for x in list_in_dir.iterdir() if x.suffix.lower() in ('.jpg', '.jpeg', '.png')]

            output_video_file_name = name_id + '.mp4' if output_format == XML_FORMAT else name_id + '.bk2'
            png_file_name = name_id + '.png'
            png_in_game_file_name = name_id + '_InGameLoading.png'
            png_long_file_name = name_id + '_long.png'
            png_result_file_name = name_id + '_Result.png'
            vxla_file_name = name_id + '.vxla'
            ogg_file_name = name_id + '.ogg'
            ogg_preview_file_name = name_id + '_preview.ogg'
            xml_file_name = name_id + '_meta.xml'

            # Getting info from the text file
            if not files_txt:
                tqdm.write('No ultrastar text file found for ' + dir_long_name + ', skipping')
                continue

            # some songs also have a duet txt file containing '[MULTI]' in its name, alphabetically we want the last one
            txt_data = UltrastarToSingit.parse_file(files_txt[-1])
            video_gap = 0
            if 'VIDEOGAP' in txt_data:
                # how many seconds the song is out of sync with the video
                #  positive - video starts before the song
                #  negative - video starts after the song
                video_gap = float(txt_data['VIDEOGAP'].replace(',', '.'))

            if files_avi and not ignore_video:
                file = files_avi[0]
                duration = get_duration(os.fspath(file))
                original_size_bytes = file.stat().st_size
                original_size_mb = original_size_bytes / (1024 * 1024)
                target_bitrate_kbps = int((original_size_mb * 8192) / duration)

                if output_video_file_name not in files_all:
                    if output_format == XML_FORMAT:
                        if original_size_mb > target_size_mb:
                            target_bitrate_kbps = int((target_size_mb * 8192) / duration)
                        create_video(file, list_in_dir, output_video_file_name, target_bitrate_kbps)
                    elif output_format == JSON_FORMAT:
                        if is_video_still_image(file):
                            quality = 0.1
                        else:
                            quality = None
                        tqdm.write(str(file))
                        temp_mp4_name = name_id + '.mp4'
                        temp_mp4_file = list_in_dir / temp_mp4_name
                        if file.suffix.lower() in ('.avi', '.divx', '.mp4', '.flv', '.mkv', '.webm'):
                            if not temp_mp4_file.exists():
                                create_video(file, list_in_dir, temp_mp4_name, target_bitrate_kbps)

                            temp_size_bytes = temp_mp4_file.stat().st_size
                            temp_size_mb = temp_size_bytes / (1024 * 1024)
                            if temp_size_mb <= target_size_mb:
                                compression_percentage = 100
                            else:
                                percentage = (target_size_mb / temp_size_mb) * 100
                                compression_percentage = max(1, min(200, int(round(percentage))))

                            create_video_bink(os.fspath(temp_mp4_file), list_in_dir, output_video_file_name, compression_percentage, quality)

            if ogg_file_name not in files_all:
                create_audio(files_avi, files_mp3, list_in_dir, ogg_file_name, video_gap)

            if ogg_preview_file_name not in files_all:
                create_audio_preview(files_avi, files_mp3, list_in_dir, ogg_preview_file_name, txt_data)

            if files_jpg and png_file_name not in files_all:
                create_cover(files_jpg, list_in_dir, png_file_name)

            if files_jpg and png_long_file_name not in files_all:
                create_cover_long(files_jpg, list_in_dir, png_long_file_name)

            if files_jpg and png_in_game_file_name not in files_all:
                create_in_game_loading_picture(files_jpg, list_in_dir, png_in_game_file_name)

            song_duration = get_duration(os.fspath(list_in_dir / ogg_file_name))

            if not files_avi or ignore_video or not os.path.exists(os.path.join(list_in_dir / output_video_file_name)):
                # If no video file was present in the song's directory, or if "RAD" Video Tools failed to convert it,
                # create a still image video from the cover image
                output_video_file_name_mp4 = name_id + '_cover.mp4'
                if not os.path.exists(list_in_dir / output_video_file_name_mp4):
                    create_still_video_from_cover_image(files_jpg, files_txt, list_in_dir, output_video_file_name_mp4, song_duration, txt_data)
                else:
                    tqdm.write(f"Static video already exists, skipping generation: {output_video_file_name_mp4}")

                if output_format == JSON_FORMAT:
                    if not os.path.exists(list_in_dir / output_video_file_name):
                        create_video_bink(os.fspath(list_in_dir / output_video_file_name_mp4), list_in_dir, output_video_file_name, None, quality=0.1)
                elif output_format == XML_FORMAT:
                    if ignore_video or not os.path.exists(list_in_dir / output_video_file_name):
                        shutil.copy2(list_in_dir / output_video_file_name_mp4, list_in_dir / output_video_file_name)

            # generating vxla file
            if pitch_correction_method == SLOW:
                pitch_corr = PitchAnalyzer.get_pitch_correction_suggestion_slow(txt_data, os.fspath(list_in_dir / ogg_file_name),
                                                                                min_pitch=PITCH_MIN, max_pitch=PITCH_MAX)
            else:
                pitch_corr = PitchAnalyzer.get_pitch_correction_suggestion_fast(txt_data, min_pitch=PITCH_MIN, max_pitch=PITCH_MAX)
            UltrastarToSingit.main(files_txt[-1], song_duration, pitch_corr, s=name_id, directory=list_in_dir, output_type=vxla_output_type, ignore_medley=ignore_medley)

            # Handle name.txt
            add_data_to_name_txt(dlc_id, name_id, output_format, dlc_json_name, cfg)

            # Handle SongsDLC.tsv for XML format, or json file for JSON format
            handle_xml_or_json(dlc_id, core_id, json_file_name, list_in_dir, txt_data,
                               name_id, output_format, xml_file_name, cfg)

            # creating the folder structure if not already present
            base_dlc_dir = os.path.join(_output_dir, dlc_id)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/audio'), exist_ok=True)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/audio_preview'), exist_ok=True)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/covers'), exist_ok=True)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/videos'), exist_ok=True)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/vxla'), exist_ok=True)

            # placing all files into the correct folders
            shutil.copy2(os.fspath(list_in_dir / ogg_file_name), os.path.join(base_dlc_dir, 'romfs/Songs/audio'))
            shutil.copy2(os.fspath(list_in_dir / ogg_preview_file_name), os.path.join(base_dlc_dir, 'romfs/Songs/audio_preview'))
            shutil.copy2(os.fspath(list_in_dir / png_file_name), os.path.join(base_dlc_dir, 'romfs/Songs/covers'))
            shutil.copy2(os.fspath(list_in_dir / vxla_file_name), os.path.join(base_dlc_dir, 'romfs/Songs/vxla'))
            shutil.copy2(os.fspath(list_in_dir / output_video_file_name), os.path.join(base_dlc_dir, 'romfs/Songs/videos'))

            if output_format == XML_FORMAT:
                os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/backgrounds/InGameLoading'), exist_ok=True)
                os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/backgrounds/Result'), exist_ok=True)
                os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/covers_duet'), exist_ok=True)
                os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/covers_long'), exist_ok=True)

                shutil.copy2(os.fspath(list_in_dir / png_in_game_file_name), os.path.join(base_dlc_dir, 'romfs/Songs/backgrounds/InGameLoading'))
                shutil.copy2(os.fspath(list_in_dir / png_in_game_file_name), os.path.join(base_dlc_dir, 'romfs/Songs/backgrounds/Result', png_result_file_name))
                shutil.copy2(os.fspath(list_in_dir / png_long_file_name), os.path.join(base_dlc_dir, 'romfs/Songs/covers_long'))
                shutil.copy2(os.fspath(list_in_dir / xml_file_name), os.path.join(base_dlc_dir, 'romfs'))

        except Exception as e:
            logger.exception(f"Error with directory {dir_long_name}")
            tqdm.write(f"Error with directory {dir_long_name}: {e}")
            continue


def main(cfg=None):
    
    if cfg is None:
        cfg = load_config()
        cfg = resolve_config(cfg)

    _init_paths(cfg)

    output_format = get_output_format(cfg)
    pitch_method = str(cfg.conversion_tweaks.pitch_correction or FAST).lower()
    ignore_medley = bool(cfg.conversion_tweaks.no_medley)
    ignore_video = bool(cfg.conversion_tweaks.still_video)

    delete_output_folder()
    rename_folders_physically()
    dirs_to_convert = find_folders_to_convert()

    tqdm.write('Beginning conversion - format: ' + output_format.upper())
    tqdm.write('Pitch correction method: ' + pitch_method)
    if ignore_medley:
        tqdm.write('MODE: Ignoring Medley tags (forcing Genius/Auto detection)')
    if ignore_video:
        tqdm.write('MODE: Ignoring original video (forcing still image video)')
    convert_files(dirs_to_convert, cfg)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert UltraStar files to Let's Sing DLC format.",
        epilog="All options override values from config_default.yml / config.yml for this run only (nothing is saved)."
    )

    # DLC / Core IDs
    parser.add_argument('--dlc-id', type=str,
                        help='DLC TitleID (e.g. 01001C101ED11002)')
    parser.add_argument('--dlc-json-name', type=str, default=None,
                        help='DLC JSON name (e.g. songs_fr). '
                             'When set the JSON/new format is used; when omitted the XML/old format is used.')
    parser.add_argument('--core-id', type=str,
                        help='Core TitleID (required for XML format)')

    # Tool paths
    parser.add_argument('--ffmpeg-path', type=str,
                        help='Path to ffmpeg executable')
    parser.add_argument('--rad-path', type=str,
                        help='Path to radvideo64 executable')

    # Folders
    parser.add_argument('--input', type=str,
                        help='Input folder containing song directories')
    parser.add_argument('--output', type=str,
                        help='Output folder for patch files')

    # Conversion tweaks
    parser.add_argument('--pitch-correction', type=str.lower,
                        choices=[FAST, SLOW],
                        help='Pitch correction method (default: from config)')
    parser.add_argument('--max-video-size', type=int,
                        help='Maximum video file size in MB')
    parser.add_argument('--no-medley', action='store_true',
                        help='Ignore MEDLEY tags in txt files and force Genius/Auto detection')
    parser.add_argument('--still-video', action='store_true',
                        help='Ignore existing video files and force still video creation from cover')

    # DLC songs inclusion
    parser.add_argument('--include-dlc-songs', action='store_true',
                        help='Include the existing songs from the DLC')
    parser.add_argument('--name-txt-path', type=str,
                        help='Path to existing name.txt from the DLC')
    parser.add_argument('--songs-json-path', type=str,
                        help='Path to existing songs_xx.json from the DLC')
    parser.add_argument('--songs-tsv-path', type=str,
                        help='Path to existing SongsDLC.tsv from the DLC')

    args = parser.parse_args()

    # 1. Load config from YAML files (same as GUI)
    config = load_config()

    # 2. Fill missing values from the DLC database
    config = resolve_config(config)

    # 3. Apply CLI overrides (without saving)
    if args.dlc_id:
        config.dlc.id = args.dlc_id
    if args.dlc_json_name is not None:
        config.dlc.json_name = args.dlc_json_name or None
    if args.core_id:
        config.core.id = args.core_id
    if args.ffmpeg_path:
        config.tools.ffmpeg_path = args.ffmpeg_path
    if args.rad_path:
        config.tools.rad_path = args.rad_path
    if args.input:
        config.folders.input = args.input
    if args.output:
        config.folders.output = args.output
    if args.pitch_correction:
        config.conversion_tweaks.pitch_correction = args.pitch_correction
    if args.max_video_size:
        config.conversion_tweaks.max_video_size = args.max_video_size
    if args.no_medley:
        config.conversion_tweaks.no_medley = True
    if args.still_video:
        config.conversion_tweaks.still_video = True
    if args.include_dlc_songs:
        config.conversion_tweaks.dlc_songs.include = True
    if args.name_txt_path:
        config.conversion_tweaks.dlc_songs.name_txt_path = args.name_txt_path
    if args.songs_json_path:
        config.conversion_tweaks.dlc_songs.songs_json_path = args.songs_json_path
    if args.songs_tsv_path:
        config.conversion_tweaks.dlc_songs.songs_dlc_tsv_path = args.songs_tsv_path

    main(config)
