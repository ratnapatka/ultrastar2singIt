## Let's Sing DLC Patcher
<p>This tool helps you add custom songs to your Let's Sing 2022 or 2025 game. It converts UltraStar karaoke files (found on a well-known Spanish UltraStar site) to the Let's Sing DLC format.</p>

### How to use
<ol>
<li>Install Let's Sing 2022 or 2025 on your console and install one DLC song pack. Note the Title IDs of your base game install and the DLC (COREID, DLCID). For 2025, also note the name of the DLC written in the name.txt file found in the installed DLCID\romfs folder (e.g., the name for the French Hits DLC for 2025 is 'songs_fr'). You can use DBI to browse the installed folders.</li> 
<li>Download a FFmpeg release to your PC. I used gyan's version 7.1.1-full_build from <a href="https://www.gyan.dev/ffmpeg/builds/">https://www.gyan.dev/ffmpeg/builds/</a>.</li>
<li>Install RAD Video Tools from <a href="https://www.radgametools.com/bnkdown.htm">https://www.radgametools.com/bnkdown.htm</a> (needed for Let's Sing 2025).</li>
<li>Create a folder (e.g., "My Songs") containing all the UltraStar song folders you want to convert. This is what your "My Songs" folder should look like:

```
My Songs/
├── Oasis - Wonderwall/
│   ├── Oasis - Wonderwall.aac
│   ├── Oasis - Wonderwall.png
│   ├── Oasis - Wonderwall.txt
│   └── Oasis - Wonderwall.webm
├── R.E.M. - Man on the Moon/
│   ├── R.E.M. - Man on the Moon.jpeg
│   ├── R.E.M. - Man on the Moon.mkv
│   ├── R.E.M. - Man on the Moon.ogg
│   └── R.E.M. - Man on the Moon.txt
└── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop)/
    ├── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop).jpg
    ├── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop).mp3
    ├── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop).mp4
    └── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop).txt
```
</li>
<li>Run the 'UltraStar to SingIt Converter' and fill out all the available fields (most will be automatically populated with default values). If empty, point to the executables for FFmpeg and RAD Video Tools and point the Input folder to your "My Songs" folder.</li>
<li>Check the preview on the right to make sure your Input folder is loaded correctly. Green ticks will be displayed for each existing UltraStar file type (or a red X if it is missing). If you've run the converter before with your input folder, a blue checked-file icon may appear next to the first icon. This icon means that a cached version of this file type is already present in the input song's folder (you can delete these by using the Clear cache button).</li>
<li>Select an output folder for the converted songs. <b>WARNING</b> - The selected folder will be purged before starting the conversion, make sure you're not selecting an important folder! It shouldn't be possible to select something important, as the contents of the selected folder are checked upon selection. The selected folder will be allowed only if it is empty or if it contains only folders named as Title IDs (i.e., from a previous conversion), but still be careful.</li>
<li>Start the conversion and track the progress in the preview table above.</li>
<li>When the conversion is done, copy the contents of the output folder ("_Patch" by default) to your SD card sd:/atmosphere/contents.</li>
<li>Launch the game and Sing!</li>
</ol>

### Tweaks
<ul>
<li><i>Include songs from the DLC</i> - By default, the songs from the DLC are ignored and won't be visible in the game. If you want to include them, check this box and point to the required files from the installed CORE/DLC.</li>
<li><i>Analyze song vocals for pitch correction</i> - Let's Sing recognizes vocal pitches in the 43-81 range. Most UltraStar files use relative pitch ranges and have values in the low 10s or even negative, so some form of pitch correction is required for them. By default, simple calculations are used to raise the pitch to the correct range. Check this box to use the <a href="https://github.com/marl/crepe">CREPE module</a> for a potentially more accurate pitch correction (takes around 10 seconds longer per song).</li>
<li><i>Ignore the UltraStar medley tags for finding chorus sections</i> - Chorus sections of a song will award more points, but finding the choruses can be tricky. The UltraStar txt files sometimes contain medley tags which point to a single chorus section. If the tags are present, they will be used to find all the choruses. If the tags are missing, the chorus data will be scraped from genius.com, and failing this, a manual chorus lookup method will be used. The medley tags offer the simplest way of finding the chorus sections, but they are sometimes incorrect. Check this box if you want to use the other methods instead.</li>
</ul>