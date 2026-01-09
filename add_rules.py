import streamlit as st
import json
from pathlib import Path

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
    """Load rules JSON, normalize old keys if needed"""
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
# UI
# -------------------------
st.title("📝 Textile Exchange Style Rules Editor")

# -------------------------
# LOAD RULES
# -------------------------
rules_data = load_rules()

# -------------------------
# ADD NEW RULE
# -------------------------
st.subheader("➕ Add New Rule")

with st.form("add_rule_form"):
    section = st.selectbox(
        "Category",
        ["style_guide_rule", "style_guide_caution"],
        format_func=lambda x: x.replace("_", " ").title()
    )
    match_text = st.text_input("Match text")
    replacement = st.text_input("Replacement (optional)")
    message = st.text_input("Message / Reasoning")
    submitted = st.form_submit_button("Add Rule")

    if submitted:
        if not match_text or not message:
            st.error("Match and Message are required")
        else:
            rules_data[section].insert(0, {
                "match": match_text.strip(),
                "replace_with": replacement.strip() if replacement else None,
                "message": message.strip()
            })
            save_rules(rules_data)
            st.success("✅ New rule added")
            st.rerun()

# -------------------------
# DISPLAY EXISTING RULES
# -------------------------
action, section, idx = display_rules("style_guide_rule", rules_data)
if not action:
    action, section, idx = display_rules("style_guide_caution", rules_data)

# -------------------------
# DELETE RULE
# -------------------------
if action == "delete":
    if idx < len(rules_data[section]):
        rules_data[section].pop(idx)
    save_rules(rules_data)
    # Clear edit state if exists
    if "edit_rule" in st.session_state:
        del st.session_state.edit_rule
    st.success("✅ Rule deleted")
    st.rerun()

# -------------------------
# EDIT RULE
# -------------------------
if "edit_rule" in st.session_state:
    section, idx = st.session_state.edit_rule
    if idx < len(rules_data.get(section, [])):
        rule = rules_data[section][idx]

        st.subheader(f"✏️ Edit Rule ({section.replace('_',' ').title()}, #{idx + 1})")

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
        # Invalid index after deletion
        del st.session_state.edit_rule
