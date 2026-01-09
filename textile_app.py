
import os
import streamlit as st
import json
from pathlib import Path
import tempfile
from collections import defaultdict
import re
from docx import Document
from docx.shared import RGBColor
import gspread
from google.oauth2.service_account import Credentials
import time
import io
import csv

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
# GOOGLE SHEETS CONFIG
# -------------------------
# Dev/Prod sheet switcher (Point 3)
# - Set ENV=prod and SHEET_ID_PROD="..." in Streamlit Cloud (Secrets/Env)
# - Locally, you can set SHEET_ID_DEV="..." or rely on the hardcoded URL below.
ENV = os.getenv("ENV", "dev").lower()
SHEET_ID_DEV = os.getenv("SHEET_ID_DEV")
SHEET_ID_PROD = os.getenv("SHEET_ID_PROD")

# Fall back to your original URL if env vars are not set
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1lLoWDMJ36X5cyd9Ysz5Lmkxc9WBZfwqSQQS2_EN9uHM"
SHEET_NAME = "Sheet1"

def build_sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}"

if ENV == "prod" and SHEET_ID_PROD:
    SHEET_URL = build_sheet_url(SHEET_ID_PROD)
elif SHEET_ID_DEV:
    SHEET_URL = build_sheet_url(SHEET_ID_DEV)
else:
    SHEET_URL = DEFAULT_SHEET_URL  # uses your original hardcoded URL

# Include Drive scope for robustness with gspread
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# -------------------------
# CREDENTIAL LOADER
# -------------------------
def _load_service_account_info() -> dict | None:
    """
    Load service account credentials from:
      1) Streamlit secrets (preferred in Cloud)
      2) GOOGLE_APPLICATION_CREDENTIALS env var (portable)
      3) Local JSON file fallback: ./service_account.json
    Returns a dict or None if not found/invalid.
    """
    # 1️⃣ Streamlit secrets (Cloud). Expect a TOML section: [gcp_service_account]
    try:
        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            sa = st.secrets["gcp_service_account"]
            if isinstance(sa, dict):
                return sa
            if isinstance(sa, str) and sa.strip():
                try:
                    return json.loads(sa)
                except Exception:
                    st.warning("Secret 'gcp_service_account' is a string but not valid JSON.")
    except Exception as e:
        st.warning(f"Failed reading Streamlit secrets: {e}")

    # 2️⃣ Local env var (portable)
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and Path(env_path).exists():
        try:
            return json.loads(Path(env_path).read_text(encoding="utf-8"))
        except Exception as e:
            st.warning(f"Env credential JSON exists but could not be parsed: {e}")

    # 3️⃣ Local file fallback for VS Code/dev
    local_json = REPO_ROOT / "service_account.json"
    if local_json.exists():
        try:
            return json.loads(local_json.read_text(encoding="utf-8"))
        except Exception as e:
            st.warning(f"Local credential JSON exists but could not be parsed: {e}")

    return None

def get_gsheet():
    """
    Authorize gspread and return the worksheet object.
    Returns None if credentials are not available or auth fails.
    """
    try:
        creds_dict = _load_service_account_info()
        if not isinstance(creds_dict, dict):
            st.warning("Google Sheet credentials not a dict. Loading rules from local JSON only.")
            return None

        # Quick validation: ensure required keys exist
        required_keys = {"type", "private_key", "client_email"}
        missing = required_keys - set(creds_dict.keys())
        if missing:
            st.warning(f"Missing keys in service account credentials: {missing}. Falling back to local JSON only.")
            return None

        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)

        # Prefer open_by_url for your current config
        sheet = client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)
        st.success(f"Google Sheet loaded successfully ✅ (ENV={ENV})")
        return sheet

    except Exception as e:
        st.warning(f"Could not load Google Sheet: {e}\nRules will be loaded from local JSON only.")
        return None

# -------------------------
# RETRY/BACKOFF HELPERS (Point 6)
# -------------------------
def with_retry(fn, attempts: int = 3, delay: float = 0.8):
    """
    Execute fn() with simple exponential backoff.
    Raises the last exception if all attempts fail.
    """
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(delay * (2 ** i))

