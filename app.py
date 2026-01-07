import streamlit as st
from checker.run import analyze_doc
import tempfile
from collections import defaultdict

st.set_page_config(page_title="Textile Exchange Style Checker")
st.title("📘 Textile Exchange Style Checker")

uploaded_file = st.file_uploader("Upload a Word document (.docx)", type=["docx"])

if uploaded_file:
    if st.button("Run style check"):
        with st.spinner("Checking document..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(uploaded_file.read())
                temp_path = tmp.name

            doc, results = analyze_doc(temp_path)

            # Save corrected Word file
            output_path = temp_path.replace(".docx", "_checked.docx")
            doc.save(output_path)

        st.success("✅ Check complete")

        st.download_button(
            "⬇️ Download corrected Word document",
            open(output_path, "rb"),
            file_name="Textile_Exchange_Checked.docx"
        )

        st.subheader("📋 Issues found")

        if not results:
            st.success("No issues found 🎉")

        # Group results by paragraph
        para_results = defaultdict(list)
        for r in results:
            para_results[r['paragraph_index']].append(r)

        for para_idx in sorted(para_results.keys()):
            para_items = para_results[para_idx]
            context_text = para_items[0]['context'].replace("\n", " ").replace("\r", " ")

            # Highlight all flagged words in paragraph context
            snippet = context_text
            for r in para_items:
                snippet = snippet.replace(r['match'], f"**{r['match']}**")

            # Truncate if very long
            MAX_SNIPPET = 100
            if len(snippet) > MAX_SNIPPET:
                snippet = snippet[:MAX_SNIPPET] + "..."

            st.markdown(f"**Paragraph {para_idx} context:** {snippet}\n")

            for r in para_items:
                icon = {
                    "advice": "🟨",
                    "warning": "🟧",
                    "error": "🟥"
                }.get(r["severity"], "🟦")

                reasoning = r['message'].replace("_", "\\_").replace("*", "\\*")
                suggestion = (r.get('suggested_replacement') or "").replace("_", "\\_").replace("*", "\\*")
                location = f"Paragraph {r['paragraph_index']}, Character {r['char_index']}"

                st.markdown(f"""{icon} **{r['match']} ({r['severity'].upper()})**  

**Reasoning:** {reasoning}  
**Suggestion:** {suggestion}  
**Location:** {location}  
""")
