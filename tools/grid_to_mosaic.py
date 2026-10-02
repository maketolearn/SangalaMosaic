"""Turn a hand-designed mosaic, written as a text grid with one letter per tile, into a
Sangala Mosaic project (.mosaic) and a picture of it.

Why this exists: a drawing with thin ink lines does not survive being sampled down to a
32 x 32 baseplate - Mosaic's build, a script, and image generators all lost it. Designing it
tile by tile, as a pixel artist would, did work (the Peter Reynolds boat, 2026-10-02). This
turns that design into a file Mosaic opens, with the parts list and build chart.

The design file: legend lines first, `<letter> = <Mosaic color name>`, then the grid, one row
per line. A letter mapped to `empty` leaves the baseplate showing.

    . = empty
    K = Black
    R = Bright Red
    ................................
    ...

    python grid_to_mosaic.py "design.txt" "Out (Ver 1.0).mosaic" [--png "picture.png"]

The .mosaic holds no photo layer and no frame; Mosaic fits the frame itself on opening.
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOSAIC_HTML = os.path.join(HERE, "..", "SangalaMosaic.html")


def palette():
    """Every PALETTE entry in order (its index is what a .mosaic stores), plus the set of
    indices that are real 1x1 tiles (TILE_ELEMENT)."""
    src = open(MOSAIC_HTML, encoding="utf-8").read()
    block = src[src.index("const PALETTE = ["):src.index("].map(p=>({name:p.name")]
    pal = [(m.group(1), [int(v) for v in m.group(2).split(",")])
           for m in re.finditer(r'name:"([^"]+)",\s*rgb:\[([\d,\s]+)\]', block)]
    tiles = {int(k) for k in json.loads(re.search(r"const TILE_ELEMENT=(\{.*?\});", src).group(1))}
    return pal, tiles


def read_design(path):
    legend, rows = {}, []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"^(\S)\s*=\s*(.+?)\s*$", line)
        if m and not rows:
            legend[m.group(1)] = m.group(2)
        elif line.strip():
            rows.append(line)
    return legend, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design"); ap.add_argument("out"); ap.add_argument("--png")
    a = ap.parse_args()
    pal, tiles = palette()
    index = {name: i for i, (name, _) in enumerate(pal)}
    legend, rows = read_design(a.design)
    gh, gw = len(rows), len(rows[0])
    if any(len(r) != gw for r in rows):
        sys.exit("Rows are not all the same length.")
    code = {}
    for ch, name in legend.items():
        if name.lower() == "empty":
            code[ch] = -1; continue
        if name not in index:
            sys.exit(f"'{name}' is not a Mosaic color.")
        if index[name] not in tiles:
            sys.exit(f"'{name}' is not sold as a 1x1 tile.")
        code[ch] = index[name]
    missing = {ch for r in rows for ch in r} - set(code)
    if missing:
        sys.exit(f"Letters with no legend entry: {''.join(sorted(missing))}")
    idx = [[code[ch] for ch in r] for r in rows]
    counts = {}
    for r in idx:
        for v in r:
            if v >= 0:
                counts[str(v)] = counts.get(str(v), 0) + 1
    proj = {"app": "Sangala Mosaic", "v": 1, "grid": {"gw": gw, "gh": gh}, "frame": None, "layers": [],
            "built": {"gw": gw, "gh": gh, "idx": idx, "counts": counts},
            "baseIdx": 0, "showPlate": True, "showGrid": True, "showBox": True, "showKey": False,
            "seeThrough": False, "medium": "tiles", "paintColor": 1}
    if os.path.exists(a.out):
        sys.exit(f"{a.out} already exists; give the next version number.")
    with open(a.out, "x", encoding="utf-8") as f:
        json.dump(proj, f)
    back = json.load(open(a.out, encoding="utf-8"))           # read it back: a finished write is not proof
    assert back["built"]["idx"] == idx
    print(f"{a.out}: {gw} x {gh}, {sum(counts.values())} tiles, {len(counts)} colors")
    for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {pal[int(k)][0]:24s} {n}")
    if a.png:
        from PIL import Image, ImageDraw
        cell = 24; im = Image.new("RGB", (gw * cell, gh * cell), (200, 200, 200)); d = ImageDraw.Draw(im)
        for y, r in enumerate(idx):
            for x, v in enumerate(r):
                rgb = tuple(pal[v][1]) if v >= 0 else (242, 243, 242)
                d.rectangle([x * cell, y * cell, x * cell + cell - 2, y * cell + cell - 2], fill=rgb)
        im.save(a.png)


if __name__ == "__main__":
    main()
