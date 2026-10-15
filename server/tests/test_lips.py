"""lips.analyze 테스트 — 합성 프레임으로 round/spread/open/closed 통과·실패, 입력 이상 처리."""
from __future__ import annotations

import json

import pytest

from server import lips

NEUTRAL = {"open": 0.02, "width": 0.95}
REST = {"open": 0.02, "width": 0.95, "pucker": 0.05, "funnel": 0.03, "jaw": 0.05, "close": 0.0}
UNAVAILABLE = {"available": False, "series": None, "checks": [], "score": None}


def make(dur=1.2, fps=30, during=None, seg=(0.5, 0.8), neutral=NEUTRAL, rest=None, fps_field=True):
    """seg 구간(초) 동안만 during 값을 덮어쓴 합성 프레임."""
    rest = dict(REST if rest is None else rest)
    frames = []
    n = int(dur * fps)
    for i in range(1, n + 1):
        t = round(i / fps, 4)
        f = dict(rest, t=t)
        if during and seg[0] <= t <= seg[1]:
            f.update(during)
        frames.append(f)
    out = {"frames": frames}
    if fps_field:
        out["fps"] = fps
    if neutral is not None:
        out["neutral"] = dict(neutral)
    return out


def s(phone, start=0.5, end=0.8, idx=0):
    return {"idx": idx, "phone": phone, "start": start, "end": end}


def one_check(data, phone, start=0.5, end=0.8):
    r = lips.analyze(data, [s(phone, start, end)])
    assert r["available"] is True
    json.dumps(r, allow_nan=False, ensure_ascii=False)
    assert len(r["checks"]) == 1, r["checks"]
    c = r["checks"][0]
    assert c["phone"] == phone and c["idx"] == 0 and isinstance(c["msg"], (str, type(None)))
    return r, c


# ── round ────────────────────────────────────────────────
def test_round_pass_by_width():
    r, c = one_check(make(during={"width": 0.95 * 0.8, "pucker": 0.1}), "O")
    assert c["expect"] == "round" and c["ok"] is True
    assert c["measured"]["width_ratio"] == pytest.approx(0.8, abs=1e-3)
    assert r["score"] == 100


def test_round_pass_by_pucker():
    _, c = one_check(make(during={"width": 0.95, "pucker": 0.4}), "U")
    assert c["ok"] is True


def test_round_fail():
    r, c = one_check(make(during={"width": 0.95, "pucker": 0.05, "funnel": 0.05}), "O")
    assert c["ok"] is False
    assert c["measured"]["width_ratio"] == pytest.approx(1.0, abs=1e-3)
    assert "동그랗게" in c["msg"] and "ㅗ" in c["msg"]
    assert r["score"] == 0


def test_round_w_diphthong_message():
    _, c = one_check(make(during={"width": 0.95, "pucker": 0.0, "funnel": 0.0}), "oA")  # ㅘ
    assert c["ok"] is False and "시작할 때" in c["msg"]


# ── spread ───────────────────────────────────────────────
def test_spread_pass():
    _, c = one_check(make(during={"width": 1.0, "pucker": 0.05}), "I")
    assert c["expect"] == "spread" and c["ok"] is True


def test_spread_fail_narrow():
    _, c = one_check(make(during={"width": 0.85, "pucker": 0.1}), "I")
    assert c["ok"] is False and "입꼬리" in c["msg"]


def test_spread_fail_pucker():
    _, c = one_check(make(during={"width": 1.0, "pucker": 0.5}), "EU")
    assert c["ok"] is False and "모였어요" in c["msg"]
    assert c["measured"]["pucker"] == pytest.approx(0.5)


# ── open ─────────────────────────────────────────────────
def test_open_pass_by_open():
    _, c = one_check(make(during={"open": 0.15, "jaw": 0.1}), "A")
    assert c["expect"] == "open" and c["ok"] is True
    assert c["measured"]["need"] == pytest.approx(0.08)


def test_open_pass_by_jaw():
    _, c = one_check(make(during={"open": 0.05, "jaw": 0.3}), "A")
    assert c["ok"] is True


def test_open_fail():
    _, c = one_check(make(during={"open": 0.05, "jaw": 0.1}), "A")
    assert c["ok"] is False and "벌려" in c["msg"]


def test_open_threshold_follows_neutral():
    # 기준 벌림이 큰 사람(0.05) → 0.11 이상 벌려야 통과
    data = make(during={"open": 0.10, "jaw": 0.1}, neutral={"open": 0.05, "width": 0.95},
                rest=dict(REST, open=0.05))
    _, c = one_check(data, "A")
    assert c["ok"] is False and c["measured"]["need"] == pytest.approx(0.11)


# ── closed ───────────────────────────────────────────────
def test_closed_pass_lips_together_at_onset():
    # 'ㅁ' 구간 0.50~0.58: 시작 근처에서 입술이 닫히고(open 0.025) 나머지는 벌어져 있음
    data = make(dur=1.2, rest=dict(REST, open=0.12), during={"open": 0.025}, seg=(0.47, 0.53))
    _, c = one_check(data, "M", 0.50, 0.58)
    assert c["expect"] == "closed" and c["ok"] is True


