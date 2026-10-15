"""철자 한글 → 표준발음 한글 (G2P).

    to_pron("국물")        == "궁물"
    to_pron("밥 먹었어요") == "밥 머거써요"

인식 모델은 '실제로 난 소리'를 음소로 내놓으므로, 여기서 만든 발음형이 틀리면
정상 발음도 오류로 판정된다. 그래서 '표준 발음법'(국립국어원)의 규칙 가운데
철자만 보고 확실히 결정되는 것만 적용하고, 형태소 정보가 있어야 하는 규칙은
일부러 적용하지 않는다(아래 '미처리 규칙').

입출력
------
- 공백(어절 경계)은 유지한다. to_pron 은 규칙을 같은 어절 안의 인접 음절 사이에만 적용하고
  어절 사이에는 연음·경음화 등을 적용하지 않는다(CONTRACT 2절). 어절 사이 규칙은
  pron_options() 가 '이어 말한 경우의 대안'으로 따로 만든다(아래 '발음 변이').
- 한글 음절(가-힣) 이외의 문자(문장부호·숫자·영문·낱자모)는 지운다. 지운 자리는
  어절 경계로 본다(``"안녕,하세요"`` → ``"안녕 하세요"``). 연속 공백은 하나로 줄이고
  앞뒤 공백은 없앤다. 빈 문자열(또는 한글이 없는 문자열) → ``""``.
- 결과의 받침은 항상 대표음 7개(ㄱ ㄴ ㄷ ㄹ ㅁ ㅂ ㅇ) 중 하나다
  (phones.pron_to_phones 가 그대로 받을 수 있는 형태).

규칙 적용 순서 (어절 단위)
--------------------------
음절을 [초성, 중성, 종성]으로 분해한 뒤,

0. 'ㅢ' (제5항 다만3): **철자상** 초성이 자음인 'ㅢ' → 'ㅣ' (희망→히망, 무늬→무니).
   초성 ㅇ의 '의'는 어두·비어두 모두 그대로 둔다(의자, 주의, 회의).
   연음보다 먼저 해야 '협의'가 [혀비]가 아니라 원칙 발음 [혀븨]가 된다.

1~6. 인접 음절 쌍(앞 음절 받침 K, 뒤 음절 초성 C)을 왼쪽부터 차례로 처리한다.
   쌍 (i, i+1) 은 i 의 받침과 i+1 의 초성만 바꾸고, 쌍 (i+1, i+2) 는 i+1 의 받침과
   i+2 의 초성만 바꾸므로 쌍끼리는 서로 간섭하지 않는다. 한 쌍 안에서의 순서:

   1. ㅎ 받침(ㅎ ㄶ ㅀ) (제12항) — 연음·유음화·비음화보다 먼저.
      ㅎ+ㄱㄷㅈ → ㅋㅌㅊ(놓고→노코, 많다→만타), ㅎ+ㅅ → ㅆ(닿소→다쏘),
      ㅎ+ㄴ → ㄴㄴ(놓는→논는; ㄶ·ㅀ은 ㅎ만 탈락: 않는→안는, 뚫는→뚤는→[유음화]뚤른),
      ㅎ+모음 → ㅎ 탈락(좋아→조아; 많아→만아→[연음]마나).
      그 밖의 자음 앞 ㅎ 은 대표음 ㄷ 으로 보고 다음 규칙으로 넘긴다.
   2. 거센소리되기 (제12항 붙임1·2): 받침 ㄱ ㄷ ㅂ ㅈ(겹받침 포함)+ㅎ → ㅋ ㅌ ㅍ ㅊ
      (축하→추카, 밝히다→발키다, 넓히다→널피다, 앉히다→안치다, 꽂히다→꼬치다).
      ㄷ 으로 소리 나는 ㅅ ㅆ ㅊ(그리고 '히·혀' 이외 앞의 ㅈ)+ㅎ → ㅌ (못하다→모타다).
      구개음화보다 먼저: ㄷ+히 → 티 → 치 (닫히다→다치다, 제17항 붙임).
      ㄺ 은 용언이면 ㄹ 이 남고(밝히다→발키다) 체언이면 ㄱ 으로 줄어 격음화(닭하고→다카고).
   3. 구개음화 (제17항): ㄷ ㅌ ㄾ + 이 → 지 치 (굳이→구지, 같이→가치, 핥이다→할치다).
      연음보다 먼저 해야 [가티]가 되지 않는다. '이'가 '이+어' 축약형 '여·였'인 경우도
      포함한다(붙여→부쳐→[부처]); 받침 있는 '여·혀'(맏형→[마텽])는 제외.
   4. 연음 (제13·14항): 받침 + 초성 ㅇ → 받침이 뒤 음절 초성으로 이동.
      겹받침은 뒤 자음만 이동하고, 이동한 ㅅ 은 ㅆ (값이→갑씨, 없어요→업써요).
      ㅇ 받침은 이동하지 않는다. 대표음화보다 먼저 해야 닭이→[달기]가 된다.
   5. 된소리되기 (제23~25항): 장애음 받침(ㄱ ㄲ ㅋ ㄳ ㄺ ㄷ ㅅ ㅆ ㅈ ㅊ ㅌ ㅂ ㅍ ㄼ(밟) ㄿ ㅄ)
      뒤 ㄱ ㄷ ㅂ ㅅ ㅈ → ㄲ ㄸ ㅃ ㅆ ㅉ. 겹받침 정체가 필요하므로 대표음화보다 먼저.
      겹받침 ㄵ ㄻ ㄼ ㄾ 은 용언 어간에만 나타나므로(제24·25항) 철자만으로 판단 가능:
      앉다→안따, 젊다→점따, 넓다→널따, 핥다→할따. 단, 피·사동 '-기-' 와 그 활용형(기·겨·겼·긴·길·김)
      앞의 ㄻ (옮기다→옴기다, 옮겨→옴겨, 옮긴→옴긴, 굶겨요→굼겨요; 제24항 다만),
      체언 '여덟', '삶·앎+과/도' 는 제외.
      ㄺ 은 용언 어간에서 ㄱ 앞이면 [ㄹ] (맑게→말께, 읽고→일꼬, 제11항 다만);
      체언(닭 흙 칡 삵)은 [ㄱ] (닭고기→닥꼬기, 흙과→흑꽈).
      어절 끝 어미 '-ㄹ게요, -ㄹ걸(요), -ㄹ거야, -ㄹ거예요, -ㄹ거에요, -ㄹ수록, -ㄹ지라도, -ㄹ지언정,
      -ㄹ진대, -ㄹ세라' 는 예외 없이 된소리가 나므로 철자 패턴으로 처리한다(할게요→할께요, 제27항 붙임).
      '-ㄹ게, -ㄹ지(요·도)' 는 '을'(먹을게→머글께) 이거나 ㄹ 어간 낱말 목록(알게·살게·만들게 …,
      부사형 '-게'·연결어미 '-지'와 철자가 같음)에 없을 때 된소리로 한다(할게→할께, 할지→할찌).
      목록에 있는 낱말과 '-ㄹ밖에'(조사 '밖에'와 철자가 같음)는 된소리형을 대안(guess)으로만 둔다.
   6. 비음화·유음화 (제18~20항):
      ㄹ 앞: 받침 ㅁ ㅇ → 뒤 ㄹ 이 ㄴ (심리→심니), 받침 ㄱ ㄷ ㅂ → 뒤 ㄹ 이 ㄴ 이 된 뒤
      받침도 비음화 (백로→백노→뱅노, 협력→혐녁), 받침 ㄴ → ㄹ (신라→실라).
      ㄴ ㅁ 앞: 받침 ㄱ ㄷ ㅂ(대표음 기준) → ㅇ ㄴ ㅁ (국물→궁물, 옷만→온만, 없는→엄는),
      받침 ㄹ + ㄴ → ㄹㄹ (칼날→칼랄).
      ㄹ→ㄴ 을 먼저 해야 받침 비음화가 따라오고, 비음화로 생긴 ㄴ 받침은 같은 쌍에서
      다시 유음화되지 않는다(독립→동닙).

7. 받침 대표음화 (제8~11항): 남은 받침을 7종성으로. ㄲ ㅋ ㄳ ㄺ→ㄱ, ㅅ ㅆ ㅈ ㅊ ㅌ ㅎ→ㄷ,
   ㅍ ㅄ ㄿ→ㅂ, ㄵ ㄶ→ㄴ, ㄼ ㄽ ㄾ ㅀ→ㄹ, ㄻ→ㅁ. 단 '밟-' 과 '넓죽-·넓둥-·넓적-' 의 ㄼ 은 ㅂ
   (넓적하다→[넙쩌카다], 넓적다리→[넙쩍따리]).
8. 'ㅈ ㅉ ㅊ' 뒤 j계 이중모음 → 단모음 (제5항 다만1: 가져→[가저], 다쳐→[다처]).
   표준 발음법은 '져 쪄 쳐'만 명시하지만 경구개음 뒤에서는 j 가 실현되지 않으므로
   ㅑ ㅒ ㅛ ㅠ ㅖ 도 같이 단모음화한다(쟤→[재]). 구개음화·거센소리되기로 생긴
   '쳐'(붙여→부쳐, 닫혀→다쳐)도 처리해야 하므로 맨 마지막에 한다.

어휘 예외 사전 (data/pron_lexicon.json)
-------------------------------------
형태소·어휘 정보가 있어야 정해지는 발음은 자주 쓰는 낱말을 사전으로 처리한다. 값은 '그 소리가 나도록
고쳐 쓴 철자'라서 위 규칙을 다시 거친다(서울역 → 서울녁 → [서울력], 출장 → 출짱). 어절 안 어디서든
찾되(해외출장), 끝 음절이 조사·접미사와 겹치는 낱말(성과·문자·안과)은 어절 처음에서만 찾는다(근성과, 질문자).
  - 제29항 'ㄴ' 첨가: 솜이불[솜니불], 꽃잎[꼰닙], 담요[담뇨], 색연필[생년필], 서울역[서울력] …
  - 제24항 용언 어간 ㄴ·ㅁ 뒤 경음화(어절 전체 일치): 안고[안꼬], 신다[신따], 감다[감따] …
  - 제26항 한자어 ㄹ 뒤 ㄷㅅㅈ: 출장[출짱], 발달[발딸], 갈등[갈뜽] …
  - 제28항 사이시옷 없는 합성어 경음화: 발바닥[발빠닥], 물고기[물꼬기], 줄넘기[줄럼끼] …
  - 제15항 실질형태소 앞 대표음화 후 연음: 겉옷[거돋], 맛없다[마덥따], 첫인상[처딘상] …
  - 제20항 다만(유음화 예외): 의견란[의견난], 생산량[생산냥], 상견례[상견녜] …
  - 그 밖: 싫증[실쯩]. 뜻에 따라 둘 다 표준인 낱말(신고·안다·감기·김밥·효과 …)은 원칙형을 쓰고
    다른 쪽은 아래 '발음 변이'의 대안으로만 둔다.

발음 변이 (pron_options) — 정상 발음을 오류로 판정하지 않기 위한 대안 목록
------------------------------------------------------------------------------
to_pron 은 원칙형 하나만 낸다. pron_options(text) 는 같은 문장에 대해 '표준으로 인정되거나 자연스럽게
이어 말하면 나는' 대안들을 자리(slot)별 선택지로 만들고, 파이프라인은 음성에 가장 그럴듯한 조합
(CTC log P 최대)을 목표로 고른다. 자리 종류:
  - allowed  (표준발음법 제5항 다만 2·4의 허용 발음): '예·례' 이외의 ㅖ→ㅔ(시계[시게]),
             단어 첫음절 이외의 '의'→ㅣ(주의[주이]), 조사 '의'→ㅔ(우리의[우리에]).
             제22항: ㅣ·ㅚ·ㅟ 뒤 어미 '어'→[여](되어[되여], 피어[피여]), '이오·아니오'→[이요·아니요].
  - natural  (모음 사이 활음): 받침 없는 'ㅣ' 뒤의 '에·애'는 이어 말하면 [예·얘]처럼 j 가 끼어든다
             (학생이에요[학쌩이예요], 우리에[우리예]). 표준 발음 규정의 조항은 아니지만 정상 발음의
             자연스러운 이음이라 오류로 보지 않는다.
  - connected(어절 사이, 이어 말한 경우): 제15항 대표음화 후 연음(몇 월[며둴], 꽃 위[꼬뒤]),
             제18항 붙임 비음화(밥 먹어요[밤머거요]), 장애음 뒤 경음화(밥 줘[밥쭤]), 제20항 유음화(일 년[일련]),
             제12항 붙임 격음화(못 해요[모태요]), 제27항 관형형 -(으)ㄹ 뒤 경음화(먹을 거예요[머글 꺼예요],
             할 수[할쑤]), 제29항 붙임2 ㄴ 첨가(할 일[할릴], 옷 입다[온닙따]).
  - lexical  (사전의 either_* 항목: 뜻에 따라 둘 다 표준).
  - guess    (사전에 없어 철자로 추정한 후보 — /api/target 에 '발음형을 확인해 주세요' 안내):
             한자어로 보이는 ㄹ+ㄷㅅㅈ(제26항), 합성어로 보이는 'ㄴ' 첨가(제29항),
             -력·-료·-량 등 앞 ㄴ+ㄹ(제20항 다만), ㄹ 어간 낱말의 '-ㄹ게·-ㄹ지'(알게/살게 …),
             '-ㄹ밖에'.

미처리 규칙 (테스트에 xfail 로 기록)
------------------------------------
- 사이시옷의 원칙 발음 (제30항): 냇가→[내까](허용 [낻까]); 현재는 허용 발음 [낻까].
  (옷고름[옫꼬름]처럼 사이시옷이 아닌 ㅅ 받침과 철자로 구별할 수 없다.)
- 사전에 없는 낱말의 제24·26·28·29항 — 위 guess 후보로만 다룬다.
- 자모 이름의 연음 (제16항): 디귿이→[디그시].
"""
from __future__ import annotations

