import io
import xml.etree.cElementTree as ET
from xml.dom import minidom
import sys
import re
import os
import unicodedata
import chardet

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

def map_data(us_data, song_duration, pitchCorr):
    sing_it = {"text": [], "notes": [], "pages": []}
    bpm = float(us_data["BPM"].replace(',', '.'))
    if "GAP" in us_data:
        gap = float(us_data["GAP"].replace(',', '.')) / 1000
    else:
        gap = 0.0
    videoGap = 0.0
    if "VIDEOGAP" in us_data:
        # how many seconds the song is out of sync with the video
        #  positive - video starts before the song, the song will have silence added to the beginning
        #  negative - video starts after the song, the song will be trimmed at the start
        videoGap = float(us_data["VIDEOGAP"].replace(',', '.'))

    if "EDITION" not in us_data or "singstar" not in us_data["EDITION"].lower():
        pitchCorr = 48

    # min_note = 1
    last_page = 0.0
    end = 1
    for note in us_data["notes"]:
        if note[0] == ":" or note[0] == "*" or note[0] == "R" or note[0] == "F":
            start = float(note[1]) * 60 / bpm / 4 + gap + videoGap
            end = start + float(note[2]) * 60 / bpm / 4
            lyric_text = strip_accents(note[4])
            lyric_text = lyric_text.replace('œ','oe')
            if lyric_text.strip() != "~": # if the lyric is just a tilde, it means no lyrics
                lyric_text = lyric_text.replace('~', '-')
                sing_it["text"].append({"t1": start, "t2": end, "value": lyric_text})

            pitch = int(note[3])
            # if pitch < min_note:
            #     pitch = min_note

            match (note[0]):
                case "R" | "F": # rap ==== freestyle
                    full_note = f"#p1#.{lyric_text}#"
                    pass
                case "G": # golden rap
                    full_note = f"#p1#.{lyric_text}#g5"
                    pass
                case "*": # golden note
                    full_note = f"#p{pitch + pitchCorr}#.{lyric_text}#g5"
                    pass
                case _: # normal note
                    full_note = f"#p{pitch + pitchCorr}#.{lyric_text}"
                    pass

            sing_it["notes"].append({"t1": start, "t2": end, "value": full_note})

        elif note[0] == "-":
            start = last_page
            end = float(note[1]) * 60 / bpm / 4 + gap + videoGap
            last_page = end
            sing_it["pages"].append(
                {"t1": start, "t2": end, "value": ""})
        elif note[0] == "E":
            if end > last_page:
                start = last_page
                sing_it["pages"].append({"t1": start, "t2": end, "value": ""})
                sing_it["pages"].append({"t1": end, "t2": song_duration, "value": ""})
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


def write_vxla_file(sing_it, filename, directory):
    root = ET.Element("AnnotationFile", version="3.0")

    doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="structure")
    ET.SubElement(doc, "Interval", t1="2.000", t2="3.000", value="couplet1")
    ET.SubElement(doc, "Interval", t1="0.000", t2="60.000", value="refrain")

    doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="challenge")
    ET.SubElement(doc, "Interval", t1="0.000", t2="0.000", value="challenge")

    doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="pages")
    write_intervals(sing_it["pages"], doc)

    doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="lyrics")
    write_intervals(sing_it["text"], doc)

    doc = ET.SubElement(root, "IntervalLayer", datatype="STRING", name="notes_full")
    write_intervals(sing_it["notes"], doc)

    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(
        encoding="Windows-1252", indent="\t")
    xmlstr = xmlstr.decode("Windows-1252")  # Decode bytes to string
    xmlstr = re.sub(r'(</IntervalLayer>)', r'\1\n', xmlstr)
    xmlstr = re.sub(r'(value="[^"]*")\/>', r'\1 />', xmlstr)

    with open(os.path.join(directory, filename), "wb") as f:
        f.write(xmlstr.encode("Windows-1252"))

def main(input_file, songDuration, pitchCorrect=0, s='', dir=''):
    us_data = parse_file(input_file)

    if s:
        output_file = s
    else:
        output_file = re.sub('[^A-Za-z0-9]+', '', us_data["TITLE"])

    sing_it = map_data(us_data, songDuration, pitchCorrect)
    write_vxla_file(sing_it, output_file + '.vxla', directory=dir)

