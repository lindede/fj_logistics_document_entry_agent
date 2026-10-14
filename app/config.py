from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
SAMPLES_DIR = DATA_DIR / "samples"
GOLD_DIR = DATA_DIR / "gold"
EVAL_DIR = DATA_DIR / "eval_cases"
MASTERDATA_DIR = DATA_DIR / "masterdata"
STORE_DIR = DATA_DIR / "store"
FEEDBACK_DIR = DATA_DIR / "feedback"
DEBUG_DIR = Path(os.getenv("DEBUG_DIR", DATA_DIR / "debug"))
SCHEMAS_DIR = DATA_DIR / "schemas"
# 启用后 process_booking 将把解析中间结果写入 DEBUG_DIR
PARSE_DEBUG_DUMP = os.getenv("PARSE_DEBUG_DUMP", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
BOOKING_DATA_SCHEMA_PATH = SCHEMAS_DIR / "booking_data.schema.json"

# 与 kb_pdf_to_vdb 对齐的 OpenAI 兼容网关配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
# 多模态默认 glm-4.6v-flash（支持 file_url 直接吃 PDF）
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "glm-4.6v-flash").strip()
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.1"))

# 兼容旧变量名（若只配了旧名仍可用）
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip() or OPENAI_API_KEY
LLM_API_BASE = (os.getenv("LLM_API_BASE", "").strip() or OPENAI_BASE_URL).strip().rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "").strip() or OPENAI_MODEL

# pdf=file_url 直传整份 PDF（推荐，多页一份）；vision=每页渲图；text=纯文本（丢版面）
LLM_INPUT_MODE = os.getenv("LLM_INPUT_MODE", "pdf").strip().lower()
# pdf 失败时是否自动回退 vision
LLM_PDF_FALLBACK_VISION = os.getenv("LLM_PDF_FALLBACK_VISION", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# vision 模式：PDF→PNG 渲染倍率（默认 1.5；越大越清、图越大）
LLM_VISION_ZOOM = float(os.getenv("LLM_VISION_ZOOM", "1.5"))


def has_llm_key() -> bool:
    return bool(LLM_API_KEY)


def make_openai_client(*, timeout_s: float = 180.0):
    """OpenAI 兼容客户端；trust_env=False 避免本机/HTTP_PROXY 拦智谱等外网。"""
    import httpx
    from openai import OpenAI

    return OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_API_BASE,
        http_client=httpx.Client(trust_env=False, timeout=timeout_s),
    )


def parse_backend() -> str:
    """默认 llm（主路径）；fixture 仅供离线单测。"""
    raw = os.getenv("PARSE_BACKEND", "llm").strip().lower()
    return raw or "llm"


PARSE_BACKEND = parse_backend()
SUBMIT_STRATEGY = os.getenv("SUBMIT_STRATEGY", "manual").lower()
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.55"))

# all=单进程（默认，测试友好）；tool=仅解析校验；agent=会话编排（parse 走 TOOL_BASE_URL）
APP_ROLE = os.getenv("APP_ROLE", "all").strip().lower()
# Agent 调用 Tool 服务的根，如 http://127.0.0.1:8001
TOOL_BASE_URL = os.getenv("TOOL_BASE_URL", "").strip().rstrip("/")
TOOL_HTTP_TIMEOUT_S = float(os.getenv("TOOL_HTTP_TIMEOUT_S", "120"))


def _type_allows_null(prop: dict[str, Any]) -> bool:
    t = prop.get("type")
    if t == "null":
        return True
    if isinstance(t, list):
        return "null" in t
    return False


def _load_booking_field_lists(
    schema_path: Path = BOOKING_DATA_SCHEMA_PATH,
) -> tuple[list[str], list[str], list[str]]:
    """从 JSON Schema 派生字段表，避免与 schema 双份维护。

    - BOOKING_FIELD_KEYS: properties 顺序
    - OPTIONAL_NULL_KEYS: type 含 null（hs_code/marks/freight）
    - REQUIRED_KEYS: 业务上必须有值（非 null）；voyage 允许 \"\" 故排除
    """
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    props: dict[str, Any] = schema.get("properties") or {}
    field_keys = list(props.keys())
    optional_null = [k for k, p in props.items() if _type_allows_null(p)]
    # voyage 在 schema 中为 string 且可空串，STRUCT-REQUIRED 不把它当「缺值」
    required_keys = [
        k for k in field_keys if k not in optional_null and k != "voyage"
    ]
    return field_keys, required_keys, optional_null


BOOKING_FIELD_KEYS, REQUIRED_KEYS, OPTIONAL_NULL_KEYS = _load_booking_field_lists()
