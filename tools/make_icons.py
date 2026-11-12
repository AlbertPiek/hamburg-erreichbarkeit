"""Erzeugt die App-Icons für die PWA (web/icons/). Einmalig nötig, braucht Pillow.

Aufruf:  python tools/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
NAVY = (29, 42, 77)
RINGS = [(215, 48, 39), (252, 141, 89), (254, 224, 139), (145, 207, 96), (26, 152, 80)]


def draw(size: int, maskable: bool) -> Image.Image:
    s = size * 4  # supersampling für glatte Kanten
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if maskable:
        d.rectangle([0, 0, s, s], fill=NAVY)
        scale = 0.62          # Inhalt in der sicheren Zone (80 %)
    else:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=NAVY)
        scale = 0.78
    c = s / 2
    r_max = s * scale / 2
    # Erreichbarkeits-Ringe von außen (rot, weit) nach innen (grün, nah)
    for i, col in enumerate(RINGS):
        r = r_max * (1 - i * 0.17)
        d.ellipse([c - r, c - r, c + r, c + r], fill=col)
        r2 = r - r_max * 0.07
        d.ellipse([c - r2, c - r2, c + r2, c + r2], fill=NAVY)
    # Startstation in der Mitte
    r = r_max * 0.17
    d.ellipse([c - r, c - r, c + r, c + r], fill=(255, 255, 255), outline=(0, 0, 0), width=max(1, s // 96))
    return img.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    draw(192, False).save(OUT / "icon-192.png")
    draw(512, False).save(OUT / "icon-512.png")
    draw(512, True).save(OUT / "icon-maskable-512.png")
    print(f"Icons geschrieben nach {OUT}")


if __name__ == "__main__":
    main()
