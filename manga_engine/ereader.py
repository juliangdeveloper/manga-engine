import datetime
import html
import io
import uuid
import zipfile

from PIL import Image, ImageFilter, ImageOps

DEFAULTS = {"margin": 6, "gamma": 1.1, "sharpen": 70, "cutoff": 0.5, "rotate": "auto", "rotateDir": "cw"}
STRIP_DEFAULTS = {"minFill": 0.5, "overlap": 40, "whiteMin": 235}
ROTATE_GAIN = 1.25
PANEL_SCALE = 2
STRIP_SCALE = 2
COVER_CSS_WIDTH = 480
UNSHARP_RADIUS = 1.2
UNSHARP_THRESHOLD = 2
LABELS = {
    "es": {"cover": "Portada", "panel": "Viñeta", "page": "Página", "start": "Inicio", "strip": "página completa", "creator": "Manga Engine"},
    "en": {"cover": "Cover", "panel": "Panel", "page": "Page", "start": "Start", "strip": "full page", "creator": "Manga Engine"},
}


def labels(cfg):
    lang = (cfg.get("meta", {}).get("lang") or "es").split("-")[0]
    return LABELS.get(lang, LABELS["es"])


class Pages:
    def __init__(self, renderer, cfg, size, fs, quality):
        self.r = renderer
        self.cfg = cfg
        self.W, self.H = size
        self.fs = fs
        self.E = dict(DEFAULTS, **cfg.get("ereader", {}))
        self.quality = self.E.get("quality", quality)
        self.L = labels(cfg)

    def tone(self, im):
        g = ImageOps.grayscale(im)
        g = ImageOps.autocontrast(g, cutoff=self.E["cutoff"])
        gam = self.E["gamma"]
        g = g.point(lambda v: round(255 * (v / 255) ** (1 / gam)))
        return g.filter(ImageFilter.UnsharpMask(radius=UNSHARP_RADIUS, percent=self.E["sharpen"], threshold=UNSHARP_THRESHOLD))

    def jpeg(self, im):
        buf = io.BytesIO()
        im.convert("L").save(buf, "JPEG", quality=self.quality, optimize=True, progressive=False)
        return buf.getvalue()

    def fit(self, im, rot):
        if rot:
            im = im.rotate(-90 if self.E["rotateDir"] == "cw" else 90, expand=True)
        m = self.E["margin"]
        s = min((self.W - 2 * m) / im.width, (self.H - 2 * m) / im.height)
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
        page = Image.new("L", (self.W, self.H), 255)
        page.paste(im, ((self.W - im.width) // 2, (self.H - im.height) // 2))
        return page

    def cover(self):
        h = round(COVER_CSS_WIDTH * self.H / self.W)
        im = self.r.cover(COVER_CSS_WIDTH, h, self.W / COVER_CSS_WIDTH)
        return self.jpeg(self.tone(im).resize((self.W, self.H), Image.LANCZOS))

    def panels(self):
        out = []
        m = self.E["margin"]
        for i, p in enumerate(self.cfg["panels"], 1):
            raw = self.tone(self.r.panel(i, self.fs, PANEL_SCALE))
            mode = (p.get("ereader") or {}).get("rotate", self.E["rotate"])
            upright = min((self.W - 2 * m) / raw.width, (self.H - 2 * m) / raw.height)
            turned = min((self.W - 2 * m) / raw.height, (self.H - 2 * m) / raw.width)
            rot = (turned > upright * ROTATE_GAIN) if mode == "auto" else bool(mode)
            out.append((self.jpeg(self.fit(raw, rot)), f"{self.L['panel']} {i}"))
        return out

    def strip(self):
        S = dict(STRIP_DEFAULTS, **self.cfg.get("strip", {}))
        W, H = self.W, self.H
        full = self.tone(self.r.full_page(STRIP_SCALE))
        full = full.resize((W, round(full.height * W / full.width)), Image.LANCZOS)
        dark = full.point(lambda v: 255 if v < S["whiteMin"] else 0)
        white = [dark.crop((0, y, W, y + 1)).getbbox() is None for y in range(full.height)]
        out, y0, k = [], 0, 1
        while y0 < full.height:
            forced = False
            if full.height - y0 <= H:
                y1 = full.height
            else:
                lo = y0 + int(H * S["minFill"])
                cuts = [y for y in range(lo, y0 + H) if white[y]]
                if cuts:
                    end = start = cuts[-1]
                    while start - 1 >= lo and white[start - 1]:
                        start -= 1
                    y1 = (start + end) // 2
                else:
                    y1, forced = y0 + H, True
            page = Image.new("L", (W, H), 255)
            page.paste(full.crop((0, y0, W, y1)), (0, 0))
            out.append((self.jpeg(page), f"{self.L['page']} {k}"))
            y0 = y1 - int(S["overlap"]) if forced else y1
            k += 1
        return out


def book_title(cfg, strip):
    L = labels(cfg)
    base = cfg.get("meta", {}).get("title") or cfg["title"]["text"].replace("\n", " ").title()
    if strip:
        return cfg.get("strip", {}).get("title") or f"{base} ({L['strip']})"
    return base


def write_epub(path, cfg, cover, pages, strip):
    L = labels(cfg)
    lang = cfg.get("meta", {}).get("lang", "es")
    title = html.escape(book_title(cfg, strip))
    creator = html.escape(cfg.get("meta", {}).get("creator", L["creator"]))
    uid = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, book_title(cfg, strip) + ("strip" if strip else "panels")))
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    css = "body{margin:0;padding:0;text-align:center}div{margin:0;padding:0;text-align:center}img{max-width:100%;max-height:100%;margin:0 auto;display:block}"
    items = [("cover", "cover.xhtml", "cover.jpg", L["cover"], cover)]
    items += [(f"p{k:02d}", f"p{k:02d}.xhtml", f"p{k:02d}.jpg", label, data) for k, (data, label) in enumerate(pages, 1)]

    def xpage(img, alt):
        return f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">
