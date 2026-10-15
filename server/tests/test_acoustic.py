"""acoustic.analyze 테스트.

- macOS `say -v Yuna` 로 만든 실제 한국어 음성(아/이/우)으로 포먼트 대소 관계 확인
- 결정적 검증은 numpy 로 만든 합성 모음(펄스열 + 공명기)으로
"""
from __future__ import annotations

import json
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from server import acoustic

SR = 16000


# ── 합성 음성 ─────────────────────────────────────────────
def _arr(v, n):
    return np.full(n, float(v)) if np.ndim(v) == 0 else np.asarray(v, dtype=float)


def synth(dur: float, f0, formants, sr: int = SR) -> np.ndarray:
    """펄스열(기본주파수 f0) → 2차 공명기 직렬(포먼트). f0/주파수는 상수 또는 샘플별 배열."""
    n = int(dur * sr)
    f0 = _arr(f0, n)
    ph = np.cumsum(f0) / sr
    y = np.zeros(n)
    y[np.where(np.diff(np.floor(ph)) > 0)[0] + 1] = 1.0
    for fr, bw in formants:
        fr = _arr(fr, n)
        r = np.exp(-np.pi * bw / sr)
        c = -r * r
        b = 2 * r * np.cos(2 * np.pi * fr / sr)
        a = 1 - b - c
        out = np.zeros(n)
        y1 = y2 = 0.0
        for i in range(n):
            v = a[i] * y[i] + b[i] * y1 + c * y2
            out[i] = v
            y2, y1 = y1, v
        y = out
    return (y / np.max(np.abs(y)) * 0.5).astype(np.float32)


VOWEL_A = [(930, 90), (1560, 110), (2900, 150), (3800, 200)]   # 여성 ㅏ 참고치 근처


def seg(phone, start, end, idx=0):
    return {"idx": idx, "phone": phone, "start": start, "end": end}


def dumps_strict(obj):
    return json.dumps(obj, allow_nan=False, ensure_ascii=False)


# ── say 로 만든 실제 음성 ─────────────────────────────────
@pytest.fixture(scope="module")
def say_vowels(tmp_path_factory):
    if not (shutil.which("say") and shutil.which("ffmpeg")):
        pytest.skip("macOS say / ffmpeg 필요")
    d = tmp_path_factory.mktemp("say")
    out = {}
    for name, text in {"A": "아", "I": "이", "U": "우"}.items():
        aiff, wav = d / f"{name}.aiff", d / f"{name}.wav"
        try:
            subprocess.run(["say", "-v", "Yuna", text, "-o", str(aiff)], check=True, capture_output=True, timeout=30)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1",
                            "-c:a", "pcm_s16le", str(wav)], check=True, capture_output=True, timeout=30)
        except (subprocess.SubprocessError, OSError) as e:
            pytest.skip(f"TTS 생성 실패: {e}")
        x, sr = sf.read(str(wav), dtype="float32")
        out[name] = (x, sr)
    return out


def test_say_vowel_formant_order(say_vowels):
    res = {}
    for ph, (x, sr) in say_vowels.items():
        r = acoustic.analyze(x, sr, [seg(ph, 0.0, len(x) / sr)], "female")
        dumps_strict(r)
        assert len(r["f0"]["t"]) <= 200 and len(r["f0"]["t"]) == len(r["f0"]["hz"])
        assert len(r["intensity"]["t"]) <= 200
        v = r["vowels"][0]
        assert v["f1"] is not None and v["f2"] is not None
        assert v["ref"] == {"f1": acoustic.FORMANT_REF["female"][ph][0], "f2": acoustic.FORMANT_REF["female"][ph][1]}
        res[ph] = v
    assert res["A"]["f1"] > res["I"]["f1"]
    assert res["I"]["f2"] > res["U"]["f2"]


# ── 합성 음성으로 결정적 검증 ─────────────────────────────
def test_contract_shape_and_types():
    x = synth(0.5, 200, VOWEL_A)
    r = acoustic.analyze(x, SR, [seg("A", 0.0, 0.5, idx=1)], "female")
    for k in ("duration", "f0", "intensity", "f0_stats", "loudness", "vowels"):
        assert k in r
    assert set(r["f0_stats"]) >= {"mean", "min", "max", "range_st", "voiced_ratio", "end_rise_st"}
    assert set(r["loudness"]) >= {"mean_db", "max_db"}
    v = r["vowels"][0]
    assert v["idx"] == 1 and v["phone"] == "A"
    assert set(v) >= {"idx", "phone", "f1", "f2", "ref", "ok"}

    def walk(o):
        if isinstance(o, dict):
            for val in o.values():
                walk(val)
        elif isinstance(o, list):
            for val in o:
                walk(val)
        else:
            assert o is None or type(o) in (int, float, str, bool), type(o)

    walk(r)
    dumps_strict(r)


