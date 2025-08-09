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

import ultrastar2singit

OLD = '2022'
NEW = '2025'

XMLtemplate = 'Zombie_meta.xml'
SongDLCfile = 'SongsDLC.tsv'
nameTxtFile = 'name.txt'

# Lets Sing 2022 IDs
COREID = '0100CC30149B8000'
DLCID_2022 = '0100CC30149B9011' # Best of 90s Vol 3 Song Pack

# Let's Sing 2025 DLC ID, core ID doesn't matter
DLCID_2025 = '01001C101ED11002' # French Hits
DLC_NAME = 'songs_fr'

musicGenreList = ['Pop', 'Rap', 'Rock', 'Ballad', 'Electro']

p = Path('.')
localDir = os.getcwd()
patchFolderName = '_Patch'
patch_dir = os.path.join(localDir, patchFolderName)

logging.basicConfig(
    filename='error.log',
    filemode='a',
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.ERROR
)
logger = logging.getLogger(__name__)

def convert_files(dirsToConvert, output_type=OLD):

    DLCID = DLCID_2022 if output_type == OLD else DLCID_2025

    for dirLongName in tqdm(dirsToConvert, desc="Converting folders"):

        try:
            # only directory with the format Artist - Title
            if not ' - ' in dirLongName:
                continue

            splitDirName = dirLongName.split(' - ')
            ArtistDirName = strip_accents(splitDirName[0])
            TitleDirName = strip_accents(splitDirName[1])
            AristCaps = [word[0].upper() for word in ArtistDirName.split()]
            AristCap = ''.join(AristCaps)
            TitleLower = ''.join(e.lower() for e in TitleDirName if e.isalnum())
            nameID = AristCap + TitleLower

            tqdm.write(nameID)

            # nameID = dirsToConvert[0]
            listInDir = Path(dirLongName)
            filesAll = [os.fspath(x.name) for x in listInDir.iterdir()]
            filesTxt = [x for x in listInDir.iterdir() if x.suffix.lower() == '.txt']
            filesAvi = [x for x in listInDir.iterdir() if x.suffix.lower() in ('.avi', '.divx', '.mp4', '.flv', '.mkv', '.webm')]
            filesMp3 = [x for x in listInDir.iterdir() if x.suffix.lower() in ('.mp3', '.ogg', '.wav', '.flac', '.aac', '.m4a', '.opus')]
            filesJpg = [x for x in listInDir.iterdir() if x.suffix.lower() in ('.jpg', '.jpeg', '.png')]

            outputVideoFileName = nameID + '.mp4' if output_type == OLD else nameID + '.bk2'
            pngFileName = nameID + '.png'
            pngInGameFileName = nameID + '_InGameLoading.png'
            pngLongFileName = nameID + '_long.png'
            pngResultFileName = nameID + '_Result.png'
            vxlaFileName = nameID + '.vxla'
            oggFileName = nameID + '.ogg'
            oggPreviewFileName = nameID + '_preview.ogg'
            xmlFileName = nameID + '_meta.xml'
            jsonFileName = DLC_NAME + '.json'

            # Getting info from the text file
            if not filesTxt:
                tqdm.write('need an ultrastar filetext!!')
                continue

            # some songs also have a duet txt file containing '[MULTI]' in its name, alphabetically we want the last one
            txtData = ultrastar2singit.parse_file(filesTxt[-1])
            videoGap = 0
            if 'VIDEOGAP' in txtData:
                # how many seconds the song is out of sync with the video
                #  positive - video starts before the song
                #  negative - video starts after the song
                videoGap = float(txtData['VIDEOGAP'].replace(',', '.'))

            if filesAvi:
                file = filesAvi[0]
                target_size_mb = 50
                duration = get_duration(os.fspath(file))
                targetBitrateKbps = int((target_size_mb * 8192) / duration)  # Convert MB to kilobits

                if outputVideoFileName not in filesAll:
                    if output_type == OLD:
                        create_video(file, listInDir, outputVideoFileName, targetBitrateKbps)
                    elif output_type == NEW:
                        if is_video_still_image(file):
                            quality = 0.1
                            peakBitrateKbps = None
                        else:
                            quality = None
                            peakBitrateKbps = targetBitrateKbps
                        tqdm.write(str(file))
                        if file.suffix.lower() in ('.flv', '.mkv', '.webm'):
                            # more like bunk compression...
                            create_video(file, listInDir, nameID + '.mp4', targetBitrateKbps)
                            file = os.fspath(listInDir / nameID) + '.mp4'
                        create_video_bink(file, listInDir, outputVideoFileName, peakBitrateKbps, quality)

            if oggFileName not in filesAll:
                create_audio(filesAvi, filesMp3, listInDir, oggFileName, videoGap)

            if oggPreviewFileName not in filesAll:
                create_audio_preview(filesAvi, filesMp3, listInDir, oggPreviewFileName, txtData)

            if filesJpg and pngFileName not in filesAll:
                create_cover(filesJpg, listInDir, pngFileName)

            if filesJpg and pngLongFileName not in filesAll:
                create_cover_long(filesJpg, listInDir, pngLongFileName)

            if filesJpg and pngInGameFileName not in filesAll:
                create_in_game_loading_picture(filesJpg, listInDir, pngInGameFileName)

            song_duration = get_duration(os.fspath(listInDir / oggFileName))

            if not filesAvi or not os.path.exists(os.path.join(listInDir / outputVideoFileName)):
                # If no video file was present in the song's directory, or if "RAD" Video Tools failed to convert it,
                # create a still image video from the cover image
                outputVideoFileNameMp4 = nameID + '.mp4'
                create_still_video_from_cover_image(filesJpg, filesTxt, listInDir, outputVideoFileNameMp4, song_duration, txtData)
                if output_type == NEW:
                    create_video_bink(os.fspath(listInDir / outputVideoFileNameMp4), listInDir, outputVideoFileName,
                                      None, quality=0.1)  # Convert to bink with low quality

            # generating vxla file
            ultrastar2singit.main(filesTxt[-1], song_duration, pitchCorrect=0, s=nameID, dir=listInDir)

            # Handle name.txt - create it at destination if it doesn't exist
            add_data_to_name_txt(DLCID, nameID, output_type)

            # Handle SongsDLC.tsv for OLD dlc, or json file for NEW dlc
            handle_xml_or_json(DLCID, jsonFileName, listInDir, txtData, nameID, output_type, xmlFileName)

            # creating the folder structure if not already present
            base_dlc_dir = os.path.join(localDir, patchFolderName, DLCID)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/audio'), exist_ok=True)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/audio_preview'), exist_ok=True)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/covers'), exist_ok=True)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/videos'), exist_ok=True)
            os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/vxla'), exist_ok=True)

            # placing all files into the correct folders
            shutil.copy2(os.fspath(listInDir / oggFileName), os.path.join(base_dlc_dir, 'romfs/Songs/audio'))
            shutil.copy2(os.fspath(listInDir / oggPreviewFileName), os.path.join(base_dlc_dir, 'romfs/Songs/audio_preview'))
            shutil.copy2(os.fspath(listInDir / pngFileName), os.path.join(base_dlc_dir, 'romfs/Songs/covers'))
            shutil.copy2(os.fspath(listInDir / outputVideoFileName), os.path.join(base_dlc_dir, 'romfs/Songs/videos'))
            shutil.copy2(os.fspath(listInDir / vxlaFileName), os.path.join(base_dlc_dir, 'romfs/Songs/vxla'))

            if output_type == OLD:
                os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/backgrounds/InGameLoading'), exist_ok=True)
                os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/backgrounds/Result'), exist_ok=True)
                os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/covers_duet'), exist_ok=True)
                os.makedirs(os.path.join(base_dlc_dir, 'romfs/Songs/covers_long'), exist_ok=True)

                shutil.copy2(os.fspath(listInDir / pngInGameFileName), os.path.join(base_dlc_dir, 'romfs/Songs/backgrounds/InGameLoading'))
                shutil.copy2(os.fspath(listInDir / pngInGameFileName), os.path.join(base_dlc_dir, 'romfs/Songs/backgrounds/Result', pngResultFileName))
                shutil.copy2(os.fspath(listInDir / pngLongFileName), os.path.join(base_dlc_dir, 'romfs/Songs/covers_long'))
                shutil.copy2(os.fspath(listInDir / xmlFileName), os.path.join(base_dlc_dir, 'romfs'))

        except Exception as e:
            logger.exception(f"Error with directory {dirLongName}")
            tqdm.write(f"Error with directory {dirLongName}: {e}")
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

