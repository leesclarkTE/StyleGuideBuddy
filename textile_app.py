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
# HELPER FUNCTIONS
# -------------------------
def load_rules():
    if not RULES_FILE.exists():
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        default_rules = {"style_guide_rule": [], "style_guide_caution": []}
        with RULES_FILE.open("w", encoding="utf-8") as f:
            json.dump(default_rules, f, indent=2, ensure_ascii=False)
        return default_rules

    with RULES_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Normalize old keys
    new_data = {"style_guide_rule": [], "style_guide_caution": []}
    if "terminology" in data:
        new_data["style_guide_rule"].extend(data["terminology"])
    elif "style_guide_rule" in data:
        new_data["style_guide_rule"].extend(data["style_guide_rule"])

    if "flag_only" in data:
        new_data["style_guide_caution"].extend(data["flag_only"])
    elif "style_guide_caution" in data:
        new_data["style_guide_caution"].extend(data["style_guide_caution"])

    return new_data

def save_rules(rules_data):
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with RULES_FILE.open("w", encoding="utf-8") as f:
        json.dump(rules_data, f, indent=2, ensure_ascii=False)

def display_rules(section_name, rules_data):
    st.subheader(section_name.replace("_", " ").title())
    rules_list = rules_data.get(section_name, [])
    for idx, rule in enumerate(rules_list):
        cols = st.columns([5, 1, 1])
        with cols[0]:
            st.markdown(
                f"**Match:** {rule.get('match','')}  \n"
                f"**Replacement:** {rule.get('replace_with','')}  \n"
                f"**Message:** {rule.get('message','')}  \n"
                f"**Category:** {section_name.replace('_',' ').title()}"
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
# DOC ANALYSIS FUNCTIONS
# -------------------------
SEVERITY_COLOR_RGB = {
    "style guide rule": RGBColor(255, 0, 0),
    "style guide caution": RGBColor(255, 165, 0),
}

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

def analyze_doc(uploaded_file, rules_data):
    doc = Document(uploaded_file)
    results = []

    # Flatten rules for easier checking
    all_rules = []
    for cat in ["style_guide_rule", "style_guide_caution"]:
        for item in rules_data.get(cat, []):
            all_rules.append({
                "pattern": item.get("match",""),
                "message": item.get("message",""),
                "rule_type": cat
            })

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

        # Apply rules
        for rule in all_rules:
            for m in re.finditer(rf"\b{re.escape(rule['pattern'])}\b", text, re.IGNORECASE):
                start, end = m.start(), m.end()
                if any(i in applied_indices for i in range(start, end)):
                    continue
                if (rule["pattern"], para_idx) in reported:
                    continue

                color = SEVERITY_COLOR_RGB.get(rule["rule_type"], RGBColor(255,0,0))
                for i in range(start, end):
                    char_to_run[i].font.color.rgb = color
                    applied_indices.add(i)

                results.append({
                    "match": m.group(),
                    "rule_category": rule["rule_type"],
                    "message": rule["message"],
                    "paragraph_index": para_idx,
                    "char_index": start + 1,
                    "context": text
                })
                reported.add((rule["pattern"], para_idx))

        # Full CAPS check
        words = re.findall(r"\b[A-Za-z]{2,}\b", text)
        caps_words = [w for w in words if w.isupper()]
        if words and len(caps_words)/len(words) >= 0.6:
            for m in re.finditer(r"\b[A-Z]{2,}\b", text):
                start, end = m.start(), m.end()
                if any(i in applied_indices for i in range(start,end)):
                    continue
                for i in range(start,end):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR_RGB["style guide caution"]
                    applied_indices.add(i)
            results.append({
                "match": "ALL CAPS sentence",
                "rule_category": "style guide caution",
                "message": "Avoid full capitalization.",
                "paragraph_index": para_idx,
                "char_index": 1,
                "context": text
            })

        # British spelling check
        for m in re.finditer(r"\b[A-Za-z']+\b", text):
            word = m.group().lower()
            start, end = m.start(), m.end()
            if word in BRITISH_TO_AMERICAN and not any(i in applied_indices for i in range(start,end)):
                for i in range(start,end):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR_RGB["style guide caution"]
                    applied_indices.add(i)
                results.append({
                    "match": word,
                    "rule_category": "style guide caution",
                    "message": "British spelling detected.",
                    "paragraph_index": para_idx,
                    "char_index": start + 1,
                    "context": text
                })

        # American English spellcheck using wordfreq
        for m in re.finditer(r"\b[A-Za-z']+\b", text):
            word = m.group().lower()
            start, end = m.start(), m.end()
            if any(i in applied_indices for i in range(start,end)) or not word.isalpha():
                continue
            freq = word_frequency(word, "en")
            if freq < 1e-6:
                for i in range(start,end):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR_RGB["style guide rule"]
                    applied_indices.add(i)
                results.append({
                    "match": word,
                    "rule_category": "style guide rule",
                    "message": "Word not recognized in American English.",
                    "paragraph_index": para_idx,
                    "char_index": start + 1,
                    "context": text
                })

    return doc, results

# -------------------------
# STREAMLIT APP
# -------------------------
st.set_page_config(page_title="Textile Exchange Rules + Checker", layout="wide")
st.title("📘 Textile Exchange Rules & Style Checker")

# Tabs for Rules vs Checker
tab1, tab2 = st.tabs(["📋 Edit Rules", "📄 Style Checker"])

# -------------------------
# TAB 1: EDIT RULES
# -------------------------
with tab1:
    st.subheader("➕ Add New Rule")
    with st.form("add_rule_form"):
        section = st.selectbox(
            "Category",
            ["style_guide_rule","style_guide_caution"],
            format_func=lambda x: x.replace("_"," ").title()
        )
        match_text = st.text_input("Match text")
        replacement = st.text_input("Replacement (optional)")
        message = st.text_input("Message / Reasoning")
        submitted = st.form_submit_button("Add Rule")
        if submitted:
            if not match_text or not message:
                st.error("Match and Message are required")
            else:
                rules_data = load_rules()
                rules_data[section].insert(0, {
                    "match": match_text.strip(),
                    "replace_with": replacement.strip() if replacement else None,
                    "message": message.strip()
                })
                save_rules(rules_data)
                st.success("✅ New rule added")
                st.rerun()

    # Display existing rules
    rules_data = load_rules()
    action, section, idx = display_rules("style_guide_rule", rules_data)
    if not action:
        action, section, idx = display_rules("style_guide_caution", rules_data)

    # Delete rule
    if action == "delete":
        if idx < len(rules_data[section]):
            rules_data[section].pop(idx)
        save_rules(rules_data)
        if "edit_rule" in st.session_state:
            del st.session_state.edit_rule
        st.success("✅ Rule deleted")
        st.rerun()

    # Edit rule
    if "edit_rule" in st.session_state:
        section, idx = st.session_state.edit_rule
        rules_data = load_rules()
        if idx < len(rules_data.get(section, [])):
            rule = rules_data[section][idx]
            st.subheader(f"✏️ Edit Rule ({section.replace('_',' ').title()}, #{idx+1})")
            with st.form("edit_rule_form"):
                match_text = st.text_input("Match", value=rule.get("match",""))
                replacement = st.text_input("Replacement", value=rule.get("replace_with") or "")
                message = st.text_input("Message", value=rule.get("message",""))
                submitted = st.form_submit_button("Update Rule")
                if submitted:
                    rules_data[section][idx] = {
                        "match": match_text.strip(),
                        "replace_with": replacement.strip() if replacement else None,
                        "message": message.strip()
                    }
                    save_rules(rules_data)
                    del st.session_state.edit_rule
                    st.success("✅ Rule updated")
                    st.rerun()
        else:
            del st.session_state.edit_rule

# -------------------------
# TAB 2: STYLE CHECKER
# -------------------------
with tab2:
    st.subheader("Upload Word Document for Style Check")
    uploaded_file = st.file_uploader("Upload a Word document (.docx)", type=["docx"])
    if uploaded_file:
        if st.button("▶️ Run style check"):
            with st.spinner("Checking document..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                    tmp.write(uploaded_file.read())
                    temp_path = tmp.name

                rules_data = load_rules()
                doc, results = analyze_doc(temp_path, rules_data)
                output_path = temp_path.replace(".docx","_highlighted.docx")
                doc.save(output_path)

            st.success("✅ Check complete")
            st.download_button(
                "⬇️ Download highlighted Word document",
                data=open(output_path,"rb"),
                file_name="Textile_Exchange_Style_Checked.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

            st.subheader("📋 Issues found")
            if not results:
                st.success("No style guide issues found 🎉")
            else:
                para_results = defaultdict(list)
                for r in results:
                    para_results[r["paragraph_index"]].append(r)
                for para_idx in sorted(para_results.keys()):
                    para_items = para_results[para_idx]
                    context_text = para_items[0]["context"].replace("\n"," ").replace("\r"," ")
                    st.markdown(f"**Paragraph {para_idx} context:** {context_text}")
                    for r in para_items:
                        if r["match"] == "ALL CAPS sentence" and any(prev is not r and prev["match"]=="ALL CAPS sentence" for prev in para_items):
                            continue
                        rule_category = r.get("rule_category","style guide rule").lower()
                        icon = "🟥" if rule_category=="style guide rule" else "🟧"
                        label = "Style guide rule" if rule_category=="style guide rule" else "Style guide caution"
                        reasoning = (r.get("message") or "").replace("_","\\_").replace("*","\\*")
                        location = f"Paragraph {r['paragraph_index']}, Character {r['char_index']}"
                        st.markdown(f"{icon} **{label}**\n\n**Issue:** {r['match']}  \n**Explanation:** {reasoning}  \n**Location:** {location}")
                    st.markdown("---")
            try:
                os.remove(temp_path)
            except Exception:
                pass
