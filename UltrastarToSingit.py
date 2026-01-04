import io
import os
import re
import xml.etree.cElementTree as ET
from difflib import SequenceMatcher
from xml.dom import minidom

import chardet
import unicodedata

OLD = '2022'
NEW = '2025'

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')

def detect_encoding(filename):
    with open(filename, 'rb') as f:
        rawdata = f.read(4096)
    result = chardet.detect(rawdata)
    return result['encoding'] or 'utf-8'

def parse_file(filename):
    data = {"notes": []}
    encoding = detect_encoding(filename)
    with io.open(filename, "r", encoding=encoding, errors='ignore') as f:
        for line in f:
            line = line.replace('\n', '')
            if line.startswith("#"):
                p = line.split(":", 1)
                if len(p) == 2:
                    data[p[0][1:]] = p[1]
            else:
                note_arr = line.split(" ", 4)
                data["notes"].append(note_arr)
    return data


def find_refrains(sing_it):
    # Group lyrics by page and find similarity with sequencematcher
    sections = []

    if not sing_it["pages"]:
        if sing_it["text"]:
            sing_it["pages"].append({"t1": 0.0, "t2": sing_it["text"][-1]["t2"], "value": ""})
        else:
            return []

    for i, page in enumerate(sing_it["pages"]):
        section_text = ""
        for text_note in sing_it["text"]:
            if text_note["t1"] < page["t2"] and text_note["t2"] > page["t1"]:
                section_text += text_note["value"].replace('-', '').replace('~', '').strip().lower()

        if section_text:
            sections.append({
                "t1": page["t1"],
                "t2": page["t2"],
                "text": section_text.replace(" ", "")
            })

    refrains = []
    MIN_LENGTH = 10  # Verses should have at least 10 characters
    MIN_SEPARATION = 10.0  # Verses should be separate by at least 10 seconds
    MIN_SIMILARITY = 0.85  # Verses should have at least 85% similarity

    for i in range(len(sections)):
        section_a = sections[i]

        if len(section_a["text"]) < MIN_LENGTH:
            continue

        for j in range(i + 1, len(sections)):
            section_b = sections[j]

            similarity = SequenceMatcher(None, section_a["text"], section_b["text"]).ratio()

            if similarity >= MIN_SIMILARITY:
                if (section_b["t1"] - section_a["t2"]) > MIN_SEPARATION:
                    refrains.append({"t1": section_a["t1"], "t2": section_a["t2"], "value": "feat"})
                    refrains.append({"t1": section_b["t1"], "t2": section_b["t2"], "value": "feat"})

    unique_refrains = []
    seen_intervals = set()
    for r in refrains:
        interval_key = (round(r["t1"], 3), round(r["t2"], 3))
        if interval_key not in seen_intervals:
            unique_refrains.append(r)
            seen_intervals.add(interval_key)

    unique_refrains.sort(key=lambda x: x["t1"])

    return unique_refrains


def merge_intervals(intervals):
    if not intervals:
        return []

    intervals.sort(key=lambda x: x['t1'])

    merged = []
    current_interval = dict(intervals[0])

    for next_interval in intervals[1:]:
        if round(current_interval['t2'], 3) == round(next_interval['t1'], 3) and current_interval['value'] == \
                next_interval['value']:
            current_interval['t2'] = next_interval['t2']
        else:
            merged.append(current_interval)
            current_interval = dict(next_interval)

    merged.append(current_interval)

    return merged


def map_data(us_data, song_duration, pitch_corr, output_type=NEW):
    sing_it = {"text": [], "notes": [], "pages": []}
    bpm = float(us_data["BPM"].replace(',', '.'))
    if "GAP" in us_data:
        gap = float(us_data["GAP"].replace(',', '.')) / 1000
    else:
        gap = 0.0
    video_gap = 0.0
    if "VIDEOGAP" in us_data:
        # how many seconds the song is out of sync with the video
        #  positive - video starts before the song, the song will have silence added to the beginning
        #  negative - video starts after the song, the song will be trimmed at the start
        video_gap = float(us_data["VIDEOGAP"].replace(',', '.'))

    # min_note = 1
    last_page = 0.0
    end = 1
    for note in us_data["notes"]:
        if note[0] == ":" or note[0] == "*" or note[0] == "R" or note[0] == "F":
            start = float(note[1]) * 60 / bpm / 4 + gap + video_gap
            end = start + float(note[2]) * 60 / bpm / 4
            lyric_text = strip_accents(note[4])
            lyric_text = lyric_text.replace("’", "'")
            lyric_text = lyric_text.replace("‘", "'")
            lyric_text = lyric_text.replace('“', '"')
            lyric_text = lyric_text.replace('”', '"')
            lyric_text = lyric_text.replace('œ', 'oe')
            if lyric_text.strip() != "~":  # if the lyric is just a tilde, it means no lyrics
                lyric_text = lyric_text.replace('~', '-')
                sing_it["text"].append({"t1": start, "t2": end, "value": lyric_text})

            pitch = int(note[3])

            match (note[0]):
                case "R" | "F": # rap ==== freestyle
                    full_note = f"#p1#.{lyric_text}"
                    pass
                case "G": # golden rap
                    full_note = f"#p1#.{lyric_text}#g5"
                    pass
                case "*": # golden note
                    full_note = f"#p{pitch + pitch_corr}#.{lyric_text}#g5"
                    pass
                case _: # normal note
                    full_note = f"#p{pitch + pitch_corr}#.{lyric_text}"
                    pass

            sing_it["notes"].append({"t1": start, "t2": end, "value": full_note})

        elif note[0] == "-":
            start = last_page
            end = float(note[1]) * 60 / bpm / 4 + gap + video_gap
            last_page = end
            sing_it["pages"].append(
                {"t1": start, "t2": end, "value": ""})
        elif note[0] == "E":
            if end > last_page:
                start = last_page
                sing_it["pages"].append({"t1": start, "t2": end, "value": ""})
                sing_it["pages"].append({"t1": end, "t2": song_duration, "value": ""})

    auto_refrains = find_refrains(sing_it)
    merged_sections = merge_intervals(auto_refrains)
    sing_it["structure"] = merged_sections

    return sing_it

