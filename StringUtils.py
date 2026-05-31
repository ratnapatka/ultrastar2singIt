import re

import unicodedata

replacements = {
    "’": "'", "‘": "'", "‚": "'", "‹": "'", "›": "'", "`": "'",
    '“': '"', '”': '"', "„": '"', "«": '"', "»": '"',
    "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE",
    "ﬁ": "fi", "ﬂ": "fl",
    "–": "-", "—": "-", "−": "-",
    "…": "", "...": ""
}

def normalize_text(text):
    for old, new in replacements.items():
        text = text.replace(old, new)
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if unicodedata.category(c) != 'Mn')


# handle special characters and feats for genius url
def normalize_for_url(text):
    text = text.strip().lower()
    text = text.replace(' with ', ' and ').replace(' feat ', ' and ').replace(' ft ', ' and ').replace(' & ', ' and ')
    text = re.sub(r'[_:@\\\/\s]', '-', text)
    text = re.sub(r'[^\w-]', '', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text

def sanitize_name(name):
    # name = re.sub(r'\[.*?\]', '', name) // removes anything inside [x]
    name = normalize_text(name)
    name = re.sub(r"[!?#$%'\"\u2018\u2019\u00B4`\u201C\u201D()\[\]]", '', name)
    return ' '.join(name.split()).strip()