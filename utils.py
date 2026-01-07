import difflib
from docx import Document

severity_color = {"error": "red", "warning": "orange", "advice": "blue"}

def generate_diff(before_text, after_text):
    diff = difflib.ndiff(before_text.split(), after_text.split())
    result = []
    for token in diff:
        if token.startswith('+'):
            result.append(f"<span style='color:green'>+{token[2:]}</span>")
        elif token.startswith('-'):
            result.append(f"<span style='color:red'>-{token[2:]}</span>")
        else:
            result.append(token[2:])
    return " ".join(result)

def add_word_comment(doc: Document, paragraph_idx: int, suggestion: str, severity: str):
    """
    Instead of a real comment (not supported), append the message inline.
    """
    para = doc.paragraphs[paragraph_idx]
    para.add_run(f"  [{severity.upper()}] {suggestion}")
    return doc
