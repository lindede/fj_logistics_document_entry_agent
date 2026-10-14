#!/usr/bin/env bash
# 启动 Agent 服务（会话 + 前端；开票经 HTTP 调 Tool）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${AGENT_PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
TOOL_URL="${TOOL_BASE_URL:-http://127.0.0.1:8001}"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export APP_ROLE=agent
# .env 里的 TOOL_BASE_URL 优先；否则用上面默认
export TOOL_BASE_URL="${TOOL_BASE_URL:-$TOOL_URL}"
export PARSE_BACKEND="${PARSE_BACKEND:-llm}"

echo "Agent → http://${HOST}:${PORT}  (APP_ROLE=agent TOOL_BASE_URL=${TOOL_BASE_URL})"
echo "请确认 Tool 已在 ${TOOL_BASE_URL} 运行（./scripts/start_tool.sh）"
exec uvicorn app.main_agent:app --host "$HOST" --port "$PORT" --reload
