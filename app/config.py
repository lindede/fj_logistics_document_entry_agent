from __future__ import annotations

import os
from pathlib import Path

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

# 与 kb_pdf_to_vdb 对齐的 OpenAI 兼容网关配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
# 多模态默认 glm-4.6v-flash（支持 file_url 直接吃 PDF）
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "glm-4.6v-flash").strip()
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.1"))

# 兼容旧变量名（若只配了旧名仍可用）
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip() or OPENAI_API_KEY
LLM_API_BASE = (os.getenv("LLM_API_BASE", "").strip() or OPENAI_BASE_URL).rstrip("/")
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


def has_llm_key() -> bool:
    return bool(LLM_API_KEY)


def parse_backend() -> str:
    """默认 llm（主路径）；fixture 仅供离线单测。heuristic 已弃用，勿作默认。"""
    raw = os.getenv("PARSE_BACKEND", "llm").strip().lower()
    return raw or "llm"


PARSE_BACKEND = parse_backend()
SUBMIT_STRATEGY = os.getenv("SUBMIT_STRATEGY", "manual").lower()
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.55"))

BOOKING_FIELD_KEYS = [
    "shipper",
    "consignee",
    "notify_party",
    "vessel",
    "voyage",
    "port_of_loading",
    "port_of_discharge",
    "containers",
    "packages_qty",
    "packages_unit",
    "goods_desc",
    "gross_weight",
    "weight_unit",
    "measurement",
    "measurement_unit",
    "hs_code",
    "marks",
    "freight",
]

REQUIRED_KEYS = [
    "shipper",
    "consignee",
    "notify_party",
    "vessel",
    "port_of_loading",
    "port_of_discharge",
    "containers",
    "packages_qty",
    "packages_unit",
    "goods_desc",
    "gross_weight",
    "weight_unit",
    "measurement",
    "measurement_unit",
]

OPTIONAL_NULL_KEYS = ["hs_code", "marks", "freight"]