def test_formant_ok_against_reference():
    x = synth(0.5, 200, VOWEL_A)
    a = acoustic.analyze(x, SR, [seg("A", 0.0, 0.5)], "female")["vowels"][0]
    assert a["ok"] is True
    assert abs(a["f1"] - 930) / 930 < 0.15 and abs(a["f2"] - 1560) / 1560 < 0.10
    wrong = acoustic.analyze(x, SR, [seg("I", 0.0, 0.5)], "female")["vowels"][0]  # ㅏ 소리를 ㅣ 로 채점
    assert wrong["ok"] is False
    assert wrong["dev"]["f1"] > 0.25 and wrong["dev"]["f2"] < -0.2


def test_diphthong_uses_last_third_and_arrival_vowel():
    # 앞 2/3 는 ㅣ 비슷한 포먼트, 뒤 1/3 은 ㅏ  → 'iA'(ㅑ)는 ㅏ 참고치로 판정되어야 한다
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    w = np.clip((t - 0.25) / 0.1, 0, 1)
    fm = [(340 + (930 - 340) * w, 80), (2700 + (1560 - 2700) * w, 110), (3300 + (2900 - 3300) * w, 150), (3900, 200)]
    x = synth(0.6, 200, fm)
    v = acoustic.analyze(x, SR, [seg("iA", 0.0, 0.6)], "female")["vowels"][0]
    assert v["ref_vowel"] == "A"
    assert v["ref"] == {"f1": 930, "f2": 1560}
    assert v["f1"] > 800 and v["ok"] is True


def test_diphthong_mapping():
    expect = {"iA": "A", "oA": "A", "iE": "E", "oE": "E", "iEO": "EO", "uEO": "EO",
              "iO": "O", "iU": "U", "uI": "I", "euI": "I"}
    for d, mono in expect.items():
        assert acoustic.ref_vowel(d) == mono
    for mono in ("A", "E", "I", "O", "U", "EO", "EU"):
        assert acoustic.ref_vowel(mono) == mono
    assert acoustic.ref_vowel("G") is None and acoustic.ref_vowel("??") is None


def test_short_segment_gives_null_formants():
    x = synth(0.5, 200, VOWEL_A)
    v = acoustic.analyze(x, SR, [seg("A", 0.20, 0.22)], "female")["vowels"][0]  # 20 ms
    assert v["f1"] is None and v["f2"] is None and v["ok"] is None
    assert v["ref"] == {"f1": 930, "f2": 1560}


def test_non_vowel_segments_ignored_and_voice_refs():
    x = synth(0.5, 120, VOWEL_A)
    r = acoustic.analyze(x, SR, [seg("G", 0.0, 0.1, 0), seg("A", 0.1, 0.5, 1)], "male")
    assert [v["idx"] for v in r["vowels"]] == [1]
    assert r["vowels"][0]["ref"] == {"f1": 740, "f2": 1310}
    r = acoustic.analyze(x, SR, [seg("A", 0.1, 0.5, 1)], "robot")  # 모르는 voice → female
    assert r["vowels"][0]["ref"] == {"f1": 930, "f2": 1560}


def test_long_audio_downsampled_and_f0_stats():
    x = synth(5.0, 200, VOWEL_A)
    r = acoustic.analyze(x, SR, [], "female")
    assert 100 < len(r["f0"]["t"]) <= 200 and len(r["f0"]["hz"]) == len(r["f0"]["t"])
    assert len(r["intensity"]["t"]) <= 200 and len(r["intensity"]["db"]) == len(r["intensity"]["t"])
    assert r["f0"]["t"] == sorted(r["f0"]["t"])
    s = r["f0_stats"]
    assert abs(s["mean"] - 200) < 5
    assert s["range_st"] is not None and s["range_st"] < 1.0
    assert s["voiced_ratio"] > 0.8
    assert r["loudness"]["max_db"] >= r["loudness"]["mean_db"]
    dumps_strict(r)


