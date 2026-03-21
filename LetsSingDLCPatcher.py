import sys


def main():
    if len(sys.argv) > 1:
        _run_cli()
    else:
        _run_gui()


def _run_cli():
    import argparse
    import logging

    from ConfigLoader import load_config
    import ConvertFiles
    from ConvertFiles import FAST, SLOW

    logging.basicConfig(level=logging.DEBUG, format='%(message)s')

    parser = argparse.ArgumentParser(
        prog="LetsSingDLCPatcher",
        description="Convert UltraStar karaoke song folders into Let's Sing DLC format.",
        epilog="All options override values from config_default.yml / config.yml for this run only.\n"
               "Example: LetsSingDLCPatcher --dlc-id 01001C101ED11002 --dlc-json-name songs_fr --still-video",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # --- Game Info ---
    game = parser.add_argument_group('Game info')
    game.add_argument('--core-id', type=str, metavar='ID',
                      help="Core TitleID. a unique 16-character hexadecimal identifier representing the game edition"
                           " (e.g. 01001C101ED10000 for Let's Sing 2025)")
    game.add_argument('--dlc-id', type=str, metavar='ID',
                      help="DLC TitleID, a unique 16-character hexadecimal identifier representing the DLC"
                           " (e.g. 01001C101ED11002 for the French Hits DLC for Let's Sing 2025)")
    game.add_argument('--dlc-json-name', type=str, default=None, metavar='NAME',
                      help='DLC JSON name (e.g. songs_fr). Presence determines output format: '
                           'set for JSON format (2024+), omit for XML format (prior to 2024)')

    # --- Tool paths ---
    tools = parser.add_argument_group('External tools')
    tools.add_argument('--ffmpeg-path', type=str, metavar='PATH',
                       help='Path to ffmpeg executable')
    tools.add_argument('--rad-path', type=str, metavar='PATH',
                       help='Path to radvideo64.exe (required for .bk2 video encoding for 2024+)')

    # --- Folders ---
    folders = parser.add_argument_group('Folders')
    folders.add_argument('--input', type=str, metavar='DIR',
                         help='Input folder containing "Artist - Title" song directories from Ultrastar')
    folders.add_argument('--output', type=str, metavar='DIR',
                         help='Output folder for the generated patch (WARNING: folder is purged before each run)')

    # --- Conversion tweaks ---
    tweaks = parser.add_argument_group('Conversion tweaks')
    tweaks.add_argument('--pitch-correction', type=str.lower, choices=[FAST, SLOW],
                        help='Pitch correction method. "fast" uses heuristics (default), '
                             '"slow" uses CREPE neural pitch detection (requires unpacked modules in the plugins folder)')
    tweaks.add_argument('--max-video-size', type=int, metavar='MB',
                        help='Maximum video file size in MB')
    tweaks.add_argument('--still-video', action='store_true',
                        help='Skip video encoding; generate a static video from the cover image instead')
    tweaks.add_argument('--no-medley', action='store_true',
                        help='Ignore UltraStar medley tags for chorus detection; '
                             'force Genius.com scraping or automatic detection instead')

    # --- DLC song inclusion ---
    dlc_songs = parser.add_argument_group('DLC song inclusion',
                   'Include the original DLC songs alongside your custom songs')
    dlc_songs.add_argument('--include-dlc-songs', action='store_true',
                           help='Include songs from the installed DLC in the output')
    dlc_songs.add_argument('--name-txt-path', type=str, metavar='PATH',
                           help='Path to the DLC name.txt file')
    dlc_songs.add_argument('--songs-json-path', type=str, metavar='PATH',
                           help='Path to the DLC songs_XX.json file (JSON format)')
    dlc_songs.add_argument('--songs-tsv-path', type=str, metavar='PATH',
                           help='Path to the DLC SongsDLC.tsv file (XML format)')

    args = parser.parse_args()
    config = load_config()

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

    ConvertFiles.main(config)


def _run_gui():
    if sys.platform == 'win32':
        import ctypes
        console_window = ctypes.windll.kernel32.GetConsoleWindow()
        if console_window:
            ctypes.windll.user32.ShowWindow(console_window, 0)

    import Gui
    Gui.main()


if __name__ == '__main__':
    main()
