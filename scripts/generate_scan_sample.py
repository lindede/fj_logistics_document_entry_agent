#!/usr/bin/env python3
"""从文本 PDF 生成「扫描件」样例：仅位图、无文本层。

默认输出：
  data/samples/BKG_scan.pdf           ← 真托运单扫描件
  data/samples/not_booking_scan.pdf   ← 假发票/非托运单扫描件
  data/samples/BKG_scan_split3.pdf    ← 扫描件第1页裁成3页（框线切断）
"""

from __future__ import annotations

import io
import random
from pathlib import Path

import fitz
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"

PAIRS = [
    (SAMPLES / "BKG.pdf", SAMPLES / "BKG_scan.pdf"),
    (SAMPLES / "not_booking.pdf", SAMPLES / "not_booking_scan.pdf"),
]


def _to_scan_look(pix: fitz.Pixmap, seed: int = 42) -> Image.Image:
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img = img.rotate(
        0.4,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(245, 245, 242),
    )
    img = ImageOps.grayscale(img).convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Brightness(img).enhance(1.05)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))

    rng = random.Random(seed)
    px = img.load()
    w, h = img.size
    for _ in range((w * h) // 80):
        x = rng.randrange(w)
        y = rng.randrange(h)
        r, g, b = px[x, y]
        d = rng.randint(-12, 12)
        px[x, y] = (
            max(0, min(255, r + d)),
            max(0, min(255, g + d)),
            max(0, min(255, b + d)),
        )
    return img


def render_scan(src: Path, out: Path, seed: int = 42) -> None:
    if not src.exists():
        raise SystemExit(f"missing source: {src}")

    src_doc = fitz.open(src)
    out_doc = fitz.open()
    matrix = fitz.Matrix(2.0, 2.0)

    for page in src_doc:
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = _to_scan_look(pix, seed=seed)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True)
        w_pt, h_pt = page.rect.width, page.rect.height
        new_page = out_doc.new_page(width=w_pt, height=h_pt)
        new_page.insert_image(new_page.rect, stream=buf.getvalue())

    out.parent.mkdir(parents=True, exist_ok=True)
    out_doc.save(out)
    n_pages = out_doc.page_count
    out_doc.close()
    src_doc.close()

    check = fitz.open(out)
    text = "".join((p.get_text() or "") for p in check)
    check.close()
    print(f"wrote {out}  pages={n_pages} text_chars={len(text.strip())}")


def split_scan_page1_to_three(
    src: Path,
    out: Path,
    *,
    cut_fracs: tuple[float, float] = (0.34, 0.583),
) -> None:
    """把扫描件第 1 页在表格单元格中间裁成 3 页。

    默认裁切：
      ~34%  船名/通知方一带（竖线被切断）
      ~58%  货描大格中部（表头在上段、内容跨到中段）
    """
    if not src.exists():
        raise SystemExit(f"missing source: {src}")

    doc = fitz.open(src)
    page = doc[0]
    # 用较高分辨率保证裁切后仍清晰
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    w, h = img.size
    cuts = sorted(int(h * f) for f in cut_fracs)
    # 保证两刀有间距、不贴边
    cuts = [max(int(h * 0.15), cuts[0]), min(int(h * 0.85), cuts[1])]
    if cuts[1] - cuts[0] < int(h * 0.12):
        cuts[1] = cuts[0] + int(h * 0.20)

    bands = [
        img.crop((0, 0, w, cuts[0])),
        img.crop((0, cuts[0], w, cuts[1])),
        img.crop((0, cuts[1], w, h)),
    ]

    a4_w, a4_h = 595.25, 841.85
    out_doc = fitz.open()
    for i, band in enumerate(bands):
        buf = io.BytesIO()
        band.save(buf, format="JPEG", quality=85, optimize=True)
        scale = a4_w / band.width
        draw_h = band.height * scale
        pg = out_doc.new_page(width=a4_w, height=a4_h)
        # 上段贴顶、中段居中偏上、下段贴底 → 更像「一张纸撕开」
        if i == 0:
            top = 0.0
        elif i == 2:
            top = max(0.0, a4_h - draw_h)
        else:
            top = max(0.0, (a4_h - draw_h) * 0.15)
        rect = fitz.Rect(0, top, a4_w, top + min(draw_h, a4_h))
        pg.insert_image(rect, stream=buf.getvalue())
        # 裁切边红虚线
        if i < 2:
            y_edge = top + min(draw_h, a4_h) - 0.5
            pg.draw_line(
                fitz.Point(0, y_edge),
                fitz.Point(a4_w, y_edge),
                color=(0.75, 0.15, 0.15),
                width=0.7,
                dashes="[2 2]",
            )
        if i > 0:
            y_edge = top + 0.5
            pg.draw_line(
                fitz.Point(0, y_edge),
                fitz.Point(a4_w, y_edge),
                color=(0.75, 0.15, 0.15),
                width=0.7,
                dashes="[2 2]",
            )

    out.parent.mkdir(parents=True, exist_ok=True)
    out_doc.save(out)
    n = out_doc.page_count
    out_doc.close()
    doc.close()
    print(f"wrote {out}  pages={n}  cuts={cuts} fracs={[round(c/h,3) for c in cuts]}")


def main() -> None:
    for i, (src, out) in enumerate(PAIRS):
        render_scan(src, out, seed=42 + i)
    split_scan_page1_to_three(
        SAMPLES / "BKG_scan.pdf",
        SAMPLES / "BKG_scan_split3.pdf",
    )


if __name__ == "__main__":
    main()