import itertools
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

try:  # 패키지(server.g2p)로 import 될 때
    from .phones import compose, decompose
except ImportError:  # server/ 디렉터리를 sys.path 루트로 쓸 때
    from phones import compose, decompose  # type: ignore[no-redef]

__all__ = ["to_pron", "pron_options", "PronOptions", "Slot", "LEXICON_PATH"]

log = logging.getLogger(__name__)

LEXICON_PATH = Path(__file__).resolve().parent / "data" / "pron_lexicon.json"

# ── 자모 표 ───────────────────────────────────────────────
_TENSE = {"ㄱ": "ㄲ", "ㄷ": "ㄸ", "ㅂ": "ㅃ", "ㅅ": "ㅆ", "ㅈ": "ㅉ"}
_ASPIRATED = {"ㄱ": "ㅋ", "ㄷ": "ㅌ", "ㅈ": "ㅊ"}
_NASAL = {"ㄱ": "ㅇ", "ㄷ": "ㄴ", "ㅂ": "ㅁ"}

# 겹받침 → (앞 자음, 뒤 자음)
_CLUSTER = {
    "ㄳ": ("ㄱ", "ㅅ"), "ㄵ": ("ㄴ", "ㅈ"), "ㄶ": ("ㄴ", "ㅎ"), "ㄺ": ("ㄹ", "ㄱ"),
    "ㄻ": ("ㄹ", "ㅁ"), "ㄼ": ("ㄹ", "ㅂ"), "ㄽ": ("ㄹ", "ㅅ"), "ㄾ": ("ㄹ", "ㅌ"),
    "ㄿ": ("ㄹ", "ㅍ"), "ㅀ": ("ㄹ", "ㅎ"), "ㅄ": ("ㅂ", "ㅅ"),
}

