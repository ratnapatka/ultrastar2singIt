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

# Lets Sing 2022 IDs
COREID = '0100CC30149B8000'
DLCID_2022 = '0100CC30149B9011' # Best of 90s Vol 3 Song Pack

# Let's Sing 2025 DLC ID, core ID doesn't matter
DLCID_2025 = '01001C101ED11002' # French Hits
DLC_NAME_DEFAULT = 'songs_fr'

OLD = '2022'
NEW = '2025'

SLOW = "slow"
FAST = "fast"

PITCH_MIN = 43
PITCH_MAX = 81
TARGET_SIZE_MB = 50.0

SONG_DLC_FILE = 'SongsDLC.tsv'
NAME_TXT_FILE = 'name.txt'

MUSIC_GENRE_LIST = ['Pop', 'Rap', 'Rock', 'Ballad', 'Electro']

p = Path('.')
local_dir = os.getcwd()
patch_folder_name = '_Patch'
patch_dir = os.path.join(local_dir, patch_folder_name)

logging.basicConfig(
    filename='error.log',
    filemode='a',
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.ERROR
)
logger = logging.getLogger(__name__)

def convert_files(dirs_to_convert, output_type=NEW, pitch_correction_method=SLOW):

    DLCID = DLCID_2022 if output_type == OLD else DLCID_2025

    json_files = [f for f in os.listdir('.') if f.endswith('.json') and os.path.isfile(f)]
    if json_files:
        dlc_name = os.path.splitext(json_files[0])[0]
    else:
        dlc_name = DLC_NAME_DEFAULT

    for dir_long_name in tqdm(dirs_to_convert, desc="Converting folders"):

        try:
            # only directory with the format Artist - Title
            if not ' - ' in dir_long_name:
                continue

            split_dir_name = dir_long_name.split(' - ')
            artist_dir_name = strip_accents(split_dir_name[0])
            title_dir_name = strip_accents(split_dir_name[1])
            arist_caps = [word[0].upper() for word in artist_dir_name.split()]
            arist_cap = ''.join(arist_caps)
            title_lower = ''.join(e.lower() for e in title_dir_name if e.isalnum())
            name_id = arist_cap + title_lower

            tqdm.write(name_id)

            list_in_dir = Path(dir_long_name)
            files_all = [os.fspath(x.name) for x in list_in_dir.iterdir()]
            files_txt = [x for x in list_in_dir.iterdir() if x.suffix.lower() == '.txt']
            files_avi = [x for x in list_in_dir.iterdir() if x.suffix.lower() in ('.avi', '.divx', '.mp4', '.flv', '.mkv', '.webm')]
            files_mp3 = [x for x in list_in_dir.iterdir() if x.suffix.lower() in ('.mp3', '.ogg', '.wav', '.flac', '.aac', '.m4a', '.opus')]
            files_jpg = [x for x in list_in_dir.iterdir() if x.suffix.lower() in ('.jpg', '.jpeg', '.png')]

            output_video_file_name = name_id + '.mp4' if output_type == OLD else name_id + '.bk2'
            png_file_name = name_id + '.png'
            png_in_game_file_name = name_id + '_InGameLoading.png'
            png_long_file_name = name_id + '_long.png'
            png_result_file_name = name_id + '_Result.png'
            vxla_file_name = name_id + '.vxla'
            ogg_file_name = name_id + '.ogg'
            ogg_preview_file_name = name_id + '_preview.ogg'
            xml_file_name = name_id + '_meta.xml'
            json_file_name = dlc_name + '.json'

            # Getting info from the text file
            if not files_txt:
                tqdm.write('need an ultrastar filetext!!')
                continue

            # some songs also have a duet txt file containing '[MULTI]' in its name, alphabetically we want the last one
            txt_data = UltrastarToSingit.parse_file(files_txt[-1])
            video_gap = 0
            if 'VIDEOGAP' in txt_data:
                # how many seconds the song is out of sync with the video
                #  positive - video starts before the song
                #  negative - video starts after the song
                video_gap = float(txt_data['VIDEOGAP'].replace(',', '.'))

            if files_avi:
                file = files_avi[0]
                duration = get_duration(os.fspath(file))
                original_size_bytes = file.stat().st_size
                original_size_mb = original_size_bytes / (1024 * 1024)
                target_bitrate_kbps = int((original_size_mb * 8192) / duration)  # Convert MB to kilobits

                if output_video_file_name not in files_all:
                    if output_type == OLD:
                        if original_size_mb > TARGET_SIZE_MB:
                            target_bitrate_kbps = int((TARGET_SIZE_MB * 8192) / duration)  # Keep bitrate below 50 mb
                        create_video(file, list_in_dir, output_video_file_name, target_bitrate_kbps)
                    elif output_type == NEW:
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
                            if temp_size_mb <= TARGET_SIZE_MB:
                                compression_percentage = 100
                            else:
                                percentage = (TARGET_SIZE_MB / temp_size_mb) * 100
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

            if not files_avi or not os.path.exists(os.path.join(list_in_dir / output_video_file_name)):
                # If no video file was present in the song's directory, or if "RAD" Video Tools failed to convert it,
                # create a still image video from the cover image
                output_video_file_name_mp4 = name_id + '.mp4'
                create_still_video_from_cover_image(files_jpg, files_txt, list_in_dir, output_video_file_name_mp4, song_duration, txt_data)
                if output_type == NEW:
                    create_video_bink(os.fspath(list_in_dir / output_video_file_name_mp4), list_in_dir, output_video_file_name,
                                      None, quality=0.1)  # Convert to bink with low quality

            # generating vxla file
            if pitch_correction_method == SLOW:
                pitch_corr = PitchAnalyzer.get_pitch_correction_suggestion(txt_data, os.fspath(list_in_dir / ogg_file_name),
                                                                              min_pitch=PITCH_MIN, max_pitch=PITCH_MAX)
            else:
                pitch_corr = PitchAnalyzer.get_pitch_correction_suggestion_fast(txt_data,min_pitch=PITCH_MIN, max_pitch=PITCH_MAX)
            UltrastarToSingit.main(files_txt[-1], song_duration, pitch_corr, s=name_id, dir=list_in_dir, output_type=output_type)

            # Handle name.txt - create it at destination if it doesn't exist
            add_data_to_name_txt(DLCID, name_id, output_type, dlc_name)

            # Handle SongsDLC.tsv for OLD dlc, or json file for NEW dlc
            handle_xml_or_json(DLCID, json_file_name, list_in_dir, txt_data, name_id, output_type, xml_file_name)

            # creating the folder structure if not already present
            base_dlc_dir = os.path.join(local_dir, patch_folder_name, DLCID)
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

            if output_type == OLD:
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