# -------------------------
# SHEET READ/WRITE HELPERS
# -------------------------
def save_rules_to_sheet(rules: dict):
    sheet = get_gsheet()
    if not sheet:
        return
    # Prepare rows (header + data)
    rows = [["Category", "Match", "Replacement", "Message", "Case Sensitive"]]
    for cat in ["style_guide_rule", "style_guide_caution"]:
        for r in rules.get(cat, []):
            rows.append([
                cat,
                r.get("match", ""),
                r.get("replace_with") or "",
                r.get("message", ""),
                bool(r.get("case_sensitive", False)),
            ])
    try:
        with_retry(lambda: sheet.clear())
        # Explicitly write starting at A1, using RAW to preserve values
        with_retry(lambda: sheet.update("A1", rows, value_input_option="RAW"))
    except Exception as e:
        st.warning(f"Failed to write rules to Google Sheet: {e}")

def load_rules_from_sheet() -> dict | None:
    sheet = get_gsheet()
    if not sheet:
        return None
    try:
        records = sheet.get_all_records()  # Assumes first row is the header
        if not records:
            return None
        rules = {"style_guide_rule": [], "style_guide_caution": []}
        for r in records:
            cat = r.get("Category", "")
            if cat not in rules:
                continue
            rules[cat].append({
                "match": r.get("Match", ""),
                "replace_with": r.get("Replacement") or None,
                "message": r.get("Message", ""),
                "case_sensitive": bool(r.get("Case Sensitive", False)),
            })
        return rules
    except Exception as e:
        st.warning(f"Could not load rules from Google Sheet: {e}")
        return None

# -------------------------
# LOCAL JSON RULE HELPERS
# -------------------------
def load_rules() -> dict:
    if RULES_FILE.exists():
        data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    else:
        data = {"style_guide_rule": [], "style_guide_caution": []}

    # Normalize old keys if present
    if "terminology" in data:
        data["style_guide_rule"].extend(data["terminology"])
        del data["terminology"]
    if "flag_only" in data:
        data["style_guide_caution"].extend(data["flag_only"])
        del data["flag_only"]

    for cat in ["style_guide_rule", "style_guide_caution"]:
        for r in data.get(cat, []):
            r.setdefault("match", "")
            r.setdefault("replace_with", None)
            r.setdefault("message", "")
            r.setdefault("case_sensitive", False)
        data.setdefault(cat, [])

    return data

def save_rules(rules: dict):
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    RULES_FILE.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")
    save_rules_to_sheet(rules)

# -------------------------
# STREAMLIT SESSION STATE INIT
# -------------------------
if "rules" not in st.session_state:
    sheet_rules = load_rules_from_sheet()
    if sheet_rules:
        st.session_state.rules = sheet_rules
    else:
        st.session_state.rules = load_rules()

# -------------------------
# CAPITALIZATION & SEVERITY
# -------------------------
CAPITALIZATION_RULES = {
    "indigenous people": "Indigenous People",
    "first nations": "First Nations",
}

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

# -------------------------
# RULE DISPLAY & DOC ANALYSIS
# -------------------------
def display_rules(section_name: str):
    st.subheader(section_name.replace("_", " ").title())
    rules_data = st.session_state.rules
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
                st.session_state.rules[section_name].pop(idx)
                save_rules(st.session_state.rules)
                st.rerun()

