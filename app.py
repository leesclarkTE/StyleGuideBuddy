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
    "Upload a Word document to check it against the Textile Exchange style rules. "
    "Errors, warnings, and advice are highlighted in the document and explained below."
)

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
            # Save uploaded file to temp location
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(uploaded_file.read())
                temp_path = tmp.name

            # Run analysis (rules pulled from JSON inside analyze_doc)
            doc, results = analyze_doc(temp_path)

            # Save corrected Word file
            output_path = temp_path.replace(".docx", "_checked.docx")
            doc.save(output_path)

        st.success("✅ Check complete")

        # -------------------------
        # DOWNLOAD
        # -------------------------
        st.download_button(
            "⬇️ Download corrected Word document",
            data=open(output_path, "rb"),
            file_name="Textile_Exchange_Checked.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        # -------------------------
        # RESULTS
        # -------------------------
        st.subheader("📋 Issues found")

        if not results:
            st.success("No issues found 🎉")
        else:
            # Group issues by paragraph
            para_results = defaultdict(list)
            for r in results:
                para_results[r["paragraph_index"]].append(r)

            for para_idx in sorted(para_results.keys()):
                para_items = para_results[para_idx]

                # Clean, compact context (no large fonts, no markdown tricks)
                context_text = (
                    para_items[0]["context"]
                    .replace("\n", " ")
                    .replace("\r", " ")
                )

                snippet = context_text[:160]
                if len(context_text) > 160:
                    snippet += "…"

                st.markdown(f"**Paragraph {para_idx} context:** {snippet}")

                # -------------------------
                # Display issues
                # -------------------------
                for r in para_items:
                    # Collapse ALL CAPS sentence warnings to one per paragraph
                    if r["match"] == "ALL CAPS sentence":
                        if any(
                            prev is not r and prev["match"] == "ALL CAPS sentence"
                            for prev in para_items
                        ):
                            continue

                    icon = {
                        "advice": "🟨",
                        "warning": "🟧",
                        "error": "🟥"
                    }.get(r["severity"], "🟦")

                    reasoning = (r.get("message") or "").replace("_", "\\_").replace("*", "\\*")
                    suggestion = (
                        r.get("suggested_replacement") or "—"
                    ).replace("_", "\\_").replace("*", "\\*")

                    location = f"Paragraph {r['paragraph_index']}, Character {r['char_index']}"

                    st.markdown(
                        f"""
{icon} **{r['match']} ({r['severity'].upper()})**

**Reasoning:** {reasoning}  
**Suggestion:** {suggestion}  
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
