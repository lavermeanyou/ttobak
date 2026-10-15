"""feedback.py — 교정 문구(phone_tip)와 점수·카드(summarize) 검증."""
from __future__ import annotations

import itertools
import re

import pytest

from server.feedback import MAX_CARDS, classify, display_jamo, josa, phone_tip, summarize
from server.phones import PHONES

CONS = [s for s, p in PHONES.items() if p.kind == "C"]
VOWELS = [s for s, p in PHONES.items() if p.kind == "V"]
OBS = ("lenis", "aspirated", "tense")


def n_sentences(text: str) -> int:
    """문장 끝(. ? !) 개수. 괄호·줄표 안쪽은 문장으로 세지 않는다."""
    return len([m for m in re.finditer(r"[.?!](?=\s|$)", text)])


def assert_tip(tip: str | None):
    assert isinstance(tip, str) and tip.strip()
    assert 1 <= n_sentences(tip) <= 2, tip
    assert len(tip) <= 220, tip
    assert "None" not in tip and "{" not in tip


# ── 조사 ────────────────────────────────────────────────
@pytest.mark.parametrize("word,pair,expect", [
    ("ㄱ", "이/가", "ㄱ이"), ("ㅏ", "이/가", "ㅏ가"), ("ㄹ", "으로/로", "ㄹ로"),
    ("ㅂ", "으로/로", "ㅂ으로"), ("ㅗ", "을/를", "ㅗ를"), ("받침 ㄹ", "은/는", "받침 ㄹ은"),
    ("ㄱ·ㄷ", "이/가", "ㄱ·ㄷ이"), ("등", "을/를", "등을"), ("사과", "은/는", "사과는"),
    ("'ㅏ'", "으로/로", "'ㅏ'로"),
])
def test_josa(word, pair, expect):
    assert josa(word, pair) == expect


# ── phone_tip ───────────────────────────────────────────
def test_ok_and_unknown_return_none():
    assert phone_tip("G", "G", "ok") is None
    assert phone_tip("XX", "G", "sub") is None
    assert phone_tip("G", "G", "ins") is None


def phonation_pairs():
    """같은 조음위치·방식이고 발성유형만 다른 모든 자음 쌍(ㅅ/ㅆ 포함)."""
    out = []
    for a, b in itertools.permutations(CONS, 2):
        A, B = PHONES[a], PHONES[b]
        if (A.place == B.place and A.manner == B.manner and A.phonation != B.phonation
                and A.phonation in OBS and B.phonation in OBS):
            out.append((a, b))
    return out


def test_phonation_pairs_exist():
    pairs = phonation_pairs()
    # ㅂㅃㅍ, ㄷㄸㅌ, ㄱㄲㅋ, ㅈㅉㅊ (각 6쌍) + ㅅ/ㅆ (2쌍) + 받침 불파음 ↔ 같은 자리 격음/경음
    assert ("B", "Ph") in pairs and ("SS", "S") in pairs and ("J", "JJ") in pairs
    assert len(pairs) >= 26


@pytest.mark.parametrize("t,h", phonation_pairs())
def test_tip_for_every_phonation_confusion(t, h):
    tip = phone_tip(t, h, "sub")
    assert_tip(tip)
    T = PHONES[t]
    if T.coda:            # 받침 불파음: 터뜨리지 말고 막은 채 멈추기
        assert "멈추" in tip
    elif T.phonation == "aspirated":
        assert "바람" in tip and ("휴지" in tip or "손바닥" in tip)
    elif T.phonation == "tense":
        assert "힘을 주" in tip and "단단" in tip
    else:                 # 평음(ㅅ 포함)
        assert "힘을 빼" in tip or "힘을 주지 말" in tip


@pytest.mark.parametrize("t,h", list(itertools.permutations(CONS, 2)))
def test_tip_for_every_consonant_pair(t, h):
    assert_tip(phone_tip(t, h, "sub"))


@pytest.mark.parametrize("t,h", list(itertools.permutations(VOWELS, 2)))
def test_tip_for_every_vowel_pair(t, h):
    tip = phone_tip(t, h, "sub")
    assert_tip(tip)


