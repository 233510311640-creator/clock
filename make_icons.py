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


if __name__ == "__main__":
    save("klock.ico", (0, 200, 255))
    save("klock_stop.ico", (255, 70, 80), stop=True)
    print("icons written to", OUT)
