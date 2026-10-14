#!/usr/bin/env python3
"""生成校验用 FAIL / 非托运单 / 跨页拆表样例（不覆盖官方 BKG.pdf）。"""

from __future__ import annotations

import io
import json
from pathlib import Path

import fitz
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
GOLD = ROOT / "data" / "gold" / "bkg_sample.json"


def _pdf_safe(text: str) -> str:
    return (
        str(text)
        .replace("–", "-")
        .replace("—", "-")
        .replace("’", "'")
        .replace("‘", "'")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def draw_booking(path: Path, lines: list[tuple[str, str]], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    _width, height = A4
    y = height - 72
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, _pdf_safe(title))
    y -= 36
    c.setFont("Helvetica", 11)
    for label, value in lines:
        c.drawString(72, y, _pdf_safe(f"{label}: {value}"))
        y -= 18
        if y < 72:
            c.showPage()
            y = height - 72
            c.setFont("Helvetica", 11)
    c.save()


def _box(c: canvas.Canvas, x: float, y: float, w: float, h: float) -> None:
    c.rect(x, y, w, h, stroke=1, fill=0)


def _vline(c: canvas.Canvas, x: float, y0: float, y1: float) -> None:
    c.line(x, y0, x, y1)


def _cell(
    c: canvas.Canvas,
    x: float,
    y_top: float,
    w: float,
    h: float,
    label: str,
    value: str,
    *,
    label_w: float = 112,
) -> float:
    """画完整「左标题 | 右内容」单元格，返回新的 y_top（下移后）。"""
    y = y_top - h
    _box(c, x, y, w, h)
    _vline(c, x + label_w, y, y + h)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + 5, y + h - 11, _pdf_safe(label))
    c.setFont("Helvetica", 9)
    text = _pdf_safe(value)
    ty = y + h - 12
    max_chars = max(16, int((w - label_w - 12) / 5.1))
    while text and ty > y + 5:
        c.drawString(x + label_w + 5, ty, text[:max_chars])
        text = text[max_chars:]
        ty -= 11
    return y


