
import json
import re
import html
import io
from pathlib import Path
from string import Template
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components
from docx import Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl

# --- Google Sheets deps ---
try:
    import gspread
    from google.oauth2.service_account import Credentials
    from gspread.exceptions import WorksheetNotFound
except Exception:
    gspread = None
    Credentials = None
    WorksheetNotFound = Exception

# ===========================
# PAGE CONFIG
# ===========================
st.set_page_config(page_title="Textile Exchange Style Guide Buddy", layout="wide")
st.title("📘 Textile Exchange Style Guide Buddy")

# ===========================
# RULES STORAGE (SHEETS or LOCAL)
# ===========================
RULES_FILE = Path("Rules/Textile_Exchange_Style_Guide_STRICT.json")

def _has_service_account_in_secrets() -> bool:
    try:
        if "google_service_account_json" in st.secrets:
            return True
        if "google_service_account" in st.secrets:
            return True
        root = st.secrets
        return (
            isinstance(root.get("type"), str)
            and root.get("type") == "service_account"
            and isinstance(root.get("client_email"), str)
            and isinstance(root.get("private_key"), str)
        )
    except Exception:
        return False

SHEETS_ENABLED = (
    gspread is not None
    and _has_service_account_in_secrets()
    and "gsheets" in st.secrets
    and "SPREADSHEET_ID" in st.secrets["gsheets"]
)

# ---- Local JSON fallback ----
def load_rules_local():
    if RULES_FILE.exists():
        data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
        data.setdefault("style_guide_rule", [])
        data.setdefault("style_guide_caution", [])
        return data
    return {"style_guide_rule": [], "style_guide_caution": []}

def save_rules_local(rules):
    RULES_FILE.parent.mkdir(exist_ok=True, parents=True)
    RULES_FILE.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")

# ---- Google Sheets backend ----
GS_EXPECTED_COLS = ["category", "match", "replace_with", "message", "case_sensitive", "updated_at"]

def _sa_info_from_secrets() -> dict:
    if "google_service_account_json" in st.secrets:
        raw = st.secrets["google_service_account_json"]
        sa_info = json.loads(raw)
    elif "google_service_account" in st.secrets:
        sa_info = dict(st.secrets["google_service_account"])
    else:
        sa_info = dict(st.secrets)

    pk = sa_info.get("private_key", "")
    if "BEGIN PRIVATE KEY" in pk:
        sa_info["private_key"] = pk.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    return sa_info

def _validate_private_key_pem(pem: str):
    if not pem or "BEGIN PRIVATE KEY" not in pem or "END PRIVATE KEY" not in pem:
        raise ValueError("Private key is missing BEGIN/END PRIVATE KEY markers.")
    lines = [ln.strip() for ln in pem.splitlines()]
    body = "".join(ln for ln in lines if ln and not ln.startswith("-----"))
    import base64, binascii
    try:
        base64.b64decode(body, validate=True)
    except binascii.Error as e:
        raise ValueError(f"Private key Base64 decoding failed (likely newline/quoting issue): {e}") from e

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    try:
        sa_info = _sa_info_from_secrets()
        _validate_private_key_pem(sa_info.get("private_key", ""))
        creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    except Exception as e:
        st.error(
            "Failed to create Google credentials. "
            "Double-check your secrets (prefer `google_service_account_json`).\n\n"
            f"Details: {type(e).__name__}: {e}"
        )
        raise
    return gspread.authorize(creds)

@st.cache_resource(show_spinner=False)
def get_or_create_worksheet():
    gc = get_gspread_client()
    sh = gc.open_by_key(st.secrets["gsheets"]["SPREADSHEET_ID"])
    ws_name = st.secrets["gsheets"].get("WORKSHEET_NAME", "rules")
    try:
        ws = sh.worksheet(ws_name)
    except WorksheetNotFound:
        ws = sh.add_worksheet(title=ws_name, rows=100, cols=10)
        ws.update("A1", [GS_EXPECTED_COLS])
    return ws

