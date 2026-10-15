"""오류 → 한국어 교정 안내, 점수 산출, 피드백 카드 우선순위 (CONTRACT 7절).

대상: 선천성 청각장애 + 인공와우 사용자. 청각 피드백이 약하므로 교정 문구는
'귀로 들어 보세요' 대신 **촉각·시각 단서**(입 앞 휴지/손바닥의 바람, 콧방울 옆 손가락의 떨림,
코 밑에 댄 거울·숟가락의 김 서림(언어치료의 비강 누출 거울 검사), 거울 속 입술 모양,
화면의 높낮이 선)를 쓴다. '코를 막았을 때 소리가 달라지는지'처럼 귀로 비교하는 검사는 쓰지 않는다.
받침 비음·유음은 '음—'·'을—'처럼 모음 ㅡ 가 든 글자로 적지 않는다(글자대로 읽으면 [바므]처럼
ㅡ 가 덧붙는 삽입 오류를 부른다). 대신 '입을 열지 말고 콧소리만 이어요'처럼 동작으로 말한다.

자주 보이는 오류와 분류(phones.PHONES 자질 기준):
  - 평음/격음/경음 혼동  : 같은 조음위치·방식, 발성유형(phonation)만 다름  → 'phonation'
  - ㅅ/ㅆ 왜곡·대치      : ㅅ→ㄷ(파열음화), ㅅ→ㅈ(파찰음화), ㅅ↔ㅆ          → 'sibilant'
  - 과비성(콧소리 섞임)  : 구강 장애음 → 비음 (ㅂ→ㅁ, ㄷ→ㄴ, 받침 ㄱ→ㅇ)   → 'hypernasal'
  - ㄹ 오류              : 탄설음 R ↔ ㄴ/ㄷ, 받침 L 을 튕기거나 막음         → 'liquid'
  - 받침 탈락            : status 'del' + 받침 위치                         → 'del'
  - 모음 중앙화          : ㅏ/ㅣ/ㅜ/ㅗ/ㅔ → ㅓ/ㅡ                              → 'centralize'
  - 이중모음 단모음화    : ㅘ→ㅏ, ㅝ→ㅓ (활음 탈락)                         → 'monophthong'
  - 음절 사이 ㅡ 삽입    : insertions 의 EU                                 → 'insertion'
  - 단조로운 억양 / 끝 억양 / 음량                                          → 'intonation', 'loudness'

조음 설명은 표준 한국어 조음음성학 기준:
  ㅂㅃㅍㅁ=양순, ㄷㄸㅌㄴㄹ=치조(윗잇몸), ㅅㅆ=치조 마찰(혀끝을 아랫니 뒤에 두는 설단 조음으로 지도),
  ㅈㅉㅊ=치조구개 파찰(혓바닥 앞부분), ㄱㄲㅋㅇ=연구개(혀 뒷부분+여린입천장), ㅎ=성문 마찰.
  평음=약한 기식·이완, 격음=강한 기식, 경음=후두 긴장·기식 거의 없음.
  초성 ㄹ=탄설음(혀끝으로 한 번 튕김), 받침 ㄹ=설측음(혀끝을 붙인 채 양옆으로 소리),
  단 받침 ㄹ 바로 뒤의 ㄹ(달리기 [tal.li.gi], 칼날, 신라→실라)은 탄설음이 아니라 설측음 [l] 이라
  '튕기기' 대신 '붙인 채 이어 가기'로 지도하고, 이 자리의 ㄹ→받침 ㄹ(설측) 인식은 오류로 보지 않는다.
  받침 ㅂㄷㄱ=불파음(막은 채 멈춤).
  평음/격음/경음은 기식·긴장뿐 아니라 뒤 모음의 시작 음높이(F0)로도 구별된다: 현대 서울말에서 어두
  예사소리는 기식이 길어 거센소리와 겹치고, 예사소리 뒤 모음은 낮게, 거센·된소리 뒤 모음은 높게 시작한다
  (Silva 2006; Kang & Guion 2008). 그래서 어절 첫소리의 발성유형 오류에는 '낮게/높게 시작하기'와
  화면의 높낮이 선 확인을 함께 안내한다.
  ㅏ=저·중설·평순, ㅓ=중·후설·평순, ㅗ=중·후설·원순, ㅜ=고·후설·원순, ㅡ=고·중설·평순,
  ㅣ=고·전설·평순, ㅔ(ㅐ)=중·전설·평순.  높이=입(턱) 벌림, 전후=혀 위치, 원순=입술.
  단 현대 서울말(특히 젊은 화자)은 ㅗ 가 위로 올라가 ㅜ 와 턱 높이가 거의 같고, 입술을 더 내밀어
  둥글게 모으는 ㅗ / 혀가 조금 앞으로 오는 ㅜ 로 구별한다 → ㅗ↔ㅜ 교정은 턱보다 입술 둥글림과 혀 앞뒤로.
  ㅣ↔ㅡ 는 혀끝이 아니라 혓바닥 앞쪽을 센입천장 가까이 올리는지로 구별한다.
  표시 자모: 음소 E 는 ㅐ/ㅔ, iE 는 ㅒ/ㅖ, oE 는 ㅙ/ㅚ/ㅞ 를 함께 나타내므로, 발음형 음절을 알면
  그 음절의 실제 모음 자모(외국 → ㅚ, 웨딩 → ㅞ)로 보여 주고 시작 입모양도 그에 맞춘다(display_jamo).
"""
from __future__ import annotations

import math
from typing import Any, Iterable

try:  # 패키지(server.feedback)로도, --app-dir 로 server/ 를 직접 잡은 경우(feedback)로도 import 가능하게
    from .phones import CODA_PHONE, ONSET_PHONE, PHONES, VOWEL_PHONE, compose, decompose, jamo_of
except ImportError:  # pragma: no cover
    from phones import CODA_PHONE, ONSET_PHONE, PHONES, VOWEL_PHONE, compose, decompose, jamo_of  # type: ignore

__all__ = ["phone_tip", "summarize", "josa", "classify", "display_jamo", "resolve_tune"]

# ── 점수 상수 ────────────────────────────────────────────
WEIGHTS = {"accuracy": 0.5, "clarity": 0.25, "intonation": 0.1, "lips": 0.15}
STATUS_CREDIT = {"ok": 1.0, "weak": 0.6, "sub": 0.0, "del": 0.0}
INSERTION_PENALTY = 0.5          # 삽입 1개당 0.5음소만큼 감점
MAX_CARDS = 4

QUESTION_RISE_OK_ST = 2.0        # 의문문: 끝 억양이 +2 반음 이상 오르면 '좋음'
RANGE_OK_ST = (2.0, 12.0)        # 평서문/단어: 음높이 폭이 2~12 반음이면 '좋음'
STATEMENT_RISE_WARN_ST = 4.0     # 평서문인데 끝이 +4 반음 이상 오르면 질문처럼 들림

# 음량 기준(acoustic.loudness, 단위 dB).
# acoustic.py 는 parselmouth(Praat) Intensity 를 쓰며, Praat 은 파형 값을 Pa 로 보고
# 20·log10(rms / 2e-5) 로 계산한다. 따라서 디지털 풀스케일 사인파 ≈ 91 dB 이고
# rms 가 -40 dBFS 이면 ≈ 54 dB, -45 dBFS 이면 ≈ 49 dB 다.
# 노트북/폰 마이크에서 30cm 안팎으로 평소 크기로 말하면 말소리 구간 평균이 대략 60~75 dB.
# mean_db 는 acoustic.py 에서 '최대값 25 dB 이내 프레임(=말소리 구간)'만 평균한 값이므로
# 앞뒤 무음 때문에 낮아지지 않는다. 그래서 50 dB 미만(≈ rms -44 dBFS 이하)이면
# 실내 소음과 분리가 어렵고 인식 정확도도 떨어지는 '너무 작은 목소리'로 본다.
QUIET_MEAN_DB = 50.0
# 창(window) RMS 가 풀스케일 사인(91 dB)에 6 dB 이내로 다가가면 파형이 잘렸을(클리핑) 가능성이 크다.
LOUD_MAX_DB = 85.0

OBSTRUENT_PHONATION = ("lenis", "aspirated", "tense")
OPEN = {"high": 0, "mid": 1, "low": 2}   # 입(턱) 벌림 정도


# ── 조사(받침 유무) ──────────────────────────────────────
_CONS_JAMO = set("ㄱㄲㄳㄴㄵㄶㄷㄸㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅃㅄㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")


def _final(word: str) -> tuple[bool, bool]:
    """마지막 글자의 (받침 있음, 받침이 ㄹ). 자음 자모는 이름(기역·니은…)이 모두 받침으로 끝난다."""
    s = word.rstrip(" '\"’”)]—")
    if not s:
        return False, False
    ch = s[-1]
    if "가" <= ch <= "힣":
        jong = (ord(ch) - 0xAC00) % 28
        return jong != 0, jong == 8        # JONG[8] = ㄹ
    if ch in _CONS_JAMO:
        return True, ch == "ㄹ"
    return False, False                    # 모음 자모(ㅏ=아 …), 기타


def josa(word: str, pair: str) -> str:
    """word + 알맞은 조사. pair 예: '이/가', '은/는', '을/를', '과/와', '으로/로'."""
    a, b = pair.split("/")
    has, is_l = _final(word)
    if pair == "으로/로":
        return word + ("로" if (not has or is_l) else "으로")
    return word + (a if has else b)


def _join(labels: list[str], limit: int = 4) -> str:
    if len(labels) > limit:
        return "·".join(labels[:limit]) + " 등"
    return "·".join(labels)


