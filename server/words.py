"""연습 단어 세트 로드 + 목표 음소열 생성 (CONTRACT 8절).

data/words.json 의 모든 항목은 pron(표준발음, 받침 대표음 7개만)을 명시한다.
pron 이 없을 때만 g2p.to_pron 을 함수 안에서 지연 import 해 쓴다.

계약 외 추가(build_target 결과):
  alt_prons — 같은 문장의 다른 표준·자연 발음형(허용 발음 시계[시게], 이어 말하기 밥 먹어요[밤머거요] 등).
              파이프라인은 녹음에 가장 그럴듯한 것을 목표로 고른다(pipeline.choose_variant).
  notes     — 자동 발음형(pron 미지정)에서 사전에 없어 추정한 자리의 '발음형을 확인해 주세요' 안내.
words.json 계약 외 필드:
  question_kind — type 이 question 인 항목의 의문문 종류. 'yn'(판정 의문문: 예/아니요로 답함, 끝을 올림)
                  | 'wh'(설명 의문문: 의문사가 있음, 끝을 내리는 것이 기본이고 올려도 됨).
  end_tune      — 'free' 면 끝 억양을 올려도 내려도 괜찮음(예: 인사 '안녕하세요'는 형태상 의문형이라 올리기도 함).
"""
from __future__ import annotations

import copy
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

try:  # 패키지(server.words)로도, --app-dir 로 server/ 를 직접 잡은 경우(words)로도 import 가능하게
    from .phones import PHONES, VOWEL_PHONE, decompose, jamo_of, pron_to_phones
except ImportError:  # pragma: no cover
    from phones import PHONES, VOWEL_PHONE, decompose, jamo_of, pron_to_phones  # type: ignore

log = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent / "data" / "words.json"
WORD_TYPES = ("word", "statement", "question")

__all__ = ["load_words", "load_categories", "load_catalog", "get_word", "build_target",
           "EmptyTargetError", "DATA_PATH", "WORD_TYPES", "infer_question_kind", "foreign_tokens"]

# 한글로 바꿔 적어야 하는 글자: 숫자·로마자(전각 포함)·한자·낱자모. g2p 는 한글 음절만 읽으므로
# 그대로 두면 '10월'이 [월]이 되어 말한 '시월'이 삽입 오류로 판정된다.
_FOREIGN = re.compile(r"[0-9A-Za-z\uFF10-\uFF19\uFF21-\uFF3A\uFF41-\uFF5A\u3131-\u318E\u4E00-\u9FFF\uF900-\uFAFF]+")
# 의문사(설명 의문문 표지). 어절이 이것으로 시작하면 'wh'.
_WH_WORDS = ("뭐", "무엇", "무슨", "뭘", "뭔", "어디", "언제", "누구", "누가", "누굴", "왜", "어떻게", "어떤",
             "어느", "얼마", "몇", "어때", "어땠", "어떠", "웬", "어째")


class EmptyTargetError(ValueError):
    """목표 문자열에 한글 음절이 없음 → API 에서 error: empty_target."""


def _syllables(s: str) -> list[str]:
    return [ch for ch in s if decompose(ch) is not None]


def foreign_tokens(text: str) -> list[str]:
    """한글로 바꿔 적어야 하는 부분(숫자·로마자·한자·낱자모) 목록."""
    return _FOREIGN.findall(text or "")


def infer_question_kind(text: str) -> str:
    """의문문 종류 추정: 어절이 의문사로 시작하면 'wh'(설명 의문문), 아니면 'yn'(판정 의문문).
    '어디 가요?'처럼 의문사가 있으면 판정·설명 두 뜻이 다 되므로 'wh'(올림·내림 모두 허용)로 둔다."""
    for w in re.sub(r"[^가-힣\s]", " ", text or "").split():
        if w.startswith(_WH_WORDS):
            return "wh"
    return "yn"


def _foreign_message(tokens: list[str]) -> str:
    shown = ", ".join(dict.fromkeys(tokens))
    if len(shown) > 40:
        shown = shown[:40] + "…"
    return (f"숫자·영어·한자는 소리 나는 대로 한글로 적어 주세요(예: 10월 → 시월, OK → 오케이). "
            f"바꿀 부분: {shown}")


def _pron_options(text: str):
    """g2p.pron_options 지연 호출(없으면 None)."""
    try:
        from .g2p import pron_options  # type: ignore
    except ImportError:
        try:
            from g2p import pron_options  # type: ignore
        except ImportError:
            return None
    try:
        return pron_options(text)
    except Exception as e:  # pragma: no cover - 대안 계산 실패가 목표 생성을 막지 않게
        log.warning("발음 대안 계산 실패 (%s): %s", text, e)
        return None


def _to_pron(text: str) -> str:
    """g2p.to_pron 지연 호출. g2p 모듈이 아직 없으면 철자를 그대로 쓴다
    (받침이 대표음뿐인 단어만 동작하고, 아니면 pron_to_phones 가 ValueError)."""
    try:
        from .g2p import to_pron  # type: ignore
    except ImportError:
        if __package__:
            log.warning("g2p 모듈을 불러올 수 없어 철자를 발음형으로 사용합니다: %s", text)
            return text
        try:  # --app-dir server 로 최상위 모듈로 실행된 경우
            from g2p import to_pron  # type: ignore
        except ImportError:
            log.warning("g2p 모듈을 불러올 수 없어 철자를 발음형으로 사용합니다: %s", text)
            return text
    return to_pron(text)


