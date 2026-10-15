#!/usr/bin/env bash
# 또박 서버 실행: 인식 모델이 없으면 내려받고(약 1.2 GB, 한 번만) uvicorn 을 띄운다.
#
#   bash scripts/run.sh                 # http://localhost:8765
#   PORT=9000 bash scripts/run.sh       # 다른 포트
#   PYTHON=/path/to/python bash scripts/run.sh
#
# 가상환경이 없으면 먼저: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"      # 마이크·카메라는 localhost(보안 문맥)에서만 켜진다
MODEL_ID="slplab/wav2vec2-xls-r-300m_phone-mfa_korean"
MODEL_DIR="$ROOT/models/ko-phone"

if [ ! -x "$PY" ]; then
  echo "파이썬을 찾을 수 없어요: $PY" >&2
  echo "먼저 가상환경을 만드세요: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# 모델 파일 확인(가중치 + 어휘 + 설정). 하나라도 없으면 내려받는다.
need_model=0
for f in config.json vocab.json preprocessor_config.json; do
  [ -s "$MODEL_DIR/$f" ] || need_model=1
done
if [ ! -s "$MODEL_DIR/pytorch_model.bin" ] && [ ! -s "$MODEL_DIR/model.safetensors" ]; then
  need_model=1
fi
if [ "$need_model" = 1 ]; then
  echo "인식 모델을 내려받는 중: $MODEL_ID → $MODEL_DIR (약 1.2 GB)"
  mkdir -p "$MODEL_DIR"
  "$PY" - "$MODEL_ID" "$MODEL_DIR" <<'EOF'
import sys
from huggingface_hub import snapshot_download
snapshot_download(sys.argv[1], local_dir=sys.argv[2])
EOF
fi

command -v ffmpeg >/dev/null 2>&1 || echo "참고: ffmpeg 가 없어 wav 가 아닌 녹음은 읽지 못해요(brew install ffmpeg)." >&2

echo "또박 서버: http://localhost:$PORT  (끝내려면 Ctrl+C)"
exec "$PY" -m uvicorn server.app:app --app-dir "$ROOT" --host "$HOST" --port "$PORT"