# 받침 → 대표음(7종성)
_REP = {"": ""}
for _rep_sym, _members in {
    "ㄱ": "ㄱㄲㅋㄳㄺ",
    "ㄴ": "ㄴㄵㄶ",
    "ㄷ": "ㄷㅅㅆㅈㅊㅌㅎ",
    "ㄹ": "ㄹㄼㄽㄾㅀ",
    "ㅁ": "ㅁㄻ",
    "ㅂ": "ㅂㅍㅄㄿ",
    "ㅇ": "ㅇ",
}.items():
    for _m in _members:
        _REP[_m] = _rep_sym

# 뒤 평음을 무조건 된소리로 만드는 장애음 받침 (ㄺ ㄼ 은 따로 판단)
_OBSTRUENT = frozenset("ㄱㄲㅋㄳㄷㅅㅆㅈㅊㅌㅂㅍㄿㅄ")

# ㅎ 계열 받침 → ㅎ 을 뺀 나머지
_H_CODA = {"ㅎ": "", "ㄶ": "ㄴ", "ㅀ": "ㄹ"}

# 경구개 파찰음 뒤 j계 이중모음 → 단모음
_DEGLIDE = {"ㅑ": "ㅏ", "ㅒ": "ㅐ", "ㅕ": "ㅓ", "ㅖ": "ㅔ", "ㅛ": "ㅗ", "ㅠ": "ㅜ"}
_PALATAL_ONSET = frozenset("ㅈㅉㅊ")

# 'ㄴ' 첨가를 일으키는 뒤 모음 (제29항: 이·야·여·요·유)
_J_VOWELS = frozenset("ㅣㅑㅕㅛㅠ")

# ── 어휘 예외(철자로 판단 가능한 최소한) ─────────────────
_NOUN_RG = frozenset("닭흙칡삵")      # ㄺ 받침 체언: ㄱ 앞에서도 [ㄱ]
_NOUN_RM = frozenset("삶앎")          # ㄻ 받침 체언(명사형)
_NOUN_RB = frozenset("덟")            # ㄼ 받침 체언(여덟): 된소리되기 없음
# '-ㄹ' 받침 뒤에 어절 끝까지 이어지면 첫 자음이 된소리가 되는 어미 (제27항 붙임)
_RIEUL_TENSE_ENDINGS = frozenset({"게요", "걸", "걸요", "거야", "거예요", "거에요", "수록",
                                  "지라도", "지언정", "진대", "세라"})