def test_range_st_definition():
    n = int(1.0 * SR)
    f0 = np.linspace(150, 300, n)  # 한 옥타브 상승
    r = acoustic.analyze(synth(1.0, f0, VOWEL_A), SR, [], "female")
    # p90/p10 은 대략 (150+0.9*150)/(150+0.1*150) → 약 9.3 st
    assert 7.5 < r["f0_stats"]["range_st"] < 11.0


def test_end_rise_question_vs_statement():
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    ramp = np.clip((t - 0.3) / 0.3, 0, 1)
    rise = acoustic.analyze(synth(0.6, 200 + 80 * ramp, VOWEL_A), SR, [], "female")["f0_stats"]["end_rise_st"]
    fall = acoustic.analyze(synth(0.6, 240 - 70 * ramp, VOWEL_A), SR, [], "female")["f0_stats"]["end_rise_st"]
    flat = acoustic.analyze(synth(0.6, 200, VOWEL_A), SR, [], "female")["f0_stats"]["end_rise_st"]
    assert rise > 3.0       # 200→280 Hz ≈ +5.8 st
    assert fall < -3.0      # 240→170 Hz ≈ −6.0 st
    assert abs(flat) < 0.5
    r = acoustic.analyze(synth(0.6, 200 + 80 * ramp, VOWEL_A), SR, [], "female")
    assert r["end_rise_st"] == r["f0_stats"]["end_rise_st"]  # 최상위 별칭


def test_silence_and_degenerate_inputs():
    r = acoustic.analyze(np.zeros(SR, dtype=np.float32), SR, [seg("A", 0.1, 0.5)], "female")
    s = r["f0_stats"]
    assert s["voiced_ratio"] == 0.0 and s["mean"] is None and s["range_st"] is None and s["end_rise_st"] is None
    assert all(h is None for h in r["f0"]["hz"])
    assert r["vowels"][0]["f1"] is None or isinstance(r["vowels"][0]["f1"], int)
    dumps_strict(r)

    for wav in (np.zeros(0, dtype=np.float32), np.zeros(160, dtype=np.float32), synth(0.03, 200, VOWEL_A)):
        r = acoustic.analyze(wav, SR, [seg("A", 0.0, 0.03)], "female")
        assert r["f0_stats"]["range_st"] is None
        dumps_strict(r)

    # 잘못된 구간 값도 죽지 않는다
    r = acoustic.analyze(synth(0.3, 200, VOWEL_A), SR,
                         [{"idx": 0, "phone": "A"}, seg("A", None, 0.2), seg("A", 0.3, 0.1), "junk", seg(None, 0, 1)],
                         "female")
    assert all(v["f1"] is None for v in r["vowels"])
    dumps_strict(r)


def test_numpy_idx_is_serializable():
    x = synth(0.3, 200, VOWEL_A)
    r = acoustic.analyze(x, SR, [{"idx": np.int64(4), "phone": "A", "start": np.float32(0.0), "end": np.float64(0.3)}],
                         "female")
    assert r["vowels"][0]["idx"] == 4 and type(r["vowels"][0]["idx"]) is int
    dumps_strict(r)


def test_int16_and_stereo_input():
    x = synth(0.5, 200, VOWEL_A)
    base = acoustic.analyze(x, SR, [seg("A", 0.0, 0.5)], "female")["vowels"][0]
    i16 = (x * 32767).astype(np.int16)
    a = acoustic.analyze(i16, SR, [seg("A", 0.0, 0.5)], "female")["vowels"][0]
    st = acoustic.analyze(np.stack([x, x], axis=1), SR, [seg("A", 0.0, 0.5)], "female")["vowels"][0]
    for v in (a, st):
        assert abs(v["f1"] - base["f1"]) <= 5 and abs(v["f2"] - base["f2"]) <= 5


# ── 리뷰 반영: 모음별 허용폭, 치조·j 문맥, ㅛ·ㅠ 비교 생략, 짧은 구간, 화자 정규화 ──
VOWEL_A_FRONTED = [(900, 90), (2150, 110), (2900, 150), (3800, 200)]   # Yuna 실측과 비슷한 ㅏ(F2 높음)


def _one(x, segs, voice="female", idx=0):
    return next(v for v in acoustic.analyze(x, SR, segs, voice)["vowels"] if v["idx"] == idx)


