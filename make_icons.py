"""Generate the Clock icons (assets/klock.ico, assets/klock_stop.ico)."""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent / "assets"
S = 1024  # draw large, then downsample for smooth edges


def render(accent, stop=False):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S // 2

    # rounded dark tile with a subtle vertical gradient
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    for y in range(S):
        t = y / S
        td.line([(0, y), (S, y)], fill=(int(10 + 10 * t), int(16 + 14 * t), int(30 + 22 * t), 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([24, 24, S - 24, S - 24], radius=210, fill=255)
    img.paste(tile, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # glow layer: outer ring, tick marks, hands
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    r = 360
    g.ellipse([c - r, c - r, c + r, c + r], outline=accent + (255,), width=34)
    for i in range(12):
        a = math.radians(i * 30)
        long = i % 3 == 0
        r1, r2 = (r - 40, r - 110) if long else (r - 40, r - 75)
        g.line([(c + r1 * math.sin(a), c - r1 * math.cos(a)),
                (c + r2 * math.sin(a), c - r2 * math.cos(a))],
               fill=accent + (255,), width=26 if long else 14)
    if stop:
        g.rounded_rectangle([c - 105, c - 105, c + 105, c + 105], radius=28, fill=accent + (255,))
    else:
        g.line([(c, c), (c, c - 215)], fill=(255, 255, 255, 255), width=34)                  # minute hand
        g.line([(c, c), (c + 150 * math.sin(math.radians(120)), c - 150 * math.cos(math.radians(120)))],
               fill=accent + (255,), width=40)                                               # hour hand
        g.ellipse([c - 36, c - 36, c + 36, c + 36], fill=(255, 255, 255, 255))               # hub
    halo = glow.filter(ImageFilter.GaussianBlur(28))
    img = Image.alpha_composite(img, halo)
    img = Image.alpha_composite(img, glow)
    return img


def save(name, accent, stop=False):
    OUT.mkdir(exist_ok=True)
    img = render(accent, stop).resize((256, 256), Image.LANCZOS)
    img.save(OUT / name, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    img.save(OUT / name.replace(".ico", ".png"))


TRAY = {  # state -> (colour, glyph); bold shapes so each state still reads at 16px
    "off": ((255, 70, 80), "stop"),
    "waiting": ((40, 220, 110), "ring"),
    "active": ((40, 220, 110), "disc"),
    "muted": ((255, 176, 32), "pause"),
    "nomic": ((140, 150, 160), "slash"),
}


def render_tray(accent, glyph):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    c, r = S // 2, 400
    box = [c - r, c - r, c + r, c + r]
    if glyph == "ring":
        g.ellipse(box, outline=accent + (255,), width=150)
    else:
        g.ellipse(box, fill=accent + (255,))
    dark = (12, 18, 28, 255)
    if glyph == "stop":
        g.rounded_rectangle([c - 170, c - 170, c + 170, c + 170], radius=40, fill=(255, 255, 255, 255))
    elif glyph == "pause":
        for x in (c - 170, c + 40):
            g.rounded_rectangle([x, c - 190, x + 130, c + 190], radius=30, fill=dark)
    elif glyph == "slash":
        g.line([(c - 250, c + 250), (c + 250, c - 250)], fill=dark, width=120)
    halo = glow.filter(ImageFilter.GaussianBlur(40))
    return Image.alpha_composite(Image.alpha_composite(img, halo), glow)


def save_tray():
    OUT.mkdir(exist_ok=True)
    for name, (accent, glyph) in TRAY.items():
        render_tray(accent, glyph).resize((64, 64), Image.LANCZOS).save(OUT / f"tray_{name}.png")


if __name__ == "__main__":
    save("klock.ico", (0, 200, 255))
    save("klock_stop.ico", (255, 70, 80), stop=True)
    save_tray()
    print("icons written to", OUT)
