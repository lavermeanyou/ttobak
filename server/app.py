"""FastAPI 앱 (CONTRACT 10절): /api/* + web/ 정적 서빙.

실행(프로젝트 루트에서):  .venv/bin/uvicorn server.app:app --port 8765
다른 위치에서:            .venv/bin/uvicorn server.app:app --app-dir /path/to/ttobak --port 8765
모든 파일 경로는 이 파일 위치(Path(__file__)) 기준이라 실행 위치와 상관없다.

모델(약 1.2GB)은 시작할 때 백그라운드 스레드에서 올린다. 그동안 /api/health 는 "loading",
/api/analyze 는 503 + 한국어 안내를 돌려준다. 환경변수 TTOBAK_PRELOAD=0 이면 미리 올리지 않고
첫 분석 요청 때 올린다(테스트용).
"""
from __future__ import annotations

import io
import json
import logging
import mimetypes
import os
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import pipeline, recognizer, words

log = logging.getLogger("ttobak")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
SAMPLES_DIR = WEB_DIR / "samples"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024      # 20MB (16k mono 16bit 기준 10분 — 실제로는 MAX_SEC 30초에서 막힌다)
FFMPEG_TIMEOUT_SEC = 30
MAX_TEXT_CHARS = 200                     # /api/target·/api/analyze 목표 문장 글자 수 상한(프런트 자유 입력은 40자)
# /api/analyze 목표 음소 수 상한. CTC-GOP 는 음소마다 40개 대안 음소열을 계산해 시간이 음소 수의 제곱 × 녹음 길이로 는다.
# 실측(Apple M3, 29.5초 녹음): 100음소 6.4초, 150음소 22초, 330음소(200자) 10분 넘게 걸림 → 서버가 사실상 멈춘다.
# 120음소 ≈ 50음절(자유 입력 40자 상한보다 넉넉함). 오프라인 평가(pipeline.analyze 직접 호출)에는 적용하지 않는다.
MAX_TARGET_PHONES = 120

# 정적 파일 MIME (시스템 mimetypes 표가 낡은 환경 대비)
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/octet-stream", ".task")
mimetypes.add_type("audio/wav", ".wav")


# ── 모델 백그라운드 로딩 ───────────────────────────────────
_model = {"status": "loading", "error": None, "started": None, "seconds": None}
_model_lock = threading.Lock()
_loader: threading.Thread | None = None


def _load_model() -> None:
    _model["started"] = time.time()
    try:
        rec = recognizer.get_recognizer()
        _model.update(status="loaded", seconds=round(time.time() - _model["started"], 1))
        log.info("인식 모델 로드 완료 (%s, %.1f초)", getattr(rec, "device", "?"), _model["seconds"])
    except Exception as e:  # pragma: no cover - 모델 파일 문제 등
        log.exception("인식 모델 로드 실패")
        _model.update(status="error", error=str(e))


def start_model_loading() -> None:
    """모델 로딩 스레드를 (한 번만) 시작한다."""
    global _loader
    with _model_lock:
        if recognizer.is_loaded():
            _model["status"] = "loaded"
            return
        if _loader is not None and _loader.is_alive():
            return
        _model.update(status="loading", error=None)
        _loader = threading.Thread(target=_load_model, name="ttobak-model-loader", daemon=True)
        _loader.start()


def model_status() -> str:
    if recognizer.is_loaded():
        return "loaded"
    return "error" if _model["status"] == "error" else "loading"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("TTOBAK_PRELOAD", "1") != "0":
        start_model_loading()
    yield


app = FastAPI(title="또박 — 발음 연습 데모", lifespan=lifespan)


def _err(code: str, message: str, status: int = 422) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


