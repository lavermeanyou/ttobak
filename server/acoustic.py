"""음향 분석 — F0(억양), 강도(크기), 모음 포먼트(F1/F2).  (CONTRACT 5절)

praat-parselmouth 로 Praat 의 표준 알고리즘을 그대로 쓴다.
- 피치:   Sound.to_pitch_ac      (자기상관, 목소리 유형별 탐색 범위)
- 강도:   Sound.to_intensity     (minimum_pitch = 피치 하한 → 분석 창 길이 결정)
- 포먼트: Sound.to_formant_burg  (최대 포먼트 주파수는 성도 길이에 따라 남/여/아동 다르게)

반환 JSON 은 그대로 직렬화 가능해야 한다: numpy 타입·NaN·inf 금지 → 순수 float/int/None.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import parselmouth

try:  # 패키지(server.acoustic)로도, --app-dir 로 server/ 를 직접 잡은 경우(acoustic)로도 import 가능하게
    from .phones import FORMANT_REF, PHONES
except ImportError:  # pragma: no cover
    from phones import FORMANT_REF, PHONES  # type: ignore

# ── 목소리 유형별 분석 파라미터 ─────────────────────────────
# 피치 범위: 성인 남성 기본주파수는 대략 85–180 Hz, 여성 165–255 Hz, 아동 250–400 Hz.
#           억양 상승·하강과 옥타브 오류 여유를 두고 넓게 잡는다.
# 최대 포먼트: Praat 권장값(남 5000 / 여 5500 Hz), 성도가 짧은 아동은 더 높게(6500 Hz).
VOICE_PARAMS: dict[str, dict[str, float]] = {
    "male":   {"pitch_floor": 70.0,  "pitch_ceiling": 300.0, "max_formant": 5000.0},
    "female": {"pitch_floor": 100.0, "pitch_ceiling": 500.0, "max_formant": 5500.0},
    "child":  {"pitch_floor": 150.0, "pitch_ceiling": 600.0, "max_formant": 6500.0},
}
DEFAULT_VOICE = "female"
MAX_FORMANTS = 5

MAX_POINTS = 200            # 프런트로 보내는 시계열의 최대 점 수
# 이보다 짧은 모음 구간은 포먼트를 신뢰할 수 없어 null. Praat Burg 분석 창은 유효 길이 25 ms·실제 길이
# 50 ms(가우스 창)라서 50 ms 미만 모음은 창이 늘 앞뒤 자음에 걸친다. 실측(Yuna 합성음, 정상 판정 모음):
# 40 ms 구간에서 사과 ㅏ (394, 917)·두부 ㅜ (1187, 2130)·두더지 ㅜ (818, 2179)처럼 다른 모음 자리로 튀었다.
MIN_VOWEL_SEC = 0.050
MIN_VOICED_FRAMES = 5       # 이보다 유성 프레임이 적으면 range_st = null
# F0 통계(voiced_ratio·range_st·end_rise_st)는 강제정렬 구간(첫 음소 시작 ~ 끝 음소 끝) ± 이 여유 안에서만 잰다.
# 녹음 전체로 재면 버튼을 늦게 뗀 긴 무음이 voiced_ratio 를 낮춰 억양 판정이 사라지고(실측: '소리'를 8초 녹음 →
# voiced_ratio 0.038 < 0.05 → intonation null), 말 앞뒤의 숨소리·험이 끝 억양에 섞인다.
F0_SPAN_PAD = 0.10
# 클리핑(소리가 너무 커서 파형 꼭대기가 잘림): |x| ≥ CLIP_LEVEL 인 표본이 말소리 표본의 CLIP_RATIO 이상이면
# loudness.clipped = true. 실측(정상 '소리'·'안녕하세요'를 4배 키워 2~3% 클리핑)에서 정상 발음이 ㅗ→ㅜ, ㄴ→ㅁ 로 판정됐다.
CLIP_LEVEL = 0.99
CLIP_RATIO = 0.002

# 참고치 비교 허용 범위 (참고치 대비 비율, (F1 하한, F1 상한, F2 하한, F2 상한)).
# FORMANT_REF 는 성인 평균값이고, 같은 성별 안에서도 화자 간 차이가 F1 은 ±20% 이상,
# F2 는 ±15% 안팎으로 보고된다(한국어 모음 음향 연구들, 예: 양병곤 1996; 신지영 2011).
# 목적은 '명백히 다른 모음처럼 들리는 경우'만 잡는 것 — 정밀한 모음 평가가 아니다. 기본은 F1 ±25%, F2 ±20%
# (F1_TOL/F2_TOL)이고, 실측과 문헌상 변이가 한쪽으로 큰 모음은 그 방향만 넓힌다:
#   ㅏ  F2 +45%: 저모음 ㅏ 는 F1(턱)이 핵심이고 F2 는 문맥·화자에 따라 크게 흔들린다. 실측(Yuna, 정상 판정
#       ㅏ 33개)에서 F2 1890~2290 Hz(참고치 1560 의 +21~+47%, 중앙값 약 +31%)였고 parselmouth 상한을
#       5000/5500/6000 으로 바꿔도 1920~2233 이었다(측정 오류가 아니라 화자 특성). ㅐ/ㅔ 와는 F1 로 갈린다.
#   ㅜ  F2 +45%, ㅡ F2 +40%·F1 −30%, ㅗ F2 +35%·F1 −30%: 현대 서울말(특히 젊은 여성)은 ㅜ 가 앞으로 나오고
#       (ㅜ 전설화) ㅗ 가 위로 올라가 ㅜ 와 F1 이 비슷해진다(ㅗ/ㅜ 근접, F2 중심 구별) — 참고: koreascience
#       JAKO201303840304443, 고려대 2021.sw.korea/95405, ICPhS 2019 #859.
#   ㅣ·ㅔ F1 −25~30%: 고·중 전설모음 F1 은 절대값이 작아 같은 Hz 차이도 비율로 크게 나온다
#       (실측 세수 ㅔ F1 439 = −26%).
#   ㅔ F1 +35%: 음소 E 는 ㅐ/ㅔ 합류형이라 입을 더 벌리는 ㅐ(여성 F1 약 650~750 Hz)도 포함한다
#       (실측 안녕하세요의 '세' F1 700 = +19%).
# 이 수치는 합성음(Yuna)과 문헌 요약으로 정한 것이라 실제 사람 녹음(성별·연령별 20명 안팎)으로 다시 맞춰야 한다.
F1_TOL = 0.25
F2_TOL = 0.20
TOL: dict[str, tuple[float, float, float, float]] = {
    "A":  (0.75, 1.25, 0.80, 1.45),
    "EO": (0.75, 1.30, 0.80, 1.30),
    "O":  (0.70, 1.25, 0.80, 1.35),
    "U":  (0.75, 1.30, 0.80, 1.45),
    "EU": (0.70, 1.30, 0.75, 1.40),
    "I":  (0.75, 1.30, 0.85, 1.20),
    "E":  (0.70, 1.35, 0.85, 1.20),
}
# 치조·경구개 자음(혀끝·혓바닥 앞) 옆의 중설·후설 모음은 F2 가 자음의 F2 궤적 목표(locus, 약 1.7~2.2 kHz)
# 쪽으로 크게 끌려 올라간다. 실측: 주스 ㅜ 2132, 후추 ㅜ 1906, 무릎 ㅜ 1315, 여름 ㅡ 2099, 다리 ㅏ 2262 Hz.
# j 활음(혓바닥을 센입천장 쪽으로 올림)도 같은 방향으로 끌어올린다: ㅑ·ㅕ 의 도착 모음, 그리고 바로 뒤에
# j 활음 모음·앞 모음이 오는 모음(가요의 ㅏ 2239, 뭐예요의 ㅝ 1554 Hz).
# 그래서 이 문맥에서는 F2 상한을 두지 않고 F1·F2 하한만 본다.
CORONAL = frozenset({"D", "DD", "Th", "N", "R", "L", "t", "S", "SS", "J", "JJ", "CHh"})
F2_FREE_VOWELS = frozenset({"A", "EO", "O", "U", "EU"})
# ㅛ·ㅠ 는 도착 모음(ㅗ·ㅜ)과 비교하지 않는다(ref=null): j 활음 뒤 ㅗ·ㅜ 는 앞으로 크게 끌려
# (실측 '-요' ㅛ F2 1205~1285 = 참고 ㅗ 의 +40~48%, 유리 ㅠ 2404·휴지 ㅠ 2221 = 참고 ㅜ 의 +120% 이상)
# 정상 발음도 '벗어남'으로 나왔다. 이 둘은 음성 인식 판정만 쓴다.
NO_REF_DIPHTHONGS = frozenset({"iO", "iU"})
# 화자 정규화: 그 녹음의 다른 모음 중 문맥 영향이 작은 값(ㅣ F1·F2, ㅔ F1·F2, ㅏ F1)의 참고치 대비 비율
# 중앙값으로 참고치를 비례 조정한 상자(성도 길이 차이 보정)도 함께 인정한다(원래 상자와의 합집합).
# 판정할 모음 자신은 빼고(leave-one-out) 계산해 틀린 모음이 스스로를 정상으로 끌어오지 못하게 하고,
# 크기는 0.90~1.12 로 묶는다. 합집합이라 정규화 추정이 빗나가도 원래 기준보다 엄격해지지는 않는다
# (단어 하나짜리 녹음은 앵커가 1~2개뿐이라 추정이 흔들린다 — 실측 ㅏ F1 비율 0.86~1.07).
SCALE_ANCHORS = {"I": (True, True), "E": (True, True), "A": (True, False)}
SCALE_RANGE = (0.90, 1.12)

# 이중모음 → 도착 단모음 (phones.PHONES 의 height/backness/rounded 와 일치하는 단모음)
DIPHTHONG_TARGET: dict[str, str] = {
    "iA": "A", "oA": "A",
    "iE": "E", "oE": "E",
    "iEO": "EO", "uEO": "EO",
    "iO": "O",
    "iU": "U",
    "uI": "I", "euI": "I",
}

END_RISE_SEC = 0.30         # 끝 억양 판정에 쓰는 마지막 유성 구간 길이
END_RISE_MIN_FRAMES = 4     # 그 안의 유성 프레임이 이보다 적으면 null
END_RISE_MIN_SPAN = 0.08    # 그 안의 유성 프레임이 덮는 시간이 이보다 짧으면 null
OCTAVE_OUTLIER_ST = 7.0     # 중앙값에서 이 이상 벗어난 프레임은 옥타브 오류로 보고 제외


# ── 작은 유틸 ─────────────────────────────────────────────
def _num(x: Any, nd: int = 2) -> float | None:
    """유한한 수면 반올림한 순수 float, 아니면 None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return round(v, nd) + 0.0  # + 0.0: -0.0 → 0.0