# '-ㄹ게, -ㄹ지(요·도…)': 부사형 '-게'·연결어미 '-지'와 철자가 같다. 'ㄹ' 받침이 ㄹ 어간에 속하면
# (알게, 살지, 만들게) 된소리가 아니므로, 아래 어간 목록에 없을 때만 된소리로 한다(할게→할께, 먹을지→머글찌).
_RIEUL_TENSE_IF_NOT_STEM = frozenset({"게", "지", "지요", "지도", "지는", "지를"})
# ㄹ 어간 용언의 '어절 처음~ㄹ 받침 음절'. '갈(가다)·볼·줄·할·잘'처럼 미래형으로 더 자주 쓰이는 꼴은 넣지 않는다.
_RIEUL_STEMS = frozenset({
    "알", "살", "놀", "울", "팔", "열", "걸", "벌", "불", "밀", "들", "길", "멀", "달", "졸", "얼",
    "날", "빌", "끌", "물", "털", "썰", "몰", "풀", "말", "절", "만들", "힘들", "둥글", "어질",
    "거칠", "드물", "가늘", "흔들", "떠들", "시들", "이끌", "베풀", "부풀", "내밀", "어설",
})
# ㄹ 받침 뒤에서 어미(놀다·놀지·놀자·놀던·놀든…)나 조사(물도·말대로)일 수 있는 음절: 제26항 추정에서 뺀다
_RIEUL_ENDING_SYL = frozenset({"다", "지", "자", "더", "던", "도", "든", "죠", "대", "데", "듯"})
# 'ㄴ' 첨가 추정에서 뺄 뒤 말(조사·어미): 책이, 학생이에요, 먹여, 맛있다 …
_NINSERT_SKIP_EXACT = frozenset({"이", "여", "인", "임", "요"})
# 한자 접미 '-일(日)·-용(用)'은 대개 ㄴ 첨가가 없다(생일[생일], 식용[시굥], 휴일). ㄴ 첨가가 나는 고유어
# 합성어(밭일·집안일·부엌일)와 일부 '-용'(영업용)은 사전에 있다.
_NINSERT_SKIP_SYL = frozenset({"일", "용"})
_NINSERT_SKIP_PREFIX = ("이에", "이야", "이었", "이여", "이라", "이랑", "이면", "이며", "이지", "이죠", "이요",
                        "이다", "이고", "이나", "이니", "이네", "이든", "이어", "인가", "인데", "인지", "일까",
                        "일지", "입니", "이세", "이시", "있", "였", "여서", "여도", "여요", "여야", "요일")
# 제27항: 관형사형 -(으)ㄹ 뒤 경음화는 의존명사 등이 올 때 주로 나타난다(할 것을, 갈 데가, 할 바를, 할 수는,
# 할 적에, 갈 곳, 할 도리). ㄹ 받침 명사(시월 구일, 물 주세요)까지 대안을 만들면 된소리 오류를 놓치므로
# 이어지는 말이 이것으로 시작할 때만 대안을 만든다.
_ADNOMINAL_NEXT = ("거", "것", "게", "걸", "겁", "건", "수", "데", "때", "줄", "적", "바", "지", "듯", "곳",
                   "도리", "정도", "생각", "뻔", "만큼")
# 제20항 다만: 2음절 이상 어간 + ㄴ 받침 뒤 -란·-량·-력·-령·-례·-론·-료·-류 는 [ㄴㄴ]
_N_SUFFIX = frozenset({"란", "량", "력", "령", "례", "론", "료", "류"})
# 어절 끝 '의'가 조사가 아니라 명사의 일부인 낱말(→ 허용 발음은 [ㅣ]만, 조사 '의'의 [ㅔ]는 아님)
_UI_NOUNS = frozenset({
    "주의", "회의", "강의", "동의", "정의", "협의", "논의", "편의", "결의", "합의", "건의", "모의",
    "문의", "성의", "신의", "예의", "유의", "이의", "저의", "창의", "호의", "심의", "질의", "토의",
    "항의", "고의", "내의", "상의", "하의", "수의", "대의", "민의", "거의", "의의", "본의", "사의",
    "선의", "악의", "열의", "용의", "적의", "제의", "중의", "부의",
})

_NON_HANGUL = re.compile(r"[^가-힣]+")


def to_pron(text: str) -> str:
    """철자 한글 → 표준발음 한글(원칙형). 공백은 어절 경계로 유지, 한글 외 문자는 제거."""
    if not text:
        return ""
    return " ".join(_pron_words([_lex_scan(w)[0] for w in _words(text)]))


def _words(text: str) -> list[str]:
    return [w for w in _NON_HANGUL.split(text or "") if w]


# ── 어휘 사전 ─────────────────────────────────────────────
@lru_cache(maxsize=1)
def _lexicon() -> dict:
    try:
        raw = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # pragma: no cover - 데이터 파일 문제
        log.warning("발음 사전을 읽지 못해 규칙만 씁니다 (%s): %s", LEXICON_PATH, e)
        raw = {}

    def ok(k: str, v: str) -> bool:
        good = (isinstance(k, str) and isinstance(v, str) and len(k) == len(v) and k
                and all(decompose(c) is not None for c in k + v))
        if not good:
            log.warning("발음 사전 항목을 건너뜀: %r → %r (음절 수가 같은 한글이어야 함)", k, v)
        return bool(good)

    def fixed(name: str) -> dict[str, str]:
        return {k: v for k, v in (raw.get(name) or {}).items() if ok(k, v)}

    def either(name: str) -> dict[str, tuple[str, ...]]:
        out = {}
        for k, vs in (raw.get(name) or {}).items():
            alts = tuple(v for v in (vs if isinstance(vs, list) else [vs]) if ok(k, v))
            if alts:
                out[k] = alts
        return out

    lex = {"infix": fixed("infix"), "prefix": fixed("prefix"), "whole": fixed("whole"),
           "either_infix": either("either_infix"), "either_whole": either("either_whole")}
    keys = set(lex["infix"]) | set(lex["either_infix"]) | set(lex["prefix"])
    lex["infix_keys"] = sorted(keys, key=lambda s: (-len(s), s))
    return lex


def _lex_scan(word: str) -> tuple[str, list[tuple[int, str, tuple[str, ...]]], set[int]]:
    """어절 하나에 사전을 적용. (고친 철자, [(위치, 원래 부분, 대안들)], 사전이 덮은 음절 위치)."""
    lex = _lexicon()
    if word in lex["whole"]:
        return lex["whole"][word], [], set(range(len(word)))
    if word in lex["either_whole"]:
        return word, [(0, word, lex["either_whole"][word])], set(range(len(word)))
    out, either, covered = list(word), [], set()
    pos = 0
    while pos < len(word):
        for key in lex["infix_keys"]:
            if key in lex["prefix"] and pos > 0:
                continue                      # 어절 처음에서만(근성과 ≠ 성과)
            if word.startswith(key, pos):
                if key in lex["prefix"]:
                    out[pos:pos + len(key)] = list(lex["prefix"][key])
                elif key in lex["infix"]:
                    out[pos:pos + len(key)] = list(lex["infix"][key])
                else:
                    either.append((pos, key, lex["either_infix"][key]))
                covered.update(range(pos, pos + len(key)))
                pos += len(key)
                break
        else:
            pos += 1
    return "".join(out), either, covered


# ── 규칙 적용 ─────────────────────────────────────────────
def _rep(jong: str, cur: str, nxt: str) -> str:
    """받침의 대표음. cur/nxt 는 해당 음절과 다음 음절의 '철자'."""
    if jong == "ㄼ" and (cur == "밟" or (cur == "넓" and nxt in ("죽", "둥", "적"))):
        return "ㅂ"
    return _REP[jong]


