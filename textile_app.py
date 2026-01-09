import streamlit as st
import json
from pathlib import Path
import tempfile
from collections import defaultdict
import os
import re
from docx import Document
from docx.shared import RGBColor
from wordfreq import word_frequency

# -------------------------
# FIND REPO ROOT SAFELY
# -------------------------
CURRENT_FILE = Path(__file__).resolve()

def find_repo_root(start_path: Path) -> Path:
    for parent in [start_path] + list(start_path.parents):
        if (parent / "Rules").exists():
            return parent
    return start_path.parent

REPO_ROOT = find_repo_root(CURRENT_FILE)
RULES_FILE = REPO_ROOT / "Rules" / "Textile_Exchange_Style_Guide_STRICT.json"

# -------------------------
# CAPITALIZATION RULES
# -------------------------
CAPITALIZATION_RULES = {
    "indigenous people": "Indigenous People",
    "first nations": "First Nations",
    # Add more capitalization-sensitive phrases here
}

# -------------------------
# RULE STORAGE HELPERS
# -------------------------
def load_rules():
    if not RULES_FILE.exists():
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        default = {"style_guide_rule": [], "style_guide_caution": []}
        RULES_FILE.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default

    data = json.loads(RULES_FILE.read_text(encoding="utf-8"))

    normalized = {"style_guide_rule": [], "style_guide_caution": []}
    # Keep all rules, normalize old keys
    normalized["style_guide_rule"].extend(data.get("style_guide_rule", []))
    normalized["style_guide_rule"].extend(data.get("terminology", []))
    normalized["style_guide_caution"].extend(data.get("style_guide_caution", []))
    normalized["style_guide_caution"].extend(data.get("flag_only", []))

    # Ensure all keys exist
    for cat in ["style_guide_rule", "style_guide_caution"]:
        for r in normalized[cat]:
            r.setdefault("match", "")
            r.setdefault("replace_with", None)
            r.setdefault("message", "")
            r.setdefault("case_sensitive", False)

    return normalized

def save_rules(rules):
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    RULES_FILE.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")

def display_rules(section_name, rules_data):
    st.subheader(section_name.replace("_", " ").title())
    for idx, rule in enumerate(rules_data.get(section_name, [])):
        cols = st.columns([5, 1, 1])
        with cols[0]:
            st.markdown(
                f"**Match:** {rule.get('match','')}  \n"
                f"**Replacement:** {rule.get('replace_with') or '—'}  \n"
                f"**Message:** {rule.get('message','')}"
            )
        with cols[1]:
            if st.button("Edit", key=f"edit_{section_name}_{idx}"):
                st.session_state.edit_rule = (section_name, idx)
                st.rerun()
        with cols[2]:
            if st.button("Delete", key=f"del_{section_name}_{idx}"):
                return "delete", section_name, idx
    return None, None, None

# -------------------------
# DOC ANALYSIS
# -------------------------
SEVERITY_COLOR = {
    "style_guide_rule": RGBColor(255, 0, 0),
    "style_guide_caution": RGBColor(255, 165, 0),
}

BRITISH_TO_AMERICAN = {
    "organisation": "organization",
    "colour": "color",
    "fibre": "fiber",
    "labour": "labor",
    "centre": "center",
    "behaviour": "behavior",
}