@pytest.mark.parametrize("t,h", [(c, v) for c in CONS for v in VOWELS] + [(v, c) for v in VOWELS for c in CONS])
def test_tip_for_cross_pairs(t, h):
    assert_tip(phone_tip(t, h, "sub"))


@pytest.mark.parametrize("sym", list(PHONES))
def test_tip_weak_del_unknown_for_every_phone(sym):
    weak = phone_tip(sym, sym, "weak")
    assert_tip(weak)
    assert "거의 맞" in weak and "또렷" in weak
    assert_tip(phone_tip(sym, None, "del"))
    assert_tip(phone_tip(sym, None, "sub"))
    assert_tip(phone_tip(sym, "[UNK]", "sub"))


def test_specific_slp_cues():
    # 과비성: 코 막기 검사
    t = phone_tip("B", "M", "sub")
    assert "코" in t and "입으로" in t
    assert classify("D", "N", "sub") == ("hypernasal", "alveolar")
    # 비음 → 구강음: 콧방울 떨림
    assert "콧방울" in phone_tip("M", "B", "sub")
    # ㅅ 파열음화/파찰음화: 혀끝 아랫니 뒤, 이 거의 붙이기
    for h in ("D", "Th", "J"):
        t = phone_tip("S", h, "sub")
        assert "아랫니" in t
    assert classify("S", "D", "sub") == ("sibilant", "stop")
    assert classify("S", "J", "sub") == ("sibilant", "affricate")
    # ㄹ: 초성 탄설음은 튕기기, 받침은 붙인 채 유지
    assert "튕기" in phone_tip("R", "N", "sub")
    assert "튕기" in phone_tip("R", "D", "sub")
    assert "붙인 채" in phone_tip("L", "N", "sub")
    assert "붙인 채" in phone_tip("L", "R", "sub")
    # 받침 탈락: 바로 떼지 말고 멈추기/이어 주기
    t = phone_tip("p", None, "del")
    assert "받침 ㅂ" in t and "바로 떼지 말고" in t and "멈추" in t
    t = phone_tip("M", None, "del", coda=True)
    assert "받침 ㅁ" in t and "다문 채" in t
    # 이중모음 단모음화: 시작·도착 모음 모두 언급
    t = phone_tip("oA", "A", "sub")
    assert "ㅗ" in t and "ㅏ" in t and "동그랗게" in t
    assert classify("uEO", "EO", "sub")[0] == "monophthong"
    t = phone_tip("uEO", "EO", "sub")
    assert "ㅜ" in t and "ㅓ" in t
    # 모음: 원순/평순, 높이, 전후
    assert "동그랗게" in phone_tip("O", "EO", "sub")
    assert "둥글게 모으지 말고" in phone_tip("EO", "O", "sub")
    assert "더 크게 벌리" in phone_tip("A", "EO", "sub")
    assert "덜 벌리" in phone_tip("U", "O", "sub")
    t = phone_tip("I", "EU", "sub")          # ㅣ↔ㅡ 는 혀끝이 아니라 혓바닥 앞쪽을 올리는지로 구별
    assert "혓바닥 앞쪽" in t and "혀끝을 아랫니" not in t
    # 중앙화
    assert classify("A", "EO", "sub") == ("centralize", "EO")
    assert classify("I", "EU", "sub") == ("centralize", "EU")
    # ㅎ 탈락은 부드럽게
    assert "ㅎ" in phone_tip("H", None, "del")
    # 조사
    assert phone_tip("Ph", "B", "sub").startswith("ㅍ은")
    assert phone_tip("A", "EO", "sub").startswith("ㅏ를")


# ── summarize ───────────────────────────────────────────
GUKMUL = [("G", 0), ("U", 0), ("NG", 0), ("M", 1), ("U", 1), ("L", 1)]


def mk(statuses: dict[int, tuple] | None = None, base=GUKMUL, gop=90):
    statuses = statuses or {}
    out = []
    for i, (ph, syl) in enumerate(base):
        st, heard, g = statuses.get(i, ("ok", ph, gop))
        out.append({"idx": i, "phone": ph, "syl": syl, "status": st,
                    "heard": heard, "gop": g, "jamo": PHONES[ph].jamo})
    return out


