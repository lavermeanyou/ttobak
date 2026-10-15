"""음소 인벤토리 — 모든 모듈이 공유하는 단일 기준.

음소 표기는 인식 모델(slplab/wav2vec2-xls-r-300m_phone-mfa_korean)의 MFA 표기를 그대로 쓴다.
표기는 '표준발음'(음운규칙 적용 후) 기준이다. 예: 국물 → 궁물 → G U NG M U L

- 초성 ㄹ = R, 받침 ㄹ = L  (ㄹㄹ 은 'L R')
- 받침 파열음은 불파음 p / t / k (대표음 7개: k t p N L M NG)
- ㅐ/ㅔ → E,  ㅒ/ㅖ → iE,  ㅙ/ㅞ/ㅚ → oE
"""
from __future__ import annotations

from dataclasses import dataclass

# ── 한글 자모 ─────────────────────────────────────────────
CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")

ONSET_PHONE = {
    "ㄱ": "G", "ㄲ": "GG", "ㅋ": "Kh",
    "ㄷ": "D", "ㄸ": "DD", "ㅌ": "Th",
    "ㅂ": "B", "ㅃ": "BB", "ㅍ": "Ph",
    "ㅈ": "J", "ㅉ": "JJ", "ㅊ": "CHh",
    "ㅅ": "S", "ㅆ": "SS", "ㅎ": "H",
    "ㅁ": "M", "ㄴ": "N", "ㄹ": "R", "ㅇ": None,
}
VOWEL_PHONE = {
    "ㅏ": "A", "ㅐ": "E", "ㅑ": "iA", "ㅒ": "iE", "ㅓ": "EO", "ㅔ": "E", "ㅕ": "iEO",
    "ㅖ": "iE", "ㅗ": "O", "ㅘ": "oA", "ㅙ": "oE", "ㅚ": "oE", "ㅛ": "iO", "ㅜ": "U",
    "ㅝ": "uEO", "ㅞ": "oE", "ㅟ": "uI", "ㅠ": "iU", "ㅡ": "EU", "ㅢ": "euI", "ㅣ": "I",
}
# 표준발음 형태(이미 음운규칙 적용됨)의 받침 → 음소. 대표음 7개만 허용.
CODA_PHONE = {"ㄱ": "k", "ㄷ": "t", "ㅂ": "p", "ㄴ": "N", "ㄹ": "L", "ㅁ": "M", "ㅇ": "NG"}


# ── 음소 자질 ─────────────────────────────────────────────
@dataclass(frozen=True)
class Phone:
    sym: str            # 모델 표기
    jamo: str           # 화면 표시용 자모
    kind: str           # 'C' 자음 | 'V' 모음
    # 자음
    place: str | None = None      # bilabial | alveolar | alveolopalatal | velar | glottal
    manner: str | None = None     # stop | affricate | fricative | nasal | liquid
    phonation: str | None = None  # lenis(평음) | aspirated(격음) | tense(경음) | sonorant
    coda: bool = False            # 받침 전용 음소(p t k L NG)
    # 모음 (이중모음은 '도착 모음' 기준 + glide)
    height: str | None = None     # high | mid | low
    backness: str | None = None   # front | central | back
    rounded: bool | None = None
    glide: str | None = None      # j | w | ɰ | None
    lip: str | None = None        # 입모양 목표: round | spread | open | neutral | closed

    @property
    def is_vowel(self) -> bool:
        return self.kind == "V"


def _c(sym, jamo, place, manner, phonation, coda=False):
    lip = "closed" if place == "bilabial" else None
    return Phone(sym, jamo, "C", place=place, manner=manner, phonation=phonation, coda=coda, lip=lip)


def _v(sym, jamo, height, backness, rounded, glide=None, lip=None):
    return Phone(sym, jamo, "V", height=height, backness=backness, rounded=rounded, glide=glide, lip=lip)


