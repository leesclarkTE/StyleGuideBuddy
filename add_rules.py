import streamlit as st
import json
import os

RULES_FILE = os.path.abspath("Rules/Textile_Exchange_Style_Guide_STRICT.json")

def load_rules():
    if not os.path.exists(RULES_FILE):
        return {"terminology": [], "flag_only": []}
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_rules(data):
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

severity_colors = {"advice":"blue", "warning":"orange", "error":"red"}

st.set_page_config(page_title="Rule Editor", layout="centered")
st.title("📝 Textile Exchange Style Guide Editor")

# --- Session state ---
if 'edit_rule' not in st.session_state:
    st.session_state['edit_rule'] = None
if 'edit_type' not in st.session_state:
    st.session_state['edit_type'] = None
if 'edit_idx' not in st.session_state:
    st.session_state['edit_idx'] = None

rules_data = load_rules()

# --- Function to start editing a rule ---
def start_edit(rule_type, idx):
    st.session_state['edit_rule'] = rules_data[rule_type][idx]
    st.session_state['edit_type'] = rule_type
    st.session_state['edit_idx'] = idx

# --- Display Existing Rules ---
st.subheader("📋 Existing Rules")

for rule_type in ["terminology","flag_only"]:
    rules = rules_data.get(rule_type, [])
    if not rules:
        st.write(f"_No {rule_type} rules yet._")
        continue
    st.markdown(f"### {rule_type.capitalize()}")
    for idx, r in enumerate(rules):
        color = severity_colors.get(r.get("severity","warning"), "black")
        with st.expander(f"{r['match']} [{r.get('severity','warning').upper()}]"):
            st.markdown(f"<span style='color:{color}'><b>Severity:</b> {r.get('severity','warning').upper()}</span>", unsafe_allow_html=True)
            st.markdown(f"**Match:** {r['match']}")
            if "replace_with" in r:
                st.markdown(f"**Replacement:** {r['replace_with']}")
            st.markdown(f"**Message:** {r.get('message','')}")
            col1, col2 = st.columns([1,1])
            with col1:
                if st.button("✏️ Edit", key=f"edit_{rule_type}_{idx}"):
                    start_edit(rule_type, idx)
            with col2:
                if st.button("🗑️ Delete", key=f"del_{rule_type}_{idx}"):
                    rules.pop(idx)
                    save_rules(rules_data)
                    st.success("🗑️ Rule deleted")

# --- Form to Add or Edit Rule ---
st.subheader("➕ Add / Edit Rule")

# Pre-fill form fields if editing
match_text = st.session_state['edit_rule']['match'] if st.session_state['edit_rule'] else ""
replacement = st.session_state['edit_rule'].get('replace_with','') if st.session_state['edit_rule'] else ""
severity = st.session_state['edit_rule'].get('severity','warning') if st.session_state['edit_rule'] else "warning"
message = st.session_state['edit_rule'].get('message','') if st.session_state['edit_rule'] else ""
rule_type = st.session_state['edit_type'] if st.session_state['edit_rule'] else "terminology"

with st.form("rule_form"):
    rule_type = st.selectbox("Rule Type", ["terminology","flag_only"], index=["terminology","flag_only"].index(rule_type))
    match_text = st.text_input("Match word/phrase", value=match_text)
    replacement = st.text_input("Suggested replacement (optional)", value=replacement)
    severity = st.selectbox("Severity", ["advice","warning","error"], index=["advice","warning","error"].index(severity))
    message = st.text_area("Message to display", value=message)

    submitted = st.form_submit_button("Save Rule")
    if submitted:
        new_rule = {
            "match": match_text.strip(),
            "message": message.strip(),
            "severity": severity
        }
        if replacement.strip():
            new_rule["replace_with"] = replacement.strip()

        if st.session_state['edit_rule']:
            # Update existing
            idx = st.session_state['edit_idx']
            rules_data[rule_type][idx] = new_rule
            st.success("✅ Rule updated!")
            st.session_state['edit_rule'] = None
            st.session_state['edit_type'] = None
            st.session_state['edit_idx'] = None
        else:
            # Add new
            rules_data[rule_type].append(new_rule)
            st.success(f"✅ Rule added to {rule_type}!")

        save_rules(rules_data)
        st.experimental_rerun = lambda: None  # completely remove old experimental rerun

