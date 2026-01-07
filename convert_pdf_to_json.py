import PyPDF2
import json

pdf_path = "Textile_Exchange_Style_Guide.pdf"

# Extract text from PDF
with open(pdf_path, "rb") as f:
    reader = PyPDF2.PdfReader(f)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

# Split text into lines
lines = text.split("\n")

# Build JSON structure
rules = {}

for line in lines:
    line = line.strip()
    if not line or "→" not in line:
        continue

    term, right = line.split("→", 1)
    term = term.strip()
    right = right.strip()

    if right.lower().startswith("message:"):
        rules[term] = {
            "message": right.replace("message:", "").strip(),
            "auto_fix": False
        }
    else:
        rules[term] = {
            "replacement": right,
            "auto_fix": True
        }

# Save JSON to file
with open("rules/terminology.json", "w") as f:
    json.dump(rules, f, indent=2)

print(f"terminology.json created with {len(rules)} rules!")

