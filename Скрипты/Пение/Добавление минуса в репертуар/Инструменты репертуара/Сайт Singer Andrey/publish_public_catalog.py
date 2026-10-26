"""Publish only repertoire.public.json using the existing WinSCP saved session."""
from __future__ import annotations
import json
import subprocess
import tempfile
from pathlib import Path

REMOTE_FILE = "/www/singer.andreway.ru/data/repertoire.public.json"

def quote(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("Invalid WinSCP command argument")
    return '"' + value.replace('"', '""') + '"'

def publish(public_file: Path, config: dict) -> None:
    data = json.loads(public_file.read_text(encoding="utf-8"))
    if not isinstance(data.get("songs"), list) or not data["songs"]:
        raise RuntimeError("Empty or invalid public catalogue; upload cancelled")
    settings = config["plus_upload"]
    executable = Path(settings["winscp_executable"])
    if not executable.is_file():
        raise FileNotFoundError(f"WinSCP.com not found: {executable}")
    session = settings["winscp_session"]
    if not session:
        raise RuntimeError("WinSCP saved session is missing")
    temp_remote = REMOTE_FILE + ".uploading"
    script = "\n".join([
        "option batch abort",
        "option confirm off",
        "open " + quote(session),
        "put -transfer=binary " + quote(str(public_file.resolve())) + " " + quote(temp_remote),
        "mv " + quote(temp_remote) + " " + quote(REMOTE_FILE),
        "exit",
        "",
    ])
    with tempfile.TemporaryDirectory(prefix="singer-publish-") as tmp:
        script_path = Path(tmp) / "publish.txt"
        script_path.write_text(script, encoding="utf-8-sig")
        result = subprocess.run(
            [str(executable), "/script=" + str(script_path)],
            capture_output=True, text=True, errors="replace",
            timeout=int(settings.get("winscp_timeout_seconds", 300)),
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"WinSCP upload failed (code {result.returncode}): {result.stdout[-1200:]} {result.stderr[-700:]}")
    print(f"WinSCP: public catalogue uploaded to {REMOTE_FILE}")