def _draw_full_form(gold: dict) -> bytes:
    """画「一整张」表格托运单（单页、偏高），供后续物理裁切。"""
    cont = gold["containers"][0]
    page_w = A4[0]
    # 比 A4 略高，保证表格完整且裁切点落在格子中间
    page_h = 980
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    margin = 40
    form_w = page_w - 2 * margin
    x0 = margin
    lw = 112

    y = page_h - 36
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(page_w / 2, y, _pdf_safe("SHIPPING ORDER / BOOKING NOTE"))
    y -= 16
    c.setFont("Helvetica", 8)
    c.drawCentredString(
        page_w / 2, y, _pdf_safe("Master B/L style form (single sheet before split)")
    )
    y -= 20

    # 外层总框起点
    form_top = y
    y = _cell(c, x0, y, form_w, 48, "Shipper", gold["shipper"], label_w=lw)
    y = _cell(c, x0, y, form_w, 48, "Consignee", gold["consignee"], label_w=lw)

    # Vessel | Voyage
    half = form_w / 2
    h = 40
    _box(c, x0, y - h, half, h)
    _vline(c, x0 + 64, y - h, y)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 5, y - 12, _pdf_safe("Vessel"))
    c.setFont("Helvetica", 11)
    c.drawString(x0 + 70, y - 16, _pdf_safe(gold["vessel"]))
    _box(c, x0 + half, y - h, half, h)
    _vline(c, x0 + half + 64, y - h, y)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + half + 5, y - 12, _pdf_safe("Voyage"))
    c.setFont("Helvetica", 11)
    c.drawString(x0 + half + 70, y - 16, _pdf_safe(gold["voyage"] or ""))
    y -= h

    y = _cell(
        c, x0, y, form_w, 36, "Port of Loading", gold["port_of_loading"], label_w=lw
    )

    # Notify：加高，标题靠上、值画在垂直中线附近 → 裁切后标题在上页、值在下页
    notify_h = 110
    y_top_n = y
    y_bot_n = y - notify_h
    _box(c, x0, y_bot_n, form_w, notify_h)
    _vline(c, x0 + lw, y_bot_n, y_top_n)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 5, y_top_n - 12, _pdf_safe("Notify Party"))
    # 值放在格子中下部，确保跨过裁切线
    c.setFont("Helvetica", 10)
    c.drawString(x0 + lw + 5, y_bot_n + 28, _pdf_safe(gold["notify_party"]))
    y = y_bot_n

    y = _cell(
        c,
        x0,
        y,
        form_w,
        36,
        "Port of Discharge",
        gold["port_of_discharge"],
        label_w=lw,
    )

    # Containers | Packages
    h = 44
    left_w = form_w * 0.48
    _box(c, x0, y - h, left_w, h)
    _vline(c, x0 + lw, y - h, y)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 5, y - 12, _pdf_safe("Containers"))
    c.setFont("Helvetica", 11)
    c.drawString(x0 + lw + 6, y - 18, _pdf_safe(f"{cont['qty']} x {cont['type']}"))
    _box(c, x0 + left_w, y - h, form_w - left_w, h)
    _vline(c, x0 + left_w + 80, y - h, y)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + left_w + 5, y - 12, _pdf_safe("Packages"))
    c.setFont("Helvetica", 11)
    c.drawString(
        x0 + left_w + 86,
        y - 18,
        _pdf_safe(f"{gold['packages_qty']} {gold['packages_unit']}"),
    )
    y -= h

    y = _cell(c, x0, y, form_w, 44, "Cargo / Goods", gold["goods_desc"], label_w=lw)

    half = form_w / 2
    h = 40
    _box(c, x0, y - h, half, h)
    _vline(c, x0 + 88, y - h, y)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 5, y - 12, _pdf_safe("Gross Weight"))
    c.setFont("Helvetica", 11)
    c.drawString(
        x0 + 94, y - 18, _pdf_safe(f"{gold['gross_weight']} {gold['weight_unit']}")
    )
    _box(c, x0 + half, y - h, half, h)
    _vline(c, x0 + half + 88, y - h, y)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + half + 5, y - 12, _pdf_safe("Measurement"))
    c.setFont("Helvetica", 11)
    c.drawString(
        x0 + half + 94,
        y - 18,
        _pdf_safe(f"{gold['measurement']} {gold['measurement_unit']}"),
    )
    y -= h

    h = 34
    _box(c, x0, y - h, half, h)
    _vline(c, x0 + 64, y - h, y)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 5, y - 12, _pdf_safe("Marks"))
    c.setFont("Helvetica", 10)
    c.drawString(x0 + 70, y - 16, _pdf_safe("N/M"))
    _box(c, x0 + half, y - h, half, h)
    _vline(c, x0 + half + 64, y - h, y)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + half + 5, y - 12, _pdf_safe("Freight"))
    c.setFont("Helvetica", 10)
    c.drawString(x0 + half + 70, y - 16, _pdf_safe("PREPAID"))
    y -= h

    # 外边框把整张表再描一圈（增强「一张单」感）
    form_bot = y
    c.setLineWidth(1.6)
    _box(c, x0 - 1, form_bot - 1, form_w + 2, form_top - form_bot + 2)
    c.setLineWidth(1)

    c.save()
    return buf.getvalue()