GOOD_AC = {"f0_stats": {"range_st": 5.0, "voiced_ratio": 0.6, "end_rise_st": -1.5},
           "loudness": {"mean_db": 66.0, "max_db": 74.0}}


def check_shape(r: dict):
    assert set(r) >= {"scores", "feedback"}
    s = r["scores"]
    assert set(s) >= {"overall", "accuracy", "clarity", "intonation", "lips"}
    for k, v in s.items():
        assert v is None or (isinstance(v, int) and 0 <= v <= 100), (k, v)
    assert isinstance(s["overall"], int) and isinstance(s["accuracy"], int)
    assert len(r["feedback"]) <= MAX_CARDS
    for c in r["feedback"]:
        assert c["level"] in ("error", "warn", "info")
        assert isinstance(c["title"], str) and c["title"]
        assert isinstance(c["body"], str) and c["body"]
        assert isinstance(c["phones"], list) and all(isinstance(i, int) for i in c["phones"])


def test_all_correct_praise_card():
    r = summarize(mk(), GOOD_AC, {"available": False, "series": None, "checks": [], "score": None}, "word")
    check_shape(r)
    assert r["scores"]["accuracy"] == 100
    assert r["scores"]["clarity"] == 90
    assert r["scores"]["lips"] is None
    assert r["feedback"][0]["level"] == "info"
    assert "다음 단계" in r["feedback"][0]["body"]
    assert all(c["level"] != "error" for c in r["feedback"])


def test_accuracy_weights_and_insertion_penalty():
    phones = mk({0: ("weak", "G", 40), 1: ("sub", "EO", 30), 2: ("del", None, 5)})
    r = summarize(phones, GOOD_AC, None, "word")
    # (1+... ) ok 3개 + weak 0.6 = 3.6 / 6
    assert r["scores"]["accuracy"] == round(3.6 / 6 * 100)
    r2 = summarize(phones, GOOD_AC, None, "word", insertions=[{"after": 2, "phone": "EU", "jamo": "ㅡ"}])
    assert r2["scores"]["accuracy"] == round((3.6 - 0.5) / 6 * 100)
    check_shape(r2)
    # 삽입이 넘쳐도 0 아래로 내려가지 않는다
    many = [{"after": 0, "phone": "EU", "jamo": "ㅡ"}] * 30
    assert summarize(phones, GOOD_AC, None, "word", insertions=many)["scores"]["accuracy"] == 0


def test_clarity_is_gop_mean_and_overall_renormalized():
    phones = mk(gop=80)
    phones[0]["gop"] = 20
    r = summarize(phones, {}, None, "word")
    assert r["scores"]["clarity"] == round((20 + 80 * 5) / 6)
    assert r["scores"]["intonation"] is None and r["scores"]["lips"] is None
    acc, cl = r["scores"]["accuracy"], r["scores"]["clarity"]
    assert r["scores"]["overall"] == round((acc * 0.5 + cl * 0.25) / 0.75)
    lips = {"available": True, "score": 40, "checks": []}
    r = summarize(phones, GOOD_AC, lips, "word")
    s = r["scores"]
    exp = (s["accuracy"] * .5 + s["clarity"] * .25 + s["intonation"] * .1 + 40 * .15) / 1.0
    assert abs(s["overall"] - exp) <= 1


def test_priority_order_and_max_cards():
    # 0 ㄱ→ㄲ(대비), 1 ㅜ→ㅓ(모음), 2 받침ㅇ 탈락, 4 ㅜ 약함, 5 ㄹ→ㄴ
    phones = mk({0: ("sub", "GG", 30), 1: ("sub", "EO", 30), 2: ("del", None, 5),
                 4: ("weak", "U", 40), 5: ("sub", "N", 20)})
    lips = {"available": True, "score": 30,
            "checks": [{"idx": 1, "phone": "U", "expect": "round", "ok": False}]}
    ac = {"f0_stats": {"range_st": 0.5, "voiced_ratio": 0.5, "end_rise_st": -2.0},
          "loudness": {"mean_db": 40.0, "max_db": 55.0}}
    r = summarize(phones, ac, lips, "question")
    check_shape(r)
    kinds = [c["kind"] for c in r["feedback"]]
    assert len(kinds) == MAX_CARDS
    assert kinds[0] == "phonation"
    assert kinds.index("del") > kinds.index("phonation")
    assert kinds.index("centralize") > kinds.index("del")
    assert "intonation" not in kinds and "loudness" not in kinds   # 우선순위에서 밀림
    assert r["feedback"][0]["title"] == "'궁'의 ㄱ이 ㄲ처럼 들려요"
    assert r["feedback"][0]["phones"] == [0]