def _uniq(xs: Iterable) -> list:
    out, seen = [], set()
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ── 음소별 핵심 지시(한 문장) ─────────────────────────────
CONS_CORE = {
    "B": "두 입술을 가볍게 붙였다가 힘을 빼고 떼세요.",
    "BB": "두 입술에 힘을 주어 꼭 붙였다가 짧고 단단하게 떼세요.",
    "Ph": "두 입술을 붙였다가 바람을 세게 터뜨리며 떼세요.",
    "D": "혀끝을 윗잇몸(윗니 바로 뒤 볼록한 곳)에 붙였다가 힘을 빼고 떼세요.",
    "DD": "혀끝을 윗잇몸에 힘주어 붙였다가 짧고 단단하게 떼세요.",
    "Th": "혀끝을 윗잇몸에 붙였다가 바람을 세게 터뜨리며 떼세요.",
    "G": "혀 뒷부분을 입천장 안쪽에 붙였다가 힘을 빼고 떼세요.",
    "GG": "혀 뒷부분을 입천장 안쪽에 힘주어 붙였다가 짧고 단단하게 떼세요.",
    "Kh": "혀 뒷부분을 입천장 안쪽에 붙였다가 바람을 세게 터뜨리며 떼세요.",
    "J": "혀 앞부분을 입천장 앞쪽에 넓게 붙였다가, 힘을 빼고 살짝 떼며 바람이 스치게 하세요.",
    "JJ": "혀 앞부분을 입천장 앞쪽에 힘주어 붙였다가 짧고 단단하게 떼세요.",
    "CHh": "혀 앞부분을 입천장 앞쪽에 붙였다가, 떼면서 바람을 세게 내보내세요.",
    "S": "혀끝을 아랫니 뒤에 두고 윗니와 아랫니를 거의 붙인 채, 그 좁은 틈으로 바람을 가늘게 내보내세요.",
    "SS": "혀끝을 아랫니 뒤에 두고 이를 거의 붙인 채, 목에 힘을 주고 좁은 틈으로 바람을 단단하고 조금 더 길게 내보내세요.",
    "H": "입을 다음 모음 모양으로 미리 벌린 채, 목에서 숨을 '하—' 내쉬듯 소리 내세요.",
    "M": "두 입술을 다물고 코로 소리를 내세요(콧방울 옆에 손가락을 대면 떨림이 느껴져요).",
    "N": "혀끝을 윗잇몸에 붙이고 코로 소리를 내세요(콧방울 옆에 손가락을 대면 떨림이 느껴져요).",
    "NG": "혀끝은 아랫니 뒤에 두고, 혀 뒷부분을 입천장 안쪽에 붙인 채 입을 열지 말고 콧소리를 내세요.",
    "R": "혀끝으로 윗잇몸을 한 번 가볍게 '톡' 튕기고 바로 떼세요.",
    "L": "혀끝을 윗잇몸에 붙인 채 떼지 말고, 소리를 혀 양옆으로 흘리며 끝내세요.",
}
# 받침 ㄹ 바로 뒤의 ㄹ(달리기·칼날·실라): 탄설음이 아니라 설측음 [l]
R_AFTER_L = "앞 받침 ㄹ에서 혀끝을 윗잇몸에 붙인 채 떼지 말고, 그대로 다음 모음으로 이어 가며 떼세요(이 ㄹ은 튕기지 않아요)."
CODA_CORE = {
    "p": "두 입술을 다문 채로 멈추고, 입술을 열며 터뜨리지 마세요.",
    "t": "혀끝을 윗잇몸에 붙인 채로 멈추고, 혀를 떼며 터뜨리지 마세요.",
    "k": "혀 뒷부분을 입천장 안쪽에 붙인 채로 멈추고, 혀를 떼며 터뜨리지 마세요.",
    "M": "두 입술을 다문 채 입을 열지 말고 콧소리만 이어 끝내세요('ㅡ'를 따로 내지 않아요).",
    "N": "혀끝을 윗잇몸에 붙인 채 입을 열지 말고 콧소리만 이어 끝내세요('ㅡ'를 따로 내지 않아요).",
    "NG": "혀 뒷부분을 입천장 안쪽에 붙인 채 콧소리만 이어 끝내세요('ㅡ'를 따로 내지 않아요).",
    "L": "혀끝을 윗잇몸에 붙인 채 떼지 말고, 소리를 혀 양옆으로 흘리며 끝내세요('ㅡ'를 따로 내지 않아요).",
}
# 받침 탈락: '받침에서 입을 바로 떼지 말고 ~에서 멈추기'
CODA_DEL = {
    "p": "{tj}에서 입을 바로 떼지 말고, 두 입술을 다문 채 잠깐 멈추세요.",
    "t": "{tj}에서 혀를 바로 떼지 말고, 혀끝을 윗잇몸에 붙인 채 잠깐 멈추세요.",
    "k": "{tj}에서 혀를 바로 떼지 말고, 혀 뒷부분을 입천장 안쪽에 붙인 채 잠깐 멈추세요.",
    "M": "{tj}에서 입을 바로 떼지 말고, 두 입술을 다문 채 콧소리를 잠깐 이어 주세요('ㅡ'는 내지 않아요).",
    "N": "{tj}에서 혀를 바로 떼지 말고, 혀끝을 윗잇몸에 붙인 채 콧소리를 잠깐 이어 주세요('ㅡ'는 내지 않아요).",
    "NG": "{tj}에서 바로 끝내지 말고, 혀 뒷부분을 입천장 안쪽에 붙인 채 콧소리를 잠깐 이어 주세요.",
    "L": "{tj}에서 혀를 바로 떼지 말고, 혀끝을 윗잇몸에 붙인 채 소리를 혀 양옆으로 잠깐 흘려 주세요.",
}
VOWEL_CORE = {
    "A": "턱을 아래로 내려 입을 위아래로 크게 벌리세요.",
    "EO": "입술은 둥글게 모으지 말고 힘을 뺀 채, 턱을 ㅏ보다 조금 덜 내리세요.",
    "O": "입술을 작고 동그랗게, 단단하게 모아 앞으로 내밀고 턱은 조금만 내리세요(ㅜ보다 입술을 더 내밀어요).",
    "U": "입술을 동그랗게 모으되 ㅗ보다 힘을 조금 빼고, 혀는 조금 앞으로 두며 입은 거의 벌리지 마세요.",
    "EU": "입술을 내밀지 말고 옆으로 살짝 편 채, 윗니와 아랫니를 거의 붙이세요.",
    "I": "입꼬리를 양옆으로 당겨 입술을 펴고, 윗니와 아랫니를 거의 붙이세요.",
    "E": "입꼬리를 옆으로 살짝 당기고, ㅣ보다 입을 조금 더 벌리세요.",
}
# 이중모음: (시작 모음, 도착 모음, 지시). 활음 j=ㅣ 모양, w=입술 둥글게(ㅗ/ㅜ), ɰ=ㅡ 모양.
DIPH = {
    "iA": ("ㅣ", "ㅏ", "입꼬리를 옆으로 편 'ㅣ' 모양에서 시작해 바로 입을 크게 벌리세요."),
    "iE": ("ㅣ", "ㅔ", "입꼬리를 옆으로 편 'ㅣ' 모양에서 시작해 바로 입을 조금 더 벌려 'ㅔ'로 넘어가세요."),
    "iEO": ("ㅣ", "ㅓ", "입꼬리를 옆으로 편 'ㅣ' 모양에서 시작해 바로 입술 힘을 빼고 턱을 내려 'ㅓ'로 넘어가세요."),
    "iO": ("ㅣ", "ㅗ", "입꼬리를 옆으로 편 'ㅣ' 모양에서 시작해 바로 입술을 동그랗게 모아 'ㅗ'로 넘어가세요."),
    "iU": ("ㅣ", "ㅜ", "입꼬리를 옆으로 편 'ㅣ' 모양에서 시작해 바로 입술을 동그랗게 모으며 'ㅜ'로 넘어가세요."),
    "oA": ("ㅗ", "ㅏ", "입술을 동그랗게 모은 'ㅗ' 모양에서 시작해 바로 입을 크게 벌리세요."),
    "oE": ("ㅗ", "ㅔ", "입술을 동그랗게 모은 'ㅗ' 모양에서 시작해 바로 입술을 펴며 'ㅔ'로 넘어가세요."),
    "uEO": ("ㅜ", "ㅓ", "입술을 동그랗게 모은 'ㅜ' 모양에서 시작해 바로 입술 힘을 빼고 턱을 내려 'ㅓ'로 넘어가세요."),
    "uI": ("ㅜ", "ㅣ", "입술을 동그랗게 모은 'ㅜ' 모양에서 시작해 바로 입꼬리를 옆으로 당기며 'ㅣ'로 넘어가세요."),
    "euI": ("ㅡ", "ㅣ", "입술을 옆으로 편 'ㅡ' 모양에서 시작해 바로 혀를 앞으로 올리며 'ㅣ'로 넘어가세요."),
}
# oE 음소는 ㅙ·ㅚ·ㅞ 를 함께 나타낸다(phones.py). 실제 철자 모음을 알면 그 모음의 시작 입모양으로 안내한다.
# ㅚ 는 원칙이 단모음 [ø](입술을 둥글게 한 채 ㅔ), 이중모음 [we] 도 허용(표준 발음법 제4항 붙임).
DIPH_BY_JAMO = {
    "ㅙ": ("ㅗ", "ㅐ", "입술을 동그랗게 모은 'ㅗ' 모양에서 시작해 바로 입술을 펴며 입을 벌려 'ㅐ'로 넘어가세요."),
    "ㅞ": ("ㅜ", "ㅔ", "입술을 동그랗게 모은 'ㅜ' 모양에서 시작해 바로 입술을 펴며 'ㅔ'로 넘어가세요."),
    "ㅚ": ("ㅗ", "ㅔ", "혀는 'ㅔ' 자리에 둔 채 입술만 동그랗게 모아 내세요(입술을 모았다가 'ㅔ'로 풀어도 돼요)."),
}
# 'w' 활음 이중모음(ㅘ·ㅝ·ㅙ·ㅞ·ㅚ·ㅟ)의 거울 확인: 끝까지 둥근 것이 아니라 끝에서 풀린다
W_CHECK = "거울을 보면 시작할 때 입술이 동그랗다가 끝에서 풀려야 해요."
VOWEL_CHECK = {
    "round": "거울을 보면 입술이 동그랗게 앞으로 나와 있어야 해요.",
    "spread": "거울을 보면 입꼬리가 옆으로 당겨져 있어야 해요.",
    "open": "거울을 보면 입이 위아래로 크게 열려 있어야 해요.",
    "neutral": "거울을 보면 입술이 둥글지 않고 편하게 열려 있어야 해요.",
}
PLACE_DESC = {
    "bilabial": "두 입술로 내는 소리예요.",
    "alveolar": "혀끝을 윗잇몸에 대어 내는 소리예요.",
    "alveolopalatal": "혀 앞부분을 입천장 앞쪽에 넓게 대어 내는 소리예요.",
    "velar": "혀 뒷부분을 입천장 안쪽에 대어 내는 소리예요.",
    "glottal": "입 안을 막지 않고 목에서 숨을 내쉬어 내는 소리예요.",
}
PLACE_CHECK = {
    "bilabial": "거울을 보며 두 입술이 붙었다 떨어지는지 확인하세요.",
    "alveolar": "혀끝이 윗니 바로 뒤 볼록한 잇몸에 닿아야 해요.",
    "alveolopalatal": "혀끝만이 아니라 혓바닥 앞부분이 넓게 닿아야 해요.",
    "velar": "혀끝은 아랫니 뒤에 둔 채 혀 뒤쪽만 들어 올리세요.",
    "glottal": "입 앞에 손바닥을 대면 따뜻한 숨이 느껴져야 해요.",
}
CODA_PLACE_DESC = {
    "bilabial": "두 입술을 닫아서 끝내는 소리예요.",
    "alveolar": "혀끝을 윗잇몸에 대어 끝내는 소리예요.",
    "velar": "혀 뒷부분을 들어 올려 끝내는 소리예요.",
}
MANNER_DESC = {
    "stop": "막았다가 한 번에 떼는 소리예요.",
    "affricate": "막았다가 천천히 떼면서 바람이 스치게 하는 소리예요.",
    "fricative": "막지 않고 좁은 틈으로 바람을 계속 내보내는 소리예요.",
    "nasal": "코로 내는 소리예요.",
    "liquid": "혀끝을 윗잇몸에 대어 내는, 코로 나가지 않는 소리예요.",
}
# 과비성 교정: 입 안에 공기를 모았다가 '입으로' 내보내기
ORAL_PUSH = {
    "bilabial": "두 입술을 꼭 붙여 입 안에 공기를 모았다가, 코가 아니라 입으로 내보내세요.",
    "alveolar": "혀끝을 윗잇몸에 꼭 붙여 입 안에 공기를 모았다가, 코가 아니라 입으로 내보내세요.",
    "alveolopalatal": "혀 앞부분을 입천장 앞쪽에 붙여 공기를 모았다가, 코가 아니라 입으로 내보내세요.",
    "velar": "혀 뒷부분을 입천장 안쪽에 꼭 붙여 공기를 모았다가, 코가 아니라 입으로 내보내세요.",
    None: "입 안에 공기를 모았다가, 코가 아니라 입으로 내보내세요.",
}
HOLD = {
    "bilabial": "두 입술을 다문 채",
    "alveolar": "혀끝을 윗잇몸에 붙인 채",
    "velar": "혀 뒷부분을 입천장 안쪽에 붙인 채",
    None: "입 안을 막은 채",
}
# 과비성 자가 확인(촉각·시각): 콧방울 떨림, 코 밑 거울·숟가락 김 서림(비강 누출 거울 검사)
NOSE_TEST = "콧방울 옆에 손가락을 대고 낼 때 떨림이 없어야 해요"
NOSE_MIRROR = "코 밑에 작은 거울이나 차가운 숟가락을 대면 김이 서리지 않아야 해요"
NOSE_FEEL = "콧방울 옆에 손가락을 대면 떨림이 느껴져야 해요."
# 어절 첫소리 예사·거센·된소리: 뒤 모음의 시작 음높이(F0)를 화면의 높낮이 선으로 확인
PITCH_CHECK = {
    "lenis": "화면의 높낮이 선에서 이 음절의 시작점이 낮게 찍혀야 해요(예사소리는 낮은 목소리로 시작해요).",
    "aspirated": "화면의 높낮이 선에서 이 음절의 시작점이 높게 찍혀야 해요(거센소리는 높은 목소리로 시작해요).",
    "tense": "화면의 높낮이 선에서 이 음절의 시작점이 높게 찍혀야 해요(된소리는 높은 목소리로 시작해요).",
}


