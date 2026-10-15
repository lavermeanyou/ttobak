"""words.py + data/words.json 검증."""
from __future__ import annotations

import collections
import json

import pytest

from server import words
from server.phones import CODA_PHONE, PHONES, decompose, pron_to_phones

RAW = json.loads(words.DATA_PATH.read_text(encoding="utf-8"))
ENTRIES = RAW["words"]


def hangul(s: str) -> list[str]:
    return [c for c in s if decompose(c) is not None]


# ── 데이터 ───────────────────────────────────────────────
def test_data_path_is_absolute_and_exists():
    assert words.DATA_PATH.is_absolute() and words.DATA_PATH.exists()


def test_categories():
    cats = RAW["categories"]
    assert len(cats) >= 8
    ids = [c["id"] for c in cats]
    assert len(ids) == len(set(ids))
    for c in cats:
        assert c["name"].strip() and c["desc"].strip()


def test_entries_basic_fields():
    assert len(ENTRIES) >= 45
    ids = [w["id"] for w in ENTRIES]
    assert len(ids) == len(set(ids)), [i for i, n in collections.Counter(ids).items() if n > 1]
    cat_ids = {c["id"] for c in RAW["categories"]}
    for w in ENTRIES:
        assert w["category"] in cat_ids, w["id"]
        assert w["type"] in words.WORD_TYPES, w["id"]
        assert w.get("pron"), f"pron 누락: {w['id']}"
        assert isinstance(w["focus"], list) and w["focus"], w["id"]
        assert w["hint"].strip(), w["id"]
        assert w["group"] is None or isinstance(w["group"], str)
        if w["type"] == "question":
            assert w["text"].rstrip().endswith("?"), w["id"]


def test_every_category_used():
    used = collections.Counter(w["category"] for w in ENTRIES)
    for c in RAW["categories"]:
        assert used[c["id"]] >= 3, c["id"]


@pytest.mark.parametrize("w", ENTRIES, ids=[w["id"] for w in ENTRIES])
def test_pron_converts_and_focus_present(w):
    phones, syl = pron_to_phones(w["pron"])          # 대표음 아닌 받침이면 ValueError
    assert phones and len(phones) == len(syl)
    for f in w["focus"]:
        assert f in PHONES, (w["id"], f)
        assert f in phones, f"{w['id']}: focus {f} 가 {phones} 에 없음"
    # 발음형 받침은 대표음 7개뿐
    for ch in hangul(w["pron"]):
        jong = decompose(ch)[2]
        assert jong == "" or jong in CODA_PHONE, (w["id"], ch)
    # 발음형과 철자의 음절 수가 같아야 음절 블록에 철자를 함께 보여 줄 수 있다
    assert len(hangul(w["pron"])) == len(hangul(w["text"])), w["id"]


def test_groups_are_minimal_pair_sets():
    groups = collections.defaultdict(list)
    for w in ENTRIES:
        if w["group"]:
            groups[w["group"]].append(w)
    assert len(groups) >= 8
    for g, ws in groups.items():
        assert len(ws) >= 2, g
        assert len({w["category"] for w in ws}) == 1, g
        assert len({w["type"] for w in ws}) == 1, g
        # 최소대립쌍: 음소 수가 같고 정확히 한 자리만 다르다
        seqs = [pron_to_phones(w["pron"])[0] for w in ws]
        assert len({len(s) for s in seqs}) == 1, g
        for a in seqs:
            for b in seqs:
                if a is not b:
                    assert sum(x != y for x, y in zip(a, b)) == 1, (g, a, b)


def test_required_contrasts_present():
    texts = {w["text"] for w in ENTRIES}
    for t in ("불", "풀", "뿔", "달", "탈", "딸", "굴", "쿨", "꿀", "자다", "차다", "짜다", "방", "팡", "빵",
              "사과", "쌀", "살", "국물", "과자", "의자", "안녕하세요", "밥 먹었어요?", "이름이 뭐예요?"):
        assert t in texts, t
    types = collections.Counter(w["type"] for w in ENTRIES)
    assert types["question"] >= 2 and types["statement"] >= 2


# ── build_target ─────────────────────────────────────────
def test_build_target_shape_gukmul():
    t = words.build_target("국물", "궁물")
    assert t["text"] == "국물" and t["pron"] == "궁물"
    assert t["phones"] == ["G", "U", "NG", "M", "U", "L"]
    assert t["phone_syl"] == [0, 0, 0, 1, 1, 1]
    assert t["syllables"] == [
        {"text": "국", "pron": "궁", "phones": [0, 1, 2], "lip": "round"},
        {"text": "물", "pron": "물", "phones": [3, 4, 5], "lip": "round"},
    ]
    assert t["jamo"] == ["ㄱ", "ㅜ", "ㅇ", "ㅁ", "ㅜ", "ㄹ"]


def test_build_target_sentence_with_space_and_punct():
    t = words.build_target("밥 먹었어요?", "밤 머거써요")
    assert t["pron"] == "밤 머거써요"
    assert [s["pron"] for s in t["syllables"]] == list("밤머거써요")
    assert [s["text"] for s in t["syllables"]] == list("밥먹었어요")
    assert t["syllables"][0]["lip"] == "open"          # ㅏ
    assert t["syllables"][1]["lip"] == "neutral"       # ㅓ
    flat = [i for s in t["syllables"] for i in s["phones"]]
    assert flat == list(range(len(t["phones"])))