def test_lips_before_prosody():
    lips = {"available": True, "score": 0,
            "checks": [{"idx": 1, "phone": "U", "expect": "round", "ok": False},
                       {"idx": 4, "phone": "U", "expect": "round", "ok": False}]}
    ac = {"f0_stats": {"range_st": 0.5, "voiced_ratio": 0.5, "end_rise_st": 0.0},
          "loudness": {"mean_db": 40.0, "max_db": 50.0}}
    r = summarize(mk({1: ("sub", "EO", 30)}), ac, lips, "question")
    kinds = [c["kind"] for c in r["feedback"]]
    assert kinds[:4] == ["centralize", "lips", "intonation", "loudness"]
    assert r["feedback"][1]["phones"] == [1, 4]


def test_same_type_errors_grouped_into_one_card():
    base = [("G", 0), ("A", 0), ("D", 1), ("A", 1)]          # 가다 → 까따
    phones = mk({0: ("sub", "GG", 20), 2: ("sub", "DD", 20)}, base=base)
    r = summarize(phones, GOOD_AC, None, "word")
    cards = [c for c in r["feedback"] if c["kind"] == "phonation"]
    assert len(cards) == 1
    assert cards[0]["phones"] == [0, 2]
    assert "ㄱ·ㄷ" in cards[0]["title"] and "ㄲ·ㄸ" in cards[0]["title"]
    # 받침 탈락 두 개도 한 카드
    base = [("G", 0), ("U", 0), ("k", 0), ("B", 1), ("A", 1), ("p", 1)]   # 국밥
    phones = mk({2: ("del", None, 5), 5: ("del", None, 5)}, base=base)
    r = summarize(phones, GOOD_AC, None, "word")
    dels = [c for c in r["feedback"] if c["kind"] == "del"]
    assert len(dels) == 1 and dels[0]["phones"] == [2, 5]
    assert dels[0]["title"] == "받침 ㄱ·ㅂ이 빠졌어요"


def test_coda_context_from_syllables():
    base = [("B", 0), ("A", 0), ("M", 0)]                     # 밤: 받침 ㅁ
    r = summarize(mk({2: ("del", None, 5)}, base=base), GOOD_AC, None, "word")
    assert "받침 ㅁ" in r["feedback"][0]["title"]
    base = [("A", 0), ("M", 1), ("A", 1)]                     # 아마: 첫소리 ㅁ
    r = summarize(mk({1: ("del", None, 5)}, base=base), GOOD_AC, None, "word")
    assert "받침" not in r["feedback"][0]["title"]


def test_insertion_card():
    r = summarize(mk(), GOOD_AC, None, "word", insertions=[{"after": 2, "phone": "EU", "jamo": "ㅡ"}])
    kinds = [c["kind"] for c in r["feedback"]]
    assert "insertion" in kinds and "praise" not in kinds
    card = r["feedback"][kinds.index("insertion")]
    assert "ㅡ" in card["title"] and card["phones"] == [2, 3]


@pytest.mark.parametrize("rise,good", [(3.5, True), (2.0, True), (0.5, False), (-2.0, False)])
def test_question_intonation(rise, good):
    ac = {"f0_stats": {"range_st": 5.0, "voiced_ratio": 0.6, "end_rise_st": rise}}
    r = summarize(mk(), ac, None, "question")
    score = r["scores"]["intonation"]
    assert (score >= 70) is good
    has_card = any(c["kind"] == "intonation" for c in r["feedback"])
    assert has_card is (not good)