# /api/* 의 프레임워크 오류도 {"error", "message"} 모양으로 돌려준다(프런트는 message 를 그대로 보여 준다).
# 실측: 2MB 짜리 lips 필드 → Starlette 가 400 {"detail": "Part exceeded maximum size of 1024KB."} (영어, 계약 밖 모양),
# /api/target?text=(201자 이상) → 422 {"detail": [...]}.
@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if not request.url.path.startswith("/api/"):
        return await http_exception_handler(request, exc)
    detail = str(exc.detail or "")
    if "exceeded maximum size" in detail or exc.status_code == 413:
        return _err("too_large", "보낸 자료가 너무 커요. 녹음을 짧게(30초 안) 해서 다시 시도해 주세요.", exc.status_code)
    if exc.status_code == 404:
        return _err("not_found", "없는 주소예요.", 404)
    if exc.status_code == 405:
        return _err("bad_request", "이 주소는 이 방식으로 부를 수 없어요.", 405)
    return _err("bad_request", "요청을 읽지 못했어요. 다시 시도해 주세요.", exc.status_code)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    if any("max_length" in str(e.get("type", "")) or "too_long" in str(e.get("type", "")) for e in exc.errors()):
        return _err("too_long", f"글자가 너무 길어요. {MAX_TEXT_CHARS}자 안으로 입력해 주세요.")
    return _err("bad_request", "요청 내용을 읽지 못했어요. 다시 시도해 주세요.")


# ── 오디오 읽기 ───────────────────────────────────────────
def read_audio(data: bytes) -> tuple[np.ndarray, int] | None:
    """업로드 바이트 → (표본 배열, 표본율). soundfile 로 못 읽으면 ffmpeg 로 16k mono wav 변환. 실패 시 None."""
    if not data:
        return None
    try:
        x, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
        if np.asarray(x).size:
            return x, int(sr)
    except Exception:
        pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        log.warning("soundfile 로 읽지 못했고 ffmpeg 도 없음")
        return None
    with tempfile.TemporaryDirectory(prefix="ttobak-") as d:
        src, dst = Path(d) / "input", Path(d) / "out.wav"
        src.write_bytes(data)
        try:
            r = subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-i", str(src),
                                "-ac", "1", "-ar", str(pipeline.SR), "-c:a", "pcm_s16le", str(dst)],
                               capture_output=True, timeout=FFMPEG_TIMEOUT_SEC)
        except (subprocess.TimeoutExpired, OSError) as e:
            log.warning("ffmpeg 변환 실패: %s", e)
            return None
        if r.returncode != 0 or not dst.exists():
            log.warning("ffmpeg 변환 실패: %s", r.stderr.decode("utf-8", "replace")[-300:])
            return None
        try:
            x, sr = sf.read(str(dst), dtype="float32", always_2d=False)
        except Exception:
            return None
        return (x, int(sr)) if np.asarray(x).size else None