@st.cache_data(ttl=60, show_spinner=False)
def load_rules_sheets():
    ws = get_or_create_worksheet()
    records = ws.get_all_records()
    out = {"style_guide_rule": [], "style_guide_caution": []}
    for r in records:
        cat = (r.get("category") or "").strip()
        if cat not in ("style_guide_rule", "style_guide_caution"):
            continue
        item = {
            "match": r.get("match") or "",
            "replace_with": r.get("replace_with") or None,
            "message": r.get("message") or "",
            "case_sensitive": bool(r.get("case_sensitive")) if r.get("case_sensitive") not in (None, "") else False,
        }
        out[cat].append(item)
    return out

def save_rules_sheets(rules: dict):
    ws = get_or_create_worksheet()
    rows = []
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for cat in ("style_guide_rule", "style_guide_caution"):
        for r in rules.get(cat, []):
            rows.append([
                cat,
                r.get("match") or "",
                r.get("replace_with") or "",
                r.get("message") or "",
                bool(r.get("case_sensitive", False)),
                now,
            ])
    values = [GS_EXPECTED_COLS] + rows
    ws.clear()
    ws.update("A1", values)
    try:
        load_rules_sheets.clear()
    except Exception:
        pass

def load_rules():
    if SHEETS_ENABLED:
        try:
            return load_rules_sheets()
        except Exception:
            st.warning("Google Sheets unavailable or misconfigured. Falling back to local JSON.")
            return load_rules_local()
    return load_rules_local()

def save_rules(rules: dict):
    if SHEETS_ENABLED:
        try:
            save_rules_sheets(rules)
            return
        except Exception:
            st.warning("Could not save to Google Sheets. Saved to local JSON instead.")
    save_rules_local(rules)

# ===========================
# SESSION STATE
# ===========================
if "rules" not in st.session_state:
    st.session_state.rules = load_rules()
if "edit_rule" not in st.session_state:
    st.session_state.edit_rule = None

# ===========================
# INLINE CHECKER
# ===========================
HIGHLIGHT_STYLE = {
    "style_guide_rule": "border-bottom:2px solid #ff4d4d;",
    "style_guide_caution": "border-bottom:2px solid #ffcc00;",
}

def flatten_rules():
    out = []
    for cat in ("style_guide_rule", "style_guide_caution"):
        for r in st.session_state.rules.get(cat, []):
            if r.get("match"):
                out.append({**r, "category": cat})
    return out

def find_matches(text, rules, location, prefix):
    matches = []
    for rule in rules:
        word = rule.get("match")
        if not word:
            continue
        flags = 0 if rule.get("case_sensitive") else re.IGNORECASE
        pattern = rf"\b{re.escape(word)}\b"
        for m in re.finditer(pattern, text, flags):
            matches.append({
                "start": m.start(),
                "end": m.end(),
                "issue": m.group(),
                "replacement": rule.get("replace_with"),
                "explanation": rule.get("message"),
                "category": rule["category"],
                "location": location,
            })
    matches.sort(key=lambda x: (x["start"], x["end"]))
    for i, m in enumerate(matches, 1):
        m["anchor"] = f"{prefix}_m{i}"
    return matches

def render_text(text, matches):
    if not matches:
        return html.escape(text)
    out, last = [], 0
    for m in matches:
        if m["start"] < last:
            continue
        out.append(html.escape(text[last:m["start"]]))
        tooltip = html.escape(
            f"Issue: {m['issue']}\n"
            f"Replacement: {m['replacement'] or '—'}\n"
            f"{m['explanation']}"
        )
        out.append(
            f'<span id="{m["anchor"]}" '
            f'style="{HIGHLIGHT_STYLE[m["category"]]}" '
            f'title="{tooltip}">'
            f'{html.escape(text[m["start"]:m["end"]])}'
            f'</span>'
        )
        last = m["end"]
    out.append(html.escape(text[last:]))
    return "".join(out)

def iter_blocks(doc):
    p_i = t_i = 0
    for el in doc.element.body.iterchildren():
        if isinstance(el, CT_P):
            yield "p", doc.paragraphs[p_i]
            p_i += 1
        elif isinstance(el, CT_Tbl):
            yield "tbl", doc.tables[t_i]
            t_i += 1

