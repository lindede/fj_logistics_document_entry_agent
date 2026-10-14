"""自然语言改字段：优先 LLM 理解任意表述；无 key / fixture 时回退正则。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import (
    BOOKING_FIELD_KEYS,
    LLM_MODEL,
    OPENAI_TEMPERATURE,
    has_llm_key,
    make_openai_client,
    parse_backend,
)

logger = logging.getLogger("fj.nl_patch")

# 允许附带的控制键（非业务字段）
_CONTROL_KEYS = {"_convert_weight"}


def _regex_nl_patch(t: str) -> dict[str, Any] | None:
    """离线/无 LLM 时的窄句式回退。"""
    m = re.search(
        r"(毛重)?\s*单位.*(从\s*)?(kgs|kg|ton|mt)\s*(换成|改为|改成|到|->|→)\s*(kgs|kg|ton|mt)",
        t,
        re.I,
    )
    if m:
        to_u = m.group(5).upper()
        if to_u == "KG":
            to_u = "KGS"
        if to_u == "MT":
            to_u = "TON"
        return {"weight_unit": to_u, "_convert_weight": True}

    m = re.search(r"(kgs|kg)\s*(->|→|换成|改为)\s*(ton|mt)", t, re.I)
    if m:
        return {
            "weight_unit": m.group(3).upper().replace("MT", "TON"),
            "_convert_weight": True,
        }

    m = re.search(r"(ton|mt)\s*(->|→|换成|改为)\s*(kgs|kg)", t, re.I)
    if m:
        return {"weight_unit": "KGS", "_convert_weight": True}

    m = re.search(r"船名.*(改为|改成|换成)\s*([a-z0-9 \-]+)", t, re.I)
    if m:
        return {"vessel": m.group(2).strip().upper()}

    m = re.search(r"(装货港|pol).*(改为|改成|换成)\s*(.+)$", t, re.I)
    if m:
        return {"port_of_loading": m.group(3).strip()}

    m = re.search(r"(目的港|卸货港|pod).*(改为|改成|换成)\s*(.+)$", t, re.I)
    if m:
        return {"port_of_discharge": m.group(3).strip()}

    return None


def _sanitize_patches(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k in _CONTROL_KEYS:
            if k == "_convert_weight":
                out[k] = bool(v)
            continue
        if k not in BOOKING_FIELD_KEYS:
            continue
        out[k] = v
    # 单位转换时至少要有 weight_unit
    if out.get("_convert_weight") and "weight_unit" not in out:
        out.pop("_convert_weight", None)
    return out


def _llm_nl_patch(
    text: str, current: dict[str, Any] | None
) -> dict[str, Any] | None:
    keys = ", ".join(BOOKING_FIELD_KEYS)
    cur = json.dumps(current or {}, ensure_ascii=False)[:4000]
    system = (
        "你是订舱单证录入助手。用户用自然语言要求修改当前已录入字段。"
        "只返回一个 JSON 对象（不要 markdown），表示要打的补丁。\n"
        f"允许修改的业务 key：{keys}\n"
        "另可含布尔控制键 _convert_weight："
        "当用户要把重量单位从 KGS 换成 TON（或反之）且需要按比例换算毛重时为 true。\n"
        "规则：\n"
        "- 只包含需要改动的字段；不要输出未改字段。\n"
        "- 若用户不是在改字段（闲聊/无关），返回 {}。\n"
        "- 数值字段用 JSON number；件数用 integer。\n"
        "- freight 仅 P/C/E 或 null；marks 无唛头用 null。\n"
        "- containers 若改箱型箱量，必须是 [{type, qty}] 数组。\n"
    )
    user = f"当前字段：\n{cur}\n\n用户指令：\n{text.strip()}"

    client = make_openai_client()
    kwargs: dict[str, Any] = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": min(OPENAI_TEMPERATURE, 0.2),
    }
    extra = {"thinking": {"type": "disabled"}}
    try:
        resp = client.chat.completions.create(
            **kwargs, response_format={"type": "json_object"}, extra_body=extra
        )
    except Exception:
        try:
            resp = client.chat.completions.create(**kwargs, extra_body=extra)
        except Exception:
            resp = client.chat.completions.create(**kwargs)

    content = (resp.choices[0].message.content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("nl_patch LLM non-JSON: %s", content[:200])
        return None
    if not isinstance(data, dict):
        return None
    patches = _sanitize_patches(data)
    return patches or None


def parse_nl_patches(
    text: str,
    *,
    current: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """将自然语言指令转为 patches；优先 LLM，否则正则回退。"""
    t = (text or "").strip()
    if not t:
        return None

    use_llm = has_llm_key() and parse_backend() != "fixture"
    if use_llm:
        try:
            patches = _llm_nl_patch(t, current)
            if patches:
                return patches
            logger.info("nl_patch LLM returned empty; falling back to regex")
        except Exception:
            logger.exception("nl_patch LLM failed; falling back to regex")

    return _regex_nl_patch(t.lower())