def write_intervals(interval_arr, parent):
    for interval in interval_arr:
        ET.SubElement(parent, "Interval",
                      t1="{0:.3f}".format(interval["t1"]), t2="{0:.3f}".format(interval["t2"]),
                      value=str(interval["value"]))

def write_metadata_file(us_data, songname):
    root = ET.Element("DLCSong")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
    ET.SubElement(root, "Genre").text = us_data.get("GENRE", "Rock")
    ET.SubElement(root, "Id").text = songname
    ET.SubElement(root, "Uid").text = "160"
    ET.SubElement(root, "Artist").text = us_data.get("ARTIST", "Unknown")
    ET.SubElement(root, "Title").text = us_data.get("TITLE", "Unknown")
    ET.SubElement(root, "Year").text = us_data.get("YEAR", "2000")
    ET.SubElement(root, "Ratio").text = "Ratio_16_9"
    ET.SubElement(root, "Difficulty").text = "Difficulty0"
    ET.SubElement(root, "Feat")
    ET.SubElement(root, "Line1").text = us_data.get("ARTIST", "Unknown")
    ET.SubElement(root, "Line2")
    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(
        encoding="utf-8", indent="\t").decode('utf-8')
    xmlbin = xmlstr.replace('\n', '\r\n').encode('utf-8-sig')
    with open("titleid/romfs/" + songname + "_meta.xml", "wb") as f:
        f.write(xmlbin)


def write_vxla_file(sing_it, filename, directory, song_duration, output_type):
    root = ET.Element("AnnotationFile", version="3.0")

    if output_type == NEW:
        doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="segments")

        if "structure" in sing_it and sing_it["structure"]:
            write_intervals(sing_it["structure"], doc)
    elif output_type == OLD:
        doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="structure")

        ET.SubElement(doc, "Interval", t1="2.000", t2="3.000", value="couplet1")
        ET.SubElement(doc, "Interval", t1="3.000", t2="{0:.3f}".format(song_duration), value="refrain")

    if output_type == OLD:
        doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="challenge")
        ET.SubElement(doc, "Interval", t1="0.000", t2="0.000", value="challenge")

    doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="pages")
    write_intervals(sing_it["pages"], doc)

    doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="lyrics")
    write_intervals(sing_it["text"], doc)

    doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="notes_full")
    write_intervals(sing_it["notes"], doc)

    if output_type == NEW:
        doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="language")
        ET.SubElement(doc, "Interval", t1="0.000", t2="{0:.3f}".format(song_duration), value="english")

    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(
        encoding="Windows-1252", indent="\t")
    xmlstr = xmlstr.decode("Windows-1252")  # Decode bytes to string
    xmlstr = re.sub(r'(</IntervalLayer>)', r'\1\n', xmlstr)
    xmlstr = re.sub(r'(value="[^"]*")\/>', r'\1 />', xmlstr)

    with open(os.path.join(directory, filename), "wb") as f:
        f.write(xmlstr.encode("Windows-1252"))

def main(input_file, song_duration, pitch_corr=0, s='', dir='', output_type=NEW):
    us_data = parse_file(input_file)

    if s:
        output_file = s
    else:
        output_file = re.sub('[^A-Za-z0-9]+', '', us_data["TITLE"])

    sing_it = map_data(us_data, song_duration, pitch_corr, output_type=output_type)
    write_vxla_file(sing_it, output_file + '.vxla', directory=dir, song_duration=song_duration, output_type=output_type)