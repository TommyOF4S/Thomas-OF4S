"""Write tests/fixtures/sample_marks.png: a 2D image drawn like a CET export, with designer marks.

Marks on the panels (counted): pink dashes at three panel-to-panel joints; a red, a yellow
(CET's golden yellow), a green, a blue and a purple dot. Marks off the drawing (flagged, not counted): one pink
dash and one blue dot. Decoys that must not count: a yellow callout box with black text (letter
holes), red dotted dimension lines (small and chunky), a yellow ring icon, and a black dot on a
panel (black is not a mark color).

Run: python tests/fixtures/make_sample_marks.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

EXPECTED = {"pink": 3, "dots": {"red": 1, "yellow": 1, "green": 1, "blue": 1, "purple": 1}, "off_panel": 2}

PINK, RED, YELLOW, GREEN, BLUE = (255, 102, 179), (230, 0, 0), (255, 213, 25), (0, 160, 0), (0, 64, 255)
PURPLE = (128, 0, 192)


def panel(d, x0, y0, x1, y1):
    d.rectangle([x0, y0, x1, y1], fill=(220, 220, 220), outline=(0, 0, 0))


def build(path: Path):
    im = Image.new("RGB", (1200, 700), "white")
    d = ImageDraw.Draw(im)
    # panels: one run along y=300 and dividers hanging below it
    panel(d, 100, 297, 900, 303)
    for x in (100, 300, 500, 700, 900):
        panel(d, x - 3, 300, x + 3, 500)
    # worksurfaces
    for x in (106, 306, 506, 706):
        d.rectangle([x, 306, x + 188, 360], fill=(240, 240, 200), outline=(0, 0, 0))
    # marks on the drawing
    for x in (200, 400, 600):
        d.line([(x, 290), (x, 310)], fill=PINK, width=4)
    for (x, y), c in {(300, 300): RED, (500, 300): YELLOW, (700, 300): GREEN, (900, 420): BLUE, (100, 420): PURPLE}.items():
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=c)
    # marks off the drawing
    d.line([(1000, 590), (1000, 610)], fill=PINK, width=4)
    d.ellipse([1043, 143, 1057, 157], fill=BLUE)
    # decoys
    d.rectangle([150, 560, 450, 620], fill=YELLOW, outline=(0, 0, 0))
    d.text((170, 575), "new reception configuration 6.00", fill=(0, 0, 0))
    for x in range(500, 900, 8):  # small red dotted dimension line
        d.rectangle([x, 650, x + 2, 652], fill=RED)
    for x in range(500, 900, 14):  # chunky red dotted line
        d.rectangle([x, 100, x + 6, 106], fill=RED)
    d.ellipse([1090, 340, 1110, 360], outline=YELLOW, width=2)  # ring icon
    d.ellipse([293, 413, 307, 427], fill=(0, 0, 0))  # black dot on a panel
    im.save(path)


if __name__ == "__main__":
    build(Path(__file__).with_name("sample_marks.png"))
