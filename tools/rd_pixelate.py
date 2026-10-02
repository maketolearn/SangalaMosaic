"""Turn a picture into a small pixel-art mosaic with the Retro Diffusion API, limited to the
1x1 tile colors Sangala Mosaic can build with.

Why this exists: Mosaic averages each grid cell, so the thin ink lines of a drawing break up
at 32 x 32. Retro Diffusion's rd_pro__pixelate model redraws the picture as pixel art at the
target size, deciding where an outline goes. The output is then mapped straight back into
Mosaic's tile palette.

The API key is read from the RD_API_KEY environment variable, or from the Windows user
environment in the registry (so a key set with `setx RD_API_KEY ...` works without
restarting anything). It is never printed.

Money: the account is prepaid and the API cannot buy credits. By default this script only
asks the price (check_cost, free). Pass --go to spend.

    python rd_pixelate.py "drawing.png" --out "folder"              price only
    python rd_pixelate.py "drawing.png" --out "folder" --go         generate
    python rd_pixelate.py --balance                                 remaining balance
"""
import argparse, base64, io, json, os, re, sys, time, urllib.request, urllib.error
from PIL import Image

API = "https://api.retrodiffusion.ai/v2"
HERE = os.path.dirname(os.path.abspath(__file__))
MOSAIC_HTML = os.path.join(HERE, "..", "SangalaMosaic.html")


def api_key():
    k = os.environ.get("RD_API_KEY")
    if not k and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = winreg.QueryValueEx(h, "RD_API_KEY")[0]
        except OSError:
            pass
    if not k:
        sys.exit("No RD_API_KEY found. Set it with:  setx RD_API_KEY \"rdpk-...\"")
    return k.strip()


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 headers={"X-RD-Token": api_key(), "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")


def tile_palette():
    """The colors Mosaic offers in Tiles mode: PALETTE entries that have a TILE_ELEMENT id."""
    src = open(MOSAIC_HTML, encoding="utf-8").read()
    block = src[src.index("const PALETTE = ["):src.index("].map(p=>({name:p.name")]
    pal = [(m.group(1), tuple(int(v) for v in m.group(2).split(",")))
           for m in re.finditer(r'name:"([^"]+)",\s*rgb:\[([\d,\s]+)\]', block)]
    elems = json.loads(re.search(r"const TILE_ELEMENT=(\{.*?\});", src).group(1))
    return [pal[int(i)] for i in sorted(elems, key=int)]


def b64png(im):
    buf = io.BytesIO(); im.save(buf, "PNG"); return base64.b64encode(buf.getvalue()).decode()


def palette_image(pal):
    im = Image.new("RGB", (len(pal), 1))
    for x, (_, rgb) in enumerate(pal):
        im.putpixel((x, 0), rgb)
    return im


def snap(im, pal):
    """Map every pixel to the nearest tile color (plain RGB distance), in case the API's
    palette step leaves anything off-palette. Returns the image and per-color counts."""
    im = im.convert("RGB"); out = im.copy(); counts = {}
    for y in range(im.height):
        for x in range(im.width):
            p = im.getpixel((x, y))
            name, rgb = min(pal, key=lambda c: sum((a - b) ** 2 for a, b in zip(p, c[1])))
            out.putpixel((x, y), rgb); counts[name] = counts.get(name, 0) + 1
    return out, counts


def side_by_side(src, mosaic, cell=16):
    big = mosaic.resize((mosaic.width * cell, mosaic.height * cell), Image.NEAREST)
    s = src.convert("RGB").resize((big.height * src.width // src.height, big.height), Image.LANCZOS)
    canvas = Image.new("RGB", (s.width + big.width + 24, big.height), (255, 255, 255))
    canvas.paste(s, (0, 0)); canvas.paste(big, (s.width + 24, 0))
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?")
    ap.add_argument("--out", default=".")
    ap.add_argument("--size", type=int, default=32)
    ap.add_argument("--style", default="rd_pro__pixelate")
    ap.add_argument("--strength", type=float, default=None, help="img2img strength 0-1 (low = closer to the source)")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--no-palette", action="store_true", help="let the model choose colors; snap to tiles afterward")
    ap.add_argument("--remove-bg", action="store_true")
    ap.add_argument("--go", action="store_true", help="spend money; without it, only the price is asked")
    ap.add_argument("--balance", action="store_true")
    a = ap.parse_args()

    if a.balance:
        print(call("GET", "/inferences/credits")); return
    if not a.image:
        ap.error("an image is required")

    pal = tile_palette()
    src = Image.open(a.image)
    flat = Image.new("RGB", src.size, (255, 255, 255))
    flat.paste(src.convert("RGBA"), mask=src.convert("RGBA").split()[3])   # API wants RGB, no alpha

    body = {"prompt": a.prompt, "prompt_style": a.style, "width": a.size, "height": a.size,
            "num_images": a.n, "input_image": b64png(flat), "remove_bg": a.remove_bg,
            "check_cost": not a.go}
    if a.strength is not None:
        body["strength"] = a.strength
    if not a.no_palette:
        body["input_palette"] = b64png(palette_image(pal))

    r = call("POST", "/inferences", body)
    if not a.go:
        print(f"Price only, nothing spent: {a.style} x{a.n} at {a.size}x{a.size} -> {json.dumps({k: v for k, v in r.items() if k != 'base64_images'})}")
        return

    os.makedirs(a.out, exist_ok=True)
    stem = f"{time.strftime('%Y%m%d-%H%M%S')} {a.style} {a.size}" + (f" s{a.strength}" if a.strength is not None else "") + (" nopal" if a.no_palette else "")
    for i, b in enumerate(r.get("base64_images", [])):
        raw = Image.open(io.BytesIO(base64.b64decode(b)))
        raw.save(os.path.join(a.out, f"{stem} {i+1} raw.png"))
        tiles, counts = snap(raw.convert("RGBA").convert("RGB"), pal)
        tiles.save(os.path.join(a.out, f"{stem} {i+1} tiles.png"))
        side_by_side(flat, tiles).save(os.path.join(a.out, f"{stem} {i+1} compare.png"))
        print(f"image {i+1}: {raw.size}, {len(counts)} tile colors:",
              ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
    print(f"cost {r.get('balance_cost')}  remaining {r.get('remaining_balance')}  model {r.get('model')}")


if __name__ == "__main__":
    main()