def _palatal_vowel(nxt: str) -> bool:
    """구개음화를 일으키는 뒤 음절인가: 'ㅣ' 또는 '이+어' 축약형('여'·'였')."""
    _, v, k = decompose(nxt)
    return v == "ㅣ" or (v == "ㅕ" and k in ("", "ㅆ"))


def _eojeol(word: str) -> str:
    return _pron_words([word])[0]


def _pron_words(words: Sequence[str], joined: Sequence[bool] = ()) -> list[str]:
    """철자 어절들 → 어절별 발음형. joined[k] 가 참이면 k 번째와 k+1 번째 어절 사이에도
    규칙 1~6 을 적용한다(쉬지 않고 이어 말한 경우). 음절 수는 바뀌지 않는다."""
    syls = [[list(decompose(ch)) for ch in w] for w in words]  # [초성, 중성, 종성]

    def is_joined(k: int) -> bool:
        return k + 1 < len(words) and k < len(joined) and bool(joined[k])

    # 0. ㅢ: 철자상 자음 초성 뒤 → ㅣ
    for ws in syls:
        for s in ws:
            if s[1] == "ㅢ" and s[0] != "ㅇ":
                s[1] = "ㅣ"

    # 1~6. 인접 음절 쌍 (왼쪽부터; 이어 말한 어절 경계도 같은 순서로)
    for k, w in enumerate(words):
        ws = syls[k]
        for i in range(len(ws) - 1):
            _apply_pair(ws[i], ws[i + 1], w, i)
        if is_joined(k):
            _apply_pair(ws[-1], syls[k + 1][0], w + words[k + 1], len(w) - 1)

    # 7. 받침 대표음화
    for k, w in enumerate(words):
        for i, s in enumerate(syls[k]):
            nxt = w[i + 1] if i + 1 < len(w) else (words[k + 1][0] if is_joined(k) else "")
            s[2] = _rep(s[2], w[i], nxt)

    # 8. ㅈ ㅉ ㅊ + j계 이중모음 → 단모음
    for ws in syls:
        for s in ws:
            if s[0] in _PALATAL_ONSET and s[1] in _DEGLIDE:
                s[1] = _DEGLIDE[s[1]]

    return ["".join(compose(*s) for s in ws) for ws in syls]


def _apply_pair(a: list[str], b: list[str], word: str, i: int) -> None:
    """앞 음절 a 의 받침과 뒤 음절 b 의 초성에 규칙 1~6 을 순서대로 적용한다(제자리 수정)."""
    cur, nxt, rest = word[i], word[i + 1], word[i + 1:]
    k = a[2]
    if not k:
        return

    # 1. ㅎ 받침 (ㅎ ㄶ ㅀ)
    if k in _H_CODA:
        remain = _H_CODA[k]
        c = b[0]
        if c in _ASPIRATED:            # ㅎ+ㄱㄷㅈ → ㅋㅌㅊ
            b[0] = _ASPIRATED[c]
            a[2] = remain
        elif c == "ㅅ":                # ㅎ+ㅅ → ㅆ
            b[0] = "ㅆ"
            a[2] = remain
        elif c == "ㄴ":                # ㅎ+ㄴ → ㄴㄴ, ㄶ/ㅀ+ㄴ → ㅎ 탈락
            a[2] = remain or "ㄴ"
        elif c in ("ㅇ", "ㅎ"):        # ㅎ 탈락(모음 앞) / ㅎ+ㅎ → ㅎ 하나
            a[2] = remain
        else:                          # 그 밖의 자음 앞: ㅎ 은 대표음 ㄷ
            a[2] = remain or "ㄷ"
        k = a[2]
        if not k:
            return

    c = b[0]

    # 2. 거센소리되기 (받침 + ㅎ)
    if c == "ㅎ":
        pal = _palatal_vowel(nxt)
        if k in ("ㄱ", "ㄲ", "ㅋ", "ㄳ"):
            a[2], b[0] = "", "ㅋ"
        elif k == "ㄺ":
            # 용언 어간은 ㄹ 이 남고(밝히다→발키다), 체언은 ㄱ 으로 줄어든 뒤 격음화(닭하고→다카고)
            a[2], b[0] = ("" if cur in _NOUN_RG else "ㄹ"), "ㅋ"
        elif k in ("ㄷ", "ㅌ"):
            a[2], b[0] = "", ("ㅊ" if pal else "ㅌ")   # 닫히다→다치다, 맏형→마텽
        elif k in ("ㅅ", "ㅆ", "ㅊ"):
            a[2], b[0] = "", "ㅌ"                       # 못하다→모타다, 꽃하고→꼬타고
        elif k == "ㅈ":
            # 피·사동 '-히-'(히·혀)와 만나면 ㅊ(꽂히다→꼬치다, 젖혀→저처),
            # 그 밖에는 ㄷ 으로 줄어든 뒤 ㅌ(낮하고→나타고, 제12항 붙임2)
            a[2], b[0] = "", ("ㅊ" if decompose(nxt)[1] in ("ㅣ", "ㅕ") else "ㅌ")
        elif k == "ㄵ":
            a[2], b[0] = "ㄴ", "ㅊ"                     # 앉히다→안치다
        elif k == "ㄾ":
            a[2], b[0] = "ㄹ", ("ㅊ" if pal else "ㅌ")
        elif k in ("ㅂ", "ㅍ", "ㅄ"):
            a[2], b[0] = "", "ㅍ"
        elif k in ("ㄼ", "ㄿ"):
            a[2], b[0] = "ㄹ", "ㅍ"                     # 넓히다→널피다, 밟히다→발피다
        # 공명음 받침(ㄴ ㄹ ㅁ ㅇ ㄻ ㄽ) 뒤 ㅎ 은 그대로 발음한다(전화, 감사합니다).
        return

    # 3. 구개음화 (ㄷ ㅌ ㄾ + 이)
    if c == "ㅇ" and k in ("ㄷ", "ㅌ", "ㄾ") and _palatal_vowel(nxt):
        if k == "ㄷ":
            a[2], b[0] = "", "ㅈ"
        elif k == "ㅌ":
            a[2], b[0] = "", "ㅊ"
        else:
            a[2], b[0] = "ㄹ", "ㅊ"
        return

    # 4. 연음
    if c == "ㅇ":
        if k == "ㅇ":
            return
        if k in _CLUSTER:
            first, second = _CLUSTER[k]
            a[2], b[0] = first, ("ㅆ" if second == "ㅅ" else second)
        else:
            a[2], b[0] = "", k
        return

    # 5. 된소리되기
    if c in _TENSE:
        if _tenses(k, c, cur, nxt, rest, word[:i + 1]):
            b[0] = _TENSE[c]
        if k == "ㄺ" and c == "ㄱ" and cur not in _NOUN_RG:
            a[2] = "ㄹ"                                 # 맑게→말께, 읽고→일꼬
        return

    # 6. 비음화·유음화
    if c in ("ㄴ", "ㅁ", "ㄹ"):
        r = _rep(k, cur, nxt)
        if c == "ㄹ":
            if r in ("ㅁ", "ㅇ"):
                b[0] = "ㄴ"                             # 심리→심니, 종로→종노
            elif r in _NASAL:
                a[2], b[0] = _NASAL[r], "ㄴ"            # 백로→뱅노, 협력→혐녁
            elif r == "ㄴ":
                a[2] = "ㄹ"                             # 신라→실라
        elif r in _NASAL:
            a[2] = _NASAL[r]                            # 국물→궁물, 옷만→온만
        elif r == "ㄹ" and c == "ㄴ":
            b[0] = "ㄹ"                                 # 칼날→칼랄, 뚫는→뚤른


