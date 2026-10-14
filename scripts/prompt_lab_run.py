#!/usr/bin/env python3
"""独立提示词试验台：同一 PDF + 多提示变体 → 落盘对比（不改生产抽取）。"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "data" / "prompt_lab" / "prompts"
RUNS_DIR = ROOT / "data" / "prompt_lab" / "runs"
DEFAULT_PDF = ROOT / "data" / "samples" / "BKG.pdf"


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
        # 取最后一个完整 {...}，避免 ANALYSIS 里的括号干扰
        matches = list(re.finditer(r"\{[\s\S]*\}", raw))
        for m in reversed(matches):
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
        return None


def _split_staged(text: str) -> tuple[str | None, dict | list | None]:
    """解析「### ANALYSIS … ### JSON …」分阶段输出。"""
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
    # 去掉可选代码围栏
    json_blob = re.sub(r"^```(?:json)?\s*", "", json_blob.strip())
    json_blob = re.sub(r"\s*```\s*$", "", json_blob)
    parsed = _parse_jsonish(json_blob)
    if parsed is None:
        parsed = _parse_jsonish(raw)
    if analysis is None and parsed is None:
        analysis = raw.strip() or None
    return analysis, parsed


def _list_variants() -> list[str]:
    names = sorted(p.stem for p in PROMPTS_DIR.glob("*.txt"))
    if not names:
        raise SystemExit(f"无提示变体：{PROMPTS_DIR}")
    return names


def _resolve_variants(spec: str) -> list[str]:
    if spec.strip().lower() == "all":
        return _list_variants()
    name = spec.strip()
    if name.endswith(".txt"):
        name = name[:-4]
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.is_file():
        raise SystemExit(f"找不到提示：{path}（可用: {', '.join(_list_variants())}）")
    return [name]


def _call_pdf(client, *, model: str, pdf_bytes: bytes, prompt: str, temperature: float) -> str:
    data_url = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode("ascii")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "file_url", "file_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        temperature=temperature,
    )
    if not resp.choices:
        return ""
    return resp.choices[0].message.content or ""


def _party_snapshot(parsed: dict | list | None) -> dict | None:
    if not isinstance(parsed, dict):
        return None
    keys = ("shipper", "consignee", "notify_party", "vessel", "voyage", "freight")
    return {k: parsed.get(k) for k in keys}


def run_one(
    *,
    variant: str,
    pdf_path: Path,
    pdf_bytes: bytes,
    client,
    model: str,
    temperature: float,
) -> Path:
    prompt = (PROMPTS_DIR / f"{variant}.txt").read_text(encoding="utf-8")
    print(f"→ {variant} …", flush=True)
    content = _call_pdf(
        client, model=model, pdf_bytes=pdf_bytes, prompt=prompt, temperature=temperature
    )
    analysis, parsed = _split_staged(content)
    # 纯 JSON 变体：无 ANALYSIS 头时 analysis 可能整篇塞进，仅当有 staged 头才保留
    if not re.search(r"###\s*ANALYSIS\b", content or "", flags=re.I):
        if parsed is not None:
            analysis = None
        elif analysis == (content or "").strip():
            pass  # 纯讲解
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {
        "ts": ts,
        "variant": variant,
        "pdf": str(pdf_path.relative_to(ROOT)) if pdf_path.is_relative_to(ROOT) else str(pdf_path),
        "model": model,
        "temperature": temperature,
        "prompt_path": f"data/prompt_lab/prompts/{variant}.txt",
        "prompt_chars": len(prompt),
        "raw": content,
        "analysis": analysis,
        "parsed": parsed,
        "party_snapshot": _party_snapshot(parsed),
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{ts}_{variant}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 可读 md：有分析 或 非纯 JSON
    md_path = None
    if analysis or (parsed is None and (content or "").strip()):
        md_path = RUNS_DIR / f"{ts}_{variant}.md"
        parts = [
            f"# prompt_lab / {variant}\n",
            f"- pdf: `{out['pdf']}`",
            f"- model: `{model}`",
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
    ap = argparse.ArgumentParser(description="Prompt lab: PDF + prompt variant → runs/")
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF, help="托运单 PDF")
    ap.add_argument(
        "--prompt",
        default="baseline",
        help="变体名（prompts/*.txt 的 stem），或 all",
    )
    ap.add_argument("--model", default="", help="默认读 OPENAI_MODEL / LLM_MODEL")
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
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("LLM_MODEL")
        or "glm-4.6v"
    ).strip()
    temp = (
        args.temperature
        if args.temperature is not None
        else float(os.environ.get("OPENAI_TEMPERATURE", "0.1"))
    )
    if not key:
        print("未配置 OPENAI_API_KEY", file=sys.stderr)
        return 1

    # 与生产一致：不走 HTTP_PROXY（Cursor/本机代理常对智谱 403）
    import httpx
    from openai import OpenAI

    client = OpenAI(
        api_key=key,
        base_url=base or None,
        http_client=httpx.Client(trust_env=False, timeout=180.0),
    )
    pdf_bytes = pdf_path.read_bytes()
    variants = _resolve_variants(args.prompt)
    print(f"model={model} pdf={pdf_path.name} variants={variants}", flush=True)
    for v in variants:
        run_one(
            variant=v,
            pdf_path=pdf_path,
            pdf_bytes=pdf_bytes,
            client=client,
            model=model,
            temperature=temp,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
