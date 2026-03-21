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
        description="Convert UltraStar files to Let's Sing DLC format.",
        epilog="All options override values from config_default.yml / config.yml for this run only."
    )

    parser.add_argument('--dlc-id', type=str, help='DLC TitleID')
    parser.add_argument('--dlc-json-name', type=str, default=None,
                        help='DLC JSON name (e.g. songs_fr). Sets JSON format when present.')
    parser.add_argument('--core-id', type=str, help='Core TitleID (required for XML format)')
    parser.add_argument('--ffmpeg-path', type=str, help='Path to ffmpeg executable')
    parser.add_argument('--rad-path', type=str, help='Path to radvideo64 executable')
    parser.add_argument('--input', type=str, help='Input folder containing song directories')
    parser.add_argument('--output', type=str, help='Output folder for patch files')
    parser.add_argument('--pitch-correction', type=str.lower, choices=[FAST, SLOW])
    parser.add_argument('--max-video-size', type=int, help='Maximum video file size in MB')
    parser.add_argument('--no-medley', action='store_true')
    parser.add_argument('--still-video', action='store_true')
    parser.add_argument('--include-dlc-songs', action='store_true')
    parser.add_argument('--name-txt-path', type=str)
    parser.add_argument('--songs-json-path', type=str)
    parser.add_argument('--songs-tsv-path', type=str)

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
