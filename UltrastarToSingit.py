import io
import json
import logging
import os
import re
import xml.etree.cElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path
from xml.dom import minidom

import chardet
import requests
import unicodedata
from Levenshtein import distance as levenshtein_distance
from bs4 import BeautifulSoup
from tqdm import tqdm

OLD = '2022'
NEW = '2025'

GENIUS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

replacements = {
    "’": "'", "‘": "'", "‚": "'", "‹": "'", "›": "'", "`": "'",
    '“': '"', '”': '"', "„": '"', "«": '"', "»": '"',
    "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE",
    "ﬁ": "fi", "ﬂ": "fl",
    "–": "-", "—": "-", "−": "-",
    "…": "..."
}

def log_debug(msg):
    tqdm.write(f"[DEBUG] {msg}")

def normalize_text(text):
    for old, new in replacements.items():
        text = text.replace(old, new)
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')

# handle special characters and feats for genius url
def normalize_for_url(text):
    text = text.strip().lower()
    text = text.replace(' with ', ' and ').replace(' feat ', ' and ').replace(' ft ', ' and ').replace(' & ', ' and ')
    text = re.sub(r'[_:@\\\/\s]', '-', text)
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
    MIN_LENGTH = 20 # Verses should have at least 20 characters
    MIN_SEPARATION = 10.0 # Verses should be separate by at least 10 seconds
    MIN_SIMILARITY = 0.85 # Verses should have at least 85% similarity

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
    if not intervals: return []
    intervals.sort(key=lambda x: x['t1'])
    merged = []
    current_interval = dict(intervals[0])

    for next_interval in intervals[1:]:
        if round(current_interval['t2'], 3) == round(next_interval['t1'], 3) and current_interval['value'] == next_interval['value']:
            current_interval['t2'] = next_interval['t2']
        else:
            merged.append(current_interval)
            current_interval = dict(next_interval)
    merged.append(current_interval)
    return merged

def map_data(us_data, song_duration, pitch_corr, input_file_name, ignore_medley=False):
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
        if note[0] in [':', '*', 'F', 'R', 'G']:
            start = float(note[1]) * 60 / bpm / 4 + gap + video_gap
            end = start + float(note[2]) * 60 / bpm / 4
            lyric_text = normalize_text(note[4])
            
            if lyric_text.strip() != "~": # if the lyric is just a tilde, don't add it to on-screen lyrics
                final_lyric = lyric_text.replace('~', '') # tildes in the middle of bottom lyrics are ugly
                sing_it["text"].append({"t1": start, "t2": end, "value": final_lyric})

                previous_word_ended_with_space = False
                if us_data['lyrics_map_list']:
                    previous_word_ended_with_space = us_data['lyrics_map_list'][-1]['lyrics'].endswith(" ")

                is_new_word = (
                    len(us_data['lyrics_map_list']) == 0 or 
                    lyric_text.startswith(" ") or 
                    (len(previous_line) > 0 and previous_line[0] in ['-']) or
                    previous_word_ended_with_space 
                )

                if is_new_word:
                    us_data['lyrics_map_list'].append({
                        'start_beat': int(note[1]),
                        'end_beat': int(note[1]) + int(note[2]),
                        'lyrics': lyric_text
                    })
                else:
                    if us_data['lyrics_map_list']:
                    # concatenate with previous lyric text
                    # (the word starts without a space and the previous line wasn't a page break)
                        us_data['lyrics_map_list'][-1]['lyrics'] += lyric_text
                        us_data['lyrics_map_list'][-1]['end_beat'] = int(note[1]) + int(note[2])
                
                previous_line = note
            else:
                if " " in lyric_text and us_data['lyrics_map_list']:
                    if not us_data['lyrics_map_list'][-1]['lyrics'].endswith(" "):
                        us_data['lyrics_map_list'][-1]['lyrics'] += " "
                previous_line = note

            pitch = int(note[3])
            note_type = note[0]
            if note_type in ["R", "F"]: full_note = f"#p1#.{final_lyric}"
            elif note_type == "G": full_note = f"#p1#.{final_lyric}#g5"
            elif note_type == "*": full_note = f"#p{pitch + pitch_corr}#.{final_lyric}#g5"
            else: full_note = f"#p{pitch + pitch_corr}#.{final_lyric}"
            
            sing_it["notes"].append({"t1": start, "t2": end, "value": full_note})

        elif note[0] == "-":
            start = last_page
            end = float(note[1]) * 60 / bpm / 4 + gap + video_gap
            last_page = end
            sing_it["pages"].append({"t1": start, "t2": end, "value": ""})
            
            # add a space to the end of the previous lyric (ultrastar lyrics omit a space along page breaks)
            if us_data['lyrics_map_list'] and not us_data['lyrics_map_list'][-1]['lyrics'].endswith(" "):
                us_data['lyrics_map_list'][-1]['lyrics'] += " "
            
            previous_line = note

        elif note[0] == "E":
            if end > last_page:
                start = last_page
                sing_it["pages"].append({"t1": start, "t2": end, "value": ""})
                sing_it["pages"].append({"t1": end, "t2": song_duration, "value": ""})

    log_debug("--- Analyzing Structure ---")
    choruses = []
    
    has_medley = 'MEDLEYSTARTBEAT' in us_data and 'MEDLEYENDBEAT' in us_data
    
    if has_medley and not ignore_medley:
        log_debug("Using MEDLEY tags from ultrastar file.")
        m_start = int(us_data['MEDLEYSTARTBEAT'])
        m_end = int(us_data['MEDLEYENDBEAT'])
        chorus_txt = get_lyrics_for_beat_range(us_data['lyrics_map_list'], m_start, m_end)
        choruses = [chorus_txt] * 5
    else:
        if has_medley and ignore_medley:
            log_debug("Tags MEDLEY ignoradas (Argument --no-medley activated).")
        artist = us_data.get('ARTIST', '')
        title = us_data.get('TITLE', '')
        choruses = genius_get_choruses(input_file_name, artist=artist, title=title)

    if choruses:
        matched = match_choruses_to_beats(us_data['lyrics_map_list'], choruses, similarity_threshold=0.7)
        for m in matched:
            sing_it['structure'].append({
                't1': float(m['start_beat']) * 60 / bpm / 4 + gap + video_gap,
                't2': float(m['end_beat']) * 60 / bpm / 4 + gap + video_gap,
                'value': 'feat'
            })

    if not sing_it['structure']:
        log_debug("!!! ALERT !!! Fallback to automatic chorus detection.")
        auto = find_refrains(sing_it)
        sing_it["structure"] = merge_intervals(auto)
        log_debug(f"Automated detection: {len(sing_it['structure'])} segments.")
    else:
        log_debug(f"Sucess Genius/Medley: {len(sing_it['structure'])} segments created.")