def test_question_intonation_top_level_end_rise_fallback():
    ac = {"f0_stats": {"range_st": 5.0, "voiced_ratio": 0.6}, "end_rise_st": 4.0}
    assert summarize(mk(), ac, None, "question")["scores"]["intonation"] >= 90


@pytest.mark.parametrize("rng,good", [(0.5, False), (1.5, False), (2.0, True), (6.0, True), (12.0, True), (20.0, False)])
def test_statement_range_intonation(rng, good):
    ac = {"f0_stats": {"range_st": rng, "voiced_ratio": 0.6, "end_rise_st": -1.0}}
    r = summarize(mk(), ac, None, "statement")
    assert (r["scores"]["intonation"] >= 70) is good
    mono = any(c["title"] == "목소리 높낮이가 거의 없어요" for c in r["feedback"])
    assert mono is (rng < 2.0)


def test_statement_rising_end_warns():
    ac = {"f0_stats": {"range_st": 6.0, "voiced_ratio": 0.6, "end_rise_st": 5.0}}
    r = summarize(mk(), ac, None, "statement")
    assert r["scores"]["intonation"] <= 60
    assert any("질문처럼" in c["title"] for c in r["feedback"])


@pytest.mark.parametrize("ac", [None, {}, {"f0_stats": {"range_st": None, "voiced_ratio": 0.0}},
                                {"f0_stats": {"range_st": 5.0, "voiced_ratio": 0.01}}])
def test_intonation_null_without_data(ac):
    for st in ("word", "statement", "question"):
        r = summarize(mk(), ac, None, st)
        assert r["scores"]["intonation"] is None
        check_shape(r)


def test_loudness_cards():
    quiet = {"f0_stats": {"range_st": 5.0, "voiced_ratio": 0.6}, "loudness": {"mean_db": 44.0, "max_db": 52.0}}
    r = summarize(mk(), quiet, None, "word")
    assert any(c["kind"] == "loudness" and c["level"] == "warn" and "작" in c["title"] for c in r["feedback"])
    ok = {"f0_stats": {"range_st": 5.0, "voiced_ratio": 0.6}, "loudness": {"mean_db": 65.0, "max_db": 75.0}}
    assert not any(c["kind"] == "loudness" for c in summarize(mk(), ok, None, "word")["feedback"])
    loud = {"f0_stats": {"range_st": 5.0, "voiced_ratio": 0.6}, "loudness": {"mean_db": 80.0, "max_db": 88.0}}
    assert any(c["kind"] == "loudness" for c in summarize(mk(), loud, None, "word")["feedback"])


def test_degenerate_inputs():
    r = summarize([], None, None, "word")
    check_shape(r)
    assert r["scores"]["accuracy"] == 0 and r["feedback"] == []
    # 상태/필드가 이상해도 죽지 않는다
    weird = [{"idx": 0, "phone": "G", "status": "sub", "heard": "[UNK]", "gop": None},
             {"idx": 1, "phone": "??", "status": "sub", "heard": "A", "gop": "x"},
             {"idx": 2, "phone": "A", "status": "del"}]
    r = summarize(weird, {"f0_stats": None, "loudness": None}, {"available": True, "checks": None}, "nonsense")
    check_shape(r)


def test_weak_only_gets_praise_plus_weak_card():
    r = summarize(mk({1: ("weak", "U", 40)}), GOOD_AC, None, "word")
    kinds = [c["kind"] for c in r["feedback"]]
    assert kinds[0] == "praise" and "weak" in kinds
    weak = r["feedback"][kinds.index("weak")]
    # weak 는 정상 화자에게도 나오는 애매한 자리라 정보 수준 카드(사람 낭독 보정)
    assert weak["level"] == "info" and weak["phones"] == [1]
    assert weak["body"].startswith("거의 맞았어요")
    assert not any(c["level"] in ("error", "warn") for c in r["feedback"])


def test_many_errors_capped():
    base = [(p, i) for i, p in enumerate(["G", "D", "B", "J", "S", "R", "M", "N"])]
    heard = {0: "GG", 1: "N", 2: "M", 3: "S", 4: "D", 5: "N", 6: "B", 7: "D"}
    phones = mk({i: ("sub", h, 10) for i, h in heard.items()}, base=base)
    r = summarize(phones, GOOD_AC, None, "word")
    check_shape(r)
    assert len(r["feedback"]) == MAX_CARDS
    assert r["feedback"][0]["kind"] == "phonation"
    assert r["feedback"][1]["kind"] == "sibilant"