def strip_accents(s):
   return ''.join(c for c in unicodedata.normalize('NFD', s)
                  if unicodedata.category(c) != 'Mn')

def get_duration(path_to_song):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries',
         'format=duration', '-of',
         'default=noprint_wrappers=1:nokey=1', path_to_song],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )
    return float(result.stdout)

def handle_xml_or_json(DLCID, json_file_name, list_in_dir, txt_data, name_id, output_type, xml_file_name):
    title = txt_data.get('TITLE', 'title')
    artist = txt_data.get('ARTIST', 'artist')
    year = txt_data.get('YEAR', '2000')
    genre = match_genre(txt_data)

    if output_type == OLD:
        # append data to SongsDLC.tsv - create it at destination if it doesn't exist
        UID = add_data_to_songsdlc_tsv(artist, name_id, title, year)

        # XML song meta file
        create_meta_xml(UID, artist, genre, list_in_dir, name_id, title, xml_file_name, year)

    elif output_type == NEW:
        # Prepare song data for JSON
        song_data = {
            "id": name_id,
            "artist": artist,
            "title": title,
            "gender": "Both",
            "year": int(year),
            "timeless": "",
            "genre": genre,
            "theme": "Love",
            "difficulty": "VeryEasy",
            "coopfriendly": "Coop"
        }
        add_song_to_json(DLCID, json_file_name, song_data)

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