def _idx(v: Any) -> Any:
    """음소 인덱스: numpy 정수 등도 순수 int 로(JSON 직렬화 보장)."""
    if isinstance(v, (int, np.integer)) and not isinstance(v, bool):
        return int(v)
    return v if v is None or isinstance(v, (str, float)) else None


def _hz(x: Any) -> int | None:
    v = _num(x, 0)
    return None if v is None else int(v)


def _downsample_idx(n: int, max_points: int = MAX_POINTS) -> np.ndarray:
    """길이 n 배열에서 고르게 뽑을 인덱스(최대 max_points 개, 양 끝 포함)."""
    if n <= max_points:
        return np.arange(n)
    return np.unique(np.linspace(0, n - 1, max_points).round().astype(int))


def _to_mono_float(wav: Any) -> np.ndarray:
    a = np.asarray(wav)
    if a.dtype.kind in "iu":
        a = a.astype(np.float64) / float(np.iinfo(a.dtype).max + 1)
    a = a.astype(np.float64, copy=False)
    if a.ndim == 2:  # (n, ch) 또는 (ch, n)
        a = a.mean(axis=1) if a.shape[0] >= a.shape[1] else a.mean(axis=0)
    a = a.reshape(-1)
    return np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)


def ref_vowel(phone: str) -> str | None:
    """모음 음소 → 참고치 비교용 단모음 기호(이중모음은 도착 모음). 참고치 없으면 None."""
    if phone in DIPHTHONG_TARGET:
        return DIPHTHONG_TARGET[phone]
    p = PHONES.get(phone)
    if p is None or not p.is_vowel:
        return None
    if p.glide is None:
        return phone
    # 표에 없는 이중모음: 자질(height/backness/rounded)이 같은 단모음을 찾는다.
    for q in PHONES.values():
        if q.is_vowel and q.glide is None and (q.height, q.backness, q.rounded) == (p.height, p.backness, p.rounded):
            return q.sym
    return None