def test_closed_pass_by_close_blendshape():
    data = make(rest=dict(REST, open=0.12), during={"close": 0.5}, seg=(0.47, 0.53))
    _, c = one_check(data, "B", 0.50, 0.58)
    assert c["ok"] is True


def test_closed_fail():
    data = make(rest=dict(REST, open=0.12, close=0.0))
    _, c = one_check(data, "M", 0.50, 0.58)
    assert c["ok"] is False and "입술" in c["msg"]


def test_closed_coda_p_message():
    data = make(rest=dict(REST, open=0.12, close=0.0))
    _, c = one_check(data, "p", 0.50, 0.58)
    assert c["expect"] == "closed" and c["ok"] is False and c["msg"].startswith("받침")


# ── 판정 생략 / 점수 ─────────────────────────────────────
def test_neutral_and_nonlip_phones_skipped():
    r = lips.analyze(make(), [s("EO"), s("iEO"), s("G"), s("S"), s("??")])
    assert r["available"] is True and r["checks"] == [] and r["score"] is None


def test_too_few_frames_in_segment_skipped():
    r = lips.analyze(make(fps=10), [s("A", 0.50, 0.52)])  # [0.46, 0.56] 안에 프레임 1개
    assert r["available"] is True and r["checks"] == []
    r = lips.analyze(make(), [s("A", 5.0, 5.3)])            # 녹화 범위 밖
    assert r["checks"] == []


def test_score_is_ok_ratio():
    data = make(during={"open": 0.15, "width": 0.95, "pucker": 0.05})  # 0.5~0.8 크게 벌림, 둥글지 않음
    r = lips.analyze(data, [s("A", 0.5, 0.8, 0), s("O", 0.5, 0.8, 1), s("A", 0.5, 0.8, 2), s("I", 0.5, 0.8, 3)])
    oks = [c["ok"] for c in r["checks"]]
    assert len(oks) == 4
    assert r["score"] == round(100 * sum(oks) / 4)
    assert oks[0] is True and oks[1] is False and oks[2] is True


def test_bad_segments_do_not_crash():
    r = lips.analyze(make(), [None, "x", {"phone": "A"}, {"phone": "A", "start": 0.8, "end": 0.5},
                              {"phone": "A", "start": "a", "end": 1}, s("A")])
    assert len(r["checks"]) == 1
    assert lips.analyze(make(), None)["checks"] == []


# ── 입력 이상 → available false ──────────────────────────
@pytest.mark.parametrize("data", [
    None,
    {},
    [],
    "frames",
    {"fps": 30},
    {"fps": 30, "frames": []},
    {"fps": 30, "frames": None},
    {"fps": 30, "frames": [{"t": 0.1}] * 20},                                   # open/width 누락
    {"fps": 30, "frames": [{"open": 0.1, "width": 0.9}] * 20},                  # t 누락
    {"fps": 30, "frames": [{"t": i / 30, "open": "x", "width": None} for i in range(20)]},
    {"fps": 30, "frames": [{"t": i / 30, "open": 0.1, "width": 0.9} for i in range(3)]},  # 너무 짧음
    {"fps": 30, "frames": [{"t": 0.5, "open": 0.1, "width": 0.9}] * 20},        # 시각이 전부 같음
])
def test_unavailable_inputs(data):
    assert lips.analyze(data, [s("A")]) == UNAVAILABLE


@pytest.mark.parametrize("fps", [0, -30, 1, 10000, "abc", float("nan"), float("inf"), True, [30]])
def test_bad_fps(fps):
    data = make(during={"open": 0.15})
    data["fps"] = fps
    assert lips.analyze(data, [s("A")]) == UNAVAILABLE


def test_timestamps_in_ms_rejected():
    data = make()
    for f in data["frames"]:
        f["t"] = f["t"] * 1000  # 초가 아니라 ms 로 보냄 → 실제 fps 0.03
    assert lips.analyze(data, [s("A")]) == UNAVAILABLE


def test_missing_fps_estimated_from_timestamps():
    r = lips.analyze(make(fps_field=False, during={"open": 0.15}), [s("A")])
    assert r["available"] is True and r["fps"] == pytest.approx(30, abs=0.5)
    assert r["checks"][0]["ok"] is True


def test_partial_frames_dropped_and_blendshapes_optional():
    data = make(during={"width": 0.95 * 0.8})
    for f in data["frames"]:
        for k in ("pucker", "funnel", "jaw", "close"):
            f.pop(k)
    data["frames"][3] = {"t": "bad"}
    data["frames"][4]["open"] = float("nan")
    r = lips.analyze(data, [s("O"), s("I", 0.1, 0.3, 1), s("A", 0.1, 0.3, 2), s("M", 0.1, 0.2, 3)])
    assert r["available"] is True
    by = {c["idx"]: c for c in r["checks"]}
    assert by[0]["ok"] is True and by[0]["measured"]["pucker"] is None
    assert by[1]["ok"] is True                     # 너비 유지 → spread 통과 (pucker 없음)
    assert by[2]["ok"] is False                    # 벌림 없음, jaw 없음
    assert by[3]["ok"] is True                     # open = 기준값
    json.dumps(r, allow_nan=False)


