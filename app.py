import streamlit as st
from checker.run import analyze_doc
import tempfile
from collections import defaultdict
import os

# -------------------------
# PAGE CONFIG
# -------------------------
st.set_page_config(
    page_title="Textile Exchange Style Checker",
    layout="wide"
)

st.title("📘 Textile Exchange Style Checker")

st.caption(
    "Upload a Word document to check it against the Textile Exchange style guide. "
    "Style guide rules and cautions are highlighted in the document and explained below."
)

# -------------------------
# UI LABEL MAPPING
# -------------------------
SEVERITY_LABELS = {
    "style guide rule": "Style guide rule",
    "style guide caution": "Style guide caution"
}

SEVERITY_ICONS = {
    "style guide rule": "🟥",   # red
    "style guide caution": "🟧" # orange
}

# -------------------------
# FILE UPLOAD
# -------------------------
uploaded_file = st.file_uploader(
    "Upload a Word document (.docx)",
    type=["docx"]
)

# -------------------------
# RUN CHECK
# -------------------------
if uploaded_file:
    if st.button("▶️ Run style check"):
        with st.spinner("Checking document..."):
            # Save uploaded file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(uploaded_file.read())
                temp_path = tmp.name

            # Analyze document (highlight only, no replacements)
            doc, results = analyze_doc(temp_path)

            # Save highlighted Word file
            output_path = temp_path.replace(".docx", "_highlighted.docx")
            doc.save(output_path)

        st.success("✅ Check complete")

        # -------------------------
        # DOWNLOAD
        # -------------------------
        st.download_button(
            "⬇️ Download highlighted Word document",
            data=open(output_path, "rb"),
            file_name="Textile_Exchange_Style_Checked.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        # -------------------------
        # DISPLAY ISSUES
        # -------------------------
        st.subheader("📋 Style guide issues found")

        if not results:
            st.success("No style guide issues found 🎉")
        else:
            # Group by paragraph
            para_results = defaultdict(list)
            for r in results:
                para_results[r["paragraph_index"]].append(r)

            for para_idx in sorted(para_results.keys()):
                para_items = para_results[para_idx]

                context_text = (
                    para_items[0]["context"]
                    .replace("\n", " ")
                    .replace("\r", " ")
                )
                st.markdown(f"**Paragraph {para_idx} context:** {context_text}")

                for r in para_items:
                    # Collapse ALL CAPS sentence warnings to one per paragraph
                    if r["match"] == "ALL CAPS sentence":
                        if any(
                            prev is not r and prev["match"] == "ALL CAPS sentence"
                            for prev in para_items
                        ):
                            continue

                    # Map rule type to proper label/icon
                    rule_category = r.get("rule_category", "style guide rule").lower()
                    icon = SEVERITY_ICONS.get(rule_category, "🟥")
                    label = SEVERITY_LABELS.get(rule_category, "Style guide rule")

                    reasoning = (r.get("message") or "").replace("_", "\\_").replace("*", "\\*")
                    location = f"Paragraph {r['paragraph_index']}, Character {r['char_index']}"

                    st.markdown(
                        f"""
{icon} **{label}**

**Issue:** {r['match']}  
**Explanation:** {reasoning}  
**Location:** {location}
"""
                    )

                st.markdown("---")

        # -------------------------
        # CLEANUP
        # -------------------------
        try:
            os.remove(temp_path)
        except Exception:
            pass