# ── 리뷰 반영: 억양 종류, 칭찬 카드, ㄹㄹ, 제목, 촉각 검사, 시작 음높이, 모음 문구, 표시 자모 ──
def _ac(rise, rng=5.0):
    return {"f0_stats": {"range_st": rng, "voiced_ratio": 0.6, "end_rise_st": rise},
            "loudness": {"mean_db": 66.0, "max_db": 74.0}}


@pytest.mark.parametrize("rise", [-5.0, 0.0, 4.0])
def test_wh_question_accepts_fall_and_rise(rise):
    """설명 의문문(이름이 뭐예요?)은 끝을 내려도 올려도 정상 — 억양 카드 없음, 점수는 음높이 폭으로."""
    r = summarize(mk(), _ac(rise), None, "question", question_kind="wh")
    assert not any(c["kind"] == "intonation" for c in r["feedback"])
    assert r["scores"]["intonation"] >= 90
    assert "끝을 내려서도" not in r["feedback"][0]["body"]


def test_yn_question_requires_rise_and_default_is_yn():
    for kw in ({"question_kind": "yn"}, {}):
        r = summarize(mk(), _ac(-5.0), None, "question", **kw)
        assert r["scores"]["intonation"] < 50
        assert any(c["kind"] == "intonation" for c in r["feedback"])


def test_free_tune_statement_has_no_rise_warning():
    """인사 '안녕하세요'(end_tune=free)는 끝이 올라가도 '질문처럼 들려요' 카드를 내지 않는다."""
    r = summarize(mk(), _ac(6.0), None, "statement", tune="free")
    assert not any("질문처럼" in c["title"] for c in r["feedback"])
    assert r["scores"]["intonation"] >= 90
    r = summarize(mk(), _ac(6.0), None, "statement")
    assert any("질문처럼" in c["title"] for c in r["feedback"])


def test_praise_card_does_not_contradict_intonation_warning():
    r = summarize(mk(), _ac(-6.0), None, "question", question_kind="yn")
    kinds = [c["kind"] for c in r["feedback"]]
    assert kinds[:2] == ["praise", "intonation"]
    praise = r["feedback"][0]
    assert praise["title"] == "소리는 모두 정확했어요"
    assert "끝을 내려" not in praise["body"] and "다음 단계" not in praise["body"]
    # 억양이 좋으면 yn 의문문에만 '끝을 내려서도' 다음 단계를 준다
    good = summarize(mk(), _ac(5.0), None, "question", question_kind="yn")["feedback"][0]
    assert good["title"] == "모든 소리가 정확하게 들렸어요" and "끝을 내려서도" in good["body"]


DALLIGI = [("D", 0), ("A", 0), ("L", 0), ("R", 1), ("I", 1), ("G", 2), ("I", 2)]


def test_r_after_l_is_lateral_not_flap():
    weak = summarize(mk({3: ("weak", "R", 40)}, base=DALLIGI), GOOD_AC, None, "word")
    card = next(c for c in weak["feedback"] if c["kind"] == "weak")
    assert "톡" not in card["body"] and "튕기" not in card["body"].replace("튕기지 않아요", "")
    assert "붙인 채" in card["body"]
    for h in ("N", "D"):
        t = phone_tip("R", h, "sub", prev="L")
        assert_tip(t)
        assert "붙인 채" in t and "톡" not in t
    # 앞이 L 이 아니면 탄설음 지시 그대로
    assert "톡" in phone_tip("R", "R", "weak") and "톡" in phone_tip("R", "D", "sub")