def handle_xml_or_json(DLCID, jsonFileName, listInDir, txtData, nameID, output_type, xmlFileName):
    title = txtData.get('TITLE', 'title')
    artist = txtData.get('ARTIST', 'artist')
    year = txtData.get('YEAR', '2000')
    genre = match_genre(txtData)

    if output_type == OLD:
        # append data to SongsDLC.tsv - create it at destination if it doesn't exist
        UID = add_data_to_songsdlc_tsv(artist, nameID, title, year)

        # XML song meta file
        create_meta_xml(UID, artist, genre, listInDir, nameID, title, xmlFileName, year)

    elif output_type == NEW:
        # Prepare song data for JSON
        song_data = {
            "id": nameID,
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
        add_song_to_json(DLCID, jsonFileName, song_data)

def create_meta_xml(UID, artist, genre, listInDir, nameID, title, xmlFileName, year):
    root = Et.Element("DLCSong")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
    Et.SubElement(root, "Genre").text = genre
    Et.SubElement(root, "Id").text = nameID
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
    with open(os.fspath(listInDir / xmlFileName), "wb") as f:
        f.write(xmlbin)

def add_song_to_json(dlcId, jsonFileName, song_data):
    dlc_romfs_dir = os.path.join(localDir, patchFolderName, dlcId, 'romfs')
    os.makedirs(dlc_romfs_dir, exist_ok=True)
    dest_json_file = os.path.join(dlc_romfs_dir, jsonFileName)

    if os.path.exists(dest_json_file):
        with open(dest_json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        if os.path.exists(jsonFileName):
            # Copy existing json from root if it exists
            shutil.copy2(jsonFileName, dest_json_file)
            with open(dest_json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            # Create a new json file
            data = {"name": DLC_NAME.split('_')[1], "songs": []}

    data['songs'].append(song_data)
    with open(dest_json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def add_data_to_songsdlc_tsv(artist, nameID, title, year):
    core_assets_dir = os.path.join(localDir, patchFolderName, COREID, 'romfs/Data/StreamingAssets')
    os.makedirs(core_assets_dir, exist_ok=True)
    dest_songs_dlc = os.path.join(core_assets_dir, SongDLCfile)
    if not os.path.exists(dest_songs_dlc):
        if os.path.exists(SongDLCfile):
            # Copy existing SongsDLC.tsv from root if it exists
            shutil.copy2(SongDLCfile, dest_songs_dlc)
        else:
            # Create a new empty SongsDLC.tsv file with proper headers
            with open(dest_songs_dlc, 'w') as outfile:
                outfile.write("ENABLED\tUID\tID\tARTIST\tTITLE\tYEAR\tDIFFICULTY\tSKU_INT\tSKU_FR\tSKU_SPA\tSKU_GER"
                              "\tDLC_INDEX\tVIDEO_RATIO\tGENRE_POP_UNLOCKED\tGENRE_RAP\tGENRE_BALLAD\tGENRE_ROCK"
                              "\tGENRE_HAPPY_UNLOCKED\tGENRE_FIESTA\tGENRE_LOVE\tGENRE_SAD\tGENRE_OLD_UNLOCKED"
                              "\tGENRE_2000\tGENRE_RECENT\tGENRE_RANDOM_UNLOCKED"
                              "\tGENRE_VO\tGENRE_WOMEN\tGENRE_ENGLISH\tGENRE_MEN\n")
    songsXls = pd.read_csv(dest_songs_dlc, sep='\t', index_col=0)
    if songsXls.empty:
        # Create the first row with default values
        UID = 200
        new_row = {
            'UID': UID,
            'ID': nameID,
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
        for col in songsXls.columns:
            if col not in new_row:
                new_row[col] = ''
        songsXls.loc[0] = new_row
        songsXls.index = ['x']  # Set index to 'x' for the first row
    else:
        highestCurrentUID = max(songsXls['UID'].values)
        UID = 200 if highestCurrentUID < 200 else highestCurrentUID + 1
        newRow = len(songsXls.index)
        original_index = songsXls.index.copy()
        songsXls.loc[newRow] = songsXls.iloc[-1].copy()
        songsXls.loc[newRow, 'UID'] = UID
        songsXls.loc[newRow, 'ID'] = nameID
        songsXls.loc[newRow, 'ARTIST'] = artist
        songsXls.loc[newRow, 'TITLE'] = title
        songsXls.loc[newRow, 'YEAR'] = int(year)
        new_index = list(original_index) + ['x']
        songsXls.index = new_index

    songsXls.to_csv(dest_songs_dlc, sep='\t', index_label='ENABLED')
    return UID

def match_genre(txtData):
    genre_raw = txtData.get('GENRE', '').lower()
    for g in musicGenreList:
        if g.lower() in genre_raw:
            return g
    return 'Pop'  # default

def add_data_to_name_txt(dlcId, nameID, output_type):
    dlc_romfs_dir = os.path.join(localDir, patchFolderName, dlcId, 'romfs')
    os.makedirs(dlc_romfs_dir, exist_ok=True)
    dest_name_txt = os.path.join(dlc_romfs_dir, nameTxtFile)
    if not os.path.exists(dest_name_txt):
        if os.path.exists(nameTxtFile):
            # Copy existing name.txt from root if it exists
            shutil.copy2(nameTxtFile, dest_name_txt)
        else:
            # Create a new empty name.txt file
            if output_type == OLD:
                open(dest_name_txt, 'w').close()
            elif output_type == NEW:
                with open(dest_name_txt, 'w') as outfile:
                    outfile.write(DLC_NAME + '\n')
    # Add new entry to name.txt in destination for OLD dlc
    if output_type == OLD:
        with open(dest_name_txt, 'a') as outfile:
            outfile.write(nameID + '\n')

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

def create_still_video_from_cover_image(filesJpg, filesTxt, listInDir, outputMp4FileName, song_duration, txtData):
    tqdm.write('creating static video: ' + outputMp4FileName)
    file = txtData.get('COVER', None)
    if file:
        file = os.path.join(os.path.dirname(os.fspath(filesTxt[-1])), txtData.get('COVER', None))
    else:
        file = filesJpg[0]
    target_size_mb = 10
    target_bitrate_kbps = int((target_size_mb * 8192) / song_duration)  # Convert MB to kilobits
    ffmpegCmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-y', '-loop', '1',
                 '-i', os.fspath(file), '-c:v', 'libx264', '-t', str(song_duration),
                 '-preset', 'medium', '-tune', 'stillimage',
                 '-b:v', f'{target_bitrate_kbps}k',
                 '-vf',
                 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=25',
                 '-pix_fmt', 'yuv420p',
                 '-an', os.fspath(listInDir / outputMp4FileName)]
    subprocess.run(ffmpegCmd)

def create_in_game_loading_picture(filesJpg, listInDir, pngInGameFileName):
    file = filesJpg[0]
    # convert Jpg file into a 512x512 png
    ffmpegCmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-i', os.fspath(file), '-vf',
                 'scale=512:512:force_original_aspect_ratio=increase,crop=512:512',
                 os.fspath(listInDir / pngInGameFileName)]
    subprocess.run(ffmpegCmd)
    tqdm.write('created : ' + pngInGameFileName)

def create_cover_long(filesJpg, listInDir, pngLongFileName):
    file = filesJpg[0]
    # convert Jpg file into a 191x396 png
    ffmpegCmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-i', os.fspath(file), '-vf',
                 'scale=191:396:force_original_aspect_ratio=increase,crop=191:396',
                 os.fspath(listInDir / pngLongFileName)]
    subprocess.run(ffmpegCmd)
    tqdm.write('created : ' + pngLongFileName)

def create_cover(filesJpg, listInDir, pngFileName):
    file = filesJpg[0]
    # convert Jpg file into a 256x256 png
    ffmpegCmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-i', os.fspath(file), '-vf',
                 'scale=256:256:force_original_aspect_ratio=increase,crop=256:256',
                 os.fspath(listInDir / pngFileName)]
    subprocess.run(ffmpegCmd)
    tqdm.write('created : ' + pngFileName)

def create_audio_preview(filesAvi, filesMp3, listInDir, oggPreviewFileName, txtData):
    if filesMp3:
        file = filesMp3[0]
    else:
        file = filesAvi[0]
    previewStartTime = 60  # default start time for preview in seconds
    previewDurationTime = 30  # default duration time for preview in seconds
    if 'MEDLEYSTARTBEAT' in txtData and 'MEDLEYENDBEAT' in txtData:
        previewStartBeat = int(txtData['MEDLEYSTARTBEAT'])
        previewEndBeat = int(txtData['MEDLEYENDBEAT'])
        bpm = float(txtData["BPM"].replace(',', '.'))
        gap = float(txtData["GAP"].replace(',', '.')) / 1000
        previewStartTime = (previewStartBeat * 60 / bpm / 4) + gap
        previewDurationTime = ((previewEndBeat - previewStartBeat) * 60 / bpm / 4)
    elif 'PREVIEWSTART' in txtData:  # in seconds
        previewStartTime = float(txtData['PREVIEWSTART'].replace(',', '.'))
    # convert Mp3 file into preview Ogg file of 30sec
    ffmpegCmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-ss', str(previewStartTime), '-i', os.fspath(file),
                 '-vn',
                 '-t', str(previewDurationTime), '-ar', '48000',
                 '-af', 'loudnorm=I=-16:LRA=11:TP=-1.5',  # Standard broadcast loudness
                 os.fspath(listInDir / oggPreviewFileName)]
    subprocess.run(ffmpegCmd)
    tqdm.write('created : ' + oggPreviewFileName)

