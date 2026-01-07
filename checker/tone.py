import re

def run_tone_checks(doc):
    issues = []

    for i, para in enumerate(doc.paragraphs, start=1):
        text = para.text

        if "Elese" in text:
            issues.append({
                "line": i,
                "type": "flag",
                "match": "Elese",
                "message": "Possible spelling error: use 'Else'.",
                "text": text
            })

        if "helps protects" in text:
            issues.append({
                "line": i,
                "type": "flag",
                "match": "helps protects",
                "message": "Grammar issue: use 'helps protect'.",
                "text": text
            })

        if re.search(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", text):
            issues.append({
                "line": i,
                "type": "flag",
                "match": "Capitalisation",
                "message": "Check inconsistent capitalisation.",
                "text": text
            })

    return issues

