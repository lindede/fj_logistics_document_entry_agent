#!/usr/bin/env python3
"""生成可抽取的样例托运单 PDF（BKG.pdf）及 FAIL 变体。"""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
GOLD = ROOT / "data" / "gold" / "bkg_sample.json"


def _pdf_safe(text: str) -> str:
    # Helvetica 仅支持 Latin-1；样例中的 en-dash 等替换为 ASCII
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
    width, height = A4
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
    draw_booking(SAMPLES / "BKG.pdf", lines, "BKG SAMPLE / SHIPPING ORDER")

    fail_lines = list(lines)
    fail_lines = [
        (k, "QINGDAO –CNTAO" if k == "Port of Discharge" else v) for k, v in fail_lines
    ]
    draw_booking(
        SAMPLES / "BKG_fail_same_ports.pdf",
        fail_lines,
        "BKG SAMPLE / SHIPPING ORDER (FAIL POL=POD)",
    )

    # 非托运单
    draw_booking(
        SAMPLES / "not_booking.pdf",
        [("Invoice No", "INV-001"), ("Amount", "100 USD")],
        "COMMERCIAL INVOICE",
    )
    print("wrote", SAMPLES / "BKG.pdf")


if __name__ == "__main__":
    main()