def create_audio(filesAvi, filesMp3, listInDir, oggFileName, videoGap):
    if filesMp3:
        file = filesMp3[0]
    else:
        file = filesAvi[0]
    filter_cmd = ''
    if videoGap < 0:
        # Negative gap: trim the beginning of the audio
        # Remove the first |videoGap| seconds
        filter_cmd = f'atrim=start={abs(videoGap)},'
    elif videoGap > 0:
        # Positive gap: add silence to the beginning
        # Insert videoGap seconds of silence before the audio
        filter_cmd = f'adelay={int(videoGap * 1000)}|{int(videoGap * 1000)},'
    filter_cmd += 'loudnorm=I=-16:LRA=11:TP=-1.5'  # Standard broadcast loudness
    # convert Mp3 file into Ogg file
    ffmpegCmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-i', os.fspath(file), '-vn', '-ar', '48000',
                 '-af', filter_cmd,
                 os.fspath(listInDir / oggFileName)]
    subprocess.run(ffmpegCmd)
    tqdm.write('created : ' + oggFileName)

def create_video(file, listInDir, outputVideoFileName, targetBitrateKbps):
    # First pass to analyze video
    ffmpegCmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-y', '-i', os.fspath(file),
                 '-c:v', 'libx264', '-preset', 'medium', '-b:v', f'{targetBitrateKbps}k',
                 '-pass', '1', '-an', '-vf',
                 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=25',
                 '-f', 'null', os.devnull]
    subprocess.run(ffmpegCmd)
    # Second pass to create final file
    ffmpegCmd = [os.fspath(p / 'ffmpeg/bin/ffmpeg.exe'), '-y', '-i', os.fspath(file),
                 '-c:v', 'libx264', '-preset', 'medium', '-b:v', f'{targetBitrateKbps}k',
                 '-pass', '2', '-an', '-vf',
                 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=25',
                 os.fspath(listInDir / outputVideoFileName)]
    subprocess.run(ffmpegCmd)
    tqdm.write('created : ' + outputVideoFileName)
    # Clean up FFmpeg passlog files
    for log_file in Path('.').glob('ffmpeg2pass*'):
        os.remove(log_file)