def analyze_inline(file_bytes):
    doc = Document(io.BytesIO(file_bytes))
    rules = flatten_rules()
    left_parts, issues = [], []

    para_i = tbl_i = 0
    for kind, block in iter_blocks(doc):
        if kind == "p":
            para_i += 1
            text = block.text or ""
            loc = f"Paragraph {para_i}"
            matches = find_matches(text, rules, loc, f"p{para_i}")
            issues.extend(matches)
            left_parts.append(f"<p>{render_text(text, matches) or '&nbsp;'}</p>")
        else:
            tbl_i += 1
            rows_html = []
            for r, row in enumerate(block.rows, 1):
                cells = []
                for c, cell in enumerate(row.cells, 1):
                    text = cell.text or ""
                    loc = f"Table {tbl_i}, row {r}, col {c}"
                    matches = find_matches(text, rules, loc, f"t{tbl_i}_{r}_{c}")
                    issues.extend(matches)
                    cells.append(f"<td>{render_text(text, matches) or '&nbsp;'}</td>")
                rows_html.append(f"<tr>{''.join(cells)}</tr>")
            left_parts.append(
                f"<table class='doc-table'><tbody>{''.join(rows_html)}</tbody></table>"
            )

    left_html = "".join(left_parts) or "<p>&nbsp;</p>"

    right_items = []
    for i in issues:
        color = "#ff4d4d" if i["category"] == "style_guide_rule" else "#ffcc00"
        card_html = (
            f"<a href=\"#{i['anchor']}\" class=\"issue-card\" data-anchor=\"{i['anchor']}\" "
            f"style=\"border-left:4px solid {color}\">"
            f"<div class=\"term\"><strong>{html.escape(i['issue'])}</strong></div>"
            f"<div><em>Replacement:</em> {html.escape(i['replacement'] or '—')}</div>"
            f"<div>{html.escape(i['explanation'])}</div>"
            f"<div class=\"loc\">{html.escape(i['location'])}</div>"
            f"</a>"
        )
        right_items.append(card_html)

    right_html = "".join(right_items) or "<div class='no-issues'>No issues found 🎉</div>"

    PAGE_TMPL = Template("""
    <style>
      html { scroll-behavior:smooth; }
      .wrap { display:grid; grid-template-columns:1fr 420px; gap:20px; }
      .doc, .issues {
        height:650px; overflow:auto; border:1px solid #e6e6e6;
        padding:16px; border-radius:8px; background:#fff;
      }
      .issues { background:#fafafa; }
      .issue-card {
        display:block; text-decoration:none; color:#000;
        background:#fff; border:1px solid #eee;
        border-radius:6px; padding:10px; margin-bottom:10px;
      }
      .doc-table td { border:1px solid #eee; padding:8px 10px; }
      @keyframes flashBg {
        0% { background:#ffe8a0; }
        100% { background:transparent; }
      }
      .flash { animation: flashBg 1.2s ease-out; }
    </style>

    <div class="wrap">
      <div class="doc" id="doc-pane">
        $left_html
      </div>
      <div class="issues">
        <h4>Issues</h4>
        $right_html
      </div>
    </div>

    <script>
    (function(){
      const docPane = document.getElementById("doc-pane");

      function offsetTop(el, ancestor){
        let top = 0;
        while (el && el !== ancestor){
          top += el.offsetTop;
          el = el.offsetParent;
        }
        return top;
      }

      function flash(el){
        el.classList.remove("flash");
        void el.offsetWidth;
        el.classList.add("flash");
      }

      document.querySelectorAll(".issue-card").forEach(card => {
        card.addEventListener("click", e => {
          e.preventDefault();
          const id = card.dataset.anchor;
          const target = document.getElementById(id);
          if (!target || !docPane) return;
          docPane.scrollTo({ top: offsetTop(target, docPane) - 12, behavior:"smooth" });
          flash(target);
        });
      });
    })();
    </script>
    """)

    full_html = PAGE_TMPL.substitute(left_html=left_html, right_html=right_html)
    return full_html, issues

# ===========================
# TABS
# ===========================
tab_check, tab_rules = st.tabs(["📄 Style Checker", "📋 Add/Edit Rules"])

with tab_check:
    uploaded = st.file_uploader("Upload Word document (.docx)", type=["docx"])
    if uploaded:
        page_html, issues = analyze_inline(uploaded.read())
        components.html(page_html, height=720, scrolling=True)

        st.subheader("🧾 Summary Table")
        st.dataframe(
            [
                {
                    "issue": i["issue"],
                    "replacement": i["replacement"] or "—",
                    "explanation": i["explanation"],
                    "location": i["location"],
                }
                for i in issues
            ],
            use_container_width=True,
        )

