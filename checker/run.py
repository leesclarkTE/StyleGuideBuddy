import os
import json
import re
from docx import Document
from docx.shared import RGBColor
from wordfreq import word_frequency  # For American English spellcheck

# -------------------------
# CONFIG
# -------------------------
RULES_FILE = "Rules/Textile_Exchange_Style_Guide_STRICT.json"

SEVERITY_COLOR_RGB = {
    "advice": RGBColor(255, 255, 0),    # Yellow
    "warning": RGBColor(255, 165, 0),   # Orange
    "error": RGBColor(255, 0, 0),       # Red
}

# British → American spellings
BRITISH_TO_AMERICAN = {
    "organisation": "organization",
    "organisations": "organizations",
    "colour": "color",
    "colours": "colors",
    "fibre": "fiber",
    "programme": "program",
    "labour": "labor",
    "centre": "center",
    "behaviour": "behavior",
    "travelling": "traveling",
    "travelled": "traveled"
}

# -------------------------
# LOAD RULES
# -------------------------
def load_rules():
    """Load rules from JSON and flatten into list of dicts"""
    if not os.path.exists(RULES_FILE):
        return []

    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    rules = []
    for section in data.values():
        for item in section:
            rules.append({
                "pattern": item["match"],
                "replacement": item.get("replace_with"),
                "message": item.get("message", ""),
                "severity": item.get("severity", "warning"),
                "type": item.get("type", "flag")  # flag or auto_fix
            })
    return rules

# -------------------------
# HELPER
# -------------------------
def is_all_caps(text):
    letters = re.findall(r"[A-Za-z]", text)
    return letters and all(c.isupper() for c in letters)

# -------------------------
# MAIN ANALYSIS
# -------------------------
def analyze_doc(uploaded_file):
    """Analyze a Word doc and highlight issues without replacing text."""
    doc = Document(uploaded_file)
    rules = load_rules()
    results = []

    for para_idx, para in enumerate(doc.paragraphs, start=1):
        text = para.text
        if not text.strip():
            continue

        # Map characters to runs
        char_to_run = {}
        pos = 0
        for run in para.runs:
            for _ in run.text:
                char_to_run[pos] = run
                pos += 1

        applied_indices = set()
        reported = set()

        # -------------------------
        # STYLE / TERMINOLOGY RULES
        # -------------------------
        for rule in rules:
            if not rule["pattern"]:
                continue

            for m in re.finditer(rf"\b{re.escape(rule['pattern'])}\b", text, re.IGNORECASE):
                start, end = m.start(), m.end()

                if any(i in applied_indices for i in range(start, end)):
                    continue
                if (rule["pattern"], para_idx) in reported:
                    continue

                # Highlight the matched text
                color = SEVERITY_COLOR_RGB.get(rule["severity"], RGBColor(255,0,0))
                for i in range(start, end):
                    char_to_run[i].font.color.rgb = color
                    applied_indices.add(i)

                results.append({
                    "match": m.group(),
                    "severity": rule["severity"],
                    "message": rule["message"],
                    "suggested_replacement": "",  # no replacement
                    "context": text,
                    "paragraph_index": para_idx,
                    "char_index": start + 1
                })
                reported.add((rule["pattern"], para_idx))

        # -------------------------
        # FULL CAPS SENTENCE CHECK
        # -------------------------
        words = re.findall(r"\b[A-Za-z]{2,}\b", text)
        caps_words = [w for w in words if w.isupper()]
        if words and len(caps_words) / len(words) >= 0.6:
            if not any(r.get('all_caps') and r['paragraph_index']==para_idx for r in results):
                for m in re.finditer(r"\b[A-Z]{2,}\b", text):
                    start, end = m.start(), m.end()
                    if any(i in applied_indices for i in range(start, end)):
                        continue
                    for i in range(start, end):
                        char_to_run[i].font.color.rgb = SEVERITY_COLOR_RGB["warning"]
                        applied_indices.add(i)

                results.append({
                    "match": "ALL CAPS sentence",
                    "severity": "warning",
                    "message": "Avoid full capitalisation. Use sentence case unless this is an approved acronym.",
                    "suggested_replacement": "",
                    "context": text,
                    "paragraph_index": para_idx,
                    "char_index": 1,
                    "all_caps": True
                })
        else:
            # Single ALL CAPS words
            for m in re.finditer(r"\b[A-Z]{3,}\b", text):
                start, end = m.start(), m.end()
                if any(i in applied_indices for i in range(start, end)):
                    continue
                word = m.group()
                for i in range(start, end):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR_RGB["warning"]
                    applied_indices.add(i)

                results.append({
                    "match": word,
                    "severity": "warning",
                    "message": "Avoid full capitalisation. Use sentence case unless this is an approved acronym.",
                    "suggested_replacement": "",
                    "context": text,
                    "paragraph_index": para_idx,
                    "char_index": start + 1
                })

        # -------------------------
        # BRITISH SPELLING CHECK
        # -------------------------
        for m in re.finditer(r"\b[A-Za-z']+\b", text):
            word = m.group()
            lower = word.lower()
            start, end = m.start(), m.end()

            if lower in BRITISH_TO_AMERICAN and not any(i in applied_indices for i in range(start, end)):
                for i in range(start, end):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR_RGB["warning"]
                    applied_indices.add(i)

                results.append({
                    "match": word,
                    "severity": "warning",
                    "message": "British spelling detected. Use American English.",
                    "suggested_replacement": "",
                    "context": text,
                    "paragraph_index": para_idx,
                    "char_index": start + 1
                })

        # -------------------------
        # AMERICAN ENGLISH SPELLCHECK (wordfreq)
        # -------------------------
        for m in re.finditer(r"\b[A-Za-z']+\b", text):
            word = m.group()
            start, end = m.start(), m.end()
            if any(i in applied_indices for i in range(start, end)):
                continue
            if not word.isalpha():
                continue
            freq = word_frequency(word.lower(), 'en')
            if freq < 1e-6:
                for i in range(start, end):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR_RGB["error"]
                    applied_indices.add(i)
                results.append({
                    "match": word,
                    "severity": "error",
                    "message": "Word not recognized in American English dictionary.",
                    "suggested_replacement": "",
                    "context": text,
                    "paragraph_index": para_idx,
                    "char_index": start + 1
                })

    return doc, results