def analyze_doc(path: str):
    doc = Document(path)
    results = []
    rules = []

    for cat in ["style_guide_rule", "style_guide_caution"]:
        for r in st.session_state.rules.get(cat, []):
            rules.append({
                "pattern": r.get("match", ""),
                "message": r.get("message", ""),
                "replace_with": r.get("replace_with"),
                "case_sensitive": r.get("case_sensitive", False),
                "rule_type": cat,
            })

    # Add capitalization rules as cautions
    for phrase, correct in CAPITALIZATION_RULES.items():
        rules.append({
            "pattern": phrase,
            "message": f"Should be capitalized: '{correct}'",
            "replace_with": correct,
            "case_sensitive": False,
            "rule_type": "style_guide_caution",
        })

    for p_idx, para in enumerate(doc.paragraphs, start=1):
        text = para.text
        if not text.strip():
            continue

        # Map character positions to the corresponding run to color later
        char_to_run = {}
        pos = 0
        for run in para.runs:
            for _ in run.text:
                char_to_run[pos] = run
                pos += 1

        applied = set()
        for rule in rules:
            flags = 0 if rule["case_sensitive"] else re.IGNORECASE
            for m in re.finditer(rf"\b{re.escape(rule['pattern'])}\b", text, flags):
                s, e = m.start(), m.end()
                if any(i in applied for i in range(s, e)):
                    continue
                for i in range(s, e):
                    char_to_run[i].font.color.rgb = SEVERITY_COLOR.get(rule["rule_type"], RGBColor(255, 0, 0))
                    applied.add(i)
                results.append({
                    "match": m.group(),
                    "rule_category": rule["rule_type"],
                    "message": rule["message"],
                    "suggested_replacement": rule.get("replace_with"),
                    "paragraph_index": p_idx,
                    "char_index": s + 1,
                    "context": text,
                })
    return doc, results

# -------------------------
# STREAMLIT UI
# -------------------------
st.set_page_config(page_title="Textile Exchange Rules + Checker", layout="wide")
st.title("📘 Textile Exchange Style Guide")

# 🔧 Diagnostics (Point 5)
with st.expander("Connection diagnostics"):
    try:
        # Try to connect and read header row
        sheet = get_gsheet()
        if sheet:
            hdr = sheet.row_values(1)
            st.write("Header row:", hdr)

            # Explicit read/write test button
            if st.button("🔌 Test Google Sheets read/write"):
                try:
                    # Read current A1, write a temp value, then revert
                    original = sheet.cell(1, 1).value
                    with_retry(lambda: sheet.update_cell(1, 1, "Category"))
                    with_retry(lambda: sheet.update_cell(1, 1, original if original is not None else "Category"))
                    st.success("Read & write test passed ✅")
                except Exception as e:
                    st.error(f"Read/write test failed: {e}")
    except Exception as e:
        st.error(f"Diagnostics failed: {e}")

tab_rules, tab_check = st.tabs(["📋 Edit Rules", "📄 Style Checker"])

# Rule editor
with tab_rules:
    with st.form("add_rule"):
        section = st.selectbox(
            "Category",
            ["style_guide_rule", "style_guide_caution"],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        match = st.text_input("Match")
        replacement = st.text_input("Replacement (optional)")
        message = st.text_input("Message")
        submitted = st.form_submit_button("Add rule")
        if submitted and match and message:
            st.session_state.rules[section].insert(0, {
                "match": match,
                "replace_with": replacement or None,
                "message": message,
                "case_sensitive": False,
            })
            save_rules(st.session_state.rules)
            st.rerun()
    display_rules("style_guide_rule")
    display_rules("style_guide_caution")

    # CSV backup download (Point 4)
    st.subheader("⬇️ Backup rules to CSV")
    if st.button("Download CSV backup"):
        sheet = get_gsheet()
        if sheet:
            try:
                values = sheet.get_all_values()
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                writer.writerows(values)
                st.download_button(
                    "Download rules_backup.csv",
                    data=buffer.getvalue(),
                    file_name="rules_backup.csv",
                    mime="text/csv",
                    key="download_rules_csv",
                )
            except Exception as e:
                st.error(f"Failed to generate CSV backup: {e}")
        else:
            st.warning("Google Sheet not available. Connect first or check credentials.")

# Style checker
with tab_check:
    uploaded = st.file_uploader("Upload Word document", type=["docx"])
    if uploaded and st.button("▶️ Run style check"):
        # Read uploaded bytes once
        file_bytes = uploaded.read()

        # Use a temp file for analysis (python-docx needs a path or file-like)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file_bytes)
            path = tmp.name

        doc, results = analyze_doc(path)

        # ✅ Save to in-memory bytes for download, with correct MIME
        doc_buffer = io.BytesIO()
        doc.save(doc_buffer)
        doc_buffer.seek(0)

        st.download_button(
            "⬇️ Download highlighted document",
            data=doc_buffer.getvalue(),
            file_name="Textile_Exchange_Style_Checked.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_checked_docx",
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