PHONES: dict[str, Phone] = {p.sym: p for p in [
    # 파열음
    _c("B", "ㅂ", "bilabial", "stop", "lenis"),
    _c("BB", "ㅃ", "bilabial", "stop", "tense"),
    _c("Ph", "ㅍ", "bilabial", "stop", "aspirated"),
    _c("D", "ㄷ", "alveolar", "stop", "lenis"),
    _c("DD", "ㄸ", "alveolar", "stop", "tense"),
    _c("Th", "ㅌ", "alveolar", "stop", "aspirated"),
    _c("G", "ㄱ", "velar", "stop", "lenis"),
    _c("GG", "ㄲ", "velar", "stop", "tense"),
    _c("Kh", "ㅋ", "velar", "stop", "aspirated"),
    # 파찰음
    _c("J", "ㅈ", "alveolopalatal", "affricate", "lenis"),
    _c("JJ", "ㅉ", "alveolopalatal", "affricate", "tense"),
    _c("CHh", "ㅊ", "alveolopalatal", "affricate", "aspirated"),
    # 마찰음
    _c("S", "ㅅ", "alveolar", "fricative", "lenis"),
    _c("SS", "ㅆ", "alveolar", "fricative", "tense"),
    _c("H", "ㅎ", "glottal", "fricative", "aspirated"),
    # 공명음
    _c("M", "ㅁ", "bilabial", "nasal", "sonorant"),
    _c("N", "ㄴ", "alveolar", "nasal", "sonorant"),
    _c("NG", "ㅇ", "velar", "nasal", "sonorant", coda=True),
    _c("R", "ㄹ", "alveolar", "liquid", "sonorant"),
    _c("L", "ㄹ", "alveolar", "liquid", "sonorant", coda=True),
    # 받침 불파음
    _c("p", "ㅂ", "bilabial", "stop", "lenis", coda=True),
    _c("t", "ㄷ", "alveolar", "stop", "lenis", coda=True),
    _c("k", "ㄱ", "velar", "stop", "lenis", coda=True),
    # 단모음
    _v("A", "ㅏ", "low", "central", False, lip="open"),
    _v("E", "ㅔ", "mid", "front", False, lip="spread"),
    _v("I", "ㅣ", "high", "front", False, lip="spread"),
    _v("O", "ㅗ", "mid", "back", True, lip="round"),
    _v("U", "ㅜ", "high", "back", True, lip="round"),
    _v("EO", "ㅓ", "mid", "back", False, lip="neutral"),
    _v("EU", "ㅡ", "high", "central", False, lip="spread"),
    # 이중모음 (자질은 도착 모음 기준)
    _v("iA", "ㅑ", "low", "central", False, glide="j", lip="open"),
    _v("iE", "ㅖ", "mid", "front", False, glide="j", lip="spread"),
    _v("iEO", "ㅕ", "mid", "back", False, glide="j", lip="neutral"),
    _v("iO", "ㅛ", "mid", "back", True, glide="j", lip="round"),
    _v("iU", "ㅠ", "high", "back", True, glide="j", lip="round"),
    _v("oA", "ㅘ", "low", "central", False, glide="w", lip="round"),   # 원순 → 벌림
    _v("oE", "ㅙ", "mid", "front", False, glide="w", lip="round"),
    _v("uEO", "ㅝ", "mid", "back", False, glide="w", lip="round"),
    _v("uI", "ㅟ", "high", "front", False, glide="w", lip="round"),
    _v("euI", "ㅢ", "high", "front", False, glide="ɰ", lip="spread"),
]}

# 모델 어휘 중 음소가 아닌 토큰
SPECIAL_TOKENS = {"[PAD]", "[UNK]", "|", "<s>", "</s>"}

# 대략적인 한국어 성인 단모음 포먼트(Hz). 시각화용 참고치 — 화자에 따라 ±15% 이상 차이가 난다.
FORMANT_REF = {
    "male":   {"A": (740, 1310), "EO": (560, 990), "O": (400, 760), "U": (340, 890),
               "EU": (370, 1500), "I": (290, 2200), "E": (480, 1880)},
    "female": {"A": (930, 1560), "EO": (680, 1180), "O": (470, 870), "U": (400, 1000),
               "EU": (430, 1680), "I": (340, 2700), "E": (590, 2300)},
    "child":  {"A": (1050, 1750), "EO": (780, 1320), "O": (540, 980), "U": (460, 1130),
               "EU": (490, 1900), "I": (390, 3000), "E": (680, 2600)},
}


def jamo_of(sym: str) -> str:
    return PHONES[sym].jamo if sym in PHONES else sym


def decompose(syllable: str) -> tuple[str, str, str] | None:
    """완성형 한글 한 글자 → (초성, 중성, 종성). 한글이 아니면 None."""
    code = ord(syllable) - 0xAC00
    if not 0 <= code < 11172:
        return None
    return CHO[code // 588], JUNG[(code % 588) // 28], JONG[code % 28]


def compose(cho: str, jung: str, jong: str = "") -> str:
    return chr(0xAC00 + CHO.index(cho) * 588 + JUNG.index(jung) * 28 + JONG.index(jong))


def pron_to_phones(pron: str) -> tuple[list[str], list[int]]:
    """표준발음 한글 문자열 → (음소 목록, 각 음소가 속한 음절 인덱스).

    공백·문장부호는 건너뛴다(음절 인덱스는 한글 음절만 센다).
    입력은 이미 음운규칙이 적용된 '발음형'이어야 한다(g2p.to_pron 결과).
    """
    phones: list[str] = []
    syl_idx: list[int] = []
    s = 0
    for ch in pron:
        d = decompose(ch)
        if d is None:
            continue
        cho, jung, jong = d
        if ONSET_PHONE[cho]:
            phones.append(ONSET_PHONE[cho]); syl_idx.append(s)
        phones.append(VOWEL_PHONE[jung]); syl_idx.append(s)
        if jong:
            if jong not in CODA_PHONE:
                raise ValueError(f"발음형에 대표음이 아닌 받침이 있음: {ch}({jong})")
            phones.append(CODA_PHONE[jong]); syl_idx.append(s)
        s += 1
    return phones, syl_idx