def _tenses(k: str, c: str, cur: str, nxt: str, rest: str, stem: str = "") -> bool:
    """받침 k 뒤의 평음 초성 c 가 된소리가 되는가. stem = 어절 처음부터 받침 음절까지의 철자."""
    if k in _OBSTRUENT or k == "ㄺ":
        return True
    if k == "ㄼ":
        if _rep(k, cur, nxt) == "ㅂ":                   # 밟다→밥따, 넓죽→넙쭉
            return True
        return c != "ㅂ" and cur not in _NOUN_RB        # 넓다→널따, 여덟도→여덜도
    if k in ("ㄵ", "ㄾ"):
        return c != "ㅂ"                                # 앉다→안따, 핥다→할따
    if k == "ㄻ":
        nc, nv, _nk = decompose(nxt)
        if c == "ㅂ" or (nc == "ㄱ" and nv in ("ㅣ", "ㅕ")):
            return False                                # 피·사동 '-기-'와 그 활용: 옮기다→옴기다, 옮겨→옴겨, 옮긴→옴긴
        if cur in _NOUN_RM and (rest.startswith("과") or rest in ("도", "조차")):
            return False                                # 삶과→삼과
        return True                                     # 젊다→점따, 삶다→삼따
    if k == "ㄹ":
        if rest in _RIEUL_TENSE_ENDINGS:                # 할게요→할께요, 할지라도→할찌라도
            return True
        if rest in _RIEUL_TENSE_IF_NOT_STEM:            # 할게→할께, 먹을지→머글찌 / 알게→알게
            return cur == "을" or stem not in _RIEUL_STEMS
    return False


# ── 발음 변이 (pron_options) ──────────────────────────────
@dataclass(frozen=True)
class Slot:
    """대안이 있는 자리 하나. options[0] 이 원칙형(to_pron 결과를 만드는 선택).

    kind : allowed(허용 발음) | natural(모음 사이 활음) | connected(어절 이어 말하기) | lexical(사전: 둘 다 표준)
           | guess(철자로 추정)
    scope: ("word", 어절, 음절 위치)  — options 는 그 자리부터 바꿔 쓸 철자(길이 같음)
           ("boundary", k)          — k 번째와 k+1 번째 어절 사이; options 는 pause|join|link|ninsert|tense
           ("syl", 어절, 음절 위치, 원래 모음) — 발음형 음절의 모음; options 는 None(그대로)|모음 자모.
                                         발음형의 그 자리 모음이 '원래 모음'일 때만 바꾼다.
    """
    kind: str
    scope: tuple
    options: tuple

    @property
    def n(self) -> int:
        return len(self.options)


def _has_final(s: str) -> bool:
    for ch in reversed(s):
        d = decompose(ch)
        if d is not None:
            return d[2] != ""
    return False


def _josa(s: str, pair: str) -> str:
    a, b = pair.split("/")
    if pair == "으로/로":
        last = next((decompose(ch) for ch in reversed(s) if decompose(ch) is not None), None)
        return a if (last and last[2] and last[2] != "ㄹ") else b
    return a if _has_final(s) else b