def semitones(hz: np.ndarray, ref: float) -> np.ndarray:
    return 12.0 * np.log2(hz / ref)


# ── F0 ───────────────────────────────────────────────────
def _end_rise_st(t: np.ndarray, hz: np.ndarray) -> float | None:
    """끝 억양: 마지막 유성 프레임에서 거슬러 END_RISE_SEC 안의 유성 프레임들에 대해
    반음(st) 값을 시간에 직선 회귀한 기울기 × 그 구간 길이.

    즉 '마지막 0.3초 동안 음높이가 몇 반음 올라갔나(+)/내려갔나(−)' 를 직선으로 근사한 값.
    의문문 끝 올림은 보통 +2 st 이상, 평서문 끝 내림은 음수.  계산 불가 시 None.
    """
    voiced = np.isfinite(hz) & (hz > 0)
    if voiced.sum() < END_RISE_MIN_FRAMES:
        return None
    tv, fv = t[voiced], hz[voiced]
    sel = tv >= tv[-1] - END_RISE_SEC
    tv, fv = tv[sel], fv[sel]
    if len(tv) < END_RISE_MIN_FRAMES:
        return None
    st = semitones(fv, float(np.median(fv)))
    keep = np.abs(st) <= OCTAVE_OUTLIER_ST
    tv, st = tv[keep], st[keep]
    if len(tv) < END_RISE_MIN_FRAMES or tv[-1] - tv[0] < END_RISE_MIN_SPAN:
        return None
    slope = np.polyfit(tv - tv[0], st, 1)[0]  # st / s
    return _num(slope * (tv[-1] - tv[0]), 2)


