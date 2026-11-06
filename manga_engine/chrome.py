import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine"
FONTS_URL = "https://fonts.googleapis.com/css2?family=Bangers&family=Comic+Neue:wght@400;700&family=Patrick+Hand&display=block"
CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
)
CHROME_ENV = "MANGA_CHROME"
TIME_BUDGET_MS = 6000
TIMEOUT_S = 120
MARGIN_PX = 40
CROP_PAD_PX = 28


class RenderError(Exception):
    pass


def find_chrome():
    custom = os.environ.get(CHROME_ENV)
    for c in ((custom,) if custom else ()) + CANDIDATES:
        path = shutil.which(c) or (c if os.path.isfile(c) else None)
        if path:
            return path
    raise RenderError(f"no encuentro Chrome ni Chromium; instálalo o indica la ruta en {CHROME_ENV}")


class Renderer:
    def __init__(self, cfg, json_path, workdir):
        self.chrome = find_chrome()
        self.cfg = cfg
        self.work = Path(workdir)
        base = Path(json_path).resolve().parent.as_uri() + "/"
        data = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
        page = f"""<!DOCTYPE html><html lang="{html.escape(cfg.get('meta', {}).get('lang', 'es'))}"><head><meta charset="utf-8">
<base href="{html.escape(base)}"><link rel="stylesheet" href="{html.escape(FONTS_URL)}">
<link rel="stylesheet" href="{(ENGINE / 'manga.css').as_uri()}"></head>
<body><div id="page"></div><script>window.PAGE={data};</script>
<script src="{(ENGINE / 'render.js').as_uri()}"></script><script>MangaEngine.boot();</script></body></html>"""
        self.page = self.work / "page.html"
        self.page.write_text(page, encoding="utf-8")
        self.size = None

    def run(self, args):
        cmd = [self.chrome, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--no-default-browser-check", "--allow-file-access-from-files",
               f"--virtual-time-budget={TIME_BUDGET_MS}"]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.append("--no-sandbox")
        try:
            return subprocess.run(cmd + args, capture_output=True, text=True, timeout=TIMEOUT_S, check=True).stdout
        except subprocess.CalledProcessError as e:
            raise RenderError(f"Chrome falló: {(e.stderr or '').strip()[-400:]}") from e
        except subprocess.TimeoutExpired as e:
            raise RenderError("Chrome no terminó a tiempo") from e

    def url(self, frag=""):
        return self.page.as_uri() + ("#" + frag if frag else "")

    def measure(self):
        if self.size:
            return self.size
        width = self.cfg.get("width", 1080)
        dom = self.run([f"--window-size={width + MARGIN_PX},1000", "--dump-dom", self.url()])
        m = re.search(r'data-height="(\d+)"', dom)
        if not m:
            raise RenderError("la página no se pudo maquetar; revisa el JSON y las imágenes")
        self.size = (width, int(m.group(1)))
        return self.size

    def shot(self, frag, w, h, scale=1.0, crop=True):
        out = self.work / "shot.png"
        self.run([f"--window-size={int(w)},{int(h)}", f"--force-device-scale-factor={scale}",
                  f"--screenshot={out}", self.url(frag)])
        im = Image.open(out).convert("RGB")
        im.load()
        out.unlink()
        if not crop:
            return im
        box = ImageOps.invert(im).getbbox()
        if not box:
            raise RenderError("la captura salió en blanco")
        return im.crop(box)

    def full_page(self, scale=1.0):
        w, h = self.measure()
        im = self.shot("", w + MARGIN_PX, h + MARGIN_PX, scale, crop=False)
        box = ImageOps.invert(im).getbbox()
        bottom = min(im.height, box[3] + round(CROP_PAD_PX * scale))
        return im.crop((0, 0, min(im.width, round(w * scale)), bottom))

    def panel(self, index, fs, scale):
        w, h = self.measure()
        return self.shot(f"panel={index}&fs={fs}", w + MARGIN_PX, h + MARGIN_PX, scale)

    def cover(self, w, h, scale):
        return self.shot(f"cover=1&w={w}&h={h}", w + MARGIN_PX, h + MARGIN_PX, scale)
