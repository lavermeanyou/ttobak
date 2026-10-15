"""입술 시계열 → 음소 구간별 입모양 판정.  (CONTRACT 6절)

입력(프런트 MediaPipe Face Landmarker 결과):
    {"fps": 30,
     "frames": [{"t": 0.033, "open": 0.12, "width": 0.92,
                 "pucker": 0.1, "funnel": 0.05, "jaw": 0.2, "close": 0.0}],
     "neutral": {"open": 0.02, "width": 0.95}}
- open/width : 얼굴 크기(양 눈 바깥꼬리 거리)로 정규화한 입 벌림·입 너비
- pucker/funnel/jaw/close : MediaPipe 블렌드셰이프(mouthPucker, mouthFunnel, jawOpen, mouthClose) 0~1

음성이 '오류 판정의 본체'이고 입술은 보조 판정이다. 그래서 기준은 일부러 너그럽게 잡았고,
애매하면 '판정 생략'(check 를 만들지 않음) 쪽을 택한다.

series.round 정의 (0~1, 클수록 입술이 둥글게 모임):
    round = clip( max( max(pucker, funnel),  1 - width / neutral.width ), 0, 1 )
    블렌드셰이프가 없는 프레임은 너비 항(1 - width_ratio)만 쓴다.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

try:  # 패키지(server.lips)로도, --app-dir 로 server/ 를 직접 잡은 경우(lips)로도 import 가능하게
    from .phones import PHONES
except ImportError:  # pragma: no cover
    from phones import PHONES  # type: ignore

# ── 입력 유효성 ───────────────────────────────────────────
MIN_TOTAL_FRAMES = 5        # 유효 프레임이 이보다 적으면 available=false
MIN_SEG_FRAMES = 3          # 한 구간에서 이보다 프레임이 적으면 그 구간 판정 생략
MIN_FPS, MAX_FPS = 5.0, 240.0   # 선언 fps 가 이 범위를 벗어나면(또는 타임스탬프로 본 실제 fps 가 너무 낮으면) 사용 안 함
MAX_POINTS = 200            # series 최대 점 수

# ── 판정 창 ───────────────────────────────────────────────
# 모음(round/spread/open)은 구간 '가운데 50%'만 본다. 앞뒤 경계 근처는 이웃 음소의 입모양이 이어지는
# 동시조음 구간이라(오이: ㅗ 의 원순성이 ㅣ 앞부분까지 남음) 경계를 넘겨 보면 ㅗ 를 잘 둥글게 낸 사람일수록
# 뒤 ㅣ 의 spread 가 실패로 나왔다. 가운데 50% 에 프레임이 MIN_SEG_FRAMES 보다 적으면 구간 전체를 보고,
# 그래도 모자라면 round/open 만 경계 ±SEG_PAD 까지 넓힌다(넓혀서 생기는 오차는 '통과' 쪽이라 덜 해롭다).
# spread 는 넓히지 않고 판정을 생략한다.
CENTER_FRAC = 0.5           # 모음 판정 창: 구간 가운데 이 비율
SEG_PAD = 0.04              # round/open 최후 수단: [start-0.04, end+0.04] (강제정렬 경계 오차 ±20~40 ms)
CLOSED_PAD = 0.06           # 양순음: 시작·끝 경계 ±0.06 s (닫힘은 짧고 경계 근처에서 일어남)

# ── 판정 임계값 ───────────────────────────────────────────
# 근거: width/open 은 눈 바깥꼬리 거리(성인 약 9 cm)로 정규화된 값이므로
#   open 0.08 ≈ 입술 사이 7 mm 남짓(모음 'ㅏ'에서 보통 1 cm 이상 벌어짐),
#   neutral.open + 0.015 ≈ 1~2 mm(입술이 맞닿은 상태의 랜드마크 지터 수준),
#   width 10% 감소 ≈ 입꼬리가 좌우 합쳐 5 mm 정도 안으로 모인 상태.
# 블렌드셰이프 임계값(0.25~0.35)은 MediaPipe 데모에서 '눈에 띄게 그 동작을 한' 수준을 경험적으로 잡은 값.
# 한계:
#   - 카메라 각도: 고개를 좌우로 돌리면(yaw) 입 너비가 짧아 보여 round 가 잘못 통과하고 spread 가 잘못 실패할 수 있다.
#     고개를 숙이거나 들면(pitch) 세로 거리 open 이 줄거나 늘어난다.
#   - 거리: 눈 사이 거리로 정규화하므로 멀어지고 가까워지는 것은 대부분 상쇄되지만,
#     너무 멀면(얼굴이 작게 잡히면) 랜드마크 지터가 커져 closed/open 판정이 흔들린다.
#   - neutral 이 없으면 녹음 중 가장 덜 벌린 프레임들로 추정하므로, 처음부터 끝까지 입을 오므린 녹음에서는 기준이 틀어진다.
#   - 블렌드셰이프는 일반 얼굴로 학습된 값이라 사람마다 기본값(무표정 값)이 다르다.
ROUND_WIDTH_RATIO_MAX = 0.90    # round: 구간 최소 너비 / 기준 너비 ≤ 0.90
ROUND_BLEND_MIN = 0.25          #        또는 max(pucker, funnel) ≥ 0.25
SPREAD_WIDTH_RATIO_MIN = 0.97   # spread: 판정 창 너비 중앙값 / 기준 너비 ≥ 0.97
SPREAD_PUCKER_MAX = 0.35        #         그리고 판정 창 pucker 75백분위 < 0.35 (한두 프레임 튐에 흔들리지 않게)
OPEN_ABS_MIN = 0.08             # open: max open ≥ max(0.08, neutral.open + 0.06)
OPEN_OVER_NEUTRAL = 0.06
OPEN_JAW_MIN = 0.25             #       또는 max jaw ≥ 0.25
CLOSED_OPEN_MARGIN = 0.015      # closed: min open ≤ neutral.open + 0.015
CLOSED_BLEND_MIN = 0.30         #         또는 max close ≥ 0.3

NEUTRAL_WIDTH_Q = 10    # neutral 없을 때: open 하위 10% 프레임들의 width 중앙값 = 기준 너비
NEUTRAL_OPEN_Q = 5      #                  open 하위 5% 분위값 = 기준 벌림

PRAISE = {
    "round": "입술을 잘 모았어요.",
    "spread": "입꼬리를 잘 당겼어요.",
    "open": "입을 잘 벌렸어요.",
    "closed": "입술을 잘 붙였어요.",
}

def _unavailable() -> dict:
    return {"available": False, "series": None, "checks": [], "score": None}


# ── 작은 유틸 ─────────────────────────────────────────────
def _f(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _r(v: Any, nd: int = 3) -> float | None:
    x = _f(v)
    return None if x is None else round(x, nd) + 0.0


def _nanmax(a: np.ndarray) -> float | None:
    a = a[np.isfinite(a)]
    return float(a.max()) if len(a) else None


def _blend(v: Any) -> float:
    x = _f(v)
    return math.nan if x is None else min(1.0, max(0.0, x))


# ── 입력 정리 ─────────────────────────────────────────────
def _parse(lips: Any) -> dict | None:
    """유효하면 numpy 배열 묶음, 아니면 None."""
    if not isinstance(lips, dict):
        return None
    frames = lips.get("frames")
    if not isinstance(frames, list) or not frames:
        return None
    if "fps" in lips and lips["fps"] is not None:
        fps = _f(lips["fps"])
        if fps is None or not (MIN_FPS <= fps <= MAX_FPS):
            return None
    # fps 가 아예 없으면 타임스탬프에서 추정한다(아래).

    rows = []
    for fr in frames:
        if not isinstance(fr, dict):
            continue
        t, o, w = _f(fr.get("t")), _f(fr.get("open")), _f(fr.get("width"))
        if t is None or o is None or w is None or w <= 0:
            continue
        rows.append((t, max(0.0, o), w, _blend(fr.get("pucker")), _blend(fr.get("funnel")),
                     _blend(fr.get("jaw")), _blend(fr.get("close"))))
    if len(rows) < MIN_TOTAL_FRAMES:
        return None
    rows.sort(key=lambda r: r[0])
    arr = np.array(rows, dtype=np.float64)
    keep = np.concatenate([[True], np.diff(arr[:, 0]) > 0])  # 같은 시각 중복 제거
    arr = arr[keep]
    if len(arr) < MIN_TOTAL_FRAMES:
        return None
    eff_fps = 1.0 / float(np.median(np.diff(arr[:, 0])))
    if eff_fps < MIN_FPS:      # 너무 듬성듬성(또는 t 가 초 단위가 아님)
        return None
    return {
        "t": arr[:, 0], "open": arr[:, 1], "width": arr[:, 2],
        "pucker": arr[:, 3], "funnel": arr[:, 4], "jaw": arr[:, 5], "close": arr[:, 6],
        "fps": eff_fps,
    }


def _neutral(lips: dict, d: dict) -> dict:
    n = lips.get("neutral") if isinstance(lips.get("neutral"), dict) else {}
    nw = _f(n.get("width"))
    no = _f(n.get("open"))
    est = False
    if nw is None or nw <= 0:
        q = np.percentile(d["open"], NEUTRAL_WIDTH_Q)
        nw = float(np.median(d["width"][d["open"] <= q]))
        est = True
    if no is None or no < -0.05:
        no = float(np.percentile(d["open"], NEUTRAL_OPEN_Q))
        est = True
    return {"open": max(0.0, no), "width": nw, "estimated": est}


# ── 판정 ──────────────────────────────────────────────────
def _msg_fail(expect: str, ph: str, info: dict) -> str:
    p = PHONES[ph]
    j = p.jamo
    if expect == "round":
        if p.glide == "w":
            return f"'{j}' 소리는 시작할 때 입술을 동그랗게 모아 앞으로 내밀었다가 풀어 주세요."
        return f"'{j}' 소리는 입술을 더 동그랗게 모아 앞으로 내밀어 보세요."
    if expect == "spread":
        if info.get("pucker_high"):
            return f"'{j}' 소리에서 입술이 앞으로 모였어요. 입술을 내밀지 말고 입꼬리를 양옆으로 당겨 보세요."
        return f"'{j}' 소리는 웃듯이 입꼬리를 양옆으로 살짝 당겨 보세요."
    if expect == "open":
        return f"'{j}' 소리는 턱을 아래로 내려 입을 더 크게 벌려 보세요."
    if expect == "closed":
        if p.coda:
            return f"받침 '{j}' 소리는 끝에서 두 입술을 꼭 닫아 주세요."
        return f"'{j}' 소리는 두 입술을 꼭 붙였다가 소리를 내 보세요."
    return "입모양을 다시 확인해 보세요."


def _window(expect: str, seg_s: float, seg_e: float, t: np.ndarray) -> tuple[np.ndarray, float, float] | None:
    """판정에 쓸 프레임 마스크와 창 (모듈 상단 '판정 창' 참고). 프레임이 모자라면 None."""
    if expect == "closed":
        m = ((t >= seg_s - CLOSED_PAD) & (t <= seg_s + CLOSED_PAD)) | ((t >= seg_e - CLOSED_PAD) & (t <= seg_e + CLOSED_PAD))
        return (m, seg_s - CLOSED_PAD, seg_e + CLOSED_PAD) if int(m.sum()) >= MIN_SEG_FRAMES else None
    d = seg_e - seg_s
    trim = 0.5 * (1.0 - CENTER_FRAC) * d
    tries = [(seg_s + trim, seg_e - trim), (seg_s, seg_e)]
    if expect != "spread":
        tries.append((seg_s - SEG_PAD, seg_e + SEG_PAD))
    for a, b in tries:
        m = (t >= a) & (t <= b)
        if int(m.sum()) >= MIN_SEG_FRAMES:
            return m, a, b
    return None


def _nanq(a: np.ndarray, q: float) -> float | None:
    a = a[np.isfinite(a)]
    return float(np.percentile(a, q)) if len(a) else None


def _check(expect: str, ph: str, seg_s: float, seg_e: float, d: dict, nt: dict) -> dict | None:
    t = d["t"]
    win = _window(expect, seg_s, seg_e, t)
    if win is None:
        return None
    m, wa, wb = win

    info: dict[str, Any] = {}
    if expect == "round":
        wr = float(d["width"][m].min()) / nt["width"]
        pk, fn = _nanmax(d["pucker"][m]), _nanmax(d["funnel"][m])
        blend = max([v for v in (pk, fn) if v is not None], default=None)
        ok = wr <= ROUND_WIDTH_RATIO_MAX or (blend is not None and blend >= ROUND_BLEND_MIN)
        measured = {"width_ratio": _r(wr), "pucker": _r(pk), "funnel": _r(fn)}
    elif expect == "spread":
        wr = float(np.median(d["width"][m])) / nt["width"]
        pk = _nanq(d["pucker"][m], 75)
        info["pucker_high"] = pk is not None and pk >= SPREAD_PUCKER_MAX
        ok = wr >= SPREAD_WIDTH_RATIO_MIN and not info["pucker_high"]
        measured = {"width_ratio": _r(wr), "pucker": _r(pk)}
    elif expect == "open":
        need = max(OPEN_ABS_MIN, nt["open"] + OPEN_OVER_NEUTRAL)
        mo = float(d["open"][m].max())
        jw = _nanmax(d["jaw"][m])
        ok = mo >= need or (jw is not None and jw >= OPEN_JAW_MIN)
        measured = {"open": _r(mo), "jaw": _r(jw), "need": _r(need)}
    elif expect == "closed":
        need = nt["open"] + CLOSED_OPEN_MARGIN
        mn = float(d["open"][m].min())
        cl = _nanmax(d["close"][m])
        ok = mn <= need or (cl is not None and cl >= CLOSED_BLEND_MIN)
        measured = {"min_open": _r(mn), "close": _r(cl), "need": _r(need)}
    else:
        return None
    ok = bool(ok)
    measured["window"] = [_r(wa), _r(wb)]
    return {"ok": ok, "measured": measured, "msg": PRAISE[expect] if ok else _msg_fail(expect, ph, info)}


def _series(d: dict, nt: dict) -> dict:
    wr = d["width"] / nt["width"]
    blend = np.fmax(d["pucker"], d["funnel"])           # 한쪽만 NaN 이면 다른 쪽
    rnd = np.where(np.isfinite(blend), np.fmax(blend, 1.0 - wr), 1.0 - wr)
    rnd = np.clip(rnd, 0.0, 1.0)
    n = len(d["t"])
    idx = np.arange(n) if n <= MAX_POINTS else np.unique(np.linspace(0, n - 1, MAX_POINTS).round().astype(int))
    return {
        "t": [_r(v, 3) for v in d["t"][idx]],
        "open": [_r(v, 4) for v in d["open"][idx]],
        "width": [_r(v, 4) for v in d["width"][idx]],
        "round": [_r(v, 3) for v in rnd[idx]],
    }


def analyze(lips: dict | None, segments: list[dict]) -> dict:
    """입술 데이터 + 강제정렬 구간 → {"available", "series", "checks", "score"}.

    segments: [{"idx", "phone", "start", "end"}] (초). PHONES[phone].lip 이
    round / spread / open / closed 인 구간만 판정하고 neutral / None 은 건너뛴다.
    추가 필드: "neutral" {"open", "width", "estimated"}, "fps"(타임스탬프로 본 실제 fps).
    """
    d = _parse(lips)
    if d is None:
        return _unavailable()
    nt = _neutral(lips, d)

    checks: list[dict] = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        ph = seg.get("phone")
        p = PHONES.get(ph) if isinstance(ph, str) else None
        if p is None or p.lip not in PRAISE:
            continue
        s, e = _f(seg.get("start")), _f(seg.get("end"))
        if s is None or e is None or e < s:
            continue
        res = _check(p.lip, ph, s, e, d, nt)
        if res is None:
            continue
        idx = seg.get("idx")
        if isinstance(idx, (int, np.integer)) and not isinstance(idx, bool):
            idx = int(idx)  # numpy 정수 → 순수 int (JSON 직렬화)
        elif not isinstance(idx, (str, type(None))):
            idx = None
        checks.append({"idx": idx, "phone": ph, "jamo": p.jamo, "expect": p.lip,
                       "start": _r(s), "end": _r(e), **res})

    score = round(100 * sum(c["ok"] for c in checks) / len(checks)) if checks else None
    return {
        "available": True,
        "series": _series(d, nt),
        "checks": checks,
        "score": score,
        "neutral": {"open": _r(nt["open"], 4), "width": _r(nt["width"], 4), "estimated": nt["estimated"]},
        "fps": _r(d["fps"], 1),
    }
