import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from . import VERSION
from .chrome import Renderer, RenderError
from .ereader import Pages, write_cbz, write_epub
from .profiles import DEFAULT_PROFILE, PROFILES, fits
from .schema import validate

SIZE_RE = re.compile(r"^(\d+)x(\d+)$")
KB = 1024


def fail(msg, details=()):
    print(f"manga: {msg}", file=sys.stderr)
    for d in details:
        print(f"  • {d}", file=sys.stderr)
    sys.exit(1)


def load(path):
    p = Path(path)
    if not p.is_file():
        fail(f"no existe {path}")
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"{path} no es JSON válido: línea {e.lineno}, columna {e.colno}: {e.msg}")
    errors = validate(cfg, str(p.resolve().parent))
    if errors:
        fail(f"{path} no cumple el esquema ({len(errors)} errores)", errors)
    return p, cfg


def size_arg(value):
    m = SIZE_RE.match(value)
    if not m:
        raise argparse.ArgumentTypeError("usa ANCHOxALTO, por ejemplo 480x800")
    return int(m.group(1)), int(m.group(2))


def fs_arg(value):
    try:
        f = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("debe ser un número, por ejemplo 1.2")
    if f <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que 0")
    return f


def report(path):
    print(f"{path}  {os.path.getsize(path) // KB} KB")


def cmd_build(a):
    src, cfg = load(a.file)
    profile = PROFILES[a.profile]
    size = a.size or profile["size"]
    if not fits(size, profile["max"]):
        fail(f"{size[0]}x{size[1]} supera el máximo de {profile['name']} ({profile['max'][0]}x{profile['max'][1]})")
    tag = a.profile if not a.size else f"{size[0]}x{size[1]}"
    out = Path(a.out) if a.out else src.parent
    out.mkdir(parents=True, exist_ok=True)
    png = a.png or not (a.epub or a.strip or a.cbz)
    modes = []
    if a.epub or (a.cbz and not a.strip):
        modes.append(False)
    if a.strip:
        modes.append(True)
    try:
        with tempfile.TemporaryDirectory(prefix="manga-") as tmp:
            r = Renderer(cfg, src, tmp)
            if png:
                path = out / f"{src.stem}.png"
                r.full_page().save(path, optimize=True)
                report(path)
            if not modes:
                return
            pages = Pages(r, cfg, size, a.fs, profile["quality"])
            cover = pages.cover()
            for strip in modes:
                sheets = pages.strip() if strip else pages.panels()
                stem = (cfg.get("strip", {}).get("file") or f"{src.stem}-strip") if strip else src.stem
                stem = f"{stem}-{tag}"
                if (a.epub and not strip) or strip:
                    path = out / f"{stem}.epub"
                    n = write_epub(path, cfg, cover, sheets, strip)
                    report(path)
                    print(f"  {n} páginas de {size[0]}x{size[1]}")
                if a.cbz:
                    path = out / f"{stem}.cbz"
                    write_cbz(path, cfg, cover, sheets, strip)
                    report(path)
    except RenderError as e:
        fail(str(e))


def cmd_validate(a):
    src, cfg = load(a.file)
    print(f"{src}: válido ({len(cfg['panels'])} viñetas)")


def cmd_profiles(a):
    for key, p in PROFILES.items():
        mark = " (por defecto)" if key == DEFAULT_PROFILE else ""
        print(f"{key:8} {p['name']}: {p['size'][0]}x{p['size'][1]}, JPEG baseline en grises{mark}")


def parser():
    ap = argparse.ArgumentParser(prog="manga", description="Convierte un JSON de página manga en PNG, ePub y CBZ.")
    ap.add_argument("--version", action="version", version=f"manga {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="renderiza la página y los formatos de e-reader")
    b.add_argument("file", help="config .json")
    b.add_argument("--png", action="store_true", help="página completa en PNG (por defecto si no pides otro formato)")
    b.add_argument("--epub", action="store_true", help="ePub con una viñeta por página")
    b.add_argument("--strip", action="store_true", help="ePub con la página completa cortada en pantallas por los canales")
    b.add_argument("--cbz", action="store_true", help="CBZ con las mismas páginas (de --strip si se pide, si no por viñeta)")
    b.add_argument("--profile", choices=sorted(PROFILES), default=DEFAULT_PROFILE, help="perfil de e-reader")
    b.add_argument("--size", type=size_arg, help="tamaño de pantalla ANCHOxALTO; reemplaza el del perfil")
    b.add_argument("--fs", type=fs_arg, default=1.0, help="escala del texto en modo una viñeta por página")
    b.add_argument("--out", help="carpeta de salida; por defecto la del JSON")
    b.set_defaults(func=cmd_build)
    v = sub.add_parser("validate", help="valida el JSON contra el esquema")
    v.add_argument("file")
    v.set_defaults(func=cmd_validate)
    p = sub.add_parser("profiles", help="lista los perfiles de e-reader")
    p.set_defaults(func=cmd_profiles)
    return ap


def main(argv=None):
    a = parser().parse_args(argv)
    a.func(a)