def create_video_bink(file, listInDir, outputVideoFileName, targetBitrateKbps, quality):
    binkconv_path = os.path.join(os.environ['ProgramFiles(x86)'], 'RADVideo', 'radvideo64.exe')
    fileFormat = '/V' + str(200) # 200 = bink2
    removeSound = '/L-1'
    binkArgs = [binkconv_path, 'binkc', file, os.fspath(listInDir / outputVideoFileName), fileFormat,
                    '/(1280', '/)720', removeSound]
    if targetBitrateKbps:
        peakBitrateSwitch = '/M' + str(targetBitrateKbps * 1024)  # in bits per second
        binkArgs.append(peakBitrateSwitch)
    if quality:
        qualitySwitch = '/Q' + str(quality) # 1.0 is the highest quality
        binkArgs.append(qualitySwitch)
    binkArgs.append('/#')
    tqdm.write(f"Converting video {file} to {outputVideoFileName} with args: {binkArgs}")
    subprocess.run(binkArgs, capture_output=True, text=True)

def find_folders_to_convert():
    dirToConvert = [os.fspath(x) for x in p.iterdir() if x.is_dir()]
    dirToRemove = [x for x in dirToConvert if x.startswith('__') or x.startswith('.')]
    dirToRemove = dirToRemove + ['ffmpeg', patchFolderName]
    for x in dirToRemove:
        if x in dirToConvert:
            dirToConvert.remove(x)
    return dirToConvert

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

def main(output_type=OLD):
    delete_patch_folder()
    dirsToConvert = find_folders_to_convert()

    tqdm.write('Beginning conversion to output type: ' + str(output_type))
    convert_files(dirsToConvert, output_type)

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Convert Ultrastar files to Sing It format.')
    parser.add_argument('output_type', nargs='?', type=str, default=OLD, choices=[OLD, NEW],
                        help='Output file type: old or new (default: old)')
    args = parser.parse_args()

    main(args.output_type)