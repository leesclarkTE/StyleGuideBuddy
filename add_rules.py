import streamlit as st
import json
from pathlib import Path

# -------------------------
# FIND REPO ROOT SAFELY
# -------------------------
CURRENT_FILE = Path(__file__).resolve()

def find_repo_root(start_path: Path) -> Path:
    """Walk upward until we find the Rules directory or fallback to parent"""
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
    """Load rules JSON or create a new default structure if missing"""
    if not RULES_FILE.exists():
        # Create empty JSON structure if missing
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        default_rules = {"terminology": [], "flag_only": []}
        with RULES_FILE.open("w", encoding="utf-8") as f:
            json.dump(default_rules, f, indent=2, ensure_ascii=False)
        return default_rules
    with RULES_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_rules(rules_data):
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with RULES_FILE.open("w", encoding="utf-8") as f:
        json.dump(rules_data, f, indent=2, ensure_ascii=False)

def display_rules(section_name, rules_data):
    st.subheader(section_name.capitalize())
    for idx, rule in enumerate(rules_data):
        cols = st.columns([5, 1, 1])
        with cols[0]:
            st.markdown(
                f"**Match:** {rule.get('match','')}  \n"
                f"**Replacement:** {rule.get('replace_with','')}  \n"
                f"**Message:** {rule.get('message','')}  \n"
                f"**Severity:** {rule.get('severity','')}"
            )
        with cols[1]:
            if st.button("Edit", key=f"edit_{section_name}_{idx}"):
                st.session_state.edit_rule = (section_name, idx)
                st.experimental_rerun()
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
terminology_rules = rules_data.get("terminology", [])
flag_only_rules = rules_data.get("flag_only", [])

# -------------------------
# ADD NEW RULE (TOP)
# -------------------------
st.subheader("➕ Add New Rule")

with st.form("add_rule_form"):
    section = st.selectbox("Section", ["terminology", "flag_only"])
    match_text = st.text_input("Match text")
    replacement = st.text_input("Replacement (optional)")
    message = st.text_input("Message / Reasoning")
    severity = st.selectbox("Severity", ["advice", "warning", "error"])
    submitted = st.form_submit_button("Add Rule")

    if submitted:
        if not match_text or not message:
            st.error("Match and Message are required")
        else:
            rules_data[section].insert(0, {
                "match": match_text.strip(),
                "replace_with": replacement.strip() if replacement else None,
                "message": message.strip(),
                "severity": severity
            })
            save_rules(rules_data)
            st.success("✅ New rule added")
            st.experimental_rerun()

# -------------------------
# DISPLAY RULES
# -------------------------
action, section, idx = display_rules("terminology", terminology_rules)
if not action:
    action, section, idx = display_rules("flag_only", flag_only_rules)

# -------------------------
# DELETE
# -------------------------
if action == "delete":
    rules_data[section].pop(idx)
    save_rules(rules_data)
    st.success("✅ Rule deleted")
    st.experimental_rerun()

# -------------------------
# EDIT
# -------------------------
if "edit_rule" in st.session_state:
    section, idx = st.session_state.edit_rule
    rule = rules_data[section][idx]

    st.subheader(f"✏️ Edit Rule ({section}, #{idx + 1})")

    with st.form("edit_rule_form"):
        match_text = st.text_input("Match", value=rule.get("match",""))
        replacement = st.text_input("Replacement", value=rule.get("replace_with") or "")
        message = st.text_input("Message", value=rule.get("message",""))
        severity = st.selectbox(
            "Severity",
            ["advice","warning","error"],
            index=["advice","warning","error"].index(rule.get("severity","warning"))
        )
        submitted = st.form_submit_button("Update Rule")

        if submitted:
            rules_data[section][idx] = {
                "match": match_text.strip(),
                "replace_with": replacement.strip() if replacement else None,
                "message": message.strip(),
                "severity": severity
            }
            save_rules(rules_data)
            del st.session_state.edit_rule
            st.success("✅ Rule updated")
            st.experimental_rerun()