def add_song_to_json(dlc_id, json_file_name, song_data):
    dlc_romfs_dir = os.path.join(local_dir, patch_folder_name, dlc_id, 'romfs')
    os.makedirs(dlc_romfs_dir, exist_ok=True)
    dest_json_file = os.path.join(dlc_romfs_dir, json_file_name)

    if os.path.exists(dest_json_file):
        with open(dest_json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        if os.path.exists(json_file_name):
            # Copy existing json from root if it exists
            shutil.copy2(json_file_name, dest_json_file)
            with open(dest_json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            # Create a new json file
            data = {"name": json_file_name.split('_')[1].split('.')[0], "songs": []}

    data['songs'].append(song_data)
    with open(dest_json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def add_data_to_songsdlc_tsv(artist, name_id, title, year):
    core_assets_dir = os.path.join(local_dir, patch_folder_name, COREID, 'romfs/Data/StreamingAssets')
    os.makedirs(core_assets_dir, exist_ok=True)
    dest_songs_dlc = os.path.join(core_assets_dir, SONG_DLC_FILE)
    if not os.path.exists(dest_songs_dlc):
        if os.path.exists(SONG_DLC_FILE):
            # Copy existing SongsDLC.tsv from root if it exists
            shutil.copy2(SONG_DLC_FILE, dest_songs_dlc)
        else:
            # Create a new empty SongsDLC.tsv file with proper headers
            with open(dest_songs_dlc, 'w') as outfile:
                outfile.write("ENABLED\tUID\tID\tARTIST\tTITLE\tYEAR\tDIFFICULTY\tSKU_INT\tSKU_FR\tSKU_SPA\tSKU_GER"
                              "\tDLC_INDEX\tVIDEO_RATIO\tGENRE_POP_UNLOCKED\tGENRE_RAP\tGENRE_BALLAD\tGENRE_ROCK"
                              "\tGENRE_HAPPY_UNLOCKED\tGENRE_FIESTA\tGENRE_LOVE\tGENRE_SAD\tGENRE_OLD_UNLOCKED"
                              "\tGENRE_2000\tGENRE_RECENT\tGENRE_RANDOM_UNLOCKED"
                              "\tGENRE_VO\tGENRE_WOMEN\tGENRE_ENGLISH\tGENRE_MEN\n")
    songs_xls = pd.read_csv(dest_songs_dlc, sep='\t', index_col=0)
    if songs_xls.empty:
        # Create the first row with default values
        UID = 200
        new_row = {
            'UID': UID,
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
        songs_xls.index = ['x']  # Set index to 'x' for the first row
    else:
        highest_current_uid = max(songs_xls['UID'].values)
        UID = 200 if highest_current_uid < 200 else highest_current_uid + 1
        newRow = len(songs_xls.index)
        original_index = songs_xls.index.copy()
        songs_xls.loc[newRow] = songs_xls.iloc[-1].copy()
        songs_xls.loc[newRow, 'UID'] = UID
        songs_xls.loc[newRow, 'ID'] = name_id
        songs_xls.loc[newRow, 'ARTIST'] = artist
        songs_xls.loc[newRow, 'TITLE'] = title
        songs_xls.loc[newRow, 'YEAR'] = int(year)
        new_index = list(original_index) + ['x']
        songs_xls.index = new_index

    songs_xls.to_csv(dest_songs_dlc, sep='\t', index_label='ENABLED')
    return UID

def match_genre(txt_data):
    genre_raw = txt_data.get('GENRE', '').lower()
    for g in MUSIC_GENRE_LIST:
        if g.lower() in genre_raw:
            return g
    return 'Pop'  # default

def add_data_to_name_txt(dlcId, name_id, output_type, dlc_name):
    dlc_romfs_dir = os.path.join(local_dir, patch_folder_name, dlcId, 'romfs')
    os.makedirs(dlc_romfs_dir, exist_ok=True)
    dest_name_txt = os.path.join(dlc_romfs_dir, NAME_TXT_FILE)
    if not os.path.exists(dest_name_txt):
        if os.path.exists(NAME_TXT_FILE):
            # Copy existing name.txt from root if it exists
            shutil.copy2(NAME_TXT_FILE, dest_name_txt)
        else:
            # Create a new empty name.txt file
            if output_type == OLD:
                open(dest_name_txt, 'w').close()
            elif output_type == NEW:
                with open(dest_name_txt, 'w') as outfile:
                    outfile.write(dlc_name + '\n')
    # Add new entry to name.txt in destination for OLD dlc
    if output_type == OLD:
        with open(dest_name_txt, 'a') as outfile:
            outfile.write(name_id + '\n')

def is_video_still_image(file):
    duration = get_duration(file)
    cmd = [
        'ffmpeg', '-i', file,
        '-vf', 'freezedetect=n=0.01:d=0.1',
        '-map', '0:v:0', '-f', 'null', '-'
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    stderr = result.stderr

    # Find freeze_start and freeze_end times
    freeze_starts = [float(m.group(1)) for m in re.finditer(r'freeze_start: ([\d.]+)', stderr)]
    freeze_ends = [float(m.group(1)) for m in re.finditer(r'freeze_end: ([\d.]+)', stderr)]

    # If freeze starts but never ends, assume it lasts until the end
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
    target_bitrate_kbps = int((target_size_mb * 8192) / song_duration)  # Convert MB to kilobits
    complex_filter = (
        "split[bg][fg];"
        "[bg]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,gblur=sigma=10[bg_blurred];"
        "[fg]scale='if(gt(iw/ih,1280/720),min(iw,1280),-1)':'if(gt(iw/ih,1280/720),-1,min(ih,720))':force_original_aspect_ratio=decrease[fg_scaled];"
        "[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2,fps=25"
    )
    ffmpeg_cmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-y', '-loop', '1',
                 '-i', os.fspath(file), '-c:v', 'libx264', '-t', str(song_duration),
                 '-preset', 'medium', '-tune', 'stillimage',
                 '-b:v', f'{target_bitrate_kbps}k',
                 '-vf', complex_filter,
                 '-pix_fmt', 'yuv420p',
                 '-an', os.fspath(list_in_dir / output_mp4_file_name)]
    subprocess.run(ffmpeg_cmd)

def create_in_game_loading_picture(files_jpg, list_in_dir, png_in_game_file_name):
    file = files_jpg[0]
    # convert Jpg file into a 512x512 png
    ffmpeg_cmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-i', os.fspath(file), '-vf',
                 'scale=512:512:force_original_aspect_ratio=increase,crop=512:512',
                 os.fspath(list_in_dir / png_in_game_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + png_in_game_file_name)

def create_cover_long(files_jpg, list_in_dir, png_long_file_name):
    file = files_jpg[0]
    # convert Jpg file into a 191x396 png
    ffmpeg_cmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-i', os.fspath(file), '-vf',
                 'scale=191:396:force_original_aspect_ratio=increase,crop=191:396',
                 os.fspath(list_in_dir / png_long_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + png_long_file_name)

def create_cover(files_jpg, list_in_dir, png_file_name):
    file = files_jpg[0]
    # convert Jpg file into a 256x256 png
    ffmpeg_cmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-i', os.fspath(file), '-vf',
                 'scale=256:256:force_original_aspect_ratio=increase,crop=256:256',
                  os.fspath(list_in_dir / png_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + png_file_name)

def create_audio_preview(files_avi, files_mp3, list_in_dir, ogg_preview_file_name, txt_data):
    if files_mp3:
        file = files_mp3[0]
    else:
        file = files_avi[0]
    preview_start_time = 60  # default start time for preview in seconds
    preview_duration_time = 30  # default duration time for preview in seconds
    if 'MEDLEYSTARTBEAT' in txt_data and 'MEDLEYENDBEAT' in txt_data:
        preview_start_beat = int(txt_data['MEDLEYSTARTBEAT'])
        preview_end_beat = int(txt_data['MEDLEYENDBEAT'])
        bpm = float(txt_data["BPM"].replace(',', '.'))
        gap = float(txt_data["GAP"].replace(',', '.')) / 1000
        preview_start_time = (preview_start_beat * 60 / bpm / 4) + gap
        preview_duration_time = ((preview_end_beat - preview_start_beat) * 60 / bpm / 4)
    elif 'PREVIEWSTART' in txt_data:  # in seconds
        preview_start_time = float(txt_data['PREVIEWSTART'].replace(',', '.'))
    # convert Mp3 file into preview Ogg file of 30sec
    ffmpeg_cmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-ss', str(preview_start_time), '-i', os.fspath(file),
                 '-vn',
                 '-t', str(preview_duration_time), '-ar', '48000',
                 '-af', 'loudnorm=I=-16:LRA=11:TP=-1.5',  # Standard broadcast loudness
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
    filter_cmd += 'loudnorm=I=-16:LRA=11:TP=-1.5'  # Standard broadcast loudness
    # convert Mp3 file into Ogg file
    ffmpeg_cmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-i', os.fspath(file), '-vn', '-ar', '48000',
                 '-af', filter_cmd,
                 os.fspath(list_in_dir / ogg_file_name)]
    subprocess.run(ffmpeg_cmd)
    tqdm.write('created : ' + ogg_file_name)

def create_video(file, list_in_dir, output_video_file_name, target_bitrate_kbps):
    # First pass to analyze video
    ffmpeg_cmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-y', '-i', os.fspath(file),
                 '-c:v', 'libx264', '-preset', 'medium', '-b:v', f'{target_bitrate_kbps}k',
                 '-pass', '1', '-an', '-vf',
                 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=25',
                 '-f', 'null', os.devnull]
    subprocess.run(ffmpeg_cmd)
    # Second pass to create final file
    ffmpeg_cmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-y', '-i', os.fspath(file),
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
    binkconv_path = os.path.join(os.environ['ProgramFiles(x86)'], 'RADVideo', 'radvideo64.exe')
    file_format = '/V' + str(200) # 200 = bink2
    remove_sound = '/L-1'
    bink_args = [binkconv_path, 'binkc', file, os.fspath(list_in_dir / output_video_file_name), file_format,
                    '/(1280', '/)720', remove_sound]
    if compression_percentage:
        data_rate_switch = '/D' + str(compression_percentage)
        bink_args.append(data_rate_switch)
    if quality:
        quality_switch = '/Q' + str(quality) # 1.0 is the highest quality
        bink_args.append(quality_switch)
    bink_args.append('/#')
    tqdm.write(f"Converting video {file} to {output_video_file_name} with args: {bink_args}")
    subprocess.run(bink_args, capture_output=True, text=True)

def find_folders_to_convert():
    dir_to_convert = [os.fspath(x) for x in p.iterdir() if x.is_dir()]
    dir_to_remove = [x for x in dir_to_convert if x.startswith('__') or x.startswith('.')]
    dir_to_remove = dir_to_remove + ['ffmpeg', patch_folder_name]
    for x in dir_to_remove:
        if x in dir_to_convert:
            dir_to_convert.remove(x)
    return dir_to_convert

def delete_patch_folder():
    try:
        if os.path.exists(patch_dir):
            tqdm.write(f"Removing existing Patch directory: {patch_dir}")
            shutil.rmtree(patch_dir)
            tqdm.write("Patch directory successfully removed")
    except PermissionError:
        tqdm.write("Error: Could not delete Patch folder - permission denied")
    except Exception as e:
        tqdm.write(f"Error deleting Patch folder: {e}")

def main(output_type=NEW, pitch_correction_method=SLOW):
    delete_patch_folder()
    dirs_to_convert = find_folders_to_convert()

    tqdm.write('Beginning conversion to output type: ' + str(output_type))
    tqdm.write('Pitch correction method: ' + str(pitch_correction_method))
    convert_files(dirs_to_convert, output_type, pitch_correction_method)

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Convert Ultrastar files to Sing It format.')
    parser.add_argument('output_type', nargs='?', type=str, default=NEW, choices=[OLD, NEW],
                        help='Output file type: old or new (default: new)')
    parser.add_argument('pitch_correction_method', nargs='?',
                        type=str.lower, default=SLOW, choices=[FAST, SLOW],
                        help='Which pitch correction method to use: '
                             '[fast] - using simple calculations '
                             '[slow] - using audio analyzer (default: slow)')

    args = parser.parse_args()

    main(args.output_type, args.pitch_correction_method)