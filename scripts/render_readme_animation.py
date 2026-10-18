"""Original transparent research-crystallization animation for GitHub README.

Render at 2x resolution, then downsample to preserve subpixel movement and
soft alpha edges. Animated WebP preserves full transparency unlike GIF.
"""
from pathlib import Path
import math
import random
from PIL import Image, ImageDraw, ImageFont, features

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, SCALE = 960, 500, 2
FRAMES, DURATION = 300, 40  # 25 fps, 12 seconds, seamless resting endpoints.
BLUE = (105, 130, 225)
TEAL = (69, 163, 158)
INK = (111, 123, 145)
PAPER_INK = (54, 67, 94)
FONTS = Path('/usr/share/fonts/truetype/dejavu')


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), round(size * SCALE))


MONO = font('DejaVuSansMono.ttf', 10)
GLYPH = font('DejaVuSansMono.ttf', 15)
SERIF = font('DejaVuSerif.ttf', 55)
SMALL_SERIF = font('DejaVuSerif.ttf', 22)
SANS = font('DejaVuSans.ttf', 13)
TINY = font('DejaVuSans.ttf', 10)


def ease(t, start, end):
    p = max(0., min(1., (t - start) / (end - start)))
    return p ** 3 * (p * (p * 6 - 15) + 10)


def bezier(a, b, c, e, t):
    return tuple((1-t)**3*a[i] + 3*(1-t)**2*t*b[i] + 3*(1-t)*t*t*c[i] + t**3*e[i] for i in (0, 1))


rng = random.Random(108)
PARTICLES = []
for i in range(68):
    angle = rng.uniform(0, math.tau)
    radius = rng.uniform(160, 270)
    origin = (689 + math.cos(angle)*radius, 245 + math.sin(angle)*radius*.78)
    target = (rng.uniform(602, 774), rng.uniform(155, 343))
    # Curved, alternating trajectories avoid a uniform straight-line collapse.
    bend = (-1 if i % 2 else 1) * rng.uniform(50, 130)
    controls = ((origin[0] + bend, origin[1] - 35),
                (target[0] - bend*.45, target[1] + 65))
    PARTICLES.append((origin, *controls, target, rng.uniform(.03, .17),
                      rng.uniform(.4, .8), rng.choice('01+·:×∴λ'), i % 4 == 0))


class Painter:
    def __init__(self, image):
        self.image = image

    def draw(self, callback, color, alpha=1):
        if alpha <= 0:
            return
        layer = Image.new('RGBA', self.image.size)
        callback(ImageDraw.Draw(layer), (*color, round(max(0, min(1, alpha))*255)))
        self.image.alpha_composite(layer)

    def text(self, xy, value, face, color=INK, alpha=1, anchor=None):
        xy = tuple(v*SCALE for v in xy)
        self.draw(lambda d, c: d.text(xy, value, font=face, fill=c, anchor=anchor), color, alpha)

    def line(self, points, color=BLUE, alpha=1, width=1):
        points = [(x*SCALE, y*SCALE) for x, y in points]
        self.draw(lambda d, c: d.line(points, fill=c, width=max(1, round(width*SCALE)), joint='curve'), color, alpha)

    def rect(self, box, radius=0, color=BLUE, alpha=1, outline=False, width=1):
        box = tuple(v*SCALE for v in box)
        self.draw(lambda d, c: d.rounded_rectangle(box, radius=radius*SCALE,
                  fill=None if outline else c, outline=c if outline else None,
                  width=max(1, round(width*SCALE))), color, alpha)

    def dot(self, x, y, radius, color=BLUE, alpha=1):
        self.draw(lambda d, c: d.ellipse(((x-radius)*SCALE, (y-radius)*SCALE,
                  (x+radius)*SCALE, (y+radius)*SCALE), fill=c), color, alpha)


def background():
    image = Image.new('RGBA', (WIDTH*SCALE, HEIGHT*SCALE))
    p = Painter(image)
    p.line([(54, 102), (87, 102)], BLUE, .8, 2)
    p.text((100, 95), 'RESEARCH SCOUT', MONO, BLUE)
    p.text((50, 130), 'Research', SERIF, BLUE)
    p.text((50, 196), 'Scout.', SERIF, BLUE)
    p.text((55, 285), 'Follow the signal.', SANS, INK)
    p.text((55, 307), 'Make room for discovery.', SANS, INK, .75)
    for i, (x, label) in enumerate([(55, 'EVIDENCE'), (165, 'CONNECT'), (268, 'INSIGHT')]):
        p.dot(x+3, 371, 2, TEAL if i == 2 else BLUE, .9)
        p.text((x+14, 365), label, MONO, INK, .9)
        if i < 2:
            p.line([(x+83, 371), (x+98, 371)], INK, .3)
    # A sparse constellation, with empty transparent space around the artwork.
    for x, y in [(488, 108), (846, 82), (899, 211), (850, 392), (514, 403)]:
        p.dot(x, y, 1.5, BLUE, .22)
    return image