def draw_split_required_pages(path: Path, gold: dict) -> None:
    """先画完整表格单，再在 Notify Party 单元格正中裁成两页 A4。

    效果：同一张表被撕成两页；左右竖线、标题栏竖线都会出现在两页边缘（框线被切断）。
    """
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    full_pdf = _draw_full_form(gold)

    src = fitz.open(stream=full_pdf, filetype="pdf")
    page = src[0]
    zoom = 2.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img_w, img_h = img.size

    # Notify 格子垂直中线（与 _draw_full_form 布局对齐：notify_h=110）
    page_h = 980.0
    notify_top_pdf = page_h - 72 - (48 + 48 + 40 + 36)
    notify_mid_pdf = notify_top_pdf - 55  # 110/2
    cut_y = int((page_h - notify_mid_pdf) * zoom)
    cut_y = max(int(img_h * 0.30), min(cut_y, int(img_h * 0.70)))

    top_img = img.crop((0, 0, img_w, cut_y))
    bot_img = img.crop((0, cut_y, img_w, img_h))

    out = fitz.open()
    a4_w, a4_h = A4

    def _page_from_pil(pil_img: Image.Image, align_top: bool) -> None:
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=85, optimize=True)
        jpeg = buf.getvalue()
        scale = a4_w / pil_img.width
        draw_h = pil_img.height * scale
        pg = out.new_page(width=a4_w, height=a4_h)
        if align_top:
            rect = fitz.Rect(0, 0, a4_w, min(draw_h, a4_h))
            y_edge = min(draw_h, a4_h) - 0.5
        else:
            top = max(0.0, a4_h - draw_h)
            rect = fitz.Rect(0, top, a4_w, a4_h)
            y_edge = top + 0.5
        pg.insert_image(rect, stream=jpeg)
        # 裁切边提示（红虚线）
        pg.draw_line(
            fitz.Point(0, y_edge),
            fitz.Point(a4_w, y_edge),
            color=(0.75, 0.15, 0.15),
            width=0.7,
            dashes="[2 2]",
        )

    _page_from_pil(top_img, align_top=True)
    _page_from_pil(bot_img, align_top=False)

    out.save(path)
    out.close()
    src.close()


def main() -> None:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    cont = gold["containers"][0]
    lines = [
        ("Shipper", gold["shipper"]),
        ("Consignee", gold["consignee"]),
        ("Notify Party", gold["notify_party"]),
        ("Vessel", gold["vessel"]),
        ("Voyage", gold["voyage"] or ""),
        ("Port of Loading", gold["port_of_loading"]),
        ("Port of Discharge", gold["port_of_discharge"]),
        ("Containers", f"{cont['qty']} x {cont['type']}"),
        ("Packages", f"{gold['packages_qty']} {gold['packages_unit']}"),
        ("Cargo", gold["goods_desc"]),
        ("Gross Weight", f"{gold['gross_weight']} {gold['weight_unit']}"),
        ("Measurement", f"{gold['measurement']} {gold['measurement_unit']}"),
    ]

    fail_lines = [
        (k, "QINGDAO" if k == "Port of Discharge" else v) for k, v in lines
    ]
    draw_booking(
        SAMPLES / "BKG_fail_same_ports.pdf",
        fail_lines,
        "BKG SAMPLE / SHIPPING ORDER (FAIL POL=POD)",
    )
    # 无通知方：刻意不写 Notify Party，供 STRUCT-REQUIRED / 空通知方用例
    no_notify_lines = [(k, v) for k, v in lines if k != "Notify Party"]
    draw_booking(
        SAMPLES / "BKG_fail_no_notify.pdf",
        no_notify_lines,
        "BKG SAMPLE / SHIPPING ORDER (FAIL missing notify)",
    )
    draw_booking(
        SAMPLES / "not_booking.pdf",
        [
            ("Invoice No", "INV-2026-10086"),
            ("Seller", "ACME Trading Co., Ltd."),
            ("Buyer", "Demo Retail Inc."),
            ("Amount", "12,580.00 USD"),
            ("Payment Terms", "T/T 30 days"),
            ("Description", "Consumer electronics accessories"),
            ("Quantity", "500 PCS"),
        ],
        "COMMERCIAL INVOICE",
    )
    split_path = SAMPLES / "BKG_split_pages.pdf"
    draw_split_required_pages(split_path, gold)

    print("wrote", SAMPLES / "BKG_fail_same_ports.pdf")
    print("wrote", SAMPLES / "BKG_fail_no_notify.pdf")
    print("wrote", SAMPLES / "not_booking.pdf")
    print("wrote", split_path)
    print("note: official BKG.pdf is not overwritten")


if __name__ == "__main__":
    main()
