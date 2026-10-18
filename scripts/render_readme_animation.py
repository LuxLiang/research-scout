"""Render an original README animation inspired by https://automlr.com/.

Scattered evidence glyphs converge into a paper, whose rows reveal in order.
No website code or assets are bundled. Run from any working directory.
"""
from pathlib import Path
import math
import random
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 880, 520
FRAMES, DURATION = 180, 80  # 14.4 seconds, including a readable final hold.
BG = (245, 244, 238)
INK = (79, 83, 91)
BLUE = (75, 91, 208)
DOT = (229, 231, 227)
FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
FONT = ImageFont.truetype(FONT_PATH, 18)
rng = random.Random(42)


def ramp(value, start, end):
    u = max(0.0, min(1.0, (value - start) / (end - start)))
    return u * u * (3 - 2 * u)


def tint(color, opacity):
    return tuple(round(b + (c - b) * max(0, min(1, opacity))) for b, c in zip(BG, color))


# Stable randomness keeps the movement smooth and the render reproducible.
particles = []
for i in range(86):
    angle = rng.uniform(0, 2 * math.pi)
    radius = rng.uniform(95, 380)
    particles.append((angle, radius, rng.uniform(-.15, .15),
                      rng.uniform(.04, .20), rng.uniform(.5, .85),
                      rng.uniform(351, 529), rng.uniform(104, 400),
                      rng.choice('01+?:×∴·')))


def render(frame):
    t = frame / (FRAMES - 1)
    image = Image.new('RGB', (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(image)
    for x in range(24, WIDTH, 52):
        for y in range(20, HEIGHT, 52):
            d.ellipse((x, y, x + 2, y + 2), fill=DOT)
    # Fade into the next loop through the same empty dot grid.
    visible = ramp(t, 0, .035) * (1 - ramp(t, .93, 1))
    for angle, radius, drift, delay, opacity, tx, ty, char in particles:
        a = angle + drift * t * 4
        sx, sy = 440 + math.cos(a) * radius, 252 + math.sin(a) * radius * .64
        gather = ramp(t, delay, .69)
        x, y = sx + (tx - sx) * gather, sy + (ty - sy) * gather
        alpha = opacity * visible * (1 - ramp(t, .57, .76))
        d.text((x, y), char, font=FONT,
               fill=tint(BLUE if gather > .8 else INK, alpha), anchor='mm')
    formed = ramp(t, .43, .59) * visible
    left, top, right, bottom = 344, 86, 536, 362

    def line(points, color=INK, alpha=1, width=1):
        d.line(points, fill=tint(color, formed * alpha), width=width)

    # Fine frame, text rules, a loss plot, and footer materialize progressively.
    line([(left, bottom), (left, top), (right, top), (right, bottom), (left, bottom)], BLUE)
    rows = [
        ([(359, 115), (503, 115)], INK, 3),
        ([(359, 129), (455, 129)], INK, 3),
        ([(359, 160), (513, 160)], INK, 1),
        ([(359, 172), (493, 172)], INK, 1),
        ([(359, 183), (503, 183)], INK, 1),
        ([(363, 201), (517, 201)], INK, 1),
        ([(363, 201), (363, 274), (517, 274), (517, 201)], INK, 1),
        ([(373, 216), (401, 216), (401, 230), (440, 230)], BLUE, 1),
        ([(440, 230), (440, 245), (478, 245)], BLUE, 1),
        ([(478, 245), (478, 260), (507, 260)], BLUE, 1),
        ([(359, 310), (513, 310)], INK, 1),
        ([(359, 323), (484, 323)], INK, 1),
        ([(359, 335), (503, 335)], INK, 1),
        ([(359, 347), (522, 347)], INK, 3),
    ]
    progress = max(0, min(1, (t - .47) / .32))
    for index, (points, color, width) in enumerate(rows):
        reveal = max(0, min(1, progress * len(rows) - index))
        if not reveal:
            continue
        # Clip each row from left to right without drawing ahead of its reveal.
        layer = image.copy()
        ld = ImageDraw.Draw(layer)
        ld.line(points, fill=tint(color, formed), width=width)
        xs, ys = zip(*points)
        box = (min(xs), min(ys) - 2, int(min(xs) + (max(xs) - min(xs) + 2) * reveal), max(ys) + 3)
        image.paste(layer.crop(box), box)
    d = ImageDraw.Draw(image)
    for i, x in enumerate([364, 383, 402, 421, 440]):
        alpha = formed * ramp(t, .50 + i * .009, .56 + i * .009)
        d.ellipse((x - 2, 143, x + 2, 147), fill=tint(BLUE, alpha))
    for i in range(7):
        alpha = formed * ramp(t, .73, .79)
        x = 363 + i * 10
        d.ellipse((x - 1, 292, x + 1, 294), fill=tint(INK, alpha * .6))
    for x, y in [(373, 216), (507, 260)]:
        alpha = formed * ramp(t, .72, .79)
        d.polygon([(x, y-4), (x+4, y), (x, y+4), (x-4, y)], fill=tint(BLUE, alpha))
    for i in range(13):
        x, y = 412 + (i % 6) * 19, 215 + (i // 6) * 14
        alpha = formed * ramp(t, .65 + i * .004, .72 + i * .004)
        d.ellipse((x-1, y-1, x+1, y+1), fill=tint(BLUE, alpha))
    return image


def main():
    output = ROOT / 'assets'
    output.mkdir(exist_ok=True)
    # A shared palette prevents color flicker between frames.
    palette = render(150).quantize(colors=96)
    frames = [render(i).quantize(palette=palette, dither=Image.Dither.NONE) for i in range(FRAMES)]
    frames[0].save(output / 'research-crystallization.gif', save_all=True,
                   append_images=frames[1:], duration=DURATION, loop=0,
                   optimize=True, disposal=1)
    render(150).save(output / 'research-crystallization.png')
    print(output / 'research-crystallization.gif')


if __name__ == '__main__':
    main()
