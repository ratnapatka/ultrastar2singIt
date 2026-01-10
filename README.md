# UltraStar to Sing It Converter
This tool helps you add custom songs to your Let's Sing! 2022 or 2025 game. It converts UltraStar karaoke files (found on a well known Spanish UltraStar site) to the Let's Sing! DLC format.
The goal of this tool is full automation, it processes the song covers, audio, video, lyrics files, and generates the required structure with minimal fiddling.

## Credits
 - Major props go to [dh4rry](https://github.com/dh4rry), the original creator of the ultrastar2singit.py script. He made the script for Let's Sing! 2019, but I see he's [still active and implementing a GUI for the tool](https://github.com/dh4rry/Ultrastar2singIt-Converter).
 - Many props go to MRJPGames over at gbatemp, he refined the original script, made it work for Let's Sing! 2022 and wrote a pretty good tutorial for getting the needed files from and onto your console in [this thread](https://gbatemp.net/threads/add-custom-songs-to-lets-sing-2022-from-ultrastar.607817/).
 - Overwhelming props go to [kosei](https://gbatemp.net/members/kosei.626603/), also at gbatemp, for writing a script to automate this whole process [in the same thread](https://gbatemp.net/threads/add-custom-songs-to-lets-sing-2022-from-ultrastar.607817/post-10037766).
 - Thanks to [Omnia](https://gbatemp.net/members/omnia.573513/) from gbatemp for contributing to the project.

UltraStar karaoke files lack proper standardization, so what began as a fun idea quickly evolved into a fully fledged project.
<br>Inspired by kosei’s post and automation script, and compelled by poor standardization, I extensively modified both scripts to streamline the conversion process (and took some [Creative Liberties](#creative-liberties)).
After successfully adding over 400 songs to Let’s Sing! 2022, I expanded support to the 2025 version, which features a superior song selection menu designed for hundreds of tracks rather than just a few dozen.

## Requirements
- Windows 7+
- Python 3.10.11 (what is legacy support?)
- [ffmpeg](https://ffmpeg.org/download.html) - I used version [7.1.1-full_build from gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
- [RAD Video Tools](https://www.radgametools.com/bnkdown.htm) (**needed only for Let's Sing 2025**) - install in default location **%ProgramFiles(x86)%\RADVideo** or change the path in the script
- Python modules used: 
  - pandas (2.2.3)
  - tqdm (4.67.1)
  - numpy (1.23.5) - low due to intel_tensorflow compatibility, higher version is possible with generic version of tensorflow
  - needed only for the slower (more accurate?) pitch correction:
    - librosa (0.11.0)
    - crepe (0.0.16)
    - intel_tensorflow (2.91.1)

## Usage
0. Install Let's Sing! 2022 or 2025 to your console and install one DLC song pack, note your COREID and DLCID values.
1. Make a working folder (I've named it "project") containing the **two Python scripts** and the **ffmpeg** release. To the same folder, copy all the UltraStar **song folders** you want to convert, this is what the folder should look like: <img width="829" height="505" alt="ProjectRoot/\n ├── ffmpeg/\n ├── Oasis - Wonderwall/\n ├── R.E.M. - Man on the Moon/\n ├── convertFiles.py\n └── ultrastar2singit.py" src="https://github.com/user-attachments/assets/6fa56ee0-2029-42a1-8662-53f25d83631a" />
2. (**optional**) If you wish to keep the songs included in the DLC instead of replacing them (make sure you don't mix up your versions because they both use name.txt for their own purposes):
   - for Let's Sing! **2022**, copy the **name.txt** (found in DLCID\romfs) and **SongsDLC.tsv** (found in COREID\romfs\Data\StreamingAssets) files from the game installation to the project folder,
   - for Let's Sing! **2025**, copy the **songs_XX.json** (found in DLCID\romfs) file from the game installation to the project folder.
3. Adjust the convertFiles.py script if needed, i.e. change the **COREID** and/or **DLCID** presets at the top to match your installed Let's Sing! ROM and DLC. These are set by default:
   - for Let's Sing! **2022**, COREID = 0100CC30149B8000, DLCID = 0100CC30149B9011
   - for Let's Sing! **2025**, DLC_NAME = songs_fr, DLCID = 01001C101ED11002
4. Run the converter from the command line ('2025' is the default output type, 'fast' is the default pitch correction method):
```
ConvertFiles.py [2022|2025] [fast|slow]
```
5. Check the **error.log** file for any errors during conversion. The script will not stop in case of errors and will skip to the next song. You can just rerun the script after any corrections in the files or script, the _Patch folder will get deleted and any previously successfully converted files will just be copied over from the songs' folders (they won't be encoded again).
6. Copy the contents of the generated _Patch folder (COREID and/or DLCID folders) to your SD card **sd:/atmosphere/contents**.
7. Run the game and sing!

## Creative Liberties
_Not mandatory reading:_
1. Some songs contain too many "F" (freestyle) notes, these notes seem mostly intended for rapping sections of songs and aren't scored. This is probably because rapping at a consistent pitch isn't possible so UltraStar apps just ignore them. This makes singing songs like Linkin Park's In The End a real snooze fest.
<br> Let's Sing! does support rapping though, every note with a pitch of 1 is considered a rap note. The pitch is ignored for these notes and only the timing matters. This is why the script considers all "F" notes to be "R" (rap) notes.
2. Song previews (~30s soundbites) are automatically cut from the songs starting at 60 seconds into the song (where most medleys start) unless there are medley tags in the text file. 
3. Many songs don't have videos, either because the uploader didn't put them, or the songs never had videos to begin with. The script makes a static video from the provided cover art in these cases.
4. Unless the video is a still image, the script will attempt to keep all video file sizes at 50 MB (same as the original songs from the DLCs) to keep the size managable, but this causes the process to take longer due to bitrate calculation for each video.
5. The RAD Video Tools aren't so rad if you ask me, they don't support flv, mkv or webm video formats (possibly more), nor do they support 4:4:4 chroma subsampling. In such cases the original video is first converted to mp4 via ffmpeg before using RAD to convert to bk2 (taking almost twice as long). Note that, in most cases, RAD Tools will simply close itself without a popup or error message when it encounters an unsupported format (preferable), but for some rare songs (out of 500 songs I've converted, it only happens with Muse's Undisclosed Desires) the script will hang until you OK the error message.
6. . Most songs have a lower pitch value (~10) than Let's Sing! expects (~50) so a fixed value of 48 is added to all notes in the original script. Songs from SingStar (#EDITION tag) don't have a low pitch so the pitch is not increased for them.
7. Silence is added at the start of a song if it has a positive #VIDEOGAP tag in the text file (cropped if the gap is negative) in order to sync the audio with the video and lyrics (seems accurate from my tests).
8. Some songs are way quiter/louder than others, the script will use ffmpeg to normalize loudness.

## TODO (probably not by me)
1. Some songs contain lyrics files for duets, these are currently ignored by the script.
2. Genres for songs are loaded from the #GENRE tag if the file contains it, otherwise it defaults to Pop. I dabbled with the idea of pinging an external API (such as [genious](https://genius.com/)) to extract the genre, but I couldn't find a free option.
3. All songs will have the lowest difficulty rating, this can probably be calculated from the song's length, BPM value, number of lyrics, variations in pitch, etc.