<head><meta charset="utf-8"/><title>{html.escape(alt)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body><div><img src="img/{img}" alt="{html.escape(alt)}"/></div></body></html>'''

    links = "\n".join(f'<li><a href="{x}">{html.escape(a)}</a></li>' for _, x, _, a, _ in items)
    nav = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">
<head><meta charset="utf-8"/><title>{title}</title></head><body>
<nav epub:type="toc" id="toc"><h1>{title}</h1><ol>
{links}
</ol></nav>
<nav epub:type="landmarks" hidden="hidden"><ol><li><a epub:type="cover" href="cover.xhtml">{L['cover']}</a></li><li><a epub:type="bodymatter" href="{items[1][1]}">{L['start']}</a></li></ol></nav>
</body></html>'''
    points = "\n".join(f'<navPoint id="n{k}" playOrder="{k}"><navLabel><text>{html.escape(a)}</text></navLabel><content src="{x}"/></navPoint>' for k, (_, x, _, a, _) in enumerate(items, 1))
    ncx = f'''<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta name="dtb:uid" content="{uid}"/><meta name="dtb:depth" content="1"/><meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>
<docTitle><text>{title}</text></docTitle><navMap>
{points}
</navMap></ncx>'''
    man = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
           '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
           '<item id="css" href="style.css" media-type="text/css"/>']
    for iid, x, img, _, _ in items:
        man.append(f'<item id="{iid}" href="{x}" media-type="application/xhtml+xml"/>')
        man.append(f'<item id="img-{iid}" href="img/{img}" media-type="image/jpeg"' + (' properties="cover-image"' if iid == "cover" else "") + "/>")
    manifest = "\n".join(man)
    spine = "\n".join(f'<itemref idref="{i}"/>' for i, *_ in items)
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{lang}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{uid}</dc:identifier><dc:title>{title}</dc:title><dc:language>{lang}</dc:language>
<dc:creator>{creator}</dc:creator>
<meta property="dcterms:modified">{now}</meta><meta name="cover" content="img-cover"/>
</metadata>
<manifest>
{manifest}
</manifest>
<spine toc="ncx">
{spine}
</spine>
<guide><reference type="cover" title="{L['cover']}" href="cover.xhtml"/></guide>
</package>'''
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0" encoding="utf-8"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", css, zipfile.ZIP_DEFLATED)
        for _, x, img, a, data in items:
            z.writestr(f"OEBPS/{x}", xpage(img, a), zipfile.ZIP_DEFLATED)
            z.writestr(f"OEBPS/img/{img}", data, zipfile.ZIP_STORED)
    return len(items)


def write_cbz(path, cfg, cover, pages, strip):
    meta = cfg.get("meta", {})
    lang = (meta.get("lang") or "es").split("-")[0]
    info = f'''<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
<Title>{html.escape(book_title(cfg, strip))}</Title>
<Writer>{html.escape(meta.get("creator", labels(cfg)["creator"]))}</Writer>
<LanguageISO>{html.escape(lang)}</LanguageISO>
<PageCount>{len(pages) + 1}</PageCount>
<BlackAndWhite>Yes</BlackAndWhite>
</ComicInfo>'''
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("000.jpg", cover, zipfile.ZIP_STORED)
        for k, (data, _) in enumerate(pages, 1):
            z.writestr(f"{k:03d}.jpg", data, zipfile.ZIP_STORED)
        z.writestr("ComicInfo.xml", info, zipfile.ZIP_DEFLATED)
    return len(pages) + 1
