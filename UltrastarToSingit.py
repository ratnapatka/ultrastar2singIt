import io
import json
import os
import re
import xml.etree.cElementTree as ET
from difflib import SequenceMatcher
from xml.dom import minidom

import chardet
import requests
import unicodedata
from bs4 import BeautifulSoup
from Levenshtein import distance as levenshtein_distance

OLD = '2022'
NEW = '2025'

replacements = {
    "’": "'", "‘": "'", "‚": "'", "‹": "'", "›": "'", "`": "'",
    '“': '"', '”': '"', "„": '"', "«": '"', "»": '"',
    "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE",
    "ﬁ": "fi", "ﬂ": "fl",
    "–": "-", "—": "-", "−": "-",
    "…": "..."
}

def normalize_text(text):
    for old, new in replacements.items():
        text = text.replace(old, new)
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')

def normalize_for_url(text):
    text = text.strip()
    # spaces and some special characters are replaced with hyphens, based on songs from LP - Reanimation
    text = re.sub(r'[_:@\\\/\s]', '-', text)
    # keep hyphens, but remove other special characters (parentheses, punctuation, etc.)
    text = re.sub(r'[^\w-]', '', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text


def detect_encoding(filename):
    with open(filename, 'rb') as f:
        rawdata = f.read(4096)
    result = chardet.detect(rawdata)
    return result['encoding'] or 'utf-8'

def parse_file(filename):
    data = {
        "notes": [], # represents rows in the txt file
        "lyrics_map_list": [] # a list of maps, each map contains a full word lyric and a start beat
                              # (lyrics spread over multiple beats are grouped by the starting beat)
    }
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


def map_data(us_data, song_duration, pitch_corr, input_file_name):
    sing_it = {"text": [], "notes": [], "pages": [], "structure": []}
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

    last_page = 0.0
    end = 1
    previous_line = []
    for note in us_data["notes"]:
        if note[0] in [':', '*', 'F', 'R']:
            start = float(note[1]) * 60 / bpm / 4 + gap + video_gap
            end = start + float(note[2]) * 60 / bpm / 4
            lyric_text = normalize_text(note[4])
            if lyric_text.strip() != "~":  # if the lyric is just a tilde, don't add it to on-screen lyrics
                lyric_text = lyric_text.replace('~', '') # tildes in the middle of bottom lyrics are ugly
                sing_it["text"].append({"t1": start, "t2": end, "value": lyric_text})

                if len(us_data['lyrics_map_list']) == 0 or lyric_text.startswith(" ") or previous_line[0] in ['-']:
                    # save the beginning of a word and its start beat
                    # (first run, begins with a space or following a page break)
                    us_data['lyrics_map_list'].append({
                        'start_beat': int(note[1]),
                        'end_beat': int(note[1]) + int(note[2]),
                        'lyrics': lyric_text
                    })
                else:
                    # concatenate with previous lyric text
                    # (the word starts without a space and the previous line wasn't a page break)
                    us_data['lyrics_map_list'][-1]['lyrics'] += lyric_text
                    us_data['lyrics_map_list'][-1]['end_beat'] = int(note[1]) + int(note[2])
                previous_line = note

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
            sing_it["pages"].append({"t1": start, "t2": end, "value": ""})
            # add a space to the end of the previous lyric (ultrastar lyrics omit a space along page breaks)
            us_data['lyrics_map_list'][-1]['lyrics'] += " "
            previous_line = note

        elif note[0] == "E":
            if end > last_page:
                start = last_page
                sing_it["pages"].append({"t1": start, "t2": end, "value": ""})
                sing_it["pages"].append({"t1": end, "t2": song_duration, "value": ""})

    if 'MEDLEYSTARTBEAT' in us_data and 'MEDLEYENDBEAT' in us_data:
        medley_start_beat = int(us_data['MEDLEYSTARTBEAT'])
        medley_end_beat = int(us_data['MEDLEYENDBEAT'])
        chorus_from_file = get_lyrics_for_beat_range(us_data['lyrics_map_list'], medley_start_beat, medley_end_beat)
        choruses = [chorus_from_file] * 5 # simulate multiple choruses, extras will get ignored
    else:
        choruses = genius_get_choruses(input_file_name)

    if choruses:
        matched_choruses = match_choruses_to_beats(us_data['lyrics_map_list'], choruses, similarity_threshold=0.7)
        for chorus in matched_choruses:
            sing_it['structure'].append({'t1': float(chorus['start_beat']) * 60 / bpm / 4 + gap + video_gap,
                                         't2': float(chorus['end_beat']) * 60 / bpm / 4 + gap + video_gap,
                                         'value': 'feat'})
    else:
        auto_refrains = find_refrains(sing_it)
        merged_sections = merge_intervals(auto_refrains)
        sing_it["structure"] = merged_sections

    return sing_it


def get_lyrics_for_beat_range(lyrics_map_list, start_beat, end_beat):
    lyrics_parts = []

    for line in lyrics_map_list:
        if start_beat <= line['start_beat'] <= end_beat:
            lyrics_parts.append(line['lyrics'])

    return ''.join(lyrics_parts)

def genius_get_choruses(input_file_name, use_cache=True):
    song_dir = input_file_name.parent
    song_name = input_file_name.stem

    # load from cache if available
    cache_file = f"{song_dir}\\{song_name}_genius_cache.json"
    if use_cache and os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached_data = json.load(f)
            return cached_data['choruses']

    song_name = input_file_name.stem
    song_name = normalize_for_url(song_name)
    url = f'https://genius.com/{song_name}-lyrics'
    response = requests.get(url)
    # If direct URL fails, try search
    if response.status_code != 200:
        url = genius_search_for_correct_path(song_name)
        if not url:
            return []
        response = requests.get(url)


    soup = BeautifulSoup(response.content, 'html.parser')
    lyrics_divs = soup.find_all(
        'div',class_=lambda x: x and x.startswith('Lyrics__Container-sc'))
    lyrics = ""
    for div in lyrics_divs:
        for excluded in div.find_all(attrs={'data-exclude-from-selection': 'true'}):
            excluded.decompose()
        lyrics += " ".join(div.stripped_strings)

    choruses = []
    pattern = r'\[Chorus(?:[:\s][^\]]*?)?\](.*?)(?=\[(?!Chorus)|\Z)'
    matches = re.findall(pattern, lyrics, re.DOTALL | re.IGNORECASE)

    for match in matches:
        choruses.append(match)

    # Save to cache
    cache_data = {
        'url': url,
        'lyrics': lyrics,
        'choruses': choruses
    }
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
    return choruses

def genius_search_for_correct_path(query):
    search_url = "https://genius.com/api/search/multi"
    params = {'q': query}

    try:
        response = requests.get(search_url, params=params)
        response.raise_for_status()
        data = response.json()

        # Navigate through the API response structure
        sections = data.get('response', {}).get('sections', [])
        for section in sections:
            if section.get('type') == 'song':
                hits = section.get('hits', [])
                if hits:
                    song_path = hits[0]['result']['path']
                    return f"https://genius.com{song_path}"

        return None
    except Exception:
        return None

def match_choruses_to_beats(lyrics_map_list, genius_choruses, similarity_threshold=0.8):
    matched_choruses = []
    used_beat_ranges = []  # Track already matched beat ranges

    for chorus_text in genius_choruses:
        best_match = None
        best_similarity = 0

        words = [lyrics_map['lyrics'].lower().strip() for lyrics_map in lyrics_map_list]
        # Slide a window across the full lyrics
        for window_size in range(len(chorus_text.split()) - 5,
                                 len(chorus_text.split()) + 5):
            if window_size <= 0 or window_size > len(words):
                continue

            for i in range(len(words) - window_size + 1):
                window_text = ' '.join(words[i:i + window_size])

                # Calculate Levenshtein similarity
                distance = levenshtein_distance(chorus_text, window_text)
                max_len = max(len(chorus_text), len(window_text))
                similarity = 1 - (distance / max_len) if max_len > 0 else 0

                if similarity > best_similarity:
                    beats = word_positions_to_beats(lyrics_map_list, i, i + window_size)
                    if beats:
                        # Check if this beat range overlaps with already used ranges
                        overlaps = any(
                            not (beats['end_beat'] < used['start_beat'] or
                                 beats['start_beat'] > used['end_beat'])
                            for used in used_beat_ranges
                        )

                        if not overlaps:
                            best_similarity = similarity
                            best_match = {
                                'text': window_text,
                                'similarity': similarity,
                                'beats': beats
                            }

        if best_match and best_match['similarity'] >= similarity_threshold:
            matched_choruses.append({
                'genius_text': chorus_text,
                'matched_text': best_match['text'],
                'similarity': best_match['similarity'],
                'start_beat': best_match['beats']['start_beat'],
                'end_beat': best_match['beats']['end_beat']
            })
            used_beat_ranges.append(best_match['beats'])

    return matched_choruses

def word_positions_to_beats(lyrics_map_list, start_word, end_word):
    word_count = 0
    start_beat = None
    end_beat = None

    for lyrics_map in lyrics_map_list:
        if word_count == start_word:
            start_beat = lyrics_map['start_beat']

        word_count += 1

        if word_count == end_word:
            end_beat = lyrics_map['end_beat']
            break

    if start_beat is not None and end_beat is not None:
        return {
            'start_beat': start_beat,
            'end_beat': end_beat
        }
    return None

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

def main(input_file_name, song_duration, pitch_corr=0, s='', directory='', output_type=NEW):
    us_data = parse_file(input_file_name)

    if s:
        output_file = s
    else:
        output_file = re.sub('[^A-Za-z0-9]+', '', us_data["TITLE"])

    sing_it = map_data(us_data, song_duration, pitch_corr, input_file_name=input_file_name)
    write_vxla_file(sing_it, output_file + '.vxla', directory=directory, song_duration=song_duration, output_type=output_type)