@dataclass
class PronOptions:
    """text 의 원칙 발음과 자리별 대안. render(choice) 로 임의 조합의 발음형을 만든다."""
    text: str
    orth: list[str]           # 원래 철자 어절
    base: list[str]           # 사전(고정 항목)을 적용한 철자 어절
    slots: list[Slot]
    canonical: str

    @property
    def zero(self) -> tuple[int, ...]:
        return (0,) * len(self.slots)

    def n_combos(self) -> int:
        n = 1
        for s in self.slots:
            n *= s.n
        return n

    def combos(self, limit: int = 64) -> list[tuple[int, ...]] | None:
        """모든 조합(원칙형 먼저). limit 를 넘으면 None."""
        if self.n_combos() > limit:
            return None
        return list(itertools.product(*[range(s.n) for s in self.slots]))

    def single_changes(self, base: Sequence[int] | None = None) -> list[tuple[int, ...]]:
        """base 에서 한 자리만 바꾼 선택들."""
        base = tuple(base) if base is not None else self.zero
        out = []
        for si, s in enumerate(self.slots):
            for c in range(s.n):
                if c != base[si]:
                    out.append(base[:si] + (c,) + base[si + 1:])
        return out

    def word_prons(self, choice: Sequence[int] | None = None) -> list[str]:
        choice = tuple(choice) if choice is not None else self.zero
        words = list(self.base)
        joined = [False] * max(0, len(words) - 1)
        for s, c in zip(self.slots, choice):
            if c and s.scope[0] == "word":
                _, w, pos = s.scope
                rep = s.options[c]
                words[w] = words[w][:pos] + rep + words[w][pos + len(rep):]
        for s, c in zip(self.slots, choice):
            if not c or s.scope[0] != "boundary":
                continue
            k = s.scope[1]
            mode = s.options[c]
            a_cho, a_jung, a_jong = decompose(words[k][-1])
            b_cho, b_jung, b_jong = decompose(words[k + 1][0])
            if mode == "link":            # 제15항: 대표음으로 바꾼 뒤 연음
                words[k] = words[k][:-1] + compose(a_cho, a_jung, _rep(a_jong, words[k][-1], ""))
            elif mode == "ninsert":       # 제29항 붙임2: ㄴ 첨가
                words[k + 1] = compose("ㄴ", b_jung, b_jong) + words[k + 1][1:]
            elif mode == "tense" and b_cho in _TENSE:   # 제27항: 관형형 -(으)ㄹ 뒤 경음화
                words[k + 1] = compose(_TENSE[b_cho], b_jung, b_jong) + words[k + 1][1:]
            joined[k] = mode in ("join", "link", "ninsert")
        prons = _pron_words(words, joined)
        for s, c in zip(self.slots, choice):
            if c and s.scope[0] == "syl":
                _, w, j, expect = s.scope
                cho, jung, jong = decompose(prons[w][j])
                if jung == expect:
                    prons[w] = prons[w][:j] + compose(cho, s.options[c], jong) + prons[w][j + 1:]
        return prons

    def render(self, choice: Sequence[int] | None = None) -> str:
        return " ".join(self.word_prons(choice))

    def find(self, pron: str, limit: int = 512) -> tuple[int, ...] | None:
        """pron(공백 무시하지 않음)을 만드는 선택. 못 찾으면 None."""
        pron = " ".join((pron or "").split())
        if pron == self.canonical:
            return self.zero
        cands = self.combos(limit)
        if cands is None:
            cands = self.single_changes()
        for ch in cands:
            if self.render(ch) == pron:
                return ch
        return None

    def describe(self, choice: Sequence[int], base: Sequence[int] | None = None) -> list[str]:
        """base(기본: 원칙형)와 다른 자리마다 '어떻게 판정했는지' 한국어 설명 한 문장."""
        choice = tuple(choice)
        base = tuple(base) if base is not None else self.zero
        p0, p1 = self.word_prons(base), self.word_prons(choice)
        out: list[str] = []
        for si, (s, c, c0) in enumerate(zip(self.slots, choice, base)):
            if c == c0:
                continue
            if s.scope[0] == "boundary":
                k = s.scope[1]
                src, got = f"{self.orth[k]} {self.orth[k + 1]}", p1[k] + p1[k + 1]
                if c == 0:
                    got = f"{p1[k]} {p1[k + 1]}"
                    msg = (f"'{src}'{_josa(src, '을/를')} 끊어 말한 것으로 보고 [{got}]{_josa(got, '으로/로')} "
                           f"판정했어요.")
                else:
                    msg = (f"'{src}'{_josa(src, '을/를')} 이어 말해 [{got}]{_josa(got, '으로/로')} "
                           f"소리 낸 것으로 보고 판정했어요.")
                out.append(msg)
                continue
            w = s.scope[1]
            # 이 자리만 바꾼 발음형으로 설명한다(어절 사이 이어 말하기로 바뀐 첫소리가 '허용 발음' 문장에 섞이지 않게:
            # '만약 박근혜'를 이어 말한 [마냑빡끈헤] → "'박근혜'를 [박끈헤]로 발음해도 표준", [빡끈헤] 아님)
            src = self.orth[w]
            got = self.word_prons(base[:si] + (c,) + base[si + 1:])[w]
            if got == p0[w]:
                continue
            if c == 0:
                msg = f"'{src}'{_josa(src, '을/를')} 원칙 발음 [{got}]{_josa(got, '으로/로')} 판정했어요."
            elif s.kind == "allowed":
                msg = f"'{src}'{_josa(src, '을/를')} [{got}]{_josa(got, '으로/로')} 발음해도 표준이에요(허용 발음)."
            elif s.kind == "natural":
                msg = f"'{src}'{_josa(src, '을/를')} [{got}]{_josa(got, '으로/로')} 이어 소리 낸 것으로 보고 판정했어요(ㅣ 뒤 모음 이음)."
            elif s.kind == "lexical":
                msg = f"'{src}'{_josa(src, '은/는')} [{got}]{_josa(got, '으로/로')}도 소리 내요(뜻에 따라 둘 다 표준)."
            else:
                msg = f"'{src}'{_josa(src, '을/를')} [{got}]{_josa(got, '으로/로')} 소리 낸 것으로 보고 판정했어요."
            if msg not in out:
                out.append(msg)
        return out

    def notes(self) -> list[str]:
        """사전에 없어 철자로 추정한 자리(guess)에 대한 '발음형을 확인해 주세요' 안내."""
        out: list[str] = []
        p0 = self.word_prons()
        for si, s in enumerate(self.slots):
            if s.kind != "guess":
                continue
            w = s.scope[1]
            for c in range(1, s.n):
                ch = self.zero[:si] + (c,) + self.zero[si + 1:]
                got = self.word_prons(ch)[w]
                if got == p0[w]:
                    continue
                msg = (f"'{self.orth[w]}'{_josa(self.orth[w], '은/는')} [{p0[w]}] 대신 [{got}]{_josa(got, '으로/로')} "
                       f"소리 날 수도 있어요. 발음형을 확인해 주세요.")
                if msg not in out:
                    out.append(msg)
        return out

    def alternatives(self, limit: int = 12) -> list[str]:
        """한 자리만 바꾼 대안 발음형들(원칙형 제외, 중복 제거)."""
        out: list[str] = []
        for ch in self.single_changes():
            p = self.render(ch)
            if p != self.canonical and p not in out:
                out.append(p)
                if len(out) >= limit:
                    break
        return out


def _ui_noun(word: str) -> bool:
    return word in _UI_NOUNS or (len(word) >= 3 and word[-2:] in _UI_NOUNS and word[-2:] != "의의")


_HIATUS_J = {"ㅓ": "ㅕ", "ㅗ": "ㅛ", "ㅔ": "ㅖ", "ㅐ": "ㅒ"}


