"""Render the README's deterministic, illustrative CLI demo (requires Pillow)."""

from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from oss_license_checker.cli import main  # noqa: E402
from contextlib import redirect_stdout
from email.message import Message
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch


def demo():
    packages = []
    for name, version, license in [
        ("demo-core", "1.4.0", "MIT"),
        ("demo-http", "2.1.0", "Apache-2.0"),
        ("demo-plugin", "0.3.0", "GPL-3.0-only"),
    ]:
        meta = Message()
        meta["Name"] = name
        meta["License-Expression"] = license
        packages.append(SimpleNamespace(metadata=meta, version=version))
    output = StringIO()
    with patch("oss_license_checker.cli.metadata.distributions", return_value=packages), redirect_stdout(output):
        code = main(["--allow", "MIT", "--allow", "Apache-2.0", "--fail-unknown"])
    assert code == 1
    return [line.split("\t") for line in output.getvalue().splitlines()[1:]]


def font(size, bold=False, mono=False):
    name = "DejaVuSansMono" if mono else "DejaVuSans"
    suffix = "-Bold" if bold else ""
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}{suffix}.ttf", size)


def render():
    rows = demo()
    frames = []
    command = "oss-license-checker --allow MIT --allow Apache-2.0 --fail-unknown"
    for tick in range(86):
        im = Image.new("RGB", (1200, 700), "#0b1017")
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((34, 30, 273, 61), 15, fill="#22352d")
        d.text((49, 37), "PYTHON  /  LOCAL-FIRST", font=font(14, bold=True), fill="#9de9b5")
        d.text((42, 84), "Know what ships.", font=font(56, bold=True), fill="#f1f3ec")
        d.text((44, 160), "Inspect licenses. Set your policy. Gate your CI.", font=font(24), fill="#a2adbb")
        d.rounded_rectangle((40, 221, 1160, 607), 18, fill="#121b26", outline="#2b3848", width=2)
        for x, color in [(68, "#f77676"), (91, "#edc86a"), (114, "#8cdaa4")]:
            d.ellipse((x, 242, x + 12, 254), fill=color)
        d.text((154, 239), "oss-license-checker", font=font(15, mono=True), fill="#8c9aab")
        d.text((918, 239), "ILLUSTRATIVE DEMO", font=font(12, bold=True), fill="#8c9aab")
        d.line((42, 274, 1158, 274), fill="#2b3848")
        count = min(len(command), max(0, (tick - 4) * 3))
        d.text((66, 298), "$", font=font(17, mono=True), fill="#9de9b5")
        d.text((91, 298), command[:count], font=font(17, mono=True), fill="#e4e9f1")
        if tick < 29 and tick % 8 < 5:
            cursor = 91 + d.textlength(command[:count], font=font(17, mono=True))
            d.rectangle((cursor + 2, 298, cursor + 11, 317), fill="#9de9b5")
        if tick >= 29:
            columns = [68, 350, 510, 970]
            for x, title in zip(columns, ["PACKAGE", "VERSION", "LICENSE", "STATUS"]):
                d.text((x, 353), title, font=font(14, mono=True), fill="#8c9aab")
            d.line((68, 380, 1130, 380), fill="#2b3848")
            for index, row in enumerate(rows):
                if tick < 33 + index * 6:
                    continue
                y = 398 + index * 43
                color = "#ffbf79" if row[3] == "denied" else "#9de9b5"
                for x, value in zip(columns[:3], row[:3]):
                    d.text((x, y), value, font=font(18, mono=True), fill="#d9e1ec")
                d.rounded_rectangle((958, y - 3, 1110, y + 28), 7, fill="#332b25" if row[3] == "denied" else "#20352e")
                d.text((973, y), row[3].upper(), font=font(17, bold=True, mono=True), fill=color)
        if tick >= 54:
            d.text((68, 550), "exit 1", font=font(18, bold=True, mono=True), fill="#ffbf79")
            d.text((169, 550), "Policy violation caught before release.", font=font(18, mono=True), fill="#b4bfcd")
        d.text((44, 638), "OSS LICENSE CHECKER", font=font(16, bold=True), fill="#edf1e8")
        d.text((637, 638), "SPDX expressions   /   JSON + CSV   /   CI ready", font=font(16), fill="#8c9aab")
        frames.append(im.quantize(colors=96))
    target = ROOT / "docs/assets/hero.gif"
    target.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(target, save_all=True, append_images=frames[1:], duration=90, loop=0, optimize=True, disposal=1)
    print(f"{target}: {target.stat().st_size:,} bytes")


if __name__ == "__main__":
    render()