def test_a_with_high_f2_is_within_widened_range():
    x = synth(0.5, 200, VOWEL_A_FRONTED)
    v = _one(x, [seg("A", 0.0, 0.5)])
    assert v["f2"] > 1872                      # 예전 기준(±20%)이면 '벗어남'
    assert v["ok"] is True and v["context"] is None
    assert v["accept"]["f2"][1] >= 2200


def test_coronal_context_waives_f2_upper_bound_only():
    x = synth(0.5, 200, [(400, 80), (2100, 110), (2900, 150), (3800, 200)])   # 주스의 ㅜ 같은 앞쪽 ㅜ
    plain = _one(x, [seg("U", 0.0, 0.5, idx=1)], idx=1)
    assert plain["ok"] is False
    ctx = _one(x, [seg("J", 0.0, 0.05, idx=0), seg("U", 0.05, 0.5, idx=1), seg("S", 0.5, 0.6, idx=2)], idx=1)
    assert ctx["context"] == "coronal" and ctx["accept"]["f2"][1] is None and ctx["ok"] is True
    # F1 은 여전히 본다: ㅜ 자리에 ㅏ 높이 F1 이면 실패
    wide = synth(0.5, 200, [(900, 90), (2100, 110), (2900, 150), (3800, 200)])
    assert _one(wide, [seg("J", 0.0, 0.05, 0), seg("U", 0.05, 0.5, 1)], idx=1)["ok"] is False


def test_iO_iU_have_no_reference():
    x = synth(0.5, 200, [(450, 80), (1250, 110), (2900, 150), (3800, 200)])
    for ph in ("iO", "iU"):
        v = _one(x, [seg(ph, 0.0, 0.5)])
        assert v["ref"] is None and v["ok"] is None and v["f1"] is not None


def test_short_vowel_marked_unreliable():
    x = synth(0.5, 200, VOWEL_A)
    v = _one(x, [seg("A", 0.20, 0.24)])        # 40 ms < 50 ms
    assert v["f1"] is None and v["ok"] is None and v["unreliable"] == "short"


def test_speaker_scale_leave_one_out_and_clamped():
    refs = acoustic.FORMANT_REF["female"]
    items = [{"phone": "I", "f1": 290, "f2": 2300}, {"phone": "A", "f1": 930, "f2": 1560},
             {"phone": "O", "f1": 700, "f2": 1200}]
    # ㅏ 판정용: 자기 자신(ㅏ)은 빼고 ㅣ 앵커만 → 0.85 근처 → 하한 0.90 으로 묶임
    assert acoustic._speaker_scale(items, refs, skip=1) == acoustic.SCALE_RANGE[0]
    # ㅗ(앵커 아님)는 배율 계산에 쓰지 않는다
    only_o = [{"phone": "O", "f1": 900, "f2": 1500}, {"phone": "A", "f1": 930, "f2": 1560}]
    assert acoustic._speaker_scale(only_o, refs, skip=1) == 1.0


def test_speaker_scale_only_relaxes(monkeypatch):
    """화자 정규화 상자는 원래 상자와 합집합 — 배율이 기준을 좁혀도 원래 기준 안의 모음은 그대로 통과."""
    x = synth(0.5, 200, VOWEL_A_FRONTED)                 # F2 ≈ 2150: 원래 상한 2262 안, 0.9배 상한 2036 밖
    monkeypatch.setattr(acoustic, "_speaker_scale", lambda *a, **k: 0.9)
    v = _one(x, [seg("A", 0.0, 0.5)])
    assert 2036 < v["f2"] <= 2262 and v["ok"] is True and v["scale"] == 0.9
    monkeypatch.setattr(acoustic, "_speaker_scale", lambda *a, **k: 1.12)   # 넓히는 쪽은 그대로 반영
    y = synth(0.5, 200, [(900, 90), (2420, 110), (3000, 150), (3800, 200)])
    assert _one(y, [seg("A", 0.0, 0.5)])["ok"] is True


def test_e_f1_allows_merged_ae():
    x = synth(0.5, 200, [(720, 90), (2300, 110), (2900, 150), (3800, 200)])   # ㅐ 쪽 ㅔ(F1 높음)
    assert _one(x, [seg("E", 0.0, 0.5)])["ok"] is True