# ── 분류 ─────────────────────────────────────────────────
def _is_coda(sym: str, coda: bool | None) -> bool:
    p = PHONES[sym]
    return p.kind == "C" and bool(p.coda or coda)


def classify(target: str, heard: str | None, status: str, coda: bool | None = None) -> tuple[str, str] | None:
    """(분류, 세부) — phone_tip 과 summarize 가 같은 기준을 쓰도록 공개한다.

    분류: weak | del | phonation | sibilant | hypernasal | denasal | liquid | coda | place | manner |
          similar | mixed | unknown | monophthong | glide_add | glide_swap | centralize | vowel
    """
    if target not in PHONES or status not in ("weak", "del", "sub"):
        return None
    T = PHONES[target]
    tc = _is_coda(target, coda)
    if status == "weak":
        return "weak", ("v" if T.is_vowel else "c")
    if status == "del":
        if T.is_vowel:
            return "del", "vowel"
        if tc:
            return "del", "coda"
        return "del", ("h" if target == "H" else "onset")

    H = PHONES.get(heard) if heard else None
    if H is None:
        return "unknown", ("v" if T.is_vowel else "c")
    if T.is_vowel != H.is_vowel:
        return "mixed", ("v" if T.is_vowel else "c")

    if T.is_vowel:
        if T.glide and not H.glide:
            return "monophthong", T.glide
        if not T.glide and H.glide:
            return "glide_add", H.glide
        if T.glide and H.glide and T.glide != H.glide:
            return "glide_swap", T.glide
        if not T.glide and target not in ("EO", "EU") and heard in ("EO", "EU"):
            return "centralize", heard
        return "vowel", ""

    # 자음
    if target in ("S", "SS"):
        if heard in ("S", "SS"):
            return "sibilant", "phonation"
        if H.manner == "stop":
            return "sibilant", "stop"
        if H.manner == "affricate":
            return "sibilant", "affricate"
        return "sibilant", "other"
    if tc and T.manner == "stop" and H.manner in ("stop", "affricate") and H.place == T.place:
        return "coda", "release"            # 받침 불파음을 터뜨림(ㅂ→ㅍ/ㅃ 등)
    if (T.place == H.place and T.manner == H.manner and T.phonation != H.phonation
            and T.phonation in OBSTRUENT_PHONATION and H.phonation in OBSTRUENT_PHONATION):
        return "phonation", f"{T.phonation}>{H.phonation}"
    if T.manner != "nasal" and H.manner == "nasal":
        if T.manner == "liquid":
            return "liquid", "nasal"
        return "hypernasal", T.place or ""
    if T.manner == "liquid":
        if H.manner in ("stop", "affricate"):
            return "liquid", "stop"
        if target == "L" and heard == "R":
            return "liquid", "flap"
        if target == "R" and heard == "L":
            return "liquid", "lateral"
        return "liquid", "other"
    if T.manner == "nasal" and H.manner != "nasal":
        return "denasal", T.place or ""
    if tc:
        return "coda", "place"
    if T.place == H.place and T.manner == H.manner:
        return "similar", ""
    if T.manner == H.manner:
        return "place", T.place or ""
    return "manner", T.manner or ""


# ── 문구 생성 ────────────────────────────────────────────
def display_jamo(sym: str, syllable: str | None = None) -> str:
    """화면 표시용 자모. 모음 음소 E(ㅐ/ㅔ)·iE(ㅒ/ㅖ)·oE(ㅙ/ㅚ/ㅞ)는 한 음소가 여러 자모를 나타내므로,
    그 음소가 속한 발음형 음절(syllable, 한 글자)의 중성이 같은 음소로 대응하면 그 자모를 쓴다
    (외국 → ㅚ, 웨딩 → ㅞ, 개 → ㅐ). 모르면 phones.PHONES 의 기본 자모."""
    base = jamo_of(sym)
    P = PHONES.get(sym)
    if P is None or not P.is_vowel or not isinstance(syllable, str) or len(syllable) != 1:
        return base
    d = decompose(syllable)
    if d is None:
        return base
    return d[1] if VOWEL_PHONE.get(d[1]) == sym else base


def _vjamo(sym: str, jamo: str | None) -> str:
    """음소 sym 의 표시 자모: jamo 가 같은 음소를 나타내는 모음 자모면 그것, 아니면 기본 자모."""
    if jamo and PHONES.get(sym) is not None and PHONES[sym].is_vowel and VOWEL_PHONE.get(jamo) == sym:
        return jamo
    return jamo_of(sym)


def _label(sym: str, coda: bool = False, jamo: str | None = None) -> str:
    j = _vjamo(sym, jamo)
    if sym in PHONES and PHONES[sym].kind == "C" and (coda or PHONES[sym].coda):
        return "받침 " + j
    return j


