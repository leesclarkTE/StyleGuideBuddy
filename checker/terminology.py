import re

def apply_terminology_rules(doc, rules):
    changes = []

    for i, para in enumerate(doc.paragraphs, start=1):
        original_text = para.text

        for rule in rules.get("terminology", []):
            pattern = re.compile(rf"\b{re.escape(rule['match'])}\b", re.IGNORECASE)

            if pattern.search(para.text):
                if rule["type"] == "auto_fix":
                    para.text = pattern.sub(rule["replace_with"], para.text)
                    changes.append({
                        "line": i,
                        "type": "auto-fix",
                        "match": rule["match"],
                        "message": rule["message"],
                        "original": original_text,
                        "updated": para.text
                    })

    return changes

