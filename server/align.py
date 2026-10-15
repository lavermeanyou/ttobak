"""목표 음소열 vs 인식 음소열 정렬 (CONTRACT 4절).

Needleman–Wunsch 전역 정렬. 치환 비용은 phones.PHONES 의 음소 자질 거리로 정한다.

비용표(작을수록 '비슷한 소리'):
  - 같은 음소                                   0.0
  - 받침/초성 변이 (L↔R, k↔G, p↔B, t↔D)          0.3   (자질상 'coda' 만 다름)
  - 같은 조음위치·방식, 발성유형만 다름 (B↔Ph↔BB)  0.4
  - 그 밖의 자음끼리                              위치·방식·발성·받침 차이를 더함 (최대 1.3)
  - 모음끼리                                      0.5 + 0.1 × (높이/전후/원순/활음 차이 수), 최대 0.9
  - 자음 ↔ 모음                                   1.6
  - 삽입 / 삭제                                   1.0

결과는 목표 순서대로 나열되며, 삽입(ins)은 들린 위치에 끼워 넣는다.
"""
from __future__ import annotations

from functools import lru_cache

from .phones import PHONES

INDEL_COST = 1.0
CV_COST = 1.6          # 자음 ↔ 모음
UNKNOWN_COST = 1.6     # 인벤토리 밖 기호와의 치환
CC_MAX = 1.3           # 자음끼리 치환 비용 상한
V_BASE, V_STEP, V_MAX = 0.5, 0.1, 0.9

# 자음 자질별 가중치
_W_CODA = 0.3          # 받침 전용 음소 여부만 다름 (L↔R, k↔G …)
_W_PHONATION = 0.4     # 평음/격음/경음/공명음
_W_MANNER = 0.5        # 파열/파찰/마찰/비음/유음
_W_MANNER_NEAR = 0.35  # 파열↔파찰, 파찰↔마찰 (조음 동작이 겹침)
_W_PLACE = 0.4         # 양순/치조/치조구개/연구개/성문
_W_PLACE_NEAR = 0.25   # 치조↔치조구개

_NEAR_MANNER = {frozenset(("stop", "affricate")), frozenset(("affricate", "fricative"))}
_NEAR_PLACE = {frozenset(("alveolar", "alveolopalatal"))}
_HEIGHT_RANK = {"high": 0, "mid": 1, "low": 2}


def _consonant_cost(a, b) -> float:
    cost = 0.0
    if a.coda != b.coda:
        cost += _W_CODA
    if a.phonation != b.phonation:
        cost += _W_PHONATION
    if a.manner != b.manner:
        cost += _W_MANNER_NEAR if frozenset((a.manner, b.manner)) in _NEAR_MANNER else _W_MANNER
    if a.place != b.place:
        cost += _W_PLACE_NEAR if frozenset((a.place, b.place)) in _NEAR_PLACE else _W_PLACE
    return min(cost, CC_MAX)


def _vowel_cost(a, b) -> float:
    diffs = 0
    if a.height != b.height:
        # 고모음↔저모음은 두 단계 차이로 센다
        diffs += abs(_HEIGHT_RANK.get(a.height, 1) - _HEIGHT_RANK.get(b.height, 1)) or 1
    if a.backness != b.backness:
        diffs += 1
    if a.rounded != b.rounded:
        diffs += 1
    if a.glide != b.glide:
        diffs += 1
    return min(V_MAX, V_BASE + V_STEP * diffs)


@lru_cache(maxsize=4096)
def sub_cost(a: str, b: str) -> float:
    """음소 a 를 b 로 치환하는 비용(대칭)."""
    if a == b:
        return 0.0
    pa, pb = PHONES.get(a), PHONES.get(b)
    if pa is None or pb is None:
        return UNKNOWN_COST
    if pa.kind != pb.kind:
        return CV_COST
    if pa.kind == "C":
        return _consonant_cost(pa, pb)
    return _vowel_cost(pa, pb)


def align(target: list[str], heard: list[str]) -> list[dict]:
    """Needleman–Wunsch 정렬 → 편집 연산 목록.

    반환: [{"op": "match"|"sub"|"del"|"ins", "t": 목표 인덱스|None, "h": 인식 인덱스|None}]
    목표 순서대로이며, ins 는 해당 위치(앞뒤 목표 음소 사이)에 끼워 넣는다.
    동점이면 치환·일치 > 삭제 > 삽입 순으로 고른다(목표 음소를 최대한 들린 소리와 짝지음).
    """
    n, m = len(target), len(heard)
    # D[i][j] = target[:i] 와 heard[:j] 정렬 최소 비용
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        D[i][0] = i * INDEL_COST
    for j in range(1, m + 1):
        D[0][j] = j * INDEL_COST
    for i in range(1, n + 1):
        ti = target[i - 1]
        row, prev = D[i], D[i - 1]
        for j in range(1, m + 1):
            row[j] = min(prev[j - 1] + sub_cost(ti, heard[j - 1]),
                         prev[j] + INDEL_COST,
                         row[j - 1] + INDEL_COST)

    ops: list[dict] = []
    i, j = n, m
    eps = 1e-9
    while i > 0 or j > 0:
        if i > 0 and j > 0 and abs(D[i][j] - (D[i - 1][j - 1] + sub_cost(target[i - 1], heard[j - 1]))) < eps:
            op = "match" if target[i - 1] == heard[j - 1] else "sub"
            ops.append({"op": op, "t": i - 1, "h": j - 1})
            i, j = i - 1, j - 1
        elif i > 0 and abs(D[i][j] - (D[i - 1][j] + INDEL_COST)) < eps:
            ops.append({"op": "del", "t": i - 1, "h": None})
            i -= 1
        else:
            ops.append({"op": "ins", "t": None, "h": j - 1})
            j -= 1
    ops.reverse()
    return ops


def edit_distance(a: list[str], b: list[str]) -> int:
    """단순 편집거리(치환·삽입·삭제 각 1). 테스트·진단용 보조 함수."""
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1]