def _clean_pron(pron: str) -> str:
    """발음형에서 한글 음절·공백만 남기고 공백을 하나로."""
    pron = re.sub(r"[^가-힣\s]", " ", pron)
    return " ".join(pron.split())


def build_target(text: str, pron: str | None = None) -> dict:
    """{"text", "pron", "phones", "phone_syl", "syllables", "jamo"}.

    syllables[i] = {"text", "pron", "phones": [음소 인덱스], "lip": 그 음절 모음의 PHONES[v].lip}
    음절은 발음형(pron) 기준. 철자 음절 수가 발음형과 같으면 text 에 철자 음절을, 아니면 발음형 음절을 넣는다.
    jamo(계약 외 추가): 음소별 표시용 자모.
    """
    text = (text or "").strip()
    auto = pron is None or not str(pron).strip()
    if auto:
        if not _syllables(text):
            raise EmptyTargetError("연습할 한글 낱말이 없어요. 한글로 입력해 주세요.")
        bad = foreign_tokens(text)
        if bad:
            raise EmptyTargetError(_foreign_message(bad))
        pron = _to_pron(text)
    pron = _clean_pron(str(pron))
    phones, phone_syl = pron_to_phones(pron)
    pron_syls = _syllables(pron)
    if not phones or not pron_syls:
        raise EmptyTargetError("연습할 한글 낱말이 없어요. 한글로 입력해 주세요.")

    orth_syls = _syllables(text)
    same = len(orth_syls) == len(pron_syls)
    by_syl: dict[int, list[int]] = {}
    for k, s in enumerate(phone_syl):
        by_syl.setdefault(s, []).append(k)

    syllables = []
    for i, ps in enumerate(pron_syls):
        idxs = by_syl.get(i, [])
        vowel = next((phones[k] for k in idxs if PHONES[phones[k]].is_vowel), None)
        syllables.append({
            "text": orth_syls[i] if same else ps,
            "pron": ps,
            "phones": idxs,
            "lip": PHONES[vowel].lip if vowel else None,
        })
    out = {
        "text": text or pron,
        "pron": pron,
        "phones": phones,
        "phone_syl": phone_syl,
        "syllables": syllables,
        "jamo": [_display_jamo(p, pron_syls[phone_syl[k]]) for k, p in enumerate(phones)],
        "alt_prons": [],
        "notes": [],
    }
    opts = _pron_options(text) if _syllables(text) else None
    if opts is not None and opts.slots:
        base = opts.find(pron)
        if base is not None:
            alts = [opts.canonical] + [opts.render(ch) for ch in opts.single_changes(base)]
            out["alt_prons"] = [p for p in dict.fromkeys(alts) if p != pron][:12]
        if auto:
            out["notes"] = opts.notes()
    return out


def _display_jamo(sym: str, syllable: str) -> str:
    """표시 자모(ㅚ·ㅞ·ㅐ 등): 발음형 음절의 중성이 같은 음소면 그 자모."""
    p = PHONES.get(sym)
    if p is None or not p.is_vowel:
        return jamo_of(sym)
    d = decompose(syllable)
    if d is not None and VOWEL_PHONE.get(d[1]) == sym:
        return d[1]
    return jamo_of(sym)


@lru_cache(maxsize=1)
def _raw() -> dict:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    data.setdefault("categories", [])
    data.setdefault("words", [])
    return data


@lru_cache(maxsize=1)
def _built() -> tuple[dict, ...]:
    out = []
    for w in _raw()["words"]:
        try:
            t = build_target(w["text"], w.get("pron"))
        except Exception as e:  # 데이터 오류 한 건 때문에 목록 전체가 죽지 않게
            log.error("words.json 항목을 건너뜀 (%s): %s", w.get("id"), e)
            continue
        item = dict(w)
        item.setdefault("type", "word")
        item.setdefault("group", None)
        item.setdefault("focus", [])
        item.setdefault("hint", "")
        item["pron"] = t["pron"]
        item["phones"] = t["phones"]
        item["phone_syl"] = t["phone_syl"]
        item["syllables"] = t["syllables"]
        out.append(item)
    return tuple(out)


def load_words() -> list[dict]:
    """각 단어에 pron, phones, phone_syl, syllables 를 채워서 반환(호출마다 새 사본)."""
    return copy.deepcopy(list(_built()))


def load_categories() -> list[dict]:
    return copy.deepcopy(_raw()["categories"])


def load_catalog() -> dict:
    """GET /api/words 응답 모양: {"categories": [...], "words": load_words()}."""
    return {"categories": load_categories(), "words": load_words()}


def get_word(word_id: str) -> dict | None:
    for w in _built():
        if w.get("id") == word_id:
            return copy.deepcopy(w)
    return None