BASE = background()


def render(frame):
    t = frame / (FRAMES - 1)
    image = BASE.copy()
    p = Painter(image)
    scene = ease(t, 0, .045) * (1-ease(t, .89, 1))
    for a, b, c, end, delay, opacity, char, teal in PARTICLES:
        progress = ease(t, delay, .58 + delay*.35)
        x, y = bezier(a, b, c, end, progress)
        alpha = opacity * scene * (1-ease(t, .44+delay*.3, .67))
        # A restrained two-dot trail carries direction without adding clutter.
        if .02 < progress < .96:
            for lag in [0.014, .028]:
                tx, ty = bezier(a, b, c, end, max(0, progress-lag))
                p.dot(tx, ty, 1, TEAL if teal else BLUE, alpha*.16)
        p.text((x, y), char, GLYPH, TEAL if teal else INK, alpha, 'mm')

    card = ease(t, .32, .52) * scene
    dy = 12*(1-ease(t, .32, .59))
    x0, y0, x1, y1 = 565, 78+dy, 815, 411+dy
    # Thin layered shadow and gently rounded paper; the canvas stays transparent.
    for spread, opacity in [(9, .012), (6, .018), (3, .028)]:
        p.rect((x0-spread, y0+5, x1+spread, y1+spread+5), 16+spread,
               PAPER_INK, card*opacity)
    p.rect((x0, y0, x1, y1), 13, (253, 254, 255), card*.98)
    p.rect((x0, y0, x1, y1), 13, BLUE, card*.28, outline=True, width=.8)
    p.rect((x0+22, y0+24, x0+25, y0+42), 1.5, TEAL, card)
    p.text((x0+35, y0+27), 'RESEARCH NOTE / 001', MONO, PAPER_INK, card*.65)
    reveal = ease(t, .43, .61)*card
    p.text((x0+22, y0+60), 'A clearer view.', SMALL_SERIF, PAPER_INK, reveal)
    for i, length in enumerate([188, 160, 177]):
        u = ease(t, .47+i*.023, .60+i*.023)
        p.rect((x0+23, y0+105+i*10, x0+23+max(.01, length*u), y0+107+i*10),
               1, INK, card*.28*u)

    # The chart appears as a continuous curve with a soft confidence ribbon.
    chart = ease(t, .55, .76)
    chart_alpha = card*ease(t, .51, .60)
    p.rect((585, 231+dy, 795, 326+dy), 7, (236, 241, 251), chart_alpha*.8)
    for row in range(3):
        y = 249+row*28+dy
        p.line([(598, y), (783, y)], BLUE, chart_alpha*.10, .65)
    pts = []
    for i in range(int(chart*120)+1):
        u = i/120
        x = 598+185*u
        y = 248 + 61*(1-math.exp(-3.4*u)) + 2*math.sin(u*11) + dy
        pts.append((x, y))
    if len(pts) > 1:
        polygon = [(x, y-5) for x, y in pts] + [(x, y+5) for x, y in reversed(pts)]
        p.draw(lambda d, c: d.polygon([(x*SCALE,y*SCALE) for x,y in polygon], fill=c), BLUE, chart_alpha*.09)
        p.line(pts, BLUE, chart_alpha, 1.9)
        x, y = pts[-1]
        p.dot(x, y, 5, BLUE, chart_alpha*.12)
        p.dot(x, y, 2.4, BLUE, chart_alpha)
    for i, length in enumerate([183, 151]):
        u = ease(t, .68+i*.025, .79+i*.025)
        p.rect((588, 344+i*10+dy, 588+max(.01,length*u), 346+i*10+dy), 1,
               INK, card*.28*u)
    done = card*ease(t, .75, .82)
    p.dot(591, 384+dy, 2.3, TEAL, done)
    p.text((601, 378+dy), 'EVIDENCE, CONNECTED.', MONO, TEAL, done)
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def main():
    if not features.check('webp_anim'):
        raise RuntimeError('Pillow needs animated WebP support.')
    output = ROOT/'assets'
    output.mkdir(exist_ok=True)
    frames = []
    for i in range(FRAMES):
        frames.append(render(i))
        if i % 75 == 0:
            print(f'Rendered {i}/{FRAMES}', flush=True)
    frames[0].save(output/'research-crystallization.webp', save_all=True,
                   append_images=frames[1:], duration=DURATION, loop=0,
                   lossless=False, quality=88, method=5, allow_mixed=True,
                   minimize_size=True)
    render(250).save(output/'research-crystallization.png')
    print('Saved transparent animated WebP and PNG.', flush=True)


if __name__ == '__main__':
    main()
