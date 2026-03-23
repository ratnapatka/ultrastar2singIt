# Let's Sing Ultrastar Converter
This tool helps you add custom songs to your Let's Sing 2022 or 2025 game. It converts UltraStar karaoke files
(found on a well known Spanish UltraStar site) to the Let's Sing DLC format.
The goal of this tool is full automation, it processes the song covers, audio, video, lyrics files, and generates the
required structure with minimal fiddling.

## Credits
 - Major props go to [dh4rry](https://github.com/dh4rry), the original creator of the ultrastar2singit.py script.
   He made the script for Let's Sing 2019, but I see he's 
   [still active and implementing a GUI for the tool](https://github.com/dh4rry/Ultrastar2singIt-Converter).
 - Many props go to MRJPGames over at gbatemp, he refined the original script, made it work for Let's Sing 2022 
   and wrote a pretty good tutorial for getting the needed files from and onto your console in
   [this thread](https://gbatemp.net/threads/add-custom-songs-to-lets-sing-2022-from-ultrastar.607817/).
 - Overwhelming props go to [kosei](https://gbatemp.net/members/kosei.626603/), also at gbatemp,
   for writing a script to automate this whole process 
   [in the same thread](https://gbatemp.net/threads/add-custom-songs-to-lets-sing-2022-from-ultrastar.607817/post-10037766).
 - Special thanks to [omnialord](https://github.com/omnialord) coming over from [gbatemp](https://gbatemp.net/members/omnia.573513/)
   for contributing to the project and keeping the dream alive.

UltraStar karaoke files lack proper standardization, so a simple desire to quickly add a couple of songs to the game quickly evolved into a fully fledged project.
<br>Inspired by kosei’s automation script, and compelled by poor standardization, I extensively modified his
scripts to streamline the conversion process as much as possible (while taking some [Creative Liberties](#creative-liberties)).
After successfully adding over 400 songs to Let’s Sing 2022 and realizing the shortcomings of this game version, I expanded support for other versions of the game as well.
Newer versions of Let's Sing (2024+) feature a superior song selection menu designed for hundreds of tracks rather than just a few dozen and aren't so prone to crashing.
To make the whole process even more user-friendly, I've implemented a GUI and packaged the tool as a standalone executable,
so you don't need to worry about installing Python or any dependencies.

## Requirements
- Windows 7+
- [ffmpeg](https://ffmpeg.org/download.html) - I used version [7.1.1-full_build from gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
- [RAD Video Tools](https://www.radgametools.com/bnkdown.htm) (**needed only for Let's Sing 2024+**)

## How to use
See the [Guide document](Guide.md) for a detailed step-by-step guide on how to use this tool and patch your DLC with custom songs.

This tool can also be run from the command line, use the `--help` flag for a quick rundown of available options.

## Creative Liberties
_Not mandatory reading:_
1. Some songs contain too many "F" (freestyle) notes, these notes seem mostly intended for rapping sections of songs and
   aren't scored. This is probably because rapping at a consistent pitch isn't possible so UltraStar apps just ignore them.
   This makes singing songs like Linkin Park's In The End a real snooze fest.
   <br> Let's Sing does support rapping though, every note with a pitch of 1 is considered a rap note. The pitch is ignored
   for these notes and only the timing matters. This is why the script considers all "F" notes to be "R" (rap) notes.
2. Song previews (~30s soundbites) are automatically cut from the songs starting at 60 seconds into the song (where most medleys start)
   unless there are medley tags in the text file. 
3. Some songs don't have videos, either because the uploader didn't put them, or the songs never had videos to begin with.
   The script makes a static video from the provided cover art in these cases. 
4. Silence is added at the start of a song if it has a positive #VIDEOGAP tag in the text file (cropped if the gap is
   negative) in order to sync the audio with the video and lyrics. 
5. Some songs are way quiter/louder than others, the script will use ffmpeg to normalize loudness.

## TODO (probably not by me)
1. Some songs contain lyrics files for duets, these are currently ignored by the script.
2. Genres for songs are loaded from the #GENRE tag if the file contains it, otherwise it defaults to Pop. I dabbled with
   the idea of pinging an external API (such as [genious](https://genius.com/)) to extract the genre, but I couldn't find a free option.
3. All songs will have the lowest difficulty rating, this can probably be calculated from the song's length, BPM value,
   number of lyrics, variations in pitch, etc.