def analyze_doc(path, rules_data):
    doc = Document(path)
    results = []

    # Flatten rules and include capitalization rules
    rules = []
    for cat in ["style_guide_rule", "style_guide_caution"]:
        for r in rules_data.get(cat, []):
            rules.append({
                "pattern": r.get("match", ""),
                "message": r.get("message", ""),
                "replace_with": r.get("replace_with"),
                "case_sensitive": r.get("case_sensitive", False),
                "rule_type": cat
            })

    # Add capitalization rules as caution
    for phrase, correct in CAPITALIZATION_RULES.items():
        rules.append({
            "pattern": phrase,
            "message": f"Should be capitalized: '{correct}'",
            "replace_with": correct,
            "case_sensitive": False,
            "rule_type": "style_guide_caution"
        })

    for p_idx, para in enumerate(doc.paragraphs, start=1):
        text = para.text
        if not text.strip():
            continue

        char_to_run = {}
        pos = 0
        for run in para.runs:
            for _ in run.text:
                char_to_run[pos] = run
                pos += 1

        applied = set()

        # Apply rules
        for rule in rules:
            flags = 0 if rule["case_sensitive"] else re.IGNORECASE
            for m in re.finditer(rf"\b{re.escape(rule['pattern'])}\b", text, flags):
                s, e = m.start(), m.end()
                if any(i in applied for i in range(s, e)):
                    continue

                for i in range(s, e):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR.get(
                        rule["rule_type"], RGBColor(255, 0, 0)
                    )
                    applied.add(i)

                results.append({
                    "match": m.group(),
                    "rule_category": rule["rule_type"],
                    "message": rule["message"],
                    "suggested_replacement": rule.get("replace_with"),
                    "paragraph_index": p_idx,
                    "char_index": s + 1,
                    "context": text
                })

        # British spelling check
        for m in re.finditer(r"\b[A-Za-z']+\b", text):
            word = m.group().lower()
            if word in BRITISH_TO_AMERICAN:
                s, e = m.start(), m.end()
                if any(i in applied for i in range(s, e)):
                    continue
                for i in range(s, e):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR["style_guide_caution"]
                results.append({
                    "match": m.group(),
                    "rule_category": "style_guide_caution",
                    "message": "British spelling detected. Use American English.",
                    "suggested_replacement": BRITISH_TO_AMERICAN[word],
                    "paragraph_index": p_idx,
                    "char_index": s + 1,
                    "context": text
                })

        # Full CAPS sentence check
        words = re.findall(r"\b[A-Za-z]{2,}\b", text)
        caps_words = [w for w in words if w.isupper()]
        if words and len(caps_words)/len(words) >= 0.6:  # threshold: 60%
            for m in re.finditer(r"\b[A-Z]{2,}\b", text):
                s, e = m.start(), m.end()
                if any(i in applied for i in range(s, e)):
                    continue
                for i in range(s, e):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR["style_guide_caution"]
                    applied.add(i)
            results.append({
                "match": "ALL CAPS sentence",
                "rule_category": "style_guide_caution",
                "message": "Avoid full capitalization. Use sentence case unless approved.",
                "suggested_replacement": None,
                "paragraph_index": p_idx,
                "char_index": 1,
                "context": text
            })

    return doc, results

# -------------------------
# STREAMLIT UI
# -------------------------
st.set_page_config("Textile Exchange Rules + Checker", layout="wide")
st.title("📘 Textile Exchange Style Guide")

tab_rules, tab_check = st.tabs(["📋 Edit Rules", "📄 Style Checker"])

# -------------------------
# RULE EDITOR
# -------------------------
with tab_rules:
    rules_data = load_rules()

    with st.form("add_rule"):
        section = st.selectbox(
            "Category",
            ["style_guide_rule", "style_guide_caution"],
            format_func=lambda x: x.replace("_", " ").title()
        )
        match = st.text_input("Match")
        replacement = st.text_input("Replacement (optional)")
        message = st.text_input("Message")
        submitted = st.form_submit_button("Add rule")

        if submitted and match and message:
            rules_data[section].insert(0, {
                "match": match,
                "replace_with": replacement or None,
                "message": message,
                "case_sensitive": False
            })
            save_rules(rules_data)
            st.rerun()

    action, sec, idx = display_rules("style_guide_rule", rules_data)
    if not action:
        action, sec, idx = display_rules("style_guide_caution", rules_data)

    if action == "delete":
        rules_data[sec].pop(idx)
        save_rules(rules_data)
        st.rerun()

# -------------------------
# STYLE CHECKER
# -------------------------
with tab_check:
    uploaded = st.file_uploader("Upload Word document", type=["docx"])
    if uploaded and st.button("▶️ Run style check"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(uploaded.read())
            path = tmp.name

        rules_data = load_rules()
        doc, results = analyze_doc(path, rules_data)

        out = path.replace(".docx", "_checked.docx")
        doc.save(out)

        st.download_button(
            "⬇️ Download highlighted document",
            data=open(out, "rb"),
            file_name="Textile_Exchange_Style_Checked.docx"
        )

        st.subheader("📋 Issues found")

        grouped = defaultdict(list)
        for r in results:
            grouped[r["paragraph_index"]].append(r)

        for p, items in grouped.items():
            st.markdown(f"**Paragraph {p}:** {items[0]['context']}")
            for r in items:
                icon = "🟥" if r["rule_category"] == "style_guide_rule" else "🟧"
                st.markdown(
                    f"{icon} **{r['match']}**  \n"
                    f"{r['message']}  \n"
                    f"**Suggested replacement:** {r.get('suggested_replacement') or '—'}"
                )
            st.markdown("---")
