#!/usr/bin/env python3
"""Docling 试验：PDF → Markdown（保留表格）+ 文本模型。不改已有 prompt_lab 脚本。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROMPTS_DIR = ROOT / "data" / "prompt_lab" / "prompts"
RUNS_DIR = ROOT / "data" / "prompt_lab" / "runs"
DEFAULT_PDF = ROOT / "data" / "samples" / "BKG.pdf"
DEFAULT_PROMPT = "v4_docling"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _parse_jsonish(text: str) -> dict | list | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        matches = list(re.finditer(r"\{[\s\S]*\}", raw))
        for m in reversed(matches):
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
        return None


def _split_staged(text: str) -> tuple[str | None, dict | list | None]:
    raw = text or ""
    analysis = None
    json_blob = raw
    m_a = re.search(
        r"###\s*ANALYSIS\s*\n([\s\S]*?)(?=###\s*JSON\b|$)",
        raw,
        flags=re.IGNORECASE,
    )
    m_j = re.search(r"###\s*JSON\s*\n([\s\S]*)", raw, flags=re.IGNORECASE)
    if m_a:
        analysis = m_a.group(1).strip()
    if m_j:
        json_blob = m_j.group(1).strip()
    json_blob = re.sub(r"^```(?:json)?\s*", "", json_blob.strip())
    json_blob = re.sub(r"\s*```\s*$", "", json_blob)
    parsed = _parse_jsonish(json_blob)
    if parsed is None:
        parsed = _parse_jsonish(raw)
    if analysis is None and parsed is None:
        analysis = raw.strip() or None
    return analysis, parsed


def _party_snapshot(parsed: dict | list | None) -> dict | None:
    if not isinstance(parsed, dict):
        return None
    keys = ("shipper", "consignee", "notify_party", "vessel", "voyage", "freight")
    return {k: parsed.get(k) for k in keys}


def docling_markdown(pdf_path: Path) -> str:
    """数字 PDF：关 OCR，开表格结构，导出 Markdown。"""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False
    options.do_table_structure = True
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    result = converter.convert(str(pdf_path))
    return (result.document.export_to_markdown() or "").strip()


def _call_text(client, *, model: str, prompt: str, doc_text: str, temperature: float) -> str:
    user = f"{prompt.rstrip()}\n\n--- Docling Markdown ---\n{doc_text}"
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": user}],
        "temperature": temperature,
    }
    extra = {"thinking": {"type": "disabled"}}
    try:
        resp = client.chat.completions.create(**kwargs, extra_body=extra)
    except Exception:
        resp = client.chat.completions.create(**kwargs)
    if not resp.choices:
        return ""
    return resp.choices[0].message.content or ""


def run_one(
    *,
    variant: str,
    pdf_path: Path,
    doc_text: str,
    client,
    model: str,
    temperature: float,
) -> Path:
    prompt_path = PROMPTS_DIR / f"{variant}.txt"
    if not prompt_path.is_file():
        raise SystemExit(f"找不到提示：{prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8")
    print(f"→ {variant} (docling) …", flush=True)
    content = _call_text(
        client,
        model=model,
        prompt=prompt,
        doc_text=doc_text,
        temperature=temperature,
    )
    analysis, parsed = _split_staged(content)
    if not re.search(r"###\s*ANALYSIS\b", content or "", flags=re.I):
        if parsed is not None:
            analysis = None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {
        "ts": ts,
        "variant": variant,
        "input_mode": "docling",
        "pdf": str(pdf_path.relative_to(ROOT)) if pdf_path.is_relative_to(ROOT) else str(pdf_path),
        "model": model,
        "temperature": temperature,
        "prompt_path": f"data/prompt_lab/prompts/{variant}.txt",
        "prompt_chars": len(prompt),
        "docling_chars": len(doc_text),
        "docling_markdown": doc_text,
        "raw": content,
        "analysis": analysis,
        "parsed": parsed,
        "party_snapshot": _party_snapshot(parsed),
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{ts}_{variant}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = RUNS_DIR / f"{ts}_{variant}.md"
    parts = [
        f"# prompt_lab_docling / {variant}\n",
        f"- pdf: `{out['pdf']}`",
        f"- input_mode: `docling`",
        f"- model: `{model}`",
        f"- docling_chars: `{len(doc_text)}`",
        f"- ts: `{ts}`",
        "",
        "---",
        "",
        "## Docling Markdown",
        "",
        doc_text,
        "",
    ]
    if analysis:
        parts += ["## ANALYSIS", "", analysis, ""]
    if parsed is not None:
        parts += [
            "## JSON (parameters)",
            "",
            "```json",
            json.dumps(parsed, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
        snap = out["party_snapshot"]
        if snap:
            parts += [
                "## party_snapshot",
                "",
                "```json",
                json.dumps(snap, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
    elif not analysis:
        parts += [(content or "").lstrip("\n")]
    md_path.write_text("\n".join(parts), encoding="utf-8")

    snap = out["party_snapshot"]
    if snap:
        print(f"  party: {json.dumps(snap, ensure_ascii=False)}", flush=True)
    else:
        preview = (content or "").replace("\n", " ")[:160]
        print(f"  (非 JSON 或解析失败) {preview}…", flush=True)
    if analysis:
        print(f"  analysis_chars={len(analysis)}", flush=True)
    print(f"  saved {path.relative_to(ROOT)}", flush=True)
    print(f"  saved {md_path.relative_to(ROOT)}", flush=True)
    return path


def main(argv: list[str] | None = None) -> int:
    _load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Prompt lab: Docling markdown + text model")
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF, help="托运单 PDF")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT, help="提示 stem，默认 v4_docling")
    ap.add_argument("--model", default="", help="默认 OPENAI_TEXT_MODEL / glm-4.5-air")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument(
        "--dump-only",
        action="store_true",
        help="只导出 Docling Markdown，不调用大模型",
    )
    args = ap.parse_args(argv)

    pdf_path = args.pdf if args.pdf.is_absolute() else ROOT / args.pdf
    if not pdf_path.is_file():
        print(f"PDF 不存在: {pdf_path}", file=sys.stderr)
        return 1

    print(f"docling convert {pdf_path.name} …", flush=True)
    doc_text = docling_markdown(pdf_path)
    if not doc_text:
        print("Docling 导出为空", file=sys.stderr)
        return 1
    print(f"docling_chars={len(doc_text)}", flush=True)

    if args.dump_only:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = RUNS_DIR / f"{ts}_docling_md.md"
        path.write_text(doc_text, encoding="utf-8")
        print(f"saved {path.relative_to(ROOT)}", flush=True)
        return 0

    key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or "").strip()
    base = (
        os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_API_BASE") or ""
    ).strip().rstrip("/")
    model = (
        args.model.strip()
        or os.environ.get("OPENAI_TEXT_MODEL")
        or os.environ.get("LLM_TEXT_MODEL")
        or "glm-4.5-air"
    ).strip()
    temp = (
        args.temperature
        if args.temperature is not None
        else float(os.environ.get("OPENAI_TEMPERATURE", "0.1"))
    )
    if not key:
        print("未配置 OPENAI_API_KEY", file=sys.stderr)
        return 1

    import httpx
    from openai import OpenAI

    client = OpenAI(
        api_key=key,
        base_url=base or None,
        http_client=httpx.Client(trust_env=False, timeout=180.0),
    )
    print(f"model={model} input=docling prompt={args.prompt}", flush=True)
    run_one(
        variant=args.prompt,
        pdf_path=pdf_path,
        doc_text=doc_text,
        client=client,
        model=model,
        temperature=temp,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
