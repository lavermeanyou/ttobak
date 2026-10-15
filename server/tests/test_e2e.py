"""통합 테스트: FastAPI TestClient 로 /api/health, /api/words, /api/target, /api/analyze 와 정적 파일을 검사한다.

샘플(web/samples/samples.json)마다:
  - kind == "normal": accuracy ≥ 70, 오류 카드(error 수준) 수가 적을 것
  - kind == "error" : expect.phones 의 목표 음소가 sub/del/weak 로 잡힐 것
                      (+ expect.heard: 들린 음소, expect.status, expect.insert: 삽입 음소,
                         expect.feedback_kind / intonation_below: 억양 오류)
샘플이 없으면 bash scripts/make_samples.sh 로 만든다(macOS say 필요).
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from server import app as app_mod
from server import pipeline

ROOT = Path(__file__).resolve().parents[2]
SAMPLES_JSON = ROOT / "web" / "samples" / "samples.json"
SAMPLES = json.loads(SAMPLES_JSON.read_text(encoding="utf-8"))["samples"]

PHONE_KEYS = {"idx", "phone", "jamo", "syl", "start", "end", "status", "heard", "heard_jamo", "gop", "tip"}
TOP_KEYS = {"target", "heard", "phones", "insertions", "syllables", "acoustic", "lips", "scores", "feedback", "meta"}
SCORE_KEYS = {"overall", "accuracy", "clarity", "intonation", "lips"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app_mod.app) as c:
        t0 = time.time()
        while time.time() - t0 < 180:
            if c.get("/api/health").json().get("model") == "loaded":
                break
            time.sleep(0.5)
        assert c.get("/api/health").json()["model"] == "loaded", "모델이 3분 안에 로드되지 않음"
        yield c


def _wav_bytes(x: np.ndarray, sr: int, subtype: str = "PCM_16", fmt: str = "WAV") -> bytes:
    buf = io.BytesIO()
    sf.write(buf, x, sr, subtype=subtype, format=fmt)
    return buf.getvalue()


def _post(client, data: bytes, text: str, **fields):
    form = {"text": text, **{k: v for k, v in fields.items() if v is not None}}
    return client.post("/api/analyze", files={"audio": ("speech.wav", data, "audio/wav")}, data=form)


def _sample_bytes(s: dict) -> bytes:
    p = ROOT / "web" / s["file"]
    if not p.exists() and shutil.which("say"):
        subprocess.run(["bash", str(ROOT / "scripts" / "make_samples.sh")], check=True)
    assert p.exists(), f"샘플 파일 없음: {p} (bash scripts/make_samples.sh)"
    return p.read_bytes()


def _check_shape(r: dict):
    assert TOP_KEYS <= set(r), TOP_KEYS - set(r)
    json.dumps(r, allow_nan=False)                     # 순수 JSON 이어야 한다
    t = r["target"]
    assert {"text", "pron", "phones", "syllables"} <= set(t)
    assert len(r["phones"]) == len(t["phones"])
    for i, p in enumerate(r["phones"]):
        assert PHONE_KEYS <= set(p), PHONE_KEYS - set(p)
        assert p["idx"] == i and p["phone"] == t["phones"][i]
        assert p["status"] in ("ok", "weak", "sub", "del")
        assert isinstance(p["gop"], int) and 0 <= p["gop"] <= 100
        assert 0 <= p["start"] <= p["end"] <= r["acoustic"]["duration"] + 1e-6
        if p["status"] == "sub":
            assert p["heard"] and p["heard"] != p["phone"] and p["heard_jamo"]
        if p["status"] == "del":
            assert p["heard"] is None and p["heard_jamo"] is None
        if p["status"] == "ok":
            assert p["tip"] is None
        else:
            assert isinstance(p["tip"], str) and p["tip"]
    for a, b in zip(r["phones"], r["phones"][1:]):
        assert a["end"] <= b["start"] + 1e-6           # 구간이 겹치지 않음
    for ins in r["insertions"]:
        assert {"after", "phone", "jamo"} <= set(ins) and -1 <= ins["after"] < len(t["phones"])
    assert [s["phones"] for s in r["syllables"]] == [s["phones"] for s in t["syllables"]]
    for s in r["syllables"]:
        assert s["status"] in ("ok", "warn", "error") and s["text"]
    assert set(r["scores"]) == SCORE_KEYS
    for k, v in r["scores"].items():
        assert v is None or (isinstance(v, int) and 0 <= v <= 100), (k, v)
    assert 1 <= len(r["feedback"]) <= 4
    for f in r["feedback"]:
        assert f["level"] in ("error", "warn", "info") and f["title"] and isinstance(f["phones"], list)
    assert isinstance(r["heard"]["phones"], list)
    assert r["heard"]["pron_guess"] is None or isinstance(r["heard"]["pron_guess"], str)
    assert r["lips"] == {"available": False, "series": None, "checks": [], "score": None} or r["lips"]["available"]
    assert isinstance(r["meta"]["elapsed_ms"], int) and r["meta"]["model"]


# ── 기본 API ──────────────────────────────────────────────
def test_health(client):
    h = client.get("/api/health").json()
    assert h["ok"] is True and h["model"] == "loaded"


def test_words(client):
    d = client.get("/api/words").json()
    assert len(d["categories"]) >= 8 and len(d["words"]) >= 45
    ids = {w["id"] for w in d["words"]}
    for s in SAMPLES:
        assert s["word_id"] in ids, s["id"]            # 샘플의 word_id 는 words.json 에 있어야 한다
    w = next(w for w in d["words"] if w["id"] == "gungmul")
    assert w["pron"] == "궁물" and w["phones"] == ["G", "U", "NG", "M", "U", "L"]


def test_target(client):
    t = client.get("/api/target", params={"text": "국물"}).json()
    assert t["pron"] == "궁물" and t["phones"] == ["G", "U", "NG", "M", "U", "L"]
    assert [s["text"] for s in t["syllables"]] == ["국", "물"]
    t = client.get("/api/target", params={"text": "밥 먹었어요?"}).json()
    assert t["pron"] == "밥 머거써요"
    r = client.get("/api/target", params={"text": "abc"})
    assert r.status_code == 422 and r.json()["error"] == "empty_target"


@pytest.mark.parametrize("path", ["/", "/index.html", "/app.js", "/styles.css", "/vendor/face_landmarker.task",
                                  "/vendor/tasks-vision/vision_bundle.mjs", "/samples/samples.json",
                                  "/samples/" + Path(SAMPLES[0]["file"]).name])
def test_static(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    if path.endswith(".mjs") or path.endswith(".js"):
        assert "javascript" in r.headers["content-type"]
    if path == "/":
        assert "<html" in r.text.lower()


# ── 샘플 분석 ─────────────────────────────────────────────
@pytest.mark.parametrize("s", SAMPLES, ids=[s["id"] for s in SAMPLES])
def test_sample(client, s):
    res = _post(client, _sample_bytes(s), s["text"], pron=s.get("pron"), word_id=s.get("word_id"),
                voice="female", sentence_type=s.get("sentence_type"))
    assert res.status_code == 200, res.text
    r = res.json()
    _check_shape(r)
    # target.pron 은 실제로 판정에 쓴 발음형(허용 발음·이어 말하기 변이 중 음성에 맞는 것), 요청은 pron_requested
    assert r["target"]["pron_requested"] == s["pron"]
    assert r["target"]["pron"] == s["pron"] or r["target"]["variant_notes"]
    if s["kind"] == "normal":
        assert r["scores"]["accuracy"] >= 70, (s["id"], r["scores"], [(p["phone"], p["status"]) for p in r["phones"]])
        assert sum(f["level"] == "error" for f in r["feedback"]) == 0, r["feedback"]
        return
    exp = s["expect"]
    for i in exp.get("phones", []):
        p = r["phones"][i]
        assert p["status"] in ("sub", "del", "weak"), (s["id"], p)
        if "heard" in exp:
            assert p["status"] == "sub" and p["heard"] == exp["heard"], (s["id"], p)
        if "status" in exp:
            assert p["status"] == exp["status"], (s["id"], p)
        assert r["syllables"][p["syl"]]["status"] in ("warn", "error")
        assert any(i in f["phones"] for f in r["feedback"]), (s["id"], r["feedback"])
    if "insert" in exp:
        assert any(x["phone"] == exp["insert"] for x in r["insertions"]), r["insertions"]
    if "feedback_kind" in exp:
        assert any(f.get("kind") == exp["feedback_kind"] for f in r["feedback"]), r["feedback"]
    if "intonation_below" in exp:
        assert r["scores"]["intonation"] is not None and r["scores"]["intonation"] < exp["intonation_below"]


def test_error_samples_score_below_normal(client):
    """같은 단어의 정상 샘플이 오류 흉내보다 정확도가 높아야 한다."""
    by_word: dict[str, dict[str, list[int]]] = {}
    for s in SAMPLES:
        r = _post(client, _sample_bytes(s), s["text"], pron=s.get("pron"), word_id=s["word_id"],
                  sentence_type=s.get("sentence_type")).json()
        by_word.setdefault(s["word_id"], {}).setdefault(s["kind"], []).append(r["scores"]["overall"])
    pairs = 0
    for wid, d in by_word.items():
        if "normal" in d and "error" in d:
            pairs += 1
            assert min(d["normal"]) > max(d["error"]), (wid, d)
    assert pairs >= 5


# ── 입력 변형·오류 ─────────────────────────────────────────
def _ok_sample() -> dict:
    return next(s for s in SAMPLES if s["id"] == "ok-sori")


def test_resampled_stereo_float_input(client):
    """44.1 kHz 스테레오 float 파일도 16k mono 로 바꿔 같은 판정을 낸다."""
    s = _ok_sample()
    x, sr = sf.read(io.BytesIO(_sample_bytes(s)), dtype="float32")
    import torch
    import torchaudio.functional as AF
    y = AF.resample(torch.from_numpy(x), sr, 44100).numpy()
    st = np.stack([y, 0.8 * y], axis=1)
    r = _post(client, _wav_bytes(st, 44100, subtype="FLOAT"), s["text"], word_id=s["word_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scores"]["accuracy"] >= 70 and body["meta"]["sr_in"] == 44100


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")
def test_ffmpeg_fallback_ogg(client, tmp_path):
    """soundfile 이 못 읽는 형식(m4a)은 ffmpeg 로 변환해 분석한다."""
    s = _ok_sample()
    src = tmp_path / "in.wav"
    src.write_bytes(_sample_bytes(s))
    dst = tmp_path / "out.m4a"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-c:a", "aac", str(dst)], check=True)
    r = client.post("/api/analyze", files={"audio": ("speech.m4a", dst.read_bytes(), "audio/mp4")},
                    data={"text": s["text"], "word_id": s["word_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["scores"]["accuracy"] >= 70


def test_no_speech_silence(client):
    r = _post(client, _wav_bytes(np.zeros(16000 * 2, dtype=np.float32), 16000), "국물")
    assert r.status_code == 422 and r.json()["error"] == "no_speech" and r.json()["message"]


def test_no_speech_noise(client):
    rng = np.random.default_rng(0)
    r = _post(client, _wav_bytes((0.003 * rng.standard_normal(32000)).astype(np.float32), 16000), "국물")
    assert r.status_code == 422 and r.json()["error"] == "no_speech"


def test_no_speech_hum(client):
    """유성음으로 잡히는 순음(전원 험)은 인식기가 음소를 거의 못 찾으므로 no_speech(예전: 분석 결과를 냄)."""
    t = np.arange(32000) / 16000
    for x in ((0.1 * np.sin(2 * np.pi * 120 * t)), (0.05 * np.sign(np.sin(2 * np.pi * 100 * t)))):
        r = _post(client, _wav_bytes(x.astype(np.float32), 16000), "소리")
        assert r.status_code == 422 and r.json()["error"] == "no_speech", r.text


def test_bad_audio(client):
    r = _post(client, b"this is not audio at all" * 10, "국물")
    assert r.status_code == 422 and r.json()["error"] == "bad_audio"
    r = _post(client, _wav_bytes(np.zeros(400, dtype=np.float32), 16000), "국물")   # 0.025초
    assert r.status_code == 422 and r.json()["error"] == "bad_audio"
    r = client.post("/api/analyze", data={"text": "국물"})
    assert r.status_code == 422 and r.json()["error"] == "bad_audio"


def test_empty_target(client):
    s = _ok_sample()
    r = _post(client, _sample_bytes(s), "hello 123")
    assert r.status_code == 422 and r.json()["error"] == "empty_target"
    r = _post(client, _sample_bytes(s), "")
    assert r.status_code == 422 and r.json()["error"] == "empty_target"


def test_word_id_fills_text_and_pron(client):
    s = next(x for x in SAMPLES if x["id"] == "ok-ot")
    r = _post(client, _sample_bytes(s), "", word_id="ot").json()
    assert r["target"]["text"] == "옷" and r["target"]["pron"] == "옫" and r["target"]["word_id"] == "ot"


def test_bad_pron_falls_back_to_g2p(client):
    s = _ok_sample()
    r = _post(client, _sample_bytes(s), "소리", pron="닭")   # 대표음이 아닌 받침 → 철자에서 다시 만든다
    assert r.status_code == 200 and r.json()["target"]["pron"] == "소리"


def test_lips_payload(client):
    s = next(x for x in SAMPLES if x["id"] == "ok-oi")
    frames = []
    for k in range(40):
        t = k / 30
        frames.append({"t": round(t, 3), "open": 0.02 + 0.1 * (0.4 < t < 0.9), "width": 0.95 - 0.15 * (0.4 < t < 0.7),
                       "pucker": 0.5 * (0.4 < t < 0.7), "funnel": 0.1, "jaw": 0.2, "close": 0.0})
    lips = json.dumps({"fps": 30, "frames": frames, "neutral": {"open": 0.02, "width": 0.95}})
    r = _post(client, _sample_bytes(s), s["text"], word_id=s["word_id"], lips=lips).json()
    assert r["lips"]["available"] is True and r["lips"]["series"]["t"]
    assert r["scores"]["lips"] is None or 0 <= r["scores"]["lips"] <= 100
    # 깨진 lips 는 무시하고 분석
    r2 = _post(client, _sample_bytes(s), s["text"], word_id=s["word_id"], lips="{broken")
    assert r2.status_code == 200 and r2.json()["lips"]["available"] is False


def test_model_loading_returns_503(client, monkeypatch):
    monkeypatch.setattr(app_mod, "model_status", lambda: "loading")
    monkeypatch.setattr(app_mod, "start_model_loading", lambda: None)
    s = _ok_sample()
    r = _post(client, _sample_bytes(s), s["text"])
    assert r.status_code == 503 and r.json()["error"] == "model_loading" and "준비" in r.json()["message"]


# ── 파이프라인 단위 ───────────────────────────────────────
def test_phones_to_hangul():
    assert pipeline.phones_to_hangul(["G", "U", "NG", "M", "U", "L"]) == "궁물"
    assert pipeline.phones_to_hangul(["A", "p", "EU"]) == "아브"
    assert pipeline.phones_to_hangul(["JJ", "A", "D", "A"]) == "짜다"
    assert pipeline.phones_to_hangul(["N", "DD"]) == "ㄴㄸ"     # 모음 없는 자음은 자모 그대로
    assert pipeline.phones_to_hangul([]) == ""


def test_decide_status_rules():
    """CTC margin 만으로 판정(사람 낭독 보정): sub/del 은 margin < −3.0, weak 는 gop < 45, 자유 인식은 쓰지 않음."""
    d = pipeline.decide_status
    assert pipeline.SUB_MARGIN == -3.0
    assert d({"alt_margin": -4.0, "gop": 3, "alt": "Ph"}, "match", "B", "B") == ("sub", "Ph")
    assert d({"alt_margin": -4.0, "gop": 3, "alt": "<del>"}, "match", "N", "N") == ("del", None)
    assert d({"alt_margin": -2.0, "gop": 27, "alt": "Ph"}, "match", "B", "B") == ("weak", "B")   # 애매 → weak
    # 자유 인식(greedy)이 sub/del 이라고 해도 CTC margin 이 문턱을 넘지 않으면 weak — 예전 계약 규칙은
    # 사람 낭독 오탐을 두 배로 늘렸다(보정셋 sub+del 2.9 % → 6.7 %)
    assert d({"alt_margin": -2.0, "gop": 27, "alt": "Ph"}, "sub", "BB", "B") == ("weak", "B")
    assert d({"alt_margin": -2.0, "gop": 27, "alt": "Ph"}, "del", None, "B") == ("weak", "B")
    assert d({"alt_margin": 3.0, "gop": 98, "alt": "Ph"}, "sub", "Ph", "B") == ("ok", "B")
    assert d({"alt_margin": 3.0, "gop": 98, "alt": "Ph"}, "match", "B", "B") == ("ok", "B")


@pytest.mark.parametrize("target,alt,ctx,ok", [
    ("DD", "D", {"idx": 3, "prev": "t", "next": "A"}, True),                 # 했다[핻따] — 받침 뒤 된소리
    ("D", "DD", {"idx": 3, "prev": "k", "next": "A"}, True),                 # 끊어 말한 어절 사이(박 다)
    ("DD", "D", {"idx": 0, "prev": None, "next": "A"}, False),               # 어두 ㄸ→ㄷ 는 오류(딸 → 달)
    ("JJ", "J", {"idx": 1, "prev": "A", "next": "A"}, False),                # 모음 뒤 ㅉ→ㅈ 는 오류
    ("JJ", "J", {"idx": 4, "prev": "L", "next": "EO", "tensified": True}, True),   # 결정[결쩡]
    ("JJ", "J", {"idx": 4, "prev": "L", "next": "EO", "tensified": False}, False),  # 철자도 ㅉ(일찍 등)
    ("H", "<del>", {"idx": 3, "prev": "N", "next": "oA"}, True),             # 전화[저놔]
    ("H", "<del>", {"idx": 0, "prev": None, "next": "A"}, False),            # 발화 첫 ㅎ 탈락은 오류(하나 → 아나)
    ("H", "<del>", {"idx": 2, "prev": "p", "next": "A"}, False),
    ("t", "<del>", {"idx": 2, "prev": "A", "next": "GG", "coda": True}, True),   # 있고[읻꼬] → [이꼬]
    ("t", "k", {"idx": 2, "prev": "A", "next": "GG", "coda": True}, True),       # 있고[익꼬]
    ("t", "<del>", {"idx": 2, "prev": "A", "next": None, "coda": True}, False),  # 끝 받침 탈락은 오류
    ("N", "NG", {"idx": 2, "prev": "iEO", "next": "G", "coda": True}, True),     # 연구[영구]
    ("N", "NG", {"idx": 2, "prev": "A", "next": None, "coda": True}, False),     # 단독 받침 ㄴ→ㅇ 은 오류
    ("N", "M", {"idx": 2, "prev": "A", "next": "B", "coda": True}, True),        # 신발[심발]
    ("E", "euI", {"idx": 5, "prev": "M", "next": "J", "word_last": True}, True), # 조사 '에' ↔ '의'
    ("E", "euI", {"idx": 1, "prev": "M", "next": "J", "word_last": False}, False),
])
def test_accepted_variants(target, alt, ctx, ok):
    assert bool(pipeline.accepted_variant(target, alt, ctx)) is ok
    st, heard = pipeline.decide_status({"alt_margin": -6.0, "gop": 1, "alt": alt}, "match", target, target, ctx)
    assert (st == "ok") is ok


def test_trim_for_recognizer_and_time_offset(client):
    """녹음 앞뒤 긴 무음은 인식기에 넣기 전에 자르고(말소리 ±0.75초), 시각은 원래 녹음 기준으로 되돌린다.
    예전: 정상 '소리' 뒤에 6.6초 무음 → ㅗ margin +1.6 → −0.2 로 sub, 억양 null(유성 비율이 녹음 전체 기준)."""
    s = _ok_sample()
    x, sr = sf.read(io.BytesIO(_sample_bytes(s)), dtype="float32")
    off, xr = pipeline.trim_for_recognizer(x)
    assert off == 0.0 and len(xr) == len(x)                  # 보통 녹음(앞뒤 0.4초)은 그대로
    lead, tail = np.zeros(int(1.0 * sr), np.float32), np.zeros(int(6.6 * sr), np.float32)
    long_x = np.concatenate([lead, x, tail])
    off2, xr2 = pipeline.trim_for_recognizer(long_x)
    assert 0.5 < off2 < 1.0 and len(xr2) / sr < len(x) / sr + 1.2
    base = _post(client, _sample_bytes(s), s["text"], word_id=s["word_id"]).json()
    r = _post(client, _wav_bytes(long_x, sr), s["text"], word_id=s["word_id"]).json()
    assert [p["status"] for p in r["phones"]] == [p["status"] for p in base["phones"]] == ["ok"] * 4
    assert r["scores"]["intonation"] is not None
    for a, b in zip(base["phones"], r["phones"]):            # 시각은 앞 무음 1초만큼 밀려야 한다
        assert abs((b["start"] - a["start"]) - 1.0) <= 0.03 and abs((b["end"] - a["end"]) - 1.0) <= 0.03
    assert r["meta"]["analyzed_span"][0] == pytest.approx(off2, abs=1e-3)


def test_phase_inverted_stereo_is_not_silence(client):
    """L = −R 스테레오(채널 평균이 0)도 말소리로 분석한다(예전: no_speech)."""
    s = _ok_sample()
    x, sr = sf.read(io.BytesIO(_sample_bytes(s)), dtype="float32")
    st = np.stack([x, -x], axis=1)
    r = _post(client, _wav_bytes(st, sr, subtype="FLOAT"), s["text"], word_id=s["word_id"])
    assert r.status_code == 200, r.text
    assert r.json()["scores"]["accuracy"] >= 70
    mono = pipeline.prepare_audio(np.stack([x, 0.5 * x], axis=1), sr)       # 보통 스테레오는 여전히 평균
    assert np.allclose(mono, pipeline.prepare_audio(0.75 * x, sr), atol=1e-4)


def test_clipped_recording_gets_first_card(client):
    """크게 찌그러진 녹음은 '소리가 너무 커서 찌그러졌어요' 카드를 맨 앞에 낸다(카드 수 제한에 밀리지 않게)."""
    s = next(x for x in SAMPLES if x["id"] == "err-hello-coda")
    x, sr = sf.read(io.BytesIO(_sample_bytes(s)), dtype="float32")
    y = np.clip(x * 12, -1, 1)
    r = _post(client, _wav_bytes(y, sr), s["text"], word_id=s["word_id"]).json()
    assert r["acoustic"]["loudness"]["clipped"] is True
    assert r["feedback"][0]["kind"] == "loudness" and "찌그러" in r["feedback"][0]["title"]
    ok = _post(client, _sample_bytes(_ok_sample()), "소리", word_id="sori").json()
    assert ok["acoustic"]["loudness"]["clipped"] is False
    assert not any("찌그러" in f["title"] for f in ok["feedback"])


def test_api_errors_have_contract_shape(client):
    """프레임워크 오류도 {"error", "message"} 모양(한국어)으로 돌려준다."""
    big_lips = "x" * (1024 * 1024 + 10)
    r = _post(client, _sample_bytes(_ok_sample()), "소리", lips=big_lips)
    assert r.status_code in (400, 413) and r.json()["error"] == "too_large" and r.json()["message"]
    r = client.get("/api/target", params={"text": "가" * 201})
    assert r.status_code == 422 and r.json()["error"] == "too_long"
    r = _post(client, _sample_bytes(_ok_sample()), "가" * 201)
    assert r.status_code == 422 and r.json()["error"] == "too_long"
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    # 200자 안이어도 음소가 너무 많으면(분석 시간이 음소 수의 제곱으로 늘어남) 모델을 돌리기 전에 거절
    long_text = " ".join(["안녕하세요"] * 13)                     # 77자, 130음소
    r = _post(client, _sample_bytes(_ok_sample()), long_text)
    assert r.status_code == 422 and r.json()["error"] == "too_long"


def test_prepare_audio_variants():
    sr = 22050
    t = np.arange(sr) / sr
    x = 0.5 * np.sin(2 * np.pi * 220 * t)
    i16 = (x * 32767).astype(np.int16)
    a = pipeline.prepare_audio(i16, sr)
    assert a.dtype == np.float32 and abs(len(a) - 16000) <= 1 and 0.45 < np.abs(a).max() < 0.55
    b = pipeline.prepare_audio(np.stack([i16, i16], axis=1), sr)
    assert np.allclose(a, b, atol=1e-4)
    with pytest.raises(pipeline.PipelineError):
        pipeline.prepare_audio(np.zeros(100, dtype=np.float32), 16000)
    with pytest.raises(pipeline.PipelineError):
        pipeline.prepare_audio(np.zeros(16000, dtype=np.float32), 0)


def test_speech_presence():
    sr = 16000
    assert not pipeline.speech_presence(np.zeros(sr, dtype=np.float32))["ok"]
    t = np.arange(sr) / sr
    tone = (0.3 * np.sign(np.sin(2 * np.pi * 150 * t)) * (np.abs(t - 0.5) < 0.2)).astype(np.float32)
    p = pipeline.speech_presence(tone)
    assert p["ok"] and p["voiced_sec"] >= 0.2


# ── 리뷰 반영: 발음 변이 선택·ㄹㄹ·포먼트 측정 실패·억양 정보 전달 ─────────
class _FakeRec:
    """seq_logps 만 흉내: 지정한 음소열이 가장 그럴듯하다고 답한다."""
    def __init__(self, best: list[str]):
        self.best = best

    def seq_logps(self, em, seqs):
        return [0.0 if s == self.best else -5.0 - abs(len(s) - len(self.best)) for s in seqs]


def test_choose_variant_picks_allowed_and_connected_forms():
    from server import words
    from server.phones import pron_to_phones
    t = words.build_target("시계", "시계")
    new, notes = pipeline.choose_variant(_FakeRec(pron_to_phones("시게")[0]), None, "시계", t)
    assert new["pron"] == "시게" and notes and "허용 발음" in notes[0]
    t = words.build_target("밥 먹었어요?", "밥 머거써요")
    new, notes = pipeline.choose_variant(_FakeRec(pron_to_phones("밤 머거써요")[0]), None, "밥 먹었어요?", t)
    assert new["pron"] == "밤 머거써요" and "이어 말해" in notes[0]
    # 요청 발음형이 가장 그럴듯하면 그대로
    same, notes = pipeline.choose_variant(_FakeRec(pron_to_phones("시계")[0]), None, "시계", words.build_target("시계"))
    assert same["pron"] == "시계" and notes == []
    # 그 문장의 변이로 만들 수 없는 사용자 지정 발음형은 바꾸지 않는다
    custom = words.build_target("시계", "시개")
    out, notes = pipeline.choose_variant(_FakeRec(pron_to_phones("시게")[0]), None, "시계", custom)
    assert out is custom and notes == []


def test_r_after_l_rule():
    ph = ["D", "A", "L", "R", "I"]
    assert pipeline._r_after_l(ph, 3, "sub", "L") == ("ok", "R")
    assert pipeline._r_after_l(ph, 3, "sub", "N") == ("sub", "N")
    assert pipeline._r_after_l(["N", "A", "R", "A"], 2, "sub", "L") == ("sub", "L")


def test_reconcile_vowels_hides_gross_mismeasurement_only_when_phone_ok():
    vs = [{"idx": 1, "phone": "U", "f1": 1370, "f2": 1863, "ref": {"f1": 400, "f2": 1000}, "ok": False},
          {"idx": 3, "phone": "O", "f1": 683, "f2": 1170, "ref": {"f1": 470, "f2": 870}, "ok": False}]
    ph = [{"idx": 1, "status": "ok", "gop": 89}, {"idx": 3, "status": "sub", "gop": 0}]
    pipeline._reconcile_vowels(vs, ph)
    assert vs[0]["f1"] is None and vs[0]["ok"] is None and vs[0]["unreliable"] == "measure" and vs[0]["f1_raw"] == 1370
    assert vs[1]["f1"] == 683 and vs[1]["ok"] is False          # 음소도 틀렸으면 포먼트 증거는 그대로 둔다


def test_target_rejects_digits(client):
    r = client.get("/api/target", params={"text": "오늘은 10월 9일이에요"})
    assert r.status_code == 422 and r.json()["error"] == "empty_target" and "한글로" in r.json()["message"]
    s = _ok_sample()
    r = _post(client, _sample_bytes(s), "커피 2잔 주세요")
    assert r.status_code == 422 and "2" in r.json()["message"]


def test_normal_samples_vowels_mostly_in_range(client):
    """정상 샘플의 포먼트 판정이 대부분 '기준 범위'여야 한다(예전엔 10개 중 7개 샘플에 '벗어남')."""
    bad = []
    for s in [x for x in SAMPLES if x["kind"] == "normal"]:
        r = _post(client, _sample_bytes(s), s["text"], pron=s.get("pron"), word_id=s.get("word_id"),
                  sentence_type=s.get("sentence_type")).json()
        st = {p["idx"]: p["status"] for p in r["phones"]}
        bad += [(s["id"], v["phone"]) for v in r["acoustic"]["vowels"] if v["ok"] is False and st[v["idx"]] == "ok"]
    assert len(bad) <= 1, bad


def test_question_kind_and_tune_reported(client):
    s = next(x for x in SAMPLES if x["id"] == "ok-name-fall")
    r = _post(client, _sample_bytes(s), s["text"], pron=s["pron"], word_id=s["word_id"], sentence_type="question").json()
    assert r["target"]["question_kind"] == "wh" and r["target"]["tune"] == "free"
    assert not any(f["kind"] == "intonation" for f in r["feedback"])
    s = next(x for x in SAMPLES if x["id"] == "err-like-flat")
    r = _post(client, _sample_bytes(s), s["text"], pron=s["pron"], word_id=s["word_id"], sentence_type="question").json()
    assert r["target"]["question_kind"] == "yn" and r["target"]["tune"] == "rise"
    assert r["feedback"][0]["title"] == "소리는 모두 정확했어요"
    assert "끝을 내려서도" not in r["feedback"][0]["body"]
