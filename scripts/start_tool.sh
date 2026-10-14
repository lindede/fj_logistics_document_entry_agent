#!/usr/bin/env bash
# 启动 Tool 服务（解析 + 校验）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${TOOL_PORT:-8001}"
HOST="${HOST:-127.0.0.1}"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# 先读 .env（不覆盖已在 shell 里 export 的变量）
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export APP_ROLE=tool
# 优先：命令行已 export > .env > 默认 llm（与 .env.example / app.config 一致）
# 离线联调：PARSE_BACKEND=fixture ./scripts/start_tool.sh
export PARSE_BACKEND="${PARSE_BACKEND:-llm}"

echo "Tool  → http://${HOST}:${PORT}  (APP_ROLE=tool PARSE_BACKEND=${PARSE_BACKEND})"
exec uvicorn app.main_tool:app --host "$HOST" --port "$PORT" --reload
