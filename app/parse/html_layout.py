"""PDF 文字层 → HTML。每个词用页面坐标，不画表格框，不含页图。"""

from __future__ import annotations

import html

# 同一行：纵坐标差小于此值（pt）
_LINE_Y_TOL = 3.0
# 同一段：前一个字右缘到下一个字左缘小于此值（pt）
_GAP_JOIN = 8.0


def words_to_html(pdf_bytes: bytes) -> str:
    """一行一个 div.line，栏位用 span 的 left 分开。"""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[str] = []
    try:
        for i, page in enumerate(doc):
            words = sorted(page.get_text("words"), key=lambda w: (w[1], w[0]))
            lines: list[list] = []
            for w in words:
                if lines and abs(w[1] - lines[-1][0][1]) <= _LINE_Y_TOL:
                    lines[-1].append(w)
                else:
                    lines.append([w])
            line_html: list[str] = []
            for line in lines:
                line.sort(key=lambda w: w[0])
                spans: list[tuple[float, float, list[str]]] = []
                for w in line:
                    text = (w[4] or "").strip()
                    if not text:
                        continue
                    if spans and w[0] - spans[-1][1] <= _GAP_JOIN:
                        spans[-1][2].append(text)
                        spans[-1] = (
                            spans[-1][0],
                            max(spans[-1][1], w[2]),
                            spans[-1][2],
                        )
                    else:
                        spans.append((w[0], w[2], [text]))
                if not spans:
                    continue
                top = line[0][1]
                bits = [
                    f'<span style="left:{x0:.1f}pt">{html.escape(" ".join(parts))}</span>'
                    for x0, _x1, parts in spans
                ]
                line_html.append(
                    f'<div class="line" style="top:{top:.1f}pt">{"".join(bits)}</div>'
                )
            pages.append(
                f'<section class="page" data-page="{i + 1}">\n'
                + "\n".join(line_html)
                + "\n</section>"
            )
    finally:
        doc.close()
    return "<article>\n" + "\n".join(pages) + "\n</article>"