def _diph(sym: str, jamo: str | None = None) -> tuple[str, str, str]:
    j = _vjamo(sym, jamo)
    return DIPH_BY_JAMO.get(j) or DIPH[sym]


def _core(sym: str, tc: bool, prev: str | None = None, jamo: str | None = None) -> str:
    p = PHONES[sym]
    if p.is_vowel:
        return VOWEL_CORE.get(sym) or _diph(sym, jamo)[2]
    if sym == "R" and prev == "L":
        return R_AFTER_L
    if tc and sym in CODA_CORE:
        return CODA_CORE[sym]
    return CONS_CORE.get(sym) or CODA_CORE.get(sym, "")


def _phonation_parts(tp: str, hp: str, tj: str, initial: bool = False) -> tuple[str, str]:
    """평음/격음/경음 교정 (첫 문장, 둘째 문장). initial: 어절 첫소리면 시작 음높이(F0) 단서를 더한다
    (예사소리 뒤 모음은 낮게, 거센·된소리 뒤 모음은 높게 시작한다)."""
    if tp == "aspirated":
        s1 = f"{josa(tj, '은/는')} 바람을 세게 내보내는 거센소리예요."
        if hp == "tense":
            s2 = "목에 힘을 주지 말고, 입 앞에 댄 휴지나 손바닥에 바람이 세게 닿도록 숨을 터뜨리세요."
            if initial:
                s2 = "목에 힘을 주지 말고, 입 앞에 댄 휴지나 손바닥에 바람이 세게 닿도록 숨을 터뜨리며 높은 목소리로 시작하세요."
        else:
            s2 = "입 앞에 휴지나 손바닥을 대고, 바람이 세게 닿을 만큼 숨을 터뜨리세요."
            if initial:
                s2 = "입 앞에 휴지나 손바닥을 대고, 바람이 세게 닿을 만큼 숨을 터뜨리며 높은 목소리로 시작하세요."
    elif tp == "tense":
        s1 = f"{josa(tj, '은/는')} 힘이 들어간 된소리예요."
        lead = "바람을 터뜨리지 말고, 목에 힘을 주고" if hp == "aspirated" else "목에 힘을 주고"
        how = "짧고 단단하게 높은 목소리로 시작하세요" if initial else "짧고 단단하게 내세요"
        s2 = f"{lead} 바람은 거의 없이 {how}—입 앞에 댄 휴지가 거의 흔들리지 않아야 해요."
    else:  # lenis
        s1 = f"{josa(tj, '은/는')} 힘을 빼고 부드럽게 내는 예사소리예요."
        if hp == "aspirated":
            how = "낮은 목소리로 약하게 시작하세요" if initial else "약하게 내세요"
            s2 = f"바람을 세게 터뜨리지 말고 힘을 뺀 채 {how}—입 앞에 댄 휴지가 살짝만 흔들리면 돼요."
        else:
            how = "힘을 빼서 낮은 목소리로 시작하세요" if initial else "힘을 빼서 내세요"
            s2 = f"목에 힘을 주지 말고 편하게 {how}—입 앞에 댄 휴지가 살짝 흔들리면 돼요."
    return s1, s2


def _vowel_instr(t: str, h: str, hj: str) -> list[tuple[str, str]]:
    """목표 모음과 들린 모음의 자질 차이 → (이어지는 꼴, 끝맺는 꼴) 지시 목록(최대 2개).
    눈에 보이는 단서(입술 → 턱/입 벌림 → 혀 위치) 순서로 고른다."""
    T, H = PHONES[t], PHONES[h]
    out: list[tuple[str, str]] = []
    # ㅗ↔ㅜ: 현대 서울말은 턱 높이 차이가 작고 입술 둥글림·내밂(ㅗ 가 더 큼)과 혀 앞뒤(ㅜ 가 조금 앞)로 구별한다
    if {T.sym, H.sym} in ({"O", "U"}, {"iO", "iU"}):
        if T.sym in ("O", "iO"):
            return [(f"{hj}보다 입술을 더 동그랗고 단단하게 모아 앞으로 내밀고", f"{hj}보다 입술을 더 동그랗고 단단하게 모아 앞으로 내미세요"),
                    ("혀를 조금 뒤로 당기고", "혀를 조금 뒤로 당기세요")]
        return [(f"{hj}보다 입술 힘을 조금 빼고 혀를 조금 앞으로 두며", f"{hj}보다 입술 힘을 조금 빼고 혀를 조금 앞으로 두세요"),
                ("입은 조금 덜 벌리고", "입은 조금 덜 벌리세요")]
    round_diff = bool(T.rounded) != bool(H.rounded)
    if round_diff:
        if T.rounded:
            out.append(("입술을 동그랗게 모아 앞으로 내밀고", "입술을 동그랗게 모아 앞으로 내미세요"))
        elif T.lip == "spread":
            out.append(("입술을 내밀지 말고 입꼬리를 옆으로 펴고", "입술을 내밀지 말고 입꼬리를 옆으로 펴세요"))
        elif T.lip == "open":
            out.append(("입술을 모으지 말고", "입술을 동그랗게 모으지 마세요"))
        else:
            out.append(("입술을 둥글게 모으지 말고 힘을 빼고", "입술을 둥글게 모으지 말고 힘을 빼세요"))
    dh = OPEN.get(T.height or "", 1) - OPEN.get(H.height or "", 1)
    if dh > 0:
        amt = "더 크게" if (t in ("A", "iA", "oA") or dh >= 2) else "조금 더"
        out.append((f"{hj}보다 입을 {amt} 벌리고", f"{hj}보다 입을 {amt} 벌리세요"))
    elif dh < 0:
        amt = "덜" if dh <= -2 else "조금 덜"
        out.append((f"{hj}보다 입을 {amt} 벌리고", f"{hj}보다 입을 {amt} 벌리세요"))
    if not round_diff:
        if T.lip == "spread" and H.lip != "spread":
            out.append(("입꼬리를 옆으로 당기고", "입꼬리를 옆으로 당기세요"))
        elif T.lip == "neutral" and H.lip == "spread":
            out.append(("입꼬리를 당기지 말고 입술 힘을 빼고", "입꼬리를 당기지 말고 입술 힘을 빼세요"))
    tf, hf = T.backness == "front", H.backness == "front"
    if tf != hf:
        # 앞 모음(ㅣ·ㅔ)은 혀끝이 아니라 혓바닥 앞쪽을 센입천장 쪽으로 올려 낸다(혀끝은 ㅡ 에서도 아랫니 뒤에 있다)
        if not tf:
            out.append(("혀를 조금 뒤로 당기고", "혀를 조금 뒤로 당기세요"))
        elif T.height == "high":
            if T.lip == "spread" and H.lip == "spread" and not round_diff:
                out.append(("혓바닥 앞쪽을 입천장 가까이 올리고 입꼬리를 당기고",
                            "혓바닥 앞쪽을 입천장 가까이 올리고 입꼬리를 당기세요"))
            else:
                out.append(("혓바닥 앞쪽을 입천장 가까이 올리고", "혓바닥 앞쪽을 입천장 가까이 올리세요"))
        else:
            out.append(("혀를 앞으로 내밀어 혓바닥 앞쪽을 조금 올리고", "혀를 앞으로 내밀어 혓바닥 앞쪽을 조금 올리세요"))
    return out[:2]