def _parse_lips(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        v = json.loads(raw)
    except (ValueError, TypeError):
        log.info("lips JSON 파싱 실패 — 입술 데이터 없이 분석")
        return None
    return v if isinstance(v, dict) else None


def _guess_type(text: str) -> str:
    t = (text or "").strip()
    if t.endswith("?") or t.endswith("？"):
        return "question"
    return "statement" if len(t.split()) > 1 else "word"


# ── API ───────────────────────────────────────────────────
@app.get("/api/health")
def health():
    st = model_status()
    body = {"ok": st != "error", "model": st}
    if st == "error":
        body["message"] = "분석 모델을 불러오지 못했어요. 서버 기록을 확인해 주세요."
    elif st == "loaded":
        rec = recognizer.get_recognizer()
        body["device"] = getattr(rec, "device", None)
    return body


@app.get("/api/words")
def api_words():
    return words.load_catalog()


@app.get("/api/target")
def api_target(text: str = Query("", max_length=MAX_TEXT_CHARS)):
    try:
        return words.build_target(text)
    except words.EmptyTargetError as e:
        return _err("empty_target", str(e) or pipeline.ERROR_MESSAGES["empty_target"])
    except ValueError:
        return _err("empty_target", "이 글자는 발음형으로 바꾸지 못했어요. 한글 낱말이나 문장으로 입력해 주세요.")


@app.post("/api/analyze")
def api_analyze(audio: UploadFile | None = File(None),
                text: str = Form(""),
                pron: str | None = Form(None),
                word_id: str | None = Form(None),
                voice: str = Form("female"),
                sentence_type: str | None = Form(None),
                lips: str | None = Form(None)):
    # 단어 목록 항목이면 그 발음형·문장 유형을 기본값으로 쓴다
    word = words.get_word(word_id) if word_id else None
    if word and not text.strip():
        text = word["text"]
    if word and not (pron and pron.strip()) and word.get("text") == text.strip():
        pron = word.get("pron")
    if not text.strip() and not (pron and pron.strip()):
        return _err("empty_target", pipeline.ERROR_MESSAGES["empty_target"])
    if len(text) > MAX_TEXT_CHARS or len(pron or "") > MAX_TEXT_CHARS:
        # 목표가 길면 CTC-GOP 계산(음소 수 × 40 개 음소열)이 수십 초로 늘어난다 — 연습 단위는 단어·짧은 문장
        return _err("too_long", f"연습할 문장이 너무 길어요. {MAX_TEXT_CHARS}자 안으로 나눠서 연습해 주세요.")
    stype = sentence_type if sentence_type in ("word", "statement", "question") else None
    if stype is None:
        stype = word.get("type") if word and word.get("type") in ("word", "statement", "question") else _guess_type(text)
    voice = voice if voice in ("male", "female", "child") else "female"
    # 단어 목록 항목의 억양 정보(계약 외): 의문문 종류(yn|wh), 끝 억양 자유(end_tune=free, 예: 인사)
    same_word = bool(word) and word.get("text", "").strip() == text.strip()
    question_kind = word.get("question_kind") if same_word else None
    end_tune = word.get("end_tune") if same_word else None

    if audio is None:
        return _err("bad_audio", "녹음 파일이 오지 않았어요. 다시 녹음해 주세요.")
    data = audio.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return _err("bad_audio", "녹음 파일이 너무 커요. 30초 안으로 짧게 녹음해 주세요.")
    decoded = read_audio(data)
    if decoded is None:
        return _err("bad_audio", pipeline.ERROR_MESSAGES["bad_audio"])
    wav, sr = decoded

    # 목표 문장 오류는 모델 없이도 알려 줄 수 있다
    try:
        tgt = words.build_target(text, pron)
    except words.EmptyTargetError as e:
        return _err("empty_target", str(e) or pipeline.ERROR_MESSAGES["empty_target"])
    except ValueError:
        tgt = None   # 잘못된 pron 은 pipeline 이 철자에서 다시 만든다
    if tgt is not None and len(tgt["phones"]) > MAX_TARGET_PHONES:
        return _err("too_long", "연습할 문장이 너무 길어요. 짧은 문장으로 나눠서 한 번에 한 문장씩 연습해 주세요.")

    st = model_status()
    if st != "loaded":
        if st == "error":
            return _err("model_error", "분석 모델을 불러오지 못해 지금은 분석할 수 없어요. 서버 기록을 확인해 주세요.", 503)
        start_model_loading()
        return _err("model_loading", "분석 모델을 준비하고 있어요. 10초쯤 뒤에 다시 시도해 주세요.", 503)

    try:
        result = pipeline.analyze(wav, sr, text, pron, _parse_lips(lips), voice=voice, sentence_type=stype,
                                  question_kind=question_kind, end_tune=end_tune)
    except Exception:
        log.exception("분석 실패 (text=%r)", text)
        return _err("internal", "분석 중에 문제가 생겼어요. 다시 녹음해 주세요.", 500)
    if "error" in result:
        a = np.asarray(wav, dtype=np.float64)
        peak = 20 * np.log10(np.max(np.abs(a)) + 1e-12) if a.size else None
        log.info("분석 거부 %s (text=%r, sr=%s, %.2f초, 최대 %s dBFS): %s", result.get("error"), text, sr,
                 (a.shape[0] / sr) if sr else 0, None if peak is None else round(float(peak), 1), result.get("message"))
        return JSONResponse(result, status_code=422)
    if word_id:
        result["target"]["word_id"] = word_id
    return result


# ── 정적 파일 (API 라우트 뒤에 마운트) ──────────────────────
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/samples", StaticFiles(directory=str(SAMPLES_DIR)), name="samples")
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
