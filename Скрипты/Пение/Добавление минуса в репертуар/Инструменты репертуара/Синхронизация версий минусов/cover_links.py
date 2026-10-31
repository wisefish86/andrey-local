from pathlib import Path
import json

PATH = Path(__file__).with_name("data") / "cover_decisions.json"

def read_links():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}

def write_links(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(PATH)
