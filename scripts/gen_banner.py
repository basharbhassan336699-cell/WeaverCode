#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_banner.py — يُولّد core/banner.py من assets/hello_weaver_code.png.

يحوّل الرسمة إلى فنّ ANSI بألوان حقيقية (أنصاف كتل) ويرسم العنوان
«Hello / WEAVER CODE» بحروف كتلية برتقالية، فيصبح الشعار نصّاً مخزّناً
يُطبَع على الطرفية بلا أي تبعية وقت التشغيل.

يتطلّب Pillow وقت التوليد فقط:  pip install pillow
الاستخدام:  python scripts/gen_banner.py
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "hello_weaver_code.png"
OUT = ROOT / "core" / "banner.py"
ORANGE = (198, 113, 33)
FULL, TOP = "\u2588", "\u2580"   # █ , ▀


def _font(px):
    for c in ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/system/fonts/Roboto-Bold.ttf"):
        if Path(c).exists():
            return ImageFont.truetype(c, px)
    return ImageFont.load_default()


def block_text(text, height):
    font = _font(height * 9)
    d = ImageDraw.Draw(Image.new("L", (10, 10)))
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    w, h = r - l, b - t
    img = Image.new("L", (w + 8, h + 8), 0)
    ImageDraw.Draw(img).text((4 - l, 4 - t), text, fill=255, font=font)
    tw = max(1, round((w / h) * height))
    px = img.resize((tw, height), Image.BOX).load()
    return [("".join(FULL if px[x, y] > 90 else " " for x in range(tw))).rstrip()
            for y in range(height)]


def half_block(box, width):
    im = Image.open(SRC).convert("RGB").crop(box)
    bw, bh = im.size
    rows = round(width * (bh / bw)); rows += rows % 2
    px = im.resize((width, rows), Image.LANCZOS).load()
    out = []
    for y in range(0, rows, 2):
        row = "".join("\033[38;2;%d;%d;%dm\033[48;2;%d;%d;%dm%s"
                      % (*px[x, y], *px[x, y + 1], TOP) for x in range(width))
        out.append(row + "\033[0m")
    return out


def colorize(lines, rgb):
    c = "\033[38;2;%d;%d;%dm" % rgb
    return [c + ln + "\033[0m" for ln in lines]


def main():
    hello = colorize(block_text("Hello", 5), ORANGE)
    weaver = colorize(block_text("WEAVER", 6), ORANGE)
    code = colorize(block_text("CODE", 6), ORANGE)
    W, H = Image.open(SRC).size
    art = half_block((int(0.27 * W), int(0.34 * H), W, int(0.93 * H)), 54)

    lines = [""]
    lines += ["  " + x for x in hello] + [""]
    lines += ["  " + x for x in weaver] + ["  " + x for x in code] + [""]
    lines += ["  " + x for x in art] + [""]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write('# -*- coding: utf-8 -*-\n"""\n')
        f.write("banner.py — شعار WeaverCode للطرفية (Hello / WEAVER CODE + الرسمة).\n")
        f.write("مُولَّد من assets/hello_weaver_code.png عبر scripts/gen_banner.py — فنّ ANSI\n")
        f.write("بألوان حقيقية، بلا أي تبعية وقت التشغيل (يُطبَع نصّاً مخزّناً).\n\"\"\"\n")
        f.write("import os\nimport sys\n\n_LINES = [\n")
        for ln in lines:
            f.write("    " + repr(ln) + ",\n")
        f.write("]\n\n\n")
        f.write("def render() -> str:\n"
                '    """يُرجع الشعار كنصّ جاهز للطباعة (ANSI بألوان حقيقية)."""\n'
                '    return "\\n".join(_LINES)\n\n\n'
                "def show() -> None:\n"
                '    """يطبع الشعار على الطرفية (Termux وكل الأنظمة)."""\n'
                "    try:\n"
                '        sys.stdout.write(render() + "\\n"); sys.stdout.flush()\n'
                "    except Exception:\n        pass\n\n\n"
                'if __name__ == "__main__":\n    show()\n')
    print("wrote", OUT)


if __name__ == "__main__":
    main()
