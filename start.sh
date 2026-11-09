#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
CONSOLE_PYTHON="${CARLADT_SERVICE_PYTHON:-$PWD/.venv/bin/python}"
if ! "$CONSOLE_PYTHON" -c 'import fastapi,uvicorn,websockets,psutil' 2>/dev/null; then
  echo '缺少网页服务依赖。请先按照 README.md 创建 .venv 并安装 requirements.lock。' >&2
  exit 1
fi
if [[ ! -f frontend/dist/index.html ]]; then
  npm run build
fi
printf 'CARLA DT Console → http://127.0.0.1:%s\n' "${CARLADT_HTTP_PORT:-8765}"
exec "$CONSOLE_PYTHON" -m uvicorn backend.app:app --host 127.0.0.1 --port "${CARLADT_HTTP_PORT:-8765}" --timeout-graceful-shutdown 3
