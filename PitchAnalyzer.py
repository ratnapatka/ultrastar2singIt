import librosa
import numpy as np
import crepe
from tqdm import tqdm

def get_pitch_correction_suggestion(txt_data, audio_file, min_pitch, max_pitch):

    pitch_from_txt = get_txt_pitch_values(txt_data)

    if min_pitch < pitch_from_txt['min'] and max_pitch > pitch_from_txt['max']:
        tqdm.write(f"Suggested pitch correction: 0")
        return 0
    pitch_from_audio = get_audio_pitch_values(audio_file)

    tqdm.write(f"Expected pitch range (from .txt): {pitch_from_txt}")
    tqdm.write(f"Actual pitch range (from audio): {pitch_from_audio}")
    tqdm.write(f"Suggested pitch correction: {pitch_from_audio['median'] - pitch_from_txt['median'] if pitch_from_audio else 0}")

    return pitch_from_audio['median'] - pitch_from_txt['median'] if pitch_from_audio else 0

def get_txt_pitch_values(txt_data):
    total_pitch = 0
    note_count = 0
    all_pitches = []
    for note in txt_data["notes"]:
        if note[0] == ":" or note[0] == "*":
            try:
                pitch = int(note[3])
                total_pitch += pitch
                note_count += 1
                all_pitches.append(pitch)
            except (ValueError, IndexError):
                continue
    average_pitch = int(round(total_pitch / note_count))
    median_pitch = int(round(np.median(all_pitches) if all_pitches else 0))
    min_pitch = min(all_pitches) if all_pitches else 0
    max_pitch = max(all_pitches) if all_pitches else 0
    pitch_from_txt = {
        'average': average_pitch,
        'min': min_pitch,
        'max': max_pitch,
        'median': median_pitch
    }
    return pitch_from_txt

def get_audio_pitch_values(audio_file):
    pitch_data = analyze_pitch_from_audio(audio_file)
    valid_notes = pitch_data['midi_notes'][~np.isnan(pitch_data['midi_notes'])]

    if len(valid_notes) == 0:
        return None

    return {
        'average': int(round(np.mean(valid_notes))),
        'min': int(round(np.min(valid_notes))),
        'max': int(round(np.max(valid_notes))),
        'median': int(round(np.median(valid_notes)))
    }

def analyze_pitch_from_audio(audio_file):
    y, sr = librosa.load(audio_file, sr=16000)
    time, frequency, confidence, activation = crepe.predict(y, sr, viterbi=True, model_capacity='tiny')
    frequency[confidence < 0.9] = np.nan
    midi_notes = librosa.hz_to_midi(frequency)

    return {
        'time': time,
        'frequency': frequency,
        'midi_notes': midi_notes,
        'confidence': confidence
    }

def get_pitch_correction_suggestion_fast(txt_data, min_pitch, max_pitch):
    pitch_from_txt = get_txt_pitch_values(txt_data)

    required_corr = 0
    if 40 <= pitch_from_txt['average'] <= 80:
        tqdm.write(f"Suggested pitch correction: 0")
        return 0
    elif pitch_from_txt['max'] > 33:
        s_max = max_pitch - pitch_from_txt['max']
        required_corr = max(required_corr, s_max)
    elif pitch_from_txt['min'] < -5:
        s_min = min_pitch - pitch_from_txt['min']
        required_corr = max(required_corr, s_min)
    if required_corr > 0:
        pitch_corr = required_corr
    else:
        pitch_corr = 48

    tqdm.write(f"Suggested pitch correction: {pitch_corr}")

    return pitch_corr
