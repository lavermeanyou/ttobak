"""align.py — Needleman–Wunsch 음소 정렬 테스트 (모델 불필요)."""
from __future__ import annotations

import itertools
import random

import pytest

from server.align import CV_COST, INDEL_COST, align, edit_distance, sub_cost
from server.phones import PHONES

CONS = [s for s, p in PHONES.items() if p.kind == "C"]
VOWS = [s for s, p in PHONES.items() if p.kind == "V"]


def _pairs(t, h):
    """연산 목록 → (op, 목표기호, 인식기호) 튜플 목록(읽기 쉬운 비교용)."""
    ops = align(t, h)
    return [(o["op"], t[o["t"]] if o["t"] is not None else None, h[o["h"]] if o["h"] is not None else None)
            for o in ops]


def _check_structure(t, h, ops):
    """연산 목록이 두 음소열을 정확히 한 번씩, 순서대로 덮는지."""
    ts = [o["t"] for o in ops if o["op"] != "ins"]
    hs = [o["h"] for o in ops if o["op"] != "del"]
    assert ts == list(range(len(t)))
    assert hs == list(range(len(h)))
    for o in ops:
        assert set(o) == {"op", "t", "h"}
        assert o["op"] in {"match", "sub", "del", "ins"}
        if o["op"] == "match":
            assert t[o["t"]] == h[o["h"]]
        elif o["op"] == "sub":
            assert t[o["t"]] != h[o["h"]]
        elif o["op"] == "del":
            assert o["h"] is None and o["t"] is not None
        else:
            assert o["t"] is None and o["h"] is not None


# ── 비용표 ──────────────────────────────────────────────────
@pytest.mark.parametrize("a,b", [("B", "Ph"), ("B", "BB"), ("Ph", "BB"), ("D", "Th"), ("DD", "Th"),
                                 ("G", "Kh"), ("G", "GG"), ("J", "CHh"), ("J", "JJ"), ("S", "SS")])
def test_phonation_only_is_cheap(a, b):
    assert sub_cost(a, b) == pytest.approx(0.4)


@pytest.mark.parametrize("a,b", [("L", "R"), ("k", "G"), ("p", "B"), ("t", "D")])
def test_coda_onset_variants(a, b):
    assert sub_cost(a, b) == pytest.approx(0.3)


def test_vowel_costs_in_range():
    for a, b in itertools.combinations(VOWS, 2):
        assert 0.5 <= sub_cost(a, b) <= 0.9, (a, b)
    # 차이가 많을수록 비싸다: ㅜ↔ㅡ(전후·원순) < ㅏ↔ㅣ(높이 2단계·전후)
    assert sub_cost("O", "EO") == pytest.approx(0.6)       # 원순만 다름
    assert sub_cost("U", "EU") < sub_cost("A", "I")


def test_consonant_vowel_and_indel():
    for c in CONS:
        for v in VOWS:
            assert sub_cost(c, v) == pytest.approx(CV_COST)
    assert INDEL_COST == 1.0
    for a, b in itertools.combinations(CONS, 2):
        assert 0.0 < sub_cost(a, b) <= 1.3, (a, b)


def test_symmetric_and_zero_on_identity():
    for a, b in itertools.product(PHONES, repeat=2):
        assert sub_cost(a, b) == sub_cost(b, a)
        assert (sub_cost(a, b) == 0.0) == (a == b)
    assert sub_cost("B", "???") == sub_cost("???", "B") > 1.0


# ── 정렬 ───────────────────────────────────────────────────
def test_identical():
    t = ["G", "U", "NG", "M", "U", "L"]
    ops = align(t, list(t))
    assert [o["op"] for o in ops] == ["match"] * 6
    assert [(o["t"], o["h"]) for o in ops] == [(i, i) for i in range(6)]


def test_empty():
    assert align([], []) == []
    assert align(["A", "B"], []) == [{"op": "del", "t": 0, "h": None}, {"op": "del", "t": 1, "h": None}]
    assert align([], ["A"]) == [{"op": "ins", "t": None, "h": 0}]


def test_contrast_substitution():
    # 불 목표에 풀 → 첫 음소 치환
    assert _pairs(["B", "U", "L"], ["Ph", "U", "L"]) == [("sub", "B", "Ph"), ("match", "U", "U"), ("match", "L", "L")]


def test_gukmul_like_tts_output():
    # 실제 모델이 TTS "국물"에서 낸 결과 형태: ㄹ 받침이 R + 삽입 I 로 들림
    t = ["G", "U", "NG", "M", "U", "L"]
    h = ["G", "EU", "N", "M", "U", "R", "I"]
    assert _pairs(t, h) == [("match", "G", "G"), ("sub", "U", "EU"), ("sub", "NG", "N"), ("match", "M", "M"),
                            ("match", "U", "U"), ("sub", "L", "R"), ("ins", None, "I")]


def test_feature_cost_picks_similar_partner():
    # L 을 R 로 바꾸고 I 를 끼워 넣는 게(0.3+1.0) L→I(1.6)+R 삽입보다 싸다
    assert _pairs(["A", "L"], ["A", "R", "I"]) == [("match", "A", "A"), ("sub", "L", "R"), ("ins", None, "I")]
    # 자음 하나가 빠지고 모음이 남으면 모음끼리 짝지어야 한다
    assert _pairs(["S", "A", "G", "oA"], ["S", "A", "oA"]) == [
        ("match", "S", "S"), ("match", "A", "A"), ("del", "G", None), ("match", "oA", "oA")]
    # 'ㅡ' 삽입(받침 뒤 모음 덧붙임)
    assert _pairs(["S", "A", "k"], ["S", "A", "k", "EU"])[-1] == ("ins", None, "EU")


def test_deletion_in_middle_keeps_target_order():
    t = ["G", "O", "M", "A", "p", "SS", "EU", "M", "N", "I", "D", "A"]
    h = ["G", "O", "M", "A", "SS", "EU", "M", "N", "I", "D", "A"]
    ops = align(t, h)
    _check_structure(t, h, ops)
    assert [o for o in ops if o["op"] != "match"] == [{"op": "del", "t": 4, "h": None}]


def test_random_sequences_structure():
    rnd = random.Random(7)
    syms = list(PHONES)
    for _ in range(300):
        t = [rnd.choice(syms) for _ in range(rnd.randint(0, 9))]
        h = [rnd.choice(syms) for _ in range(rnd.randint(0, 9))]
        ops = align(t, h)
        _check_structure(t, h, ops)
        # 정렬 비용 ≤ 단순 편집거리 상한(모든 치환 비용 ≤ 1.6, 삽입·삭제 1.0 이므로 ≤ 1.6 × 편집거리)
        cost = sum(sub_cost(t[o["t"]], h[o["h"]]) if o["op"] in ("match", "sub") else INDEL_COST for o in ops)
        assert cost <= 1.6 * edit_distance(t, h) + 1e-9


def test_edit_distance_helper():
    assert edit_distance([], []) == 0
    assert edit_distance(["A"], []) == 1
    assert edit_distance(list("GUNG"), list("GNG")) == 1
    assert edit_distance(["G", "U", "NG", "M", "U", "L"], ["G", "EU", "N", "M", "U", "I"]) == 3