def _parts(cls: tuple[str, str], t: str, h: str | None, coda: bool | None = None,
           tj: str | None = None, hj: str | None = None, place: Any = "auto",
           prev: str | None = None, initial: bool = False, jamo: str | None = None) -> tuple[str, str]:
    """(첫 문장, 둘째 문장). tj/hj 로 여러 자모를 묶은 표기를 넘길 수 있다(카드용).
    prev: 바로 앞 목표 음소(받침 ㄹ 뒤 ㄹ 판단), initial: 어절 첫소리 여부(시작 음높이 단서),
    jamo: 목표 음소의 표시 자모(ㅚ·ㅞ·ㅐ 등, display_jamo)."""
    cat, sub = cls
    T = PHONES[t]
    tc = _is_coda(t, coda)
    tj = tj or _label(t, tc, jamo)
    hj = hj or (jamo_of(h) if h else "")
    H = PHONES.get(h) if h else None
    pl = T.place if place == "auto" else place

    if cat == "weak":
        return f"거의 맞았어요—{josa(tj, '을/를')} 조금 더 또렷하게 내 보세요.", _core(t, tc, prev, jamo)

    if cat == "del":
        if sub == "coda":
            return f"{josa(tj, '이/가')} 빠졌어요.", CODA_DEL.get(t, "{tj}의 모양에서 잠깐 멈추세요.").format(tj=tj)
        if sub == "h":
            return ("ㅎ 소리가 약해서 거의 들리지 않았어요.",
                    "모음 앞에서 목으로 숨을 '하—' 내쉬듯 살려 주세요(입 앞 손바닥에 따뜻한 숨이 느껴져야 해요).")
        if sub == "vowel":
            return f"모음 {josa(tj, '이/가')} 빠졌어요.", _core(t, False, jamo=jamo)
        return f"{tj} 소리가 빠졌어요.", _core(t, tc, prev)

    if cat == "phonation":
        return _phonation_parts(T.phonation, H.phonation if H else "lenis", tj, initial=bool(initial) and not tc)

    if cat == "sibilant":
        if sub == "phonation":
            if t == "SS":
                return (f"{josa(tj, '은/는')} 힘이 들어간 된소리예요.",
                        "혀끝을 아랫니 뒤에 두고 이를 거의 붙인 채, 목에 힘을 주고 좁은 틈으로 바람을 단단하고 조금 더 길게 내보내세요.")
            return (f"{josa(tj, '은/는')} 힘을 빼고 부드럽게 내는 소리예요.",
                    "목에 힘을 주지 말고, 혀끝을 아랫니 뒤에 둔 채 이 사이 좁은 틈으로 바람을 가늘고 부드럽게 내보내세요.")
        if sub == "stop":
            if H is not None and H.place == "alveolar":   # 가장 흔한 ㅅ→ㄷ: 혀끝이 윗잇몸을 막음
                s2 = "혀끝을 아랫니 뒤에 두고 윗니와 아랫니를 거의 붙인 채, 혀가 윗잇몸에 닿지 않게 바람을 가늘게 이어서 내보내세요."
            else:
                s2 = "혀끝을 아랫니 뒤에 두고 윗니와 아랫니를 거의 붙인 채, 막지 말고 그 틈으로 바람을 가늘게 이어서 내보내세요."
            return f"{josa(tj, '이/가')} 막았다가 터지는 소리({hj})로 바뀌었어요.", s2
        if sub == "affricate":
            return (f"{josa(tj, '이/가')} {hj}처럼 막혔다가 터지고 있어요.",
                    "혀가 입천장에 붙지 않게 혀끝을 아랫니 뒤에 두고, 이 사이 좁은 틈으로 바람을 끊지 말고 가늘게 흘려 보내세요.")
        return (f"{josa(tj, '은/는')} 이 사이 좁은 틈으로 바람을 가늘게 내보내는 소리예요.",
                "혀끝을 아랫니 뒤에 두고 윗니와 아랫니를 거의 붙인 채, 모음 없이 바람 소리만 길게 늘여 보세요(바람이 끊기지 않아야 해요).")

    if cat == "hypernasal":
        s1 = f"{tj}에 콧소리가 섞였어요—{NOSE_TEST}."
        if tc and t in CODA_CORE:
            return s1, f"받침에서 코로 소리를 내지 말고, {HOLD.get(pl, HOLD[None])} 소리를 멈추세요."
        return s1, ORAL_PUSH.get(pl, ORAL_PUSH[None]).rstrip(".") + f"({NOSE_MIRROR})."

    if cat == "denasal":
        return f"{josa(tj, '은/는')} 코로 내는 콧소리예요.", f"{HOLD.get(pl, HOLD[None])} 코로 소리를 내 보세요—{NOSE_FEEL}"

    if cat == "liquid":
        if t == "R" and prev == "L":
            # 받침 ㄹ 뒤의 ㄹ(달리기·칼날): 설측음 [l] — 튕기지 않고 붙인 채 이어 간다
            if sub == "nasal":
                return (f"{josa(tj, '은/는')} 코로 내는 소리가 아니에요.",
                        "앞 받침 ㄹ에서 혀끝을 윗잇몸에 붙인 채 떼지 말고 그대로 다음 모음으로 이어 가세요—"
                        "콧방울 옆에 댄 손가락에 떨림이 없어야 해요.")
            if sub == "stop":
                return f"{josa(tj, '은/는')} 혀를 세게 붙였다가 터뜨리는 소리가 아니에요.", R_AFTER_L
            return f"{josa(tj, '은/는')} 앞 받침 ㄹ에 이어 혀끝을 윗잇몸에 붙인 채 내는 소리예요.", R_AFTER_L
        if t == "R":
            if sub == "nasal":
                return (f"{josa(tj, '은/는')} 코로 내는 소리가 아니에요.",
                        "혀끝으로 윗잇몸을 한 번 가볍게 '톡' 튕기고 바로 떼세요—콧방울 옆에 댄 손가락에 떨림이 없어야 해요.")
            if sub == "stop":
                return (f"{josa(tj, '은/는')} 혀를 붙였다가 터뜨리는 소리가 아니에요.",
                        "혀끝으로 윗잇몸을 아주 짧게 한 번 '톡' 튕기고 바로 떼세요.")
            if sub == "lateral":
                return (f"첫소리 {josa(tj, '은/는')} 혀를 붙이고 있는 소리가 아니에요.",
                        "혀끝으로 윗잇몸을 한 번 가볍게 튕기고 바로 떼세요.")
            return (f"{josa(tj, '은/는')} 혀끝으로 윗잇몸을 한 번 가볍게 튕기는 소리예요.",
                    "혀에 힘을 빼고 '톡' 치듯 짧게 한 번만 닿았다 떼세요.")
        # 받침 L
        if sub == "nasal":
            return (f"{josa(tj, '은/는')} 코로 내는 소리가 아니에요.",
                    "혀끝을 윗잇몸에 붙인 채로 유지하고 소리를 혀 양옆으로 흘려 보내세요—콧방울 옆에 댄 손가락에 떨림이 없어야 해요.")
        if sub == "stop":
            return (f"{josa(tj, '은/는')} 소리를 막는 받침이 아니에요.",
                    "혀끝을 윗잇몸에 붙인 채, 소리가 혀 양옆으로 계속 흘러나오게 이어 보세요('ㅡ'를 따로 내지 않아요).")
        if sub == "flap":
            return (f"{josa(tj, '은/는')} 혀를 튕기지 않아요.",
                    "혀끝을 윗잇몸에 붙인 채 떼지 말고, 소리를 혀 양옆으로 흘리며 끝내세요.")
        return (f"{josa(tj, '은/는')} 혀끝을 윗잇몸에 붙인 채로 내는 소리예요.",
                "혀끝을 떼지 말고 소리를 혀 양옆으로 흘려 보내세요('ㅡ'를 따로 내지 않아요).")

    if cat == "coda":
        if sub == "release":
            return (f"{josa(tj, '은/는')} 터뜨리지 않고 막은 채로 멈추는 소리예요.",
                    f"{HOLD.get(pl, HOLD[None])} 멈추세요—입 앞에 댄 휴지가 흔들리지 않아야 해요.")
        return (f"{josa(tj, '은/는')} {CODA_PLACE_DESC.get(pl, '그 자리에서 멈추는 소리예요.')}", _core(t, True))

    if cat == "place":
        return (f"{josa(tj, '은/는')} {PLACE_DESC.get(pl, '')}".strip(), PLACE_CHECK.get(pl, _core(t, tc)))

    if cat == "manner":
        if t == "H":
            return f"{josa(tj, '은/는')} {PLACE_DESC['glottal']}", PLACE_CHECK["glottal"]
        return f"{josa(tj, '은/는')} {MANNER_DESC.get(T.manner or '', '')}".strip(), _core(t, tc)

    if cat in ("similar", "unknown"):
        if T.is_vowel:
            return f"{josa(tj, '이/가')} 조금 다르게 들렸어요.", _core(t, False, jamo=jamo)
        return f"{josa(tj, '이/가')} 조금 다르게 들렸어요.", _core(t, tc, prev)

    if cat == "mixed":
        if T.is_vowel:
            return f"모음 {josa(tj, '이/가')} 또렷하게 들리지 않았어요.", _core(t, False, jamo=jamo)
        return f"{josa(tj, '이/가')} 모음 {hj}처럼 들렸어요.", _core(t, tc, prev)

    # ── 모음 ──
    if cat == "monophthong":
        s, e, how = _diph(t, jamo)
        if _vjamo(t, jamo) == "ㅚ":
            return f"{josa(tj, '은/는')} 입술을 둥글게 모은 채 내는 소리예요.", how
        return f"{josa(tj, '은/는')} '{s}'에서 '{e}'{josa(e, '으로/로')[len(e):]} 재빨리 넘어가는 소리예요.", how
    if cat == "glide_add":
        return f"{josa(tj, '은/는')} 처음부터 끝까지 같은 입모양으로 내는 소리예요.", _core(t, False, jamo=jamo)
    if cat == "glide_swap":
        s, _e, how = _diph(t, jamo)
        return f"{josa(tj, '은/는')} '{s}' 모양에서 시작하는 소리예요.", how
    # centralize / vowel
    instr = _vowel_instr(t, h, hj) if H is not None else []
    check = W_CHECK if T.glide == "w" else VOWEL_CHECK.get(T.lip or "", "")
    if not instr:
        return _core(t, False, jamo=jamo), check
    if len(instr) == 1:
        body = instr[0][1]
    else:
        body = f"{instr[0][0]}, {instr[1][1]}"
    return f"{josa(tj, '을/를')} 낼 때는 {body}.", check


def phone_tip(target: str, heard: str | None, status: str, *, coda: bool | None = None,
              prev: str | None = None, initial: bool = False, jamo: str | None = None) -> str | None:
    """음소 하나에 대한 교정 문구(한국어 1~2문장). 맞았거나(ok) 모르는 음소면 None.

    coda: 이 음소가 받침 자리인지(선택). p/t/k/L/NG 는 원래 받침 전용이라 몰라도 된다.
          ㅁ/ㄴ 받침을 구별하고 싶을 때만 넘긴다(summarize 는 음절 정보로 자동 판단).
    (계약 외 선택 인자)
    prev: 바로 앞 목표 음소. 'L' 이면 초성 ㄹ 을 설측음(붙인 채 이어 가기)으로 지도한다.
    initial: 어절 첫소리면 평음/격음/경음 교정에 시작 음높이(낮게/높게) 단서를 더한다.
    jamo: 표시 자모(display_jamo) — ㅚ·ㅞ·ㅐ 처럼 한 음소가 여러 자모를 나타낼 때.
    """
    cls = classify(target, heard, status, coda)
    if cls is None:
        return None
    s1, s2 = _parts(cls, target, heard, coda, prev=prev, initial=initial, jamo=jamo)
    return " ".join(x for x in (s1, s2) if x).strip() or None


# ── 점수 ─────────────────────────────────────────────────
def _num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _clamp100(v: float) -> int:
    return int(round(min(100.0, max(0.0, v))))