# ── neutral 추정 / series ───────────────────────────────
def test_neutral_estimated_when_missing():
    data = make(neutral=None, during={"open": 0.2, "width": 1.05})
    r = lips.analyze(data, [s("A")])
    assert r["neutral"]["estimated"] is True
    assert r["neutral"]["width"] == pytest.approx(0.95, abs=1e-6)
    assert r["neutral"]["open"] == pytest.approx(0.02, abs=1e-6)
    assert r["checks"][0]["ok"] is True


def test_invalid_neutral_falls_back_to_estimate():
    data = make(neutral={"open": "?", "width": 0}, during={"width": 0.95 * 0.8})
    r = lips.analyze(data, [s("O")])
    assert r["neutral"]["estimated"] is True and r["neutral"]["width"] == pytest.approx(0.95, abs=1e-6)
    assert r["checks"][0]["ok"] is True


def test_series_shape_and_round_definition():
    data = make(dur=20.0, during={"width": 0.95 * 0.7, "pucker": 0.2, "funnel": 0.1}, seg=(5.0, 6.0))
    r = lips.analyze(data, [])
    ser = r["series"]
    assert set(ser) >= {"t", "open", "width", "round"}
    n = len(ser["t"])
    assert 100 < n <= 200 and all(len(ser[k]) == n for k in ("open", "width", "round"))
    assert ser["t"] == sorted(ser["t"])
    assert all(0.0 <= v <= 1.0 for v in ser["round"])
    # 구간 안: round = max(max(pucker, funnel), 1 - width_ratio) = max(0.2, 0.3) = 0.3
    inside = [rv for t, rv in zip(ser["t"], ser["round"]) if 5.1 < t < 5.9]
    assert inside and all(v == pytest.approx(0.3, abs=1e-3) for v in inside)
    # 구간 밖: max(0.05, 0) = 0.05
    outside = [rv for t, rv in zip(ser["t"], ser["round"]) if t < 4.0]
    assert all(v == pytest.approx(0.05, abs=1e-3) for v in outside)
    json.dumps(r, allow_nan=False)


def test_numpy_idx_is_serializable():
    import numpy as np
    r = lips.analyze(make(during={"open": 0.15}), [{"idx": np.int64(2), "phone": "A", "start": np.float32(0.5), "end": 0.8}])
    assert type(r["checks"][0]["idx"]) is int and r["checks"][0]["idx"] == 2
    json.dumps(r, allow_nan=False)


def test_unsorted_frames_are_sorted():
    data = make(during={"open": 0.15})
    data["frames"].reverse()
    r = lips.analyze(data, [s("A")])
    assert r["series"]["t"] == sorted(r["series"]["t"]) and r["checks"][0]["ok"] is True


# ── 동시조음: 앞 ㅗ 의 원순성이 ㅣ 경계로 넘어와도 ㅣ 판정은 구간 가운데로 ──
def _oi_frames(o_pucker=0.6, i_width=1.08, i_pucker=0.03, trans=0.06):
    frames = []
    for k in range(1, 30):
        t = k / 30
        if t < 0.10:
            pk, w = 0.05, 0.95
        elif t <= 0.30:
            pk, w = o_pucker, 0.80
        elif t <= 0.30 + trans:
            a = (t - 0.30) / trans
            pk, w = o_pucker + (i_pucker - o_pucker) * a, 0.80 + (i_width * 0.95 - 0.80) * a
        elif t <= 0.55:
            pk, w = i_pucker, i_width * 0.95
        else:
            pk, w = 0.05, 0.95
        frames.append({"t": round(t, 4), "open": 0.05, "width": w, "pucker": pk, "funnel": 0.05, "jaw": 0.1, "close": 0.0})
    return {"fps": 30, "frames": frames, "neutral": dict(NEUTRAL)}


def test_spread_after_round_is_not_penalized_by_coarticulation():
    r = lips.analyze(_oi_frames(), [s("O", 0.10, 0.30, 0), s("I", 0.30, 0.55, 1)])
    by = {c["phone"]: c for c in r["checks"]}
    assert by["O"]["ok"] is True and by["I"]["ok"] is True, r["checks"]
    assert by["I"]["measured"]["pucker"] < 0.35
    a, b = by["I"]["measured"]["window"]
    assert 0.30 < a < b < 0.55                       # 경계 밖(앞 ㅗ 구간)을 보지 않는다
    assert r["score"] == 100


def test_spread_still_fails_when_lips_pucker_inside_segment():
    r = lips.analyze(_oi_frames(i_pucker=0.5, i_width=1.0, trans=0.02), [s("I", 0.30, 0.55, 1)])
    c = r["checks"][0]
    assert c["ok"] is False and "모였어요" in c["msg"]


def test_short_spread_segment_is_skipped_not_padded():
    # 1 프레임짜리 ㅣ: 가운데·전체 구간 모두 프레임이 모자라면 경계 밖으로 넓히지 않고 판정 생략
    r = lips.analyze(_oi_frames(), [s("I", 0.30, 0.34, 1)])
    assert r["checks"] == []
