
# Tools/fetch_us_dict.py
from pathlib import Path
import ssl
import urllib.request
import certifi

DEST = Path("dictionaries/en_US")
DEST.mkdir(parents=True, exist_ok=True)

BASE = "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/en"
FILES = {
    "en_US.aff": f"{BASE}/en_US.aff",
    "en_US.dic": f"{BASE}/en_US.dic",
}

# Use certifi’s CA bundle so SSL verification succeeds even if the system bundle is missing
ctx = ssl.create_default_context(cafile=certifi.where())

for fname, url in FILES.items():
    out = DEST / fname
    print(f"Downloading {fname} …")
    with urllib.request.urlopen(url, context=ctx) as r, open(out, "wb") as f:
        f.write(r.read())

print("Done. Files saved to dictionaries/en_US/")