def _interp(x: float, pts: list[tuple[float, float]]) -> float:
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


# 의문문 끝 상승(반음) → 점수. +2 st 에서 75(좋음 경계), +5 st 이상 100.
_RISE_CURVE = [(-3.0, 10.0), (0.0, 40.0), (QUESTION_RISE_OK_ST, 75.0), (5.0, 100.0)]
# 평서문/단어 음높이 폭(반음) → 점수. 2~12 st 가 좋음(≥75), 2 미만은 단조, 아주 넓으면 약간 감점.
_RANGE_CURVE = [(0.0, 20.0), (1.0, 45.0), (RANGE_OK_ST[0], 75.0), (3.0, 90.0), (4.0, 100.0),
                (9.0, 100.0), (RANGE_OK_ST[1], 80.0), (16.0, 55.0), (24.0, 35.0)]


def _f0_stats(acoustic: dict | None) -> dict:
    if not isinstance(acoustic, dict):
        return {}
    st = acoustic.get("f0_stats")
    return st if isinstance(st, dict) else {}


def _end_rise(acoustic: dict | None) -> float | None:
    v = _num(_f0_stats(acoustic).get("end_rise_st"))
    if v is None and isinstance(acoustic, dict):
        v = _num(acoustic.get("end_rise_st"))
    return v


def resolve_tune(sentence_type: str, question_kind: str | None = None, tune: str | None = None) -> str | None:
    """끝 억양 기대: rise(판정 의문문: 끝을 올려야 함) | fall(평서문: 끝이 크게 오르면 질문처럼 들림)
    | free(설명 의문문·인사처럼 올려도 내려도 자연스러움) | None(단어: 음높이 폭만 봄).

    국어 억양의 기본: 판정 의문문(예/아니요로 답하는 물음: 밥 먹었어요?)은 끝을 올리고, 설명 의문문
    (의문사 물음: 이름이 뭐예요?)은 끝을 내리는 것이 기본이며(K-ToBI 에서도 HL%·L% 가 흔함) 올려도 틀리지 않다.
    """
    if tune in ("rise", "fall", "free"):
        return tune
    if sentence_type == "question":
        return "free" if question_kind == "wh" else "rise"
    if sentence_type == "statement":
        return "fall"
    return None


def _intonation_score(acoustic: dict | None, sentence_type: str, tune: str | None = "auto") -> int | None:
    st = _f0_stats(acoustic)
    vr = _num(st.get("voiced_ratio"))
    if vr is not None and vr < 0.05:      # 유성음이 거의 없으면 억양을 판단할 수 없다
        return None
    if tune == "auto":
        tune = resolve_tune(sentence_type)
    if tune == "rise":
        rise = _end_rise(acoustic)
        return None if rise is None else _clamp100(_interp(rise, _RISE_CURVE))
    rng = _num(st.get("range_st"))
    if rng is None:
        return None
    score = _interp(max(0.0, rng), _RANGE_CURVE)
    if tune == "fall":
        rise = _end_rise(acoustic)
        if rise is not None and rise >= STATEMENT_RISE_WARN_ST:
            score = min(score, 60.0)
    return _clamp100(score)


def _scores(phones: list[dict], n_ins: int, acoustic: dict | None, lips: dict | None,
            sentence_type: str, tune: str | None = "auto") -> dict:
    targets = [p for p in phones if p.get("status") != "ins"]
    n = len(targets)
    if n:
        credit = sum(STATUS_CREDIT.get(p.get("status") or "ok", 0.0) for p in targets)
        accuracy = _clamp100((credit - INSERTION_PENALTY * n_ins) / n * 100.0)
    else:
        accuracy = 0
    gops = [_num(p.get("gop")) for p in targets]
    gops = [min(100.0, max(0.0, g)) for g in gops if g is not None]
    clarity = _clamp100(sum(gops) / len(gops)) if gops else None
    intonation = _intonation_score(acoustic, sentence_type, tune)
    lip_score = None
    if isinstance(lips, dict) and lips.get("available"):
        v = _num(lips.get("score"))
        lip_score = _clamp100(v) if v is not None else None
    parts = {"accuracy": accuracy, "clarity": clarity, "intonation": intonation, "lips": lip_score}
    wsum = sum(WEIGHTS[k] for k, v in parts.items() if v is not None)
    overall = _clamp100(sum(WEIGHTS[k] * v for k, v in parts.items() if v is not None) / wsum) if wsum else 0
    return {"overall": overall, **parts}


# ── 피드백 카드 ──────────────────────────────────────────
# (단계, 단계 안 순서). CONTRACT 7절: 대비 오류 > 탈락 > 모음 오류 > 입모양 > 억양/크기.
# 0 대비 오류(평/격/경, ㅅ/ㅆ) → 1 그 밖의 자음 대치(과비성·ㄹ·받침·조음위치 — 역시 음소 대비가 무너진 것)
# → 2 탈락 → 4 모음(삽입은 계약에 없어 모음 오류 바로 뒤) → 5 입모양 → 6 약함(weak) → 7 억양/크기
_ORDER = {
    "clipped": (-1, 0),            # 녹음 품질(찌그러짐): 음소 판정의 전제라 맨 앞
    "phonation": (0, 0), "sibilant": (0, 1),
    "hypernasal": (1, 0), "denasal": (1, 1), "liquid": (1, 2), "coda": (1, 3), "place": (1, 4),
    "manner": (1, 5), "similar": (1, 6), "mixed_c": (1, 7), "unknown_c": (1, 8),
    "del": (2, 0), "del_h": (2, 1),
    "centralize": (4, 0), "monophthong": (4, 1), "glide_add": (4, 2), "glide_swap": (4, 3),
    "vowel": (4, 4), "mixed_v": (4, 5), "unknown_v": (4, 6),
    "insertion": (4, 9),
    "lips": (5, 0),
    "weak": (6, 0),
    "intonation": (7, 0), "loudness": (7, 1),
}
CENTRAL_PREFIX = "입 모양을 크게 움직이지 않으면 모음이 ㅓ·ㅡ처럼 가운데로 흐려져요."


def _syllable_texts(phones: list[dict]) -> dict[int, str]:
    """목표 음소열(+syl) → 음절 번호별 발음형 한 글자(카드 제목의 위치 표시용)."""
    onset_jamo = {v: k for k, v in ONSET_PHONE.items() if v}
    coda_jamo = {v: k for k, v in CODA_PHONE.items()}
    by_syl: dict[int, list[str]] = {}
    vj: dict[int, str | None] = {}
    for p in phones:
        s = p.get("syl")
        if isinstance(s, int) and p.get("phone") in PHONES and p.get("status") != "ins":
            by_syl.setdefault(s, []).append(p["phone"])
            if PHONES[p["phone"]].is_vowel:
                vj[s] = p.get("jamo") if isinstance(p.get("jamo"), str) else None
    out: dict[int, str] = {}
    for s, syms in by_syl.items():
        try:
            vi = next(i for i, x in enumerate(syms) if PHONES[x].is_vowel)
            cho = onset_jamo.get(syms[vi - 1], "ㅇ") if vi > 0 else "ㅇ"
            jong = coda_jamo.get(syms[vi + 1], "") if vi + 1 < len(syms) else ""
            out[s] = compose(cho, _vjamo(syms[vi], vj.get(s)), jong)
        except (StopIteration, ValueError, KeyError):
            continue
    return out


def _coda_flag(phones: list[dict], i: int) -> bool | None:
    sym = phones[i].get("phone")
    P = PHONES.get(sym)
    if P is None or P.is_vowel:
        return False
    if P.coda:
        return True
    if i == 0:
        return False
    prev = PHONES.get(phones[i - 1].get("phone"))
    if prev is None or not prev.is_vowel:
        return False
    s, sp = phones[i].get("syl"), phones[i - 1].get("syl")
    if s is None or sp is None:
        return None
    return s == sp


def _group_key(cat: str, sub: str, t: str, h: str | None) -> tuple:
    T = PHONES[t]
    if cat == "phonation":
        return ("phonation", sub)                 # 예: lenis>tense 끼리 한 카드
    if cat in ("hypernasal", "denasal", "centralize", "monophthong", "weak"):
        return (cat,)
    if cat == "del":
        return ("del", sub)
    if cat in ("mixed", "unknown"):
        return (f"{cat}_{sub}", t)
    return (cat, sub, t)


def _order_name(cat: str, sub: str) -> str:
    if cat == "del":
        return "del_h" if sub == "h" else "del"
    if cat in ("mixed", "unknown"):
        return f"{cat}_{sub}"
    return cat


def _with_where(prefix: str | None, title: str) -> str:
    return f"'{prefix}'의 {title}" if prefix else title