def _segments_span(segments: list[dict] | None) -> tuple[float, float] | None:
    """강제정렬 구간 전체의 [처음, 끝](초). 없으면 None."""
    st, en = [], []
    for s in segments or []:
        try:
            a, b = float(s.get("start")), float(s.get("end"))
        except (TypeError, ValueError, AttributeError):
            continue
        if math.isfinite(a) and math.isfinite(b) and b >= a:
            st.append(a)
            en.append(b)
    return (min(st), max(en)) if st else None


def _f0_stats(t: np.ndarray, hz: np.ndarray) -> dict:
    n = len(hz)
    voiced = np.isfinite(hz) & (hz > 0)
    v = hz[voiced]
    stats: dict[str, Any] = {
        "mean": None, "min": None, "max": None, "range_st": None,
        "voiced_ratio": _num(voiced.sum() / n, 3) if n else 0.0,
        "end_rise_st": None,
    }
    if len(v):
        stats.update(mean=_num(v.mean(), 1), min=_num(v.min(), 1), max=_num(v.max(), 1))
    if len(v) >= MIN_VOICED_FRAMES:
        p10, p90 = np.percentile(v, [10, 90])
        stats["range_st"] = _num(12.0 * math.log2(p90 / p10), 2) if p10 > 0 else None
    stats["end_rise_st"] = _end_rise_st(t, hz)
    return stats


