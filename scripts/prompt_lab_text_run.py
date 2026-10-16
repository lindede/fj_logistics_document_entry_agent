#!/usr/bin/env python3
"""文本层试验：pypdf 抽字 + 文本模型（默认 glm-4.5-air）。不改 prompt_lab_run.py。"""

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

from app.parse.pdf_io import extract_text  # noqa: E402

PROMPTS_DIR = ROOT / "data" / "prompt_lab" / "prompts"
RUNS_DIR = ROOT / "data" / "prompt_lab" / "runs"
DEFAULT_PDF = ROOT / "data" / "samples" / "BKG.pdf"
DEFAULT_PROMPT = "v4_text"


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


def _call_text(client, *, model: str, prompt: str, pdf_text: str, temperature: float) -> str:
    user = f"{prompt.rstrip()}\n\n--- PDF 文本层 ---\n{pdf_text}"
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
    pdf_text: str,
    client,
    model: str,
    temperature: float,
) -> Path:
    prompt_path = PROMPTS_DIR / f"{variant}.txt"
    if not prompt_path.is_file():
        raise SystemExit(f"找不到提示：{prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8")
    print(f"→ {variant} (text) …", flush=True)
    content = _call_text(
        client,
        model=model,
        prompt=prompt,
        pdf_text=pdf_text,
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
        "input_mode": "text",
        "pdf": str(pdf_path.relative_to(ROOT)) if pdf_path.is_relative_to(ROOT) else str(pdf_path),
        "model": model,
        "temperature": temperature,
        "prompt_path": f"data/prompt_lab/prompts/{variant}.txt",
        "prompt_chars": len(prompt),
        "pdf_text_chars": len(pdf_text),
        "raw": content,
        "analysis": analysis,
        "parsed": parsed,
        "party_snapshot": _party_snapshot(parsed),
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{ts}_{variant}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = None
    if analysis or (parsed is None and (content or "").strip()):
        md_path = RUNS_DIR / f"{ts}_{variant}.md"
        parts = [
            f"# prompt_lab_text / {variant}\n",
            f"- pdf: `{out['pdf']}`",
            f"- input_mode: `text`",
            f"- model: `{model}`",
            f"- pdf_text_chars: `{len(pdf_text)}`",
            f"- ts: `{ts}`",
            "",
            "---",
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
    if md_path:
        print(f"  saved {md_path.relative_to(ROOT)}", flush=True)
    return path


def main(argv: list[str] | None = None) -> int:
    _load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Prompt lab text: pypdf text + text model")
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF, help="托运单 PDF")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT, help="提示 stem，默认 v4_text")
    ap.add_argument("--model", default="", help="默认 OPENAI_TEXT_MODEL / glm-4.5-air")
    ap.add_argument("--temperature", type=float, default=None)
    args = ap.parse_args(argv)

    pdf_path = args.pdf if args.pdf.is_absolute() else ROOT / args.pdf
    if not pdf_path.is_file():
        print(f"PDF 不存在: {pdf_path}", file=sys.stderr)
        return 1

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
    pdf_text = extract_text(pdf_path.read_bytes()).strip()
    if not pdf_text:
        print("文本层为空，这份 PDF 不适合文本试验", file=sys.stderr)
        return 1
    print(
        f"model={model} input=text pdf={pdf_path.name} chars={len(pdf_text)} prompt={args.prompt}",
        flush=True,
    )
    run_one(
        variant=args.prompt,
        pdf_path=pdf_path,
        pdf_text=pdf_text,
        client=client,
        model=model,
        temperature=temp,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