def _render_group(g: dict, sylmap: dict[int, str]) -> dict:
    items = g["items"]
    cat, sub = g["cat"], g["sub"]
    first = items[0]
    tls = _uniq(it["tlabel"] for it in items)
    hls = _uniq(it["hlabel"] for it in items if it["hlabel"])
    pairs = _uniq((it["t"], it["h"], it["tc"]) for it in items)
    syls = _uniq(it["syl"] for it in items)
    where = sylmap.get(syls[0]) if len(syls) == 1 and syls[0] is not None else None
    level = "error"

    # 제목
    if cat == "del":
        if sub == "coda":
            title = f"받침 {josa(_join(_uniq(jamo_of(it['t']) for it in items)), '이/가')} 빠졌어요"
        elif sub == "h":
            title, level = "ㅎ 소리가 약하게 들려요", "warn"
        elif sub == "vowel":
            title = f"모음 {josa(_join(tls), '이/가')} 빠졌어요"
        else:
            title = f"{_join(tls)} 소리가 빠졌어요"
    elif cat == "weak":
        # 정보 수준: weak 는 '대안과 비슷하게 들린' 애매한 자리라 정상 화자에게도 나온다(사람 낭독 실측 음소의 약 2 %)
        title, level = f"{josa(_join(tls), '을/를')} 조금 더 또렷하게 내 보세요", "info"
    elif hls and set(hls) <= {_vjamo(it["t"], it.get("jamo")) for it in items}:
        # 목표와 들린 소리의 자모가 같은 대치(받침 ㅂ→첫소리 ㅂ, 받침 ㄹ↔첫소리 ㄹ …):
        # 'ㄹ이 ㄹ처럼 들려요'는 뜻이 안 통하므로 무엇을 어떻게 했는지 동작으로 말한다
        if cat == "coda" and sub == "release":
            title = f"{josa(_join(tls), '을/를')} 터뜨려서 소리 냈어요"
        elif cat == "liquid" and sub == "flap":
            title = f"{josa(_join(tls), '을/를')} 튕겨서 소리 냈어요"
        elif cat == "liquid" and sub == "lateral":
            title = f"첫소리 {josa(_join(tls), '을/를')} 혀를 붙인 채로 소리 냈어요"
        else:
            title = f"{josa(_join(tls), '이/가')} 조금 다르게 들려요"
    elif hls:
        title = f"{josa(_join(tls), '이/가')} {_join(hls)}처럼 들려요"
    else:
        title = f"{josa(_join(tls), '이/가')} 다르게 들려요"
    title = _with_where(where, title)

    # 본문
    def ctx(it: dict) -> dict:
        return {"prev": it.get("prev"), "initial": it.get("initial", False), "jamo": it.get("jamo")}

    def full(it: dict, **kw) -> str:
        s1, s2 = _parts((it["cat"], it["sub"]), it["t"], it["h"], it["tc"], **{**ctx(it), **kw})
        return " ".join(x for x in (s1, s2) if x)

    reps: list[dict] = []          # (목표, 들린 소리, 받침) 조합별 대표 1개
    seen: set = set()
    for it in items:
        k = (it["t"], it["h"], it["tc"])
        if k not in seen:
            seen.add(k)
            reps.append(it)

    if cat == "weak":
        # 제목이 '…을 조금 더 또렷하게'이므로 본문은 GOP 가 낮은 순으로 핵심 지시만(최대 2개)
        def gop_key(it: dict) -> float:
            g = _num(it.get("gop"))
            return g if g is not None else 101.0
        worst = sorted(reps, key=gop_key)[:2]
        def core(it: dict) -> str:
            return _core(it["t"], it["tc"], it.get("prev"), it.get("jamo"))
        if len(worst) == 1:
            body = "거의 맞았어요. " + core(worst[0])
        else:
            body = "거의 맞았어요. " + " ".join(f"{it['tlabel']}: {core(it)}" for it in worst)
    elif cat == "del":
        # 제목이 '…이 빠졌어요'이므로 본문은 자모를 밝힌 교정 지시만
        body = " ".join(_parts((it["cat"], it["sub"]), it["t"], it["h"], it["tc"], **ctx(it))[1] for it in reps[:3])
    elif cat == "centralize":
        # '흐려짐' 설명 + 목표 모음별 지시(최대 2개); 하나뿐이면 거울 확인 문장도 붙인다
        parts = [_parts((it["cat"], it["sub"]), it["t"], it["h"], it["tc"], **ctx(it)) for it in reps[:2]]
        body = " ".join([CENTRAL_PREFIX] + [p[0] for p in parts] + ([parts[0][1]] if len(parts) == 1 else []))
    elif len(pairs) == 1:
        body = full(first)
    elif cat == "phonation":
        body = full(first, tj=_join(tls), hj=_join(hls), initial=any(it.get("initial") for it in items))
    elif cat in ("hypernasal", "denasal"):
        places = _uniq(PHONES[it["t"]].place for it in items)
        any_coda = any(it["tc"] for it in items)
        all_coda = all(it["tc"] for it in items)
        s1, s2 = _parts((cat, sub), first["t"], first["h"], first["tc"] if all_coda or not any_coda else False,
                        tj=_join(tls), hj=_join(hls), place=places[0] if len(places) == 1 else None)
        body = f"{s1} {s2}"
    else:
        body = " ".join(full(it) for it in reps[:2])
    if cat == "phonation":
        # 어절 첫소리의 예사·거센·된소리: 시작 음높이를 화면의 높낮이 선으로 확인(눈으로 보는 단서)
        tps = _uniq(PHONES[it["t"]].phonation for it in items if it.get("initial") and not it["tc"])
        if len(tps) == 1 and tps[0] in PITCH_CHECK:
            body = f"{body} {PITCH_CHECK[tps[0]]}"
    return {"level": level, "title": title, "body": body,
            "phones": sorted(_uniq(it["idx"] for it in items)), "kind": cat}


def _insertion_cards(insertions: list[dict], phones: list[dict], sylmap: dict[int, str]) -> list[tuple]:
    n = len(phones)
    groups: dict[str, list[dict]] = {}
    for ins in insertions or []:
        sym = ins.get("phone")
        if sym not in PHONES:
            continue
        key = "EU" if sym == "EU" else ("V" if PHONES[sym].is_vowel else "C")
        groups.setdefault(key, []).append(ins)
    out = []
    for key, items in groups.items():
        idxs: list[int] = []
        for ins in items:
            a = ins.get("after")
            a = a if isinstance(a, int) else -1
            for k in (a, a + 1):
                if 0 <= k < n:
                    idxs.append(int(phones[k].get("idx", k)))
        first_after = items[0].get("after") if isinstance(items[0].get("after"), int) else -1
        where = None
        if len(items) == 1 and 0 <= first_after < n:
            where = sylmap.get(phones[first_after].get("syl"))
        # NG 의 자모 'ㅇ'만 쓰면 '오이'처럼 초성 ㅇ(소리 없음)이 든 낱말에서 "글자에 없는 ㅇ"이 모순으로 읽힌다
        hj = _join(_uniq("받침 ㅇ" if i["phone"] == "NG" else jamo_of(i["phone"]) for i in items))
        if key == "EU":
            title = (f"'{where}' 뒤에 ㅡ 소리가 끼어들었어요" if where else "자음 뒤에 ㅡ 소리가 끼어들었어요")
            body = ("자음 뒤에 'ㅡ'를 덧붙이지 말고 바로 다음 소리로 이어 가세요. "
                    "받침은 입술이나 혀를 붙인 채로 멈추면 'ㅡ'가 생기지 않아요.")
        elif key == "V":
            title = f"글자에 없는 {hj} 소리가 더 들렸어요"
            body = "음절 사이에 다른 모음을 넣지 말고, 입 모양을 바로 다음 소리로 옮겨 이어 가세요."
        else:
            title = f"글자에 없는 {hj} 소리가 더 들렸어요"
            body = "글자에 없는 소리가 끼어들지 않도록, 화면의 음절 칸을 보며 한 음절씩 천천히 이어 말해 보세요."
        first = min(idxs) if idxs else n
        out.append((_ORDER["insertion"], first,
                    {"level": "warn", "title": title, "body": body,
                     "phones": sorted(_uniq(idxs)), "kind": "insertion"}))
    return out


LIPS_TEXT = {
    "round": ("입술을 더 동그랗게 모아 보세요",
              "카메라로 보니 {tj}에서 입술이 덜 모아졌어요. 입술을 동그랗게 모아 앞으로 내밀어 보세요—거울 속 입술이 작은 동그라미가 되면 좋아요."),
    "spread": ("입꼬리를 옆으로 더 당겨 보세요",
               "카메라로 보니 {tj}에서 입꼬리가 덜 당겨졌어요. 미소 짓듯 입꼬리를 옆으로 당겨 보세요."),
    "open": ("입을 더 크게 벌려 보세요",
             "카메라로 보니 {tj}에서 입이 덜 벌어졌어요. 턱을 아래로 내려 입을 위아래로 크게 벌려 보세요."),
    "closed": ("두 입술을 꼭 붙여 보세요",
               "카메라로 보니 {tj}에서 두 입술이 완전히 닫히지 않았어요. ㅂ·ㅃ·ㅍ·ㅁ은 두 입술이 한 번 꼭 붙었다가 떨어져야 해요."),
}


def _lips_cards(lips: dict | None) -> list[tuple]:
    if not isinstance(lips, dict) or not lips.get("available"):
        return []
    groups: dict[str, list[dict]] = {}
    for c in lips.get("checks") or []:
        if isinstance(c, dict) and c.get("ok") is False and c.get("expect") in LIPS_TEXT:
            groups.setdefault(c["expect"], []).append(c)
    out = []
    for expect, items in groups.items():
        title, body = LIPS_TEXT[expect]
        tj = _join(_uniq(jamo_of(c.get("phone", "")) for c in items if c.get("phone")))
        idxs = [int(c["idx"]) for c in items if isinstance(c.get("idx"), int)]
        out.append((_ORDER["lips"], min(idxs) if idxs else 0,
                    {"level": "warn", "title": title, "body": body.format(tj=tj or "입술 소리"),
                     "phones": sorted(_uniq(idxs)), "kind": "lips"}))
    return out