def _allowed_slots(orig: str, w: int) -> list[Slot]:
    """허용 발음(제5항 다만 2·4, 제22항)과 모음 사이 활음 자리. 철자(orig) 기준으로 찾는다."""
    out = []
    for j, ch in enumerate(orig):
        cho, jung, jong = decompose(ch)
        if jung == "ㅖ" and cho not in ("ㅇ", "ㄹ") and cho not in _PALATAL_ONSET:
            out.append(Slot("allowed", ("syl", w, j, "ㅖ"), (None, "ㅔ")))        # 시계[시게], 혜택[헤택]
        elif ch == "의" and j >= 1:
            if j == len(orig) - 1 and not _ui_noun(orig):
                _pc, pv, pk = decompose(orig[j - 1])
                glide = ("ㅖ",) if (pv == "ㅣ" and not pk) else ()          # 우리의[우리에] → 이어 말하면 [우리예]
                out.append(Slot("allowed", ("syl", w, j, "ㅢ"), (None, "ㅔ", "ㅣ") + glide))  # 조사 '의': 우리의[우리에]
            else:
                out.append(Slot("allowed", ("syl", w, j, "ㅢ"), (None, "ㅣ")))       # 주의[주이], 회의실[회이실]
        elif j >= 1 and cho == "ㅇ" and jung in _HIATUS_J:
            _pc, pv, pk = decompose(orig[j - 1])
            if pk:
                continue
            if jung == "ㅓ" and pv in ("ㅣ", "ㅚ", "ㅟ"):
                out.append(Slot("allowed", ("syl", w, j, jung), (None, "ㅕ")))      # 제22항: 되어[되여], 피어[피여]
            elif jung == "ㅗ" and orig[j - 1] in ("이", "니") and ch == "오" and j == len(orig) - 1:
                out.append(Slot("allowed", ("syl", w, j, jung), (None, "ㅛ")))      # 제22항 붙임: 이오[이요], 아니오[아니요]
            elif jung in ("ㅔ", "ㅐ") and pv == "ㅣ":
                out.append(Slot("natural", ("syl", w, j, jung), (None, _HIATUS_J[jung])))  # 이에요[이예요]
    return out


def _ninsert_ok(word: str, j: int) -> bool:
    rest = word[j:]
    return not (rest in _NINSERT_SKIP_EXACT or rest.startswith(_NINSERT_SKIP_PREFIX)
                or word[j] in _NINSERT_SKIP_SYL)


def _guess_slots(word: str, w: int, covered: set[int]) -> list[Slot]:
    """사전에 없는 낱말에서 철자로 추정한 대안 자리(guess). 원칙형은 그대로 두고 대안만 만든다."""
    out = []
    for j in range(1, len(word)):
        if j in covered or (j - 1) in covered:
            continue
        _pc, _pv, pk = decompose(word[j - 1])
        c, v, k = decompose(word[j])
        rest = word[j:]
        alt = None
        if pk == "ㄹ" and c in ("ㄷ", "ㅅ", "ㅈ") and word[j] not in _RIEUL_ENDING_SYL:
            alt = compose(_TENSE[c], v, k)                       # 제26항: 한자어 ㄹ 뒤 ㄷㅅㅈ (발달[발딸])
        elif (pk and pk not in _H_CODA and c == "ㅇ" and v in _J_VOWELS and _ninsert_ok(word, j)):
            alt = compose("ㄴ", v, k)                            # 제29항: ㄴ 첨가 (솜이불[솜니불])
        elif pk == "ㄴ" and j >= 2 and word[j] in _N_SUFFIX:
            alt = compose("ㄴ", v, k)                            # 제20항 다만: 판단력[판단녁]
        elif (pk == "ㄹ" and c in ("ㄱ", "ㅈ") and rest in _RIEUL_TENSE_IF_NOT_STEM
              and word[:j] in _RIEUL_STEMS):
            # 살게[살께](사다+-ㄹ게) / [살게](살다+-게): 뜻에 따라 둘 다 표준
            out.append(Slot("lexical", ("word", w, j), (word[j], compose(_TENSE[c], v, k))))
            continue
        elif pk == "ㄹ" and rest.startswith("밖에"):
            # 어미 '-ㄹ밖에'[-ㄹ빠께](갈밖에) / 조사 '밖에'[바께](물밖에): 뜻에 따라 둘 다 표준
            out.append(Slot("lexical", ("word", w, j), (word[j], compose("ㅃ", v, k))))
            continue
        if alt and alt != word[j]:
            out.append(Slot("guess", ("word", w, j), (word[j], alt)))
    return out


def _boundary_modes(a: str, b: str) -> tuple[str, ...]:
    """어절 a 와 b 를 쉬지 않고 이어 말할 때 가능한 변화(원칙형 'pause' 제외)."""
    _ac, _av, ka = decompose(a[-1])
    cb, vb, _kb = decompose(b[0])
    if not ka or ka in _H_CODA:
        return ()
    r = _rep(ka, a[-1], "")
    if cb == "ㅇ":
        if ka == "ㅇ":
            return ()
        if vb in _J_VOWELS:                       # 할 일[할릴], 옷 입다[온닙따] / 밥 있어요[바비써요]
            return ("ninsert",) if r == "ㄷ" else ("ninsert", "link")   # ㄷ+이 는 구개음화가 되므로 연음 대안 없음
        return ("link",)                          # 몇 월[며둴], 꽃 위[꼬뒤]
    if r in ("ㄱ", "ㄷ", "ㅂ") and (cb in ("ㄴ", "ㅁ", "ㅎ") or cb in _TENSE):
        return ("join",)                          # 밥 먹어요[밤머거요], 못 해요[모태요], 밥 줘[밥쭤]
    if (r == "ㄹ" and cb == "ㄴ") or (r == "ㄴ" and cb == "ㄹ"):
        # 유음화(제20항)가 어절 사이에서도 일어남: 할 나이[할라이], 일 년[일련], 한 라인[할라인].
        # 사람 낭독 실측: 앞 어절 끝 ㄹ 뒤 어절 첫 ㄴ 을 ㄹ 로 들은 오탐 29건(보정+검증) — 이어 말하면 정상.
        return ("join",)
    if ka == "ㄹ" and cb in _TENSE and a[-1] != "를" and b.startswith(_ADNOMINAL_NEXT):
        return ("tense",)                         # 먹을 거예요[머글 꺼예요], 할 수[할 쑤]
    return ()


def pron_options(text: str) -> PronOptions:
    """원칙형(to_pron 과 같음) + 자리별 대안. 한글이 없으면 slots=[] canonical=""."""
    orth = _words(text)
    base: list[str] = []
    slots: list[Slot] = []
    for w, word in enumerate(orth):
        fixed, either, covered = _lex_scan(word)
        base.append(fixed)
        for pos, key, alts in either:
            slots.append(Slot("lexical", ("word", w, pos), (key,) + tuple(alts)))
        slots += _guess_slots(fixed, w, covered)
        slots += _allowed_slots(word, w)
    for k in range(len(base) - 1):
        modes = _boundary_modes(base[k], base[k + 1])
        if modes:
            slots.append(Slot("connected", ("boundary", k), ("pause",) + modes))
    order = {"word": 0, "syl": 1, "boundary": 2}
    slots.sort(key=lambda s: (s.scope[1], order[s.scope[0]], s.scope[2] if s.scope[0] != "boundary" else 99))
    canonical = " ".join(_pron_words(base))
    return PronOptions(text=text, orth=orth, base=base, slots=slots, canonical=canonical)