def test_same_jamo_substitution_titles():
    geoul = [("G", 0), ("EO", 0), ("U", 1), ("L", 1)]
    r = summarize(mk({3: ("sub", "R", 10)}, base=geoul), GOOD_AC, None, "word")
    assert r["feedback"][0]["title"] == "'울'의 받침 ㄹ을 튕겨서 소리 냈어요"
    nara = [("N", 0), ("A", 0), ("R", 1), ("A", 1)]
    r = summarize(mk({2: ("sub", "L", 10)}, base=nara), GOOD_AC, None, "word")
    assert r["feedback"][0]["title"] == "'라'의 첫소리 ㄹ을 혀를 붙인 채로 소리 냈어요"
    for c in r["feedback"]:
        assert "ㄹ이 ㄹ처럼" not in c["title"]
    # 받침 불파음 → 첫소리 같은 자모(기존 동작 유지)
    ap = [("A", 0), ("p", 0)]
    r = summarize(mk({1: ("sub", "B", 10)}, base=ap), GOOD_AC, None, "word")
    assert r["feedback"][0]["title"] == "'압'의 받침 ㅂ을 터뜨려서 소리 냈어요"


@pytest.mark.parametrize("t,h,st", [("B", "M", "sub"), ("D", "N", "sub"), ("k", "NG", "sub"), ("R", "N", "sub"),
                                     ("L", "N", "sub"), ("M", "B", "sub")])
def test_nasal_checks_are_tactile_or_visual(t, h, st):
    tip = phone_tip(t, h, st)
    assert "코를 막" not in tip and "코를 살짝 막" not in tip and "소리가 그대로" not in tip
    assert "콧방울" in tip or "거울" in tip or "멈추" in tip


@pytest.mark.parametrize("sym", ["M", "N", "NG", "L"])
def test_coda_sonorant_tips_do_not_write_eu_syllables(sym):
    for tip in (phone_tip(sym, None, "del", coda=True), phone_tip(sym, sym, "weak", coda=True),
                phone_tip(sym, "R" if sym == "L" else "B", "sub", coda=True)):
        for bad in ("음—", "은—", "응—", "을—"):
            assert bad not in tip, tip


def test_phonation_initial_adds_pitch_cue():
    assert "낮은 목소리" in phone_tip("B", "Ph", "sub", initial=True)
    assert "높은 목소리" in phone_tip("Ph", "B", "sub", initial=True)
    assert "높은 목소리" in phone_tip("BB", "B", "sub", initial=True)
    assert "목소리" not in phone_tip("B", "Ph", "sub")              # 어절 첫소리가 아니면 음높이 언급 없음
    assert_tip(phone_tip("BB", "Ph", "sub", initial=True))
    bul = [("B", 0), ("U", 0), ("L", 0)]
    r = summarize(mk({0: ("sub", "Ph", 5)}, base=bul), GOOD_AC, None, "word")
    assert "높낮이 선" in r["feedback"][0]["body"]


def test_o_u_and_w_diphthong_vowel_text():
    o = phone_tip("O", "U", "sub")
    u = phone_tip("U", "O", "sub")
    assert "입술" in o and "혀" in o and "내밀" in o
    assert "혀를 조금 앞으로" in u and "쭉" not in u
    w = phone_tip("oA", "uEO", "sub")
    assert "끝에서 풀려" in w and "동그랗게 앞으로 나와 있어야" not in w


def test_display_jamo_for_merged_vowels():
    assert display_jamo("oE", "외") == "ㅚ" and display_jamo("oE", "웨") == "ㅞ" and display_jamo("oE", "왜") == "ㅙ"
    assert display_jamo("E", "개") == "ㅐ" and display_jamo("E", "게") == "ㅔ" and display_jamo("iE", "얘") == "ㅒ"
    assert display_jamo("oE", "가") == "ㅙ" and display_jamo("G", "외") == "ㄱ"
    t = phone_tip("oE", "E", "sub", jamo="ㅞ")
    assert t.startswith("ㅞ는") and "'ㅜ'" in t
    t = phone_tip("oE", "E", "sub", jamo="ㅚ")
    assert t.startswith("ㅚ는") and "둥글게" in t
    ph = mk({0: ("sub", "I", 5)}, base=[("oE", 0), ("G", 1), ("U", 1), ("k", 1)])
    ph[0]["jamo"] = "ㅚ"
    r = summarize(ph, GOOD_AC, None, "word")
    assert r["feedback"][0]["title"].startswith("'외'의 ㅚ")