def _prosody_cards(acoustic: dict | None, sentence_type: str, n_syl: int, tune: str | None = "auto") -> list[tuple]:
    out = []
    st = _f0_stats(acoustic)
    vr = _num(st.get("voiced_ratio"))
    reliable = vr is None or vr >= 0.05
    if tune == "auto":
        tune = resolve_tune(sentence_type)
    if reliable and tune == "rise":
        rise = _end_rise(acoustic)
        if rise is not None and rise < QUESTION_RISE_OK_ST:
            out.append((_ORDER["intonation"], 0, {
                "level": "warn", "title": "질문인데 끝이 올라가지 않았어요",
                "body": "'예/아니요'로 답하는 물음은 마지막 음절에서 목소리를 올려요. 화면의 높낮이 선 끝이 위로 올라가도록 마지막 음절을 올려 말해 보세요.",
                "phones": [], "kind": "intonation"}))
    elif reliable:
        rise = _end_rise(acoustic)
        rng = _num(st.get("range_st"))
        if tune == "fall" and rise is not None and rise >= STATEMENT_RISE_WARN_ST:
            out.append((_ORDER["intonation"], 0, {
                "level": "warn", "title": "끝이 올라가서 질문처럼 들려요",
                "body": "말하는 문장은 끝을 편하게 내려요. 마지막 음절에서 높낮이 선이 아래로 내려가게 말해 보세요.",
                "phones": [], "kind": "intonation"}))
        elif rng is not None and rng < RANGE_OK_ST[0] and (sentence_type in ("statement", "question") or n_syl >= 2):
            body = ("목소리가 한 높이로만 이어지면 단조롭게 들려요. 낱말마다 목소리가 조금 올라갔다 내려오도록, "
                    "높낮이 선이 물결처럼 움직이게 말해 보세요."
                    if sentence_type in ("statement", "question") else
                    "목소리가 한 높이로만 이어지면 단조롭게 들려요. 낱말 안에서 목소리가 조금 올라갔다가 끝에서 편하게 내려오도록 말해 보세요.")
            out.append((_ORDER["intonation"], 0, {
                "level": "warn", "title": "목소리 높낮이가 거의 없어요", "body": body,
                "phones": [], "kind": "intonation"}))

    loud = acoustic.get("loudness") if isinstance(acoustic, dict) else None
    if isinstance(loud, dict):
        mean_db, max_db = _num(loud.get("mean_db")), _num(loud.get("max_db"))
        if loud.get("clipped") is True:
            # 찌그러진 녹음은 음소 판정 자체를 믿기 어렵다 → 다른 카드보다 먼저, 카드 수 제한에 밀리지 않게
            out.append((_ORDER["clipped"], 0, {
                "level": "warn", "title": "소리가 너무 커서 찌그러졌어요",
                "body": "녹음이 찌그러지면 맞게 낸 소리도 틀리게 판정될 수 있어요. 마이크에서 한 뼘쯤 떨어져 "
                        "편안한 크기로 다시 말해 보세요.",
                "phones": [], "kind": "loudness"}))
        elif mean_db is not None and mean_db < QUIET_MEAN_DB:
            out.append((_ORDER["loudness"], 0, {
                "level": "warn", "title": "목소리가 작아요",
                "body": "소리가 작으면 정확히 분석하기 어려워요. 마이크와 한 뼘 거리에서, 화면의 소리 크기 막대가 절반 넘게 올라가도록 조금 더 크게 말해 보세요.",
                "phones": [], "kind": "loudness"}))
        elif max_db is not None and max_db >= LOUD_MAX_DB:
            out.append((_ORDER["loudness"], 0, {
                "level": "warn", "title": "소리가 너무 커요",
                "body": "소리가 너무 크면 녹음이 찌그러져 분석이 부정확해져요. 마이크에서 조금 떨어지거나 편안한 크기로 말해 보세요.",
                "phones": [], "kind": "loudness"}))
    return out


def _praise_card(sentence_type: str, has_weak: bool, scores: dict, warn_kinds: set | None = None,
                 tune: str | None = "auto") -> dict:
    """음소 오류가 없을 때 맨 앞에 두는 칭찬 카드. warn_kinds: 함께 나간 주의 카드 종류
    (intonation/loudness/lips) — 있으면 '모든 소리가 정확'이 아니라 '소리는 정확'으로 범위를 좁히고,
    그 안내와 어긋나는 '다음 단계'(예: 끝을 내려서도 말해 보기)를 내지 않는다."""
    warn_kinds = set(warn_kinds or ())
    if tune == "auto":
        tune = resolve_tune(sentence_type)
    title = "모든 소리가 정확하게 들렸어요"
    if has_weak:
        nxt = "거의 완벽해요. 아래 표시된 소리를 조금 더 또렷하게 내면 더 좋아요."
    elif scores.get("clarity") is not None and scores["clarity"] < 70:
        nxt = "소리는 모두 맞았어요. 입 모양을 조금 더 크게 움직이면 더 또렷해져요."
    elif "intonation" in warn_kinds:
        title = "소리는 모두 정확했어요"
        nxt = "이제 아래 억양 안내를 따라, 화면의 높낮이 선을 보며 한 번 더 말해 보세요."
    elif warn_kinds & {"lips", "loudness"}:
        title = "소리는 모두 정확했어요"
        nxt = "아래 안내를 확인하고 한 번 더 말해 보세요."
    elif tune == "rise":
        nxt = "다음 단계: 같은 문장을 대답하듯 끝을 내려서도 말해 보며 억양 차이를 연습해 보세요."
    elif sentence_type == "question":
        nxt = ("다음 단계: '뭐'·'어디' 같은 말이 든 물음은 끝을 내려도, 올려도 자연스러워요. "
               "두 가지로 모두 말해 보며 화면의 높낮이 선을 비교해 보세요.")
    elif sentence_type == "statement":
        nxt = "다음 단계: 쉬지 않고 한 번에, 평소 말하는 속도로 이어서 말해 보세요."
    else:
        nxt = "다음 단계: 같은 묶음의 다른 단어(예: 불·풀·뿔)와 번갈아 말하거나, 이 단어가 들어간 짧은 문장으로 넓혀 보세요."
    return {"level": "info", "title": title, "body": nxt, "phones": [], "kind": "praise"}


def summarize(phones: list[dict], acoustic: dict, lips: dict, sentence_type: str,
              insertions: list[dict] | None = None, *, question_kind: str | None = None,
              tune: str | None = None) -> dict:
    """점수 + 피드백 카드(최대 4개).

    phones: 파이프라인의 음소별 결과 [{"idx","phone","syl","status","heard","gop",...}]
            (계약 외 선택 필드: "jamo" 표시 자모, "initial" 어절 첫소리 여부)
    insertions: (선택, 계약 외 추가 인자) [{"after","phone","jamo"}] — 넘기면 정확도에서
                삽입 1개당 0.5음소 감점하고 'ㅡ 삽입' 카드를 만든다.
    question_kind: (선택) 의문문 종류 'yn'(판정: 끝 올림을 확인) | 'wh'(설명: 올림·내림 모두 허용).
                   없으면 'yn' 으로 본다.
    tune: (선택) 끝 억양 기대를 직접 지정 rise | fall | free (resolve_tune 참고). 예: 인사 '안녕하세요'는 free.
    반환: {"scores": {"overall","accuracy","clarity","intonation","lips"}, "feedback": [...]}
    """
    phones = [p for p in (phones or []) if isinstance(p, dict)]
    stype = (sentence_type or "word").lower()
    if stype not in ("statement", "question", "word"):
        stype = "word"
    tune = resolve_tune(stype, question_kind, tune)
    ins_list = [i for i in (insertions or []) if isinstance(i, dict)]
    n_ins = len(ins_list) + sum(1 for p in phones if p.get("status") == "ins")
    targets = [p for p in phones if p.get("status") != "ins"]

    scores = _scores(targets, n_ins, acoustic, lips, stype, tune)
    sylmap = _syllable_texts(targets)
    n_syl = len({p.get("syl") for p in targets if p.get("syl") is not None}) or (1 if targets else 0)

    # 음소 오류 → 그룹
    groups: dict[tuple, dict] = {}
    has_err = n_ins > 0
    has_weak = False
    for i, p in enumerate(targets):
        status = p.get("status")
        t = p.get("phone")
        if status not in ("weak", "del", "sub") or t not in PHONES:
            continue
        h = p.get("heard") if p.get("heard") in PHONES else None
        tc = _coda_flag(targets, i)
        cls = classify(t, h, status, tc)
        if cls is None:
            continue
        cat, sub = cls
        if status == "weak":
            has_weak = True
        else:
            has_err = True
        idx = p.get("idx", i)
        idx = int(idx) if isinstance(idx, (int, float)) else i
        prev = targets[i - 1].get("phone") if i > 0 else None
        jamo = p.get("jamo") if isinstance(p.get("jamo"), str) else None
        initial = p.get("initial")
        initial = bool(initial) if isinstance(initial, bool) else (i == 0)
        item = {"idx": idx, "t": t, "h": h, "tc": bool(tc), "cat": cat, "sub": sub, "gop": p.get("gop"),
                "syl": p.get("syl"), "prev": prev, "initial": initial, "jamo": jamo,
                "tlabel": _label(t, bool(tc), jamo), "hlabel": (jamo_of(h) if h else None)}
        key = _group_key(cat, sub, t, h)
        if key not in groups:
            groups[key] = {"cat": cat, "sub": sub, "order": _ORDER[_order_name(cat, sub)],
                           "first": idx, "items": []}
        groups[key]["items"].append(item)

    ranked: list[tuple] = [(g["order"], g["first"], _render_group(g, sylmap)) for g in groups.values()]
    ranked += _insertion_cards(ins_list, targets, sylmap)
    ranked += _lips_cards(lips)
    ranked += _prosody_cards(acoustic, stype, n_syl, tune)
    ranked.sort(key=lambda x: (x[0], x[1]))
    cards = [c for _o, _f, c in ranked]

    if targets and not has_err:
        warn_kinds = {c.get("kind") for c in cards if c.get("kind") in ("intonation", "loudness", "lips")}
        cards.insert(0, _praise_card(stype, has_weak, scores, warn_kinds, tune))
    return {"scores": scores, "feedback": cards[:MAX_CARDS]}