# ── 포먼트 ────────────────────────────────────────────────
def _formant_tracks(snd: parselmouth.Sound, max_formant: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(times, F1, F2) — 정의되지 않은 프레임은 NaN."""
    fm = snd.to_formant_burg(max_number_of_formants=MAX_FORMANTS, maximum_formant=max_formant)
    ts = np.asarray(fm.xs(), dtype=np.float64)
    f1 = np.array([fm.get_value_at_time(1, x) for x in ts], dtype=np.float64)
    f2 = np.array([fm.get_value_at_time(2, x) for x in ts], dtype=np.float64)
    return ts, f1, f2


def _vowel_window(start: float, end: float, diphthong: bool, before_vowel: bool = False) -> tuple[float, float]:
    d = end - start
    if diphthong and before_vowel:   # 뒤에 바로 모음이 오면(뭐예요) 끝 1/3 은 다음 모음으로 넘어가는 중이라 가운데 1/3
        return start + d / 3.0, end - d / 3.0
    if diphthong:              # 이중모음: 활음 이후 도착 모음이 안정되는 후반 1/3
        return end - d / 3.0, end
    return start + 0.25 * d, end - 0.25 * d   # 단모음: 앞뒤 전이부를 뺀 중앙 50%


def _median_in(ts: np.ndarray, vals: np.ndarray, voiced_at: np.ndarray | None, a: float, b: float) -> float | None:
    sel = (ts >= a) & (ts <= b) & np.isfinite(vals)
    # 유성 프레임이 충분하면 그것만 쓴다(구간 경계가 무음/자음에 걸쳤을 때 대비)
    if voiced_at is not None:
        sv = sel & voiced_at
        if sv.sum() >= 3:
            sel = sv
    if not sel.any():
        # 창이 프레임 간격보다 좁으면 창 중앙에 가장 가까운 프레임
        mid = 0.5 * (a + b)
        fin = np.isfinite(vals)
        if not fin.any():
            return None
        i = int(np.argmin(np.where(fin, np.abs(ts - mid), np.inf)))
        if abs(ts[i] - mid) > 0.02:
            return None
        return float(vals[i])
    return float(np.median(vals[sel]))


def _neighbors(segments: list[dict]) -> dict:
    """음소 인덱스 → 음소 기호(모음이 아닌 구간 포함). 앞뒤 자음 문맥을 보려고 쓴다."""
    out = {}
    for seg in segments or []:
        if isinstance(seg, dict) and isinstance(seg.get("phone"), str):
            k = _idx(seg.get("idx"))
            if isinstance(k, int):
                out[k] = seg["phone"]
    return out


def _speaker_scale(items: list[dict], refs: dict, skip: int) -> float:
    """화자 정규화 배율(leave-one-out). 앵커가 없으면 1.0."""
    logs = []
    for k, it in enumerate(items):
        if k == skip or it["f1"] is None or it["f2"] is None:
            continue
        use = SCALE_ANCHORS.get(it["phone"])          # 단모음만(이중모음은 문맥 영향이 커서 제외)
        ref = refs.get(it["phone"])
        if not use or not ref:
            continue
        if use[0]:
            logs.append(math.log(it["f1"] / ref[0]))
        if use[1]:
            logs.append(math.log(it["f2"] / ref[1]))
    if not logs:
        return 1.0
    a = math.exp(float(np.median(logs)))
    return min(SCALE_RANGE[1], max(SCALE_RANGE[0], a))


def _vowels(segments: list[dict], tracks, voiced_at_fn, voice: str, duration: float) -> list[dict]:
    refs = FORMANT_REF.get(voice, FORMANT_REF[DEFAULT_VOICE])
    ctx = _neighbors(segments)
    out: list[dict] = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        phone = seg.get("phone")
        p = PHONES.get(phone) if isinstance(phone, str) else None
        if p is None or not p.is_vowel:
            continue
        rv = None if phone in NO_REF_DIPHTHONGS else ref_vowel(phone)
        ref = refs.get(rv) if rv else None
        idx = _idx(seg.get("idx"))
        prev = ctx.get(idx - 1) if isinstance(idx, int) else None
        nxt = ctx.get(idx + 1) if isinstance(idx, int) else None
        item: dict[str, Any] = {
            "idx": idx, "phone": phone,
            "start": _num(seg.get("start"), 3), "end": _num(seg.get("end"), 3),
            "f1": None, "f2": None,
            "ref": {"f1": int(ref[0]), "f2": int(ref[1])} if ref else None,
            "ref_vowel": rv if ref else None,
            "ok": None,
            "dev": None,   # 참고치 대비 상대 오차 {"f1": +0.12, "f2": -0.05} (+ 는 참고치보다 높음)
        }
        out.append(item)
        s, e = item["start"], item["end"]
        if s is None or e is None or tracks is None:
            continue
        s, e = max(0.0, s), min(duration, e)
        if e - s < MIN_VOWEL_SEC - 1e-9:
            item["unreliable"] = "short"
            continue
        before_vowel = nxt is not None and nxt in PHONES and PHONES[nxt].is_vowel
        a, b = _vowel_window(s, e, p.glide is not None, before_vowel)
        ts, f1, f2 = tracks
        voiced_at = voiced_at_fn(ts) if voiced_at_fn else None
        m1 = _median_in(ts, f1, voiced_at, a, b)
        m2 = _median_in(ts, f2, voiced_at, a, b)
        item["f1"], item["f2"] = _hz(m1), _hz(m2)
        coronal = (prev in CORONAL) or (nxt in CORONAL)
        nxt_p = PHONES.get(nxt) if isinstance(nxt, str) else None
        palatal = p.glide == "j" or (nxt_p is not None and nxt_p.is_vowel
                                     and (nxt_p.glide == "j" or nxt_p.backness == "front"))
        item["context"] = "coronal" if coronal else ("palatal" if palatal else None)

    # 참고치 비교 (화자 정규화는 모든 모음을 잰 뒤에)
    for k, item in enumerate(out):
        ref = refs.get(item["ref_vowel"]) if item["ref_vowel"] else None
        if not ref or item["f1"] is None or item["f2"] is None:
            continue
        rv = item["ref_vowel"]
        d1 = item["f1"] / ref[0] - 1.0
        d2 = item["f2"] / ref[1] - 1.0
        item["dev"] = {"f1": _num(d1, 3), "f2": _num(d2, 3)}
        scale = _speaker_scale(out, refs, k)
        lo1, hi1, lo2, hi2 = TOL.get(rv, (1 - F1_TOL, 1 + F1_TOL, 1 - F2_TOL, 1 + F2_TOL))
        f2_free = rv in F2_FREE_VOWELS and item.get("context") is not None

        def box_of(a: float) -> dict:
            r1, r2 = ref[0] * a, ref[1] * a
            return {"f1": [int(round(r1 * lo1)), int(round(r1 * hi1))],
                    "f2": [int(round(r2 * lo2)), None if f2_free else int(round(r2 * hi2))]}

        def inside(b: dict) -> bool:
            return (b["f1"][0] <= item["f1"] <= b["f1"][1] and item["f2"] >= b["f2"][0]
                    and (b["f2"][1] is None or item["f2"] <= b["f2"][1]))

        box = box_of(1.0)
        item["ok"] = bool(inside(box) or (scale != 1.0 and inside(box_of(scale))))
        item["scale"] = _num(scale, 3)
        item["accept"] = box
    return out


# ── 진입점 ────────────────────────────────────────────────
def analyze(wav: np.ndarray, sr: int, vowel_segments: list[dict], voice: str) -> dict:
    """음성 → F0·강도 시계열, F0 통계, 크기, 모음별 포먼트와 참고치 비교.

    vowel_segments: [{"idx", "phone", "start", "end"}] (초). 모음이 아닌 항목은 무시한다.
    voice: male | female | child (그 밖의 값은 female 로 처리).

    계약 외 추가 필드:
      f0_stats.end_rise_st (+ 최상위 end_rise_st 동일값) — 끝 억양(반음, + 상승 / − 하강, 계산 불가 시 null)
      loudness.floor_db — 강도 하위 10% 분위(배경 소음 수준)
      vowels[].start/end, ref_vowel(참고치로 쓴 단모음), dev(참고치 대비 상대 오차),
             accept {"f1": [하한, 상한], "f2": [하한, 상한|null]} (ok 판정 기준 Hz 범위: 참고치 × 모음별 허용폭,
             치조·경구개·j 문맥이면 F2 상한 없음 — 이 범위를 scale 배 한 범위도 함께 인정), scale(화자 정규화 배율),
             context("coronal" | "palatal" | null), unreliable("short": 너무 짧아 측정 생략)
      voice — 실제로 쓴 목소리 유형
    vowel_segments 에는 강제정렬 구간 전체(자음 포함)를 넘겨도 된다 — 모음만 결과에 넣고, 자음은 앞뒤 문맥
    (치조·경구개 자음 옆인지)을 보는 데만 쓴다. ㅛ(iO)·ㅠ(iU)는 ref=null(도착 모음 비교 안 함).
    """
    voice = voice if voice in VOICE_PARAMS else DEFAULT_VOICE
    prm = VOICE_PARAMS[voice]
    x = _to_mono_float(wav)
    sr = int(sr) if sr else 16000
    duration = len(x) / sr if sr > 0 else 0.0

    result: dict[str, Any] = {
        "duration": _num(duration, 3) or 0.0,
        "voice": voice,
        "f0": {"t": [], "hz": []},
        "intensity": {"t": [], "db": []},
        "f0_stats": {"mean": None, "min": None, "max": None, "range_st": None,
                     "voiced_ratio": 0.0, "end_rise_st": None},
        "loudness": {"mean_db": None, "max_db": None, "floor_db": None},
        "vowels": [],
        "end_rise_st": None,   # = f0_stats.end_rise_st (편의상 최상위에도 둔다)
    }

    snd = None
    if len(x) and sr > 0:
        try:
            snd = parselmouth.Sound(x, sampling_frequency=sr)
        except Exception:
            snd = None

    # F0
    pt = ph = None
    if snd is not None:
        try:
            pitch = snd.to_pitch_ac(pitch_floor=prm["pitch_floor"], pitch_ceiling=prm["pitch_ceiling"])
            pt = np.asarray(pitch.xs(), dtype=np.float64)
            ph = np.asarray(pitch.selected_array["frequency"], dtype=np.float64)
            ph = np.where(ph > 0, ph, np.nan)          # Praat: 무성 = 0 Hz
        except Exception:
            pt = ph = None
    if pt is not None and len(pt):
        idx = _downsample_idx(len(pt))
        result["f0"] = {"t": [_num(v, 3) for v in pt[idx]], "hz": [_num(v, 1) for v in ph[idx]]}
        span = _segments_span(vowel_segments)
        sel = np.ones(len(pt), dtype=bool)
        if span is not None:
            sel = (pt >= span[0] - F0_SPAN_PAD) & (pt <= span[1] + F0_SPAN_PAD)
            if not sel.any():
                sel[:] = True
        result["f0_stats"] = _f0_stats(pt[sel], ph[sel])
        result["end_rise_st"] = result["f0_stats"]["end_rise_st"]

    # 강도
    if snd is not None:
        try:
            inten = snd.to_intensity(minimum_pitch=prm["pitch_floor"])
            it = np.asarray(inten.xs(), dtype=np.float64)
            idb = np.asarray(inten.values, dtype=np.float64).reshape(-1)
        except Exception:
            it = idb = None
        if it is not None and len(it):
            idx = _downsample_idx(len(it))
            result["intensity"] = {"t": [_num(v, 3) for v in it[idx]], "db": [_num(v, 1) for v in idb[idx]]}
            fin = idb[np.isfinite(idb)]
            if len(fin):
                mx = float(fin.max())
                # 평균 크기: 최대값에서 25 dB 안쪽(=말소리가 있는) 프레임만 평균 — 앞뒤 무음 제외
                active = fin[fin >= mx - 25.0]
                result["loudness"] = {"mean_db": _num(active.mean(), 1), "max_db": _num(mx, 1),
                                      "floor_db": _num(np.percentile(fin, 10), 1)}
    if len(x):
        ax = np.abs(x)
        n_clip = int(np.sum(ax >= CLIP_LEVEL))
        n_act = int(np.sum(ax >= 0.02 * float(ax.max()))) if float(ax.max()) > 0 else 0
        ratio = n_clip / n_act if n_act else 0.0
        result["loudness"]["clip_ratio"] = _num(ratio, 4)
        result["loudness"]["clipped"] = bool(n_clip >= 10 and ratio >= CLIP_RATIO)

    # 모음 포먼트
    tracks = None
    if snd is not None:
        try:
            tracks = _formant_tracks(snd, prm["max_formant"])
        except Exception:
            tracks = None
    voiced_at_fn = None
    if pt is not None and len(pt) > 1:
        step = float(pt[1] - pt[0])
        voiced_mask = np.isfinite(ph)

        def voiced_at_fn(ts: np.ndarray) -> np.ndarray:  # 포먼트 프레임 시각 → 가장 가까운 피치 프레임의 유성 여부
            j = np.clip(np.round((ts - pt[0]) / step).astype(int), 0, len(pt) - 1)
            return voiced_mask[j]
    result["vowels"] = _vowels(vowel_segments, tracks, voiced_at_fn, voice, duration)
    return result