def test_build_target_syllable_count_mismatch_uses_pron():
    t = words.build_target("abc 가", "가나")
    assert [s["text"] for s in t["syllables"]] == ["가", "나"]


def test_build_target_lip_per_vowel():
    t = words.build_target("오이", "오이")
    assert [s["lip"] for s in t["syllables"]] == ["round", "spread"]
    t = words.build_target("과자", "과자")
    assert [s["lip"] for s in t["syllables"]] == [PHONES["oA"].lip, "open"]


def test_build_target_empty_raises():
    with pytest.raises(ValueError):
        words.build_target("", "")
    with pytest.raises(words.EmptyTargetError):
        words.build_target("hello")
    with pytest.raises(ValueError):
        words.build_target("닭", "닭")          # 발음형이 아님(겹받침)


def test_build_target_with_g2p():
    pytest.importorskip("server.g2p")
    t = words.build_target("국물")
    assert t["pron"] == "궁물"
    assert t["phones"] == ["G", "U", "NG", "M", "U", "L"]


# ── load_words ───────────────────────────────────────────
def test_load_words_filled_and_copied():
    ws = words.load_words()
    assert len(ws) == len(ENTRIES)
    for w in ws:
        for k in ("id", "text", "pron", "category", "focus", "group", "type", "hint",
                  "phones", "phone_syl", "syllables"):
            assert k in w, (w["id"], k)
        assert len(w["phones"]) == len(w["phone_syl"])
        assert all(s["lip"] in ("open", "spread", "round", "neutral") for s in w["syllables"])
    ws[0]["phones"].append("XX")
    assert "XX" not in words.load_words()[0]["phones"]


def test_load_catalog_and_get_word():
    cat = words.load_catalog()
    assert set(cat) == {"categories", "words"}
    assert len(cat["categories"]) >= 8
    w = words.get_word("gungmul")
    assert w and w["pron"] == "궁물" and w["phones"][2] == "NG"
    assert words.get_word("nope") is None


# ── 리뷰 반영: 억양 종류, 허용 발음, 숫자·영문 ───────────────
def test_questions_have_kind_and_hints_match():
    qs = [w for w in ENTRIES if w["type"] == "question"]
    assert {w["id"] for w in qs} >= {"s_ate", "s_name", "s_where", "s_okay", "s_like"}
    for w in qs:
        assert w.get("question_kind") in ("yn", "wh"), w["id"]
        assert w["question_kind"] == words.infer_question_kind(w["text"]), w["id"]
        if w["question_kind"] == "wh":
            # 설명 의문문 힌트가 '끝을 올려라'만 요구하면 안 된다
            assert "내려" in w["hint"] or "내리" in w["hint"], w["id"]
    assert sum(w["question_kind"] == "yn" for w in qs) >= 3
    hello = next(w for w in ENTRIES if w["id"] == "s_hello")
    assert hello.get("end_tune") == "free"


def test_sigye_uses_principle_pron_with_allowed_alt():
    w = next(w for w in ENTRIES if w["id"] == "sigye")
    assert w["pron"] == "시계" and "게" in w["hint"]
    t = words.build_target("시계", "시계")
    assert t["alt_prons"] == ["시게"]


def test_hints_use_tactile_checks_and_no_eu_syllables():
    texts = [c["desc"] for c in RAW["categories"]] + [w["hint"] for w in ENTRIES]
    for t in texts:
        assert "코를 막" not in t and "코를 살짝 막" not in t, t
        for bad in ("'음—'", "'은—'", "'응—'", "'을—'"):
            assert bad not in t, t
    contrast = next(c for c in RAW["categories"] if c["id"] == "contrast")
    assert "힘만" not in contrast["desc"] and "높낮이 선" in contrast["desc"]


@pytest.mark.parametrize("text,bad", [("오늘은 10월 9일이에요", "10"), ("커피 2잔 주세요", "2"), ("OK 좋아요", "OK"),
                                      ("１월", "１"), ("學校 가요", "學校"), ("ㅋㅋ 좋아", "ㅋㅋ")])
def test_build_target_rejects_digits_and_latin(text, bad):
    with pytest.raises(words.EmptyTargetError) as e:
        words.build_target(text)
    assert "한글로 적어" in str(e.value) and bad in str(e.value)
    assert words.foreign_tokens(text)


def test_build_target_explicit_pron_skips_foreign_check_and_punct_ok():
    assert words.build_target("10월", "시월")["pron"] == "시월"
    assert words.build_target("안녕하세요!")["pron"] == "안녕하세요"


def test_infer_question_kind():
    assert words.infer_question_kind("이름이 뭐예요?") == "wh"
    assert words.infer_question_kind("어디 가요?") == "wh"
    assert words.infer_question_kind("몇 시예요?") == "wh"
    assert words.infer_question_kind("밥 먹었어요?") == "yn"
    assert words.infer_question_kind("괜찮아요?") == "yn"


def test_build_target_alt_prons_notes_and_display_jamo():
    t = words.build_target("밥 먹었어요?", "밤 머거써요")
    assert t["alt_prons"][0] == "밥 머거써요"
    t = words.build_target("결속")
    assert t["notes"] and "확인" in t["notes"][0]
    assert words.build_target("결속", "결속")["notes"] == []      # 직접 준 발음형엔 안내 없음
    assert words.build_target("외국")["jamo"][0] == "ㅚ"
    assert words.build_target("웨딩")["jamo"][0] == "ㅞ"
