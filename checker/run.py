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

# Map rule categories to colors
RULE_COLOR_RGB = {
    "style guide rule": RGBColor(255, 0, 0),      # RED
    "style guide caution": RGBColor(255, 165, 0)  # ORANGE
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
    """Load rules from JSON and normalize to two categories"""
    if not os.path.exists(RULES_FILE):
        return []

    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    rules = []

    for section_name, section in data.items():
        for item in section:
            raw_type = item.get("type", "flag_only")

            rule_type = (
                "style guide caution"
                if raw_type == "flag_only" or section_name == "style_guide_caution"
                else "style guide rule"
            )

            rules.append({
                "pattern": item.get("match", ""),
                "message": item.get("message", ""),
                "replace_with": item.get("replace_with"),   # ✅ ADDED
                "rule_type": rule_type,
                "case_sensitive": item.get("case_sensitive", False)
            })

    return rules

# -------------------------
# MAIN ANALYSIS
# -------------------------
def analyze_doc(uploaded_file):
    """Analyze a Word doc and highlight issues"""
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
        # STYLE GUIDE RULES (CASE-AWARE)
        # -------------------------
        for rule in rules:
            if not rule["pattern"]:
                continue

            flags = 0 if rule["case_sensitive"] else re.IGNORECASE

            for m in re.finditer(
                rf"\b{re.escape(rule['pattern'])}\b",
                text,
                flags
            ):
                start, end = m.start(), m.end()

                if any(i in applied_indices for i in range(start, end)):
                    continue
                if (rule["pattern"], para_idx) in reported:
                    continue

                color = RULE_COLOR_RGB[rule["rule_type"]]

                for i in range(start, end):
                    char_to_run[i].font.color.rgb = color
                    applied_indices.add(i)

                results.append({
                    "match": m.group(),
                    "rule_category": rule["rule_type"].title(),
                    "message": rule["message"],
                    "suggested_replacement": rule.get("replace_with"),  # ✅ ADDED
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
            for m in re.finditer(r"\b[A-Z]{2,}\b", text):
                start, end = m.start(), m.end()
                if any(i in applied_indices for i in range(start, end)):
                    continue

                for i in range(start, end):
                    char_to_run[i].font.color.rgb = RULE_COLOR_RGB["style guide caution"]
                    applied_indices.add(i)

            results.append({
                "match": "ALL CAPS sentence",
                "rule_category": "Style guide caution",
                "message": "Avoid full capitalisation. Use sentence case unless this is an approved acronym.",
                "suggested_replacement": None,
                "context": text,
                "paragraph_index": para_idx,
                "char_index": 1
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
                    char_to_run[i].font.color.rgb = RULE_COLOR_RGB["style guide caution"]
                    applied_indices.add(i)

                results.append({
                    "match": word,
                    "rule_category": "Style guide caution",
                    "message": "British spelling detected. Use American English.",
                    "suggested_replacement": BRITISH_TO_AMERICAN[lower],
                    "context": text,
                    "paragraph_index": para_idx,
                    "char_index": start + 1
                })

        # -------------------------
        # AMERICAN ENGLISH SPELLCHECK
        # -------------------------
        for m in re.finditer(r"\b[A-Za-z']+\b", text):
            word = m.group()
            start, end = m.start(), m.end()

            if any(i in applied_indices for i in range(start, end)):
                continue
            if not word.isalpha():
                continue

            freq = word_frequency(word.lower(), "en")
            if freq < 1e-6:
                for i in range(start, end):
                    char_to_run[i].font.color.rgb = RULE_COLOR_RGB["style guide rule"]
                    applied_indices.add(i)

                results.append({
                    "match": word,
                    "rule_category": "Style guide rule",
                    "message": "Word not recognized in American English dictionary.",
                    "suggested_replacement": None,
                    "context": text,
                    "paragraph_index": para_idx,
                    "char_index": start + 1
                })

    return doc, results
