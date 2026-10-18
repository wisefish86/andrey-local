# Install in a trusted CI environment: pip install cairosvg Pillow
import json
import io
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree as ET
import cairosvg
from PIL import Image

root = Path(__file__).resolve().parents[2] / "Ресурсы" / "Иконки"
settings = json.loads((root / "icon-map.json").read_text(encoding="utf-8-sig"))
for name, lucide in settings["icons"].items():
    if not name.replace("-", "").isalnum() or not lucide.replace("-", "").isalnum():
        raise ValueError("Invalid icon name")
    url = "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/" + lucide + ".svg"
    with urlopen(url, timeout=15) as response:
        source = ET.fromstring(response.read())
    source.set("x", "8")
    source.set("y", "8")
    source.set("width", "48")
    source.set("height", "48")
    source.set("stroke", settings["style"]["color"])
    source.set("stroke-width", str(settings["style"]["strokeWidth"]))
    root_svg = ET.Element("{http://www.w3.org/2000/svg}svg", {"viewBox":"0 0 64 64", "width":"64", "height":"64"})
    ET.SubElement(root_svg, "{http://www.w3.org/2000/svg}rect", {"x":"1","y":"1","width":"62","height":"62","rx":"14","fill":settings["style"]["background"]})
    root_svg.append(source)
    data = ET.tostring(root_svg, encoding="utf-8")
    (root / "SVG").mkdir(exist_ok=True)
    (root / "ICO").mkdir(exist_ok=True)
    (root / "SVG" / (name + ".svg")).write_bytes(data)
    sizes = [16,24,32,48,64,128,256]
    png = cairosvg.svg2png(bytestring=data, output_width=256, output_height=256)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    img.save(root / "ICO" / (name + ".ico"), format="ICO", sizes=[(s,s) for s in sizes])
    print("Built", name)