# adds #g5 to all notes within chorus segments
    if sing_it["structure"]:
        for note in sing_it["notes"]:
            if "#g5" in note["value"]:
                continue

            note_midpoint = note["t1"] + (note["t2"] - note["t1"]) / 2
            
            for section in sing_it["structure"]:
                if section["t1"] <= note_midpoint <= section["t2"]:
                    note["value"] += "#g5"
                    break

    return sing_it

def get_lyrics_for_beat_range(lyrics_map_list, start_beat, end_beat):
    return ''.join([l['lyrics'] for l in lyrics_map_list if start_beat <= l['start_beat'] <= end_beat])

def clean_artist_name(artist):
    text = artist.lower()
    separators = [' feat', ' ft.', ' ft ', ' with ', ' & ', ' vs ', ',']
    for sep in separators:
        if sep in text:
            text = text.split(sep)[0]
    return text.strip()

def genius_search_for_correct_path(artist, title):
    primary_artist = clean_artist_name(artist)
    clean_title = title.split('(')[0].strip() # Remove (Live), (Remix)
    
    queries_to_try = [
        f"{primary_artist} {clean_title}",  # 1. Try main artist + song
        clean_title,                         # 2. Try song
        f"{artist} {title}"                     # 3. Try original names
    ]
    
    queries_to_try = list(dict.fromkeys(queries_to_try))

    for query in queries_to_try:
        log_debug(f"Attempting search to Genius API: '{query}'")
        try:
            resp = requests.get("https://genius.com/api/search/multi", params={'q': query}, headers=GENIUS_HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for section in data.get('response', {}).get('sections', []):
                    if section['type'] == 'song':
                        for hit in section.get('hits', []):
                            result = hit['result']
                            
                            hit_title = normalize_text(result['title']).lower()
                            hit_artist = normalize_text(result['primary_artist']['name']).lower()
                            
                            target_title = normalize_text(clean_title).lower()
                            target_artist_full = normalize_text(artist).lower()
                            target_artist_clean = normalize_text(primary_artist).lower()

                            # Validate name match with search results
                            
                            title_match = (target_title in hit_title) or (hit_title in target_title)
                            
                            artist_match = (hit_artist in target_artist_full) or \
                                           (target_artist_clean in hit_artist)
                            
                            is_trash = "deleted" in hit_artist or "tracklist" in hit_title

                            if title_match and artist_match and not is_trash:
                                log_debug(f"Match Confirmed: '{result['full_title']}'")
                                return "https://genius.com" + result['path']
                                
        except Exception as e:
            error_msg = f"Could not find '{query}': {str(e)}"
            log_debug(error_msg)
            logging.error(error_msg)
            continue
            
    log_debug("No song matches found on Genius.")
    return None

def genius_get_choruses(input_file_name, artist=None, title=None, use_cache=True):
    input_path = Path(input_file_name)
    cache_file = input_path.parent / f"{input_path.stem}_genius_cache.json"

# International chorus terms
    terms = [
        'Chorus', 'Refrain', 'Estribillo', 'Refrão', 'Refrao', 
        'Ritornello', 'Refrein', 'Refren', 'Nakarat', 'Припев', 'サビ'
    ]

    terms_pattern = '|'.join(terms)

    if not artist or not title:
        parts = input_path.stem.split(' - ')
        if len(parts) >= 2:
            artist = parts[0]
            title = parts[1]
        else:
            artist = ""
            title = input_path.stem

    log_debug(f"Genius Processing: {artist} - {title}")
    
    if use_cache and cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data['choruses']
        except: pass

    urls_to_try = []
    
    url_artist_full = normalize_for_url(artist)
    url_title = normalize_for_url(title)
    urls_to_try.append(f'https://genius.com/{url_artist_full}-{url_title}-lyrics')
    
    primary_artist = clean_artist_name(artist)
    if primary_artist != artist.lower():
        url_artist_clean = normalize_for_url(primary_artist)
        urls_to_try.append(f'https://genius.com/{url_artist_clean}-{url_title}-lyrics')

    urls_to_try = list(dict.fromkeys(urls_to_try))

    final_response = None
    found_url = None

    for url in urls_to_try:
        log_debug(f"Testing direct URL: {url}")
        try:
            resp = requests.get(url, headers=GENIUS_HEADERS, timeout=5)
            if resp.status_code == 200:
                final_response = resp
                found_url = url
                break
        except: continue

    if not final_response or final_response.status_code != 200:
        log_debug("Direct URL failed. Attempting title search...")
        api_url = genius_search_for_correct_path(artist, title)
        if api_url:
            try:
                final_response = requests.get(api_url, headers=GENIUS_HEADERS, timeout=10)
                found_url = api_url
            except Exception as e:
                logging.error(f"Error connecting to Genius API URL ({api_url}): {e}")
    
    if not final_response or final_response.status_code != 200:
        logging.warning(f"Genius search failed for '{artist} - {title}'. Chorus data not downloaded")
        return []

    soup = BeautifulSoup(final_response.content, 'html.parser')
    lyrics_divs = soup.find_all('div', class_=lambda x: x and x.startswith('Lyrics__Container'))
    
    lyrics = ""
    for div in lyrics_divs:
        for excluded in div.find_all(['script', 'style', 'button']):
            excluded.decompose()
        lyrics += div.get_text(separator="\n")

    choruses = []
    pattern = rf'\[(?:{terms_pattern})(?:[:\s][^\]]*?)?\](.*?)(?=\[(?!{terms_pattern})|\Z)'
    matches = re.findall(pattern, lyrics, re.DOTALL | re.IGNORECASE | re.UNICODE)
    
    for m in matches:
        clean_m = m.strip()
        if len(clean_m) > 10:
            choruses.append(clean_m)

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump({'url': found_url, 'choruses': choruses}, f, indent=2, ensure_ascii=False)
        
    return choruses

def recover_repeats_from_txt(lyrics_map_list, matched_choruses):
    words = [l['lyrics'].lower().strip() for l in lyrics_map_list]
    new_matches = []
    
    confirmed_texts = []
    for m in matched_choruses:
        start_idx = next((i for i, l in enumerate(lyrics_map_list) if l['start_beat'] == m['start_beat']), 0)
        end_idx = next((i for i, l in enumerate(lyrics_map_list) if l['end_beat'] == m['end_beat']), len(lyrics_map_list)-1)
        
        segment_text = ' '.join(words[start_idx:end_idx+1])
        clean_segment = re.sub(r'[^\w\s]', '', segment_text)
        
        if len(clean_segment) > 20: 
            confirmed_texts.append(clean_segment)

    for target_text in confirmed_texts:
        target_len = len(target_text.split()) # contagem aproximada de palavras
        target_clean = target_text.replace(' ', '')
        
        for win_size in range(max(1, target_len - 2), target_len + 3):
             if win_size > len(words): continue
             
             for i in range(len(words) - win_size + 1):
                window_text = ''.join(words[i:i+win_size])
                window_clean = re.sub(r'[^\w\s]', '', window_text)
                
                if abs(len(target_clean) - len(window_clean)) > len(target_clean) * 0.2: continue
                
                if SequenceMatcher(None, target_clean, window_clean).ratio() > 0.90:
                    match_data = {
                        'start_beat': lyrics_map_list[i]['start_beat'],
                        'end_beat': lyrics_map_list[i+win_size-1]['end_beat']
                    }
                    
                    overlap = False
                    all_existing = matched_choruses + new_matches
                    for existing in all_existing:
                        if not (match_data['end_beat'] < existing['start_beat'] or match_data['start_beat'] > existing['end_beat']):
                            overlap = True
                            break
                    
                    if not overlap:
                        new_matches.append(match_data)

    return new_matches

def match_choruses_to_beats(lyrics_map_list, genius_choruses, similarity_threshold=0.7):
    matched_choruses = []
    used_ranges = []
    
    words = [l['lyrics'].lower().strip() for l in lyrics_map_list]

    for chorus_text in genius_choruses:
        chorus_text_clean = re.sub(r'[\(\[\]\)]', ' ', chorus_text)
        chorus_clean = re.sub(r'[^\w\s]', '', chorus_text_clean.lower())
        c_len = len(chorus_clean.split())
        best_match = None
        best_sim = 0

        for win_size in range(max(1, c_len - 5), c_len + 5):
            if win_size > len(words): continue
            
            for i in range(len(words) - win_size + 1):
                win_text = ' '.join(words[i:i + win_size])
                win_clean = re.sub(r'[^\w\s]', '', win_text)
                
                if abs(len(chorus_clean) - len(win_clean)) > len(chorus_clean) * 0.4: continue
                
                dist = levenshtein_distance(chorus_clean, win_clean)
                sim = 1 - (dist / max(len(chorus_clean), len(win_clean)))

                if sim > best_sim:
                    beats = word_positions_to_beats(lyrics_map_list, i, i + win_size)
                    if beats:
                        overlaps = any(not (beats['end_beat'] < u['start_beat'] or beats['start_beat'] > u['end_beat']) for u in used_ranges)
                        if not overlaps:
                            best_sim = sim
                            best_match = {'beats': beats, 'sim': sim, 'txt': win_text}

        if best_match and best_match['sim'] >= similarity_threshold:
            log_debug(f"MATCH: {best_match['sim']:.2f} | TXT: {best_match['txt'][:30]}...")
            matched_choruses.append({
                'start_beat': best_match['beats']['start_beat'],
                'end_beat': best_match['beats']['end_beat']
            })
            used_ranges.append(best_match['beats'])

    if matched_choruses:
        repeats = recover_repeats_from_txt(lyrics_map_list, matched_choruses)
        matched_choruses.extend(repeats)
            
    return matched_choruses

def word_positions_to_beats(lyrics_map_list, start_word, end_word):
    if start_word < len(lyrics_map_list) and end_word <= len(lyrics_map_list):
        return {
            'start_beat': lyrics_map_list[start_word]['start_beat'],
            'end_beat': lyrics_map_list[end_word-1]['end_beat']
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

    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(encoding="Windows-1252", indent="\t")
    xmlstr = xmlstr.decode("Windows-1252")
    xmlstr = re.sub(r'(</IntervalLayer>)', r'\1\n', xmlstr)
    xmlstr = re.sub(r'(value="[^"]*")\/>', r'\1 />', xmlstr)

    with open(os.path.join(directory, filename), "wb") as f:
        f.write(xmlstr.encode("Windows-1252", errors='xmlcharrefreplace'))

def main(input_file_name, song_duration, pitch_corr=0, s='', directory='', output_type=NEW, ignore_medley=False):
    us_data = parse_file(input_file_name)
    output_file = s if s else re.sub('[^A-Za-z0-9]+', '', us_data.get("TITLE", "Song"))
    
    sing_it = map_data(us_data, song_duration, pitch_corr, input_file_name=input_file_name, ignore_medley=ignore_medley)
    write_vxla_file(sing_it, output_file + '.vxla', directory=directory, song_duration=song_duration, output_type=output_type)