with tab_rules:
    if SHEETS_ENABLED:
        st.success("Using Google Sheets as the source of truth for rules.")
        local_has_data = any(load_rules_local().values())
        sheets_has_data = False
        try:
            _s = load_rules_sheets()
            sheets_has_data = any(_s.values())
        except Exception:
            sheets_has_data = False

        if local_has_data and not sheets_has_data:
            with st.expander("Migrate local JSON rules to Google Sheets"):
                if st.button("🚚 Migrate now"):
                    save_rules_sheets(load_rules_local())
                    st.toast("Migration complete. Reloading from Google Sheets...")
                    try:
                        load_rules_sheets.clear()
                    except Exception:
                        pass
                    st.session_state.rules = load_rules()
                    st.rerun()
    else:
        st.info("Using local JSON file for rules (Google Sheets not configured).")

    st.subheader("➕ Add New Rule")

    with st.form("add_rule"):
        category = st.selectbox(
            "Category",
            ["style_guide_rule", "style_guide_caution"],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        match = st.text_input("Word or phrase to flag")
        replacement = st.text_input("Suggested replacement (optional)")
        message = st.text_input("Explanation shown to users")
        case_sensitive = st.checkbox("Case sensitive match", value=False)

        submitted = st.form_submit_button("Add rule")

        if submitted and match and message:
            st.session_state.rules.setdefault(category, []).insert(
                0,
                {
                    "match": match,
                    "replace_with": replacement or None,
                    "message": message,
                    "case_sensitive": case_sensitive,
                },
            )
            save_rules(st.session_state.rules)
            st.success("Rule added successfully.")
            st.rerun()

    st.divider()
    st.subheader("📋 Existing Rules")

    for cat in ("style_guide_rule", "style_guide_caution"):
        st.markdown(f"### {cat.replace('_', ' ').title()}")

        rules_list = st.session_state.rules.get(cat, [])
        if not rules_list:
            st.info("No rules in this category yet.")
            continue

        for idx, rule in enumerate(rules_list):
            cols = st.columns([5, 2, 1])

            with cols[0]:
                if st.session_state.edit_rule == (cat, idx):
                    new_match = st.text_input("Match", rule["match"], key=f"edit_match_{cat}_{idx}")
                    new_repl = st.text_input("Replacement", rule.get("replace_with") or "", key=f"edit_repl_{cat}_{idx}")
                    new_msg = st.text_input("Message", rule["message"], key=f"edit_msg_{cat}_{idx}")
                    new_cs = st.checkbox(
                        "Case sensitive",
                        value=bool(rule.get("case_sensitive", False)),
                        key=f"edit_cs_{cat}_{idx}",
                    )
                else:
                    st.markdown(
                        f"**Match:** `{rule['match']}`  \n"
                        f"**Replacement:** {rule.get('replace_with') or '—'}  \n"
                        f"**Message:** {rule['message']}  \n"
                        f"**Case sensitive:** {bool(rule.get('case_sensitive', False))}"
                    )


            with cols[1]:
                if st.session_state.edit_rule == (cat, idx):
                    if st.button("💾 Save", key=f"save_{cat}_{idx}"):
                        # Persist edits
                        rule["match"] = new_match
                        rule["replace_with"] = new_repl or None
                        rule["message"] = new_msg
                        rule["case_sensitive"] = bool(new_cs)
                        save_rules(st.session_state.rules)
                        st.session_state.edit_rule = None
                        st.rerun()

                    if st.button("✖ Cancel", key=f"cancel_{cat}_{idx}"):
                        st.session_state.edit_rule = None
                        st.rerun()
                else:
                    if st.button("✏ Edit", key=f"edit_{cat}_{idx}"):
                        st.session_state.edit_rule = (cat, idx)
                        st.rerun()

            with cols[2]:
                if st.button("🗑 Delete", key=f"delete_{cat}_{idx}"):
                    st.session_state.rules[cat].pop(idx)
                    save_rules(st.session_state.rules)
                    st.rerun()
