"""g2p.to_pron / pron_options 테스트.

기대값은 '표준 발음법'(국립국어원)의 조항별 예시를 장음 표시 없이 옮긴 것이 대부분이다.
어휘 정보가 필요한 규칙은 data/pron_lexicon.json 사전으로 처리하고(LEXICON), 철자만으로 정할 수 없는
규칙은 xfail 로 기록한다. 허용 발음·어절 이어 말하기는 pron_options 의 대안으로 검사한다.
"""
from __future__ import annotations

import random

import pytest

from server.g2p import pron_options, to_pron
from server.phones import CODA_PHONE, decompose, pron_to_phones


def _pairs(spec: str) -> list[tuple[str, str]]:
    """'국물→궁물, 신라→실라' → [("국물", "궁물"), ("신라", "실라")]"""
    out = []
    for item in spec.split(","):
        item = item.strip()
        if item:
            src, dst = item.split("→")
            out.append((src.strip(), dst.strip()))
    return out


# ── 과제에서 반드시 통과해야 한다고 지정한 예 ─────────────
REQUIRED = _pairs("""
국물→궁물, 밥 먹었어요→밥 머거써요, 고맙습니다→고맙씀니다, 같이→가치, 굳이→구지,
밭이→바치, 좋아요→조아요, 좋다→조타, 놓고→노코, 많다→만타, 많아→마나, 싫어→시러,
놓는→논는, 신라→실라, 난로→날로, 칼날→칼랄, 닭→닥, 닭이→달기, 흙→흑, 삶→삼,
앉아→안자, 앉다→안따, 읽다→익따, 넓다→널따, 밟다→밥따, 값이→갑씨, 없어요→업써요,
몫→목, 학교→학꾜, 먹다→먹따, 국밥→국빱, 식당→식땅, 숙제→숙쩨, 깍두기→깍뚜기,
입니다→임니다, 국민→궁민, 받는→반는, 옷만→온만, 심리→심니, 종로→종노, 백로→뱅노,
협력→혐녁, 희망→히망, 희다→히다, 무늬→무니, 의자→의자, 꽃→꼳, 꽃이→꼬치, 옷→옫,
옷이→오시, 부엌→부억, 잎→입, 앞으로→아프로, 맛있다→마싣따, 안녕하세요→안녕하세요,
감사합니다→감사함니다, 축하해요→추카해요, 괜찮아요→괜차나요, 읽어요→일거요, 밝아요→발가요
""")

# ── 규칙별 추가 예 ────────────────────────────────────────
RULE_CASES: dict[str, list[tuple[str, str]]] = {
    # 제9항 받침 대표음화
    "대표음화": _pairs("""
        닦다→닥따, 키읔→키윽, 키읔과→키윽꽈, 웃다→욷따, 있다→읻따, 젖→젇, 빚다→빋따,
        쫓다→쫃따, 솥→솓, 뱉다→밷따, 앞→압, 덮다→덥따, 끝→끋, 무릎→무릅, 히읗→히읃, 몇→멷
    """),
    # 제10·11항 겹받침
    "겹받침": _pairs("""
        넋→넉, 넋과→넉꽈, 여덟→여덜, 외곬→외골, 핥다→할따, 값→갑, 없다→업따,
        밟소→밥쏘, 밟지→밥찌, 밟게→밥께, 밟고→밥꼬, 넓죽하다→넙쭈카다, 넓둥글다→넙뚱글다,
        흙과→흑꽈, 맑다→막따, 늙지→늑찌, 젊다→점따, 읊고→읍꼬, 읊다→읍따,
        맑게→말께, 묽고→물꼬, 얽거나→얼꺼나, 읽고→일꼬, 닭고기→닥꼬기, 칡범→칙뻠,
        짧다→짤따, 짧게→짤께
    """),
    # 제12항 ㅎ
    "ㅎ받침": _pairs("""
        좋던→조턴, 쌓지→싸치, 많고→만코, 않던→안턴, 닳지→달치, 싫다→실타, 끓고→끌코,
        닿소→다쏘, 많소→만쏘, 싫소→실쏘, 놓습니다→노씀니다, 좋습니다→조씀니다,
        괜찮습니다→괜찬씀니다, 그렇습니다→그러씀니다,
        쌓네→싼네, 좋네→존네, 않네→안네, 않는→안는, 뚫네→뚤레, 뚫는→뚤른,
        낳은→나은, 놓아→노아, 쌓이다→싸이다, 않은→아는, 닳아→다라, 싫어도→시러도,
        끓이다→끄리다, 잃어버렸어요→이러버려써요, 좋아해요→조아해요
    """),
    # 제12항 붙임 거센소리되기
    "격음화": _pairs("""
        각하→가카, 먹히다→머키다, 밝히다→발키다, 맏형→마텽, 좁히다→조피다, 넓히다→널피다,
        꽂히다→꼬치다, 앉히다→안치다, 밟히다→발피다, 못하다→모타다, 깨끗하다→깨끄타다,
        따뜻해요→따뜨태요, 생각해요→생가캐요, 입학→이팍, 급히→그피, 역할→여칼,
        백화점→배콰점, 꽃향기→꼬턍기, 밥하고→바파고, 행복해요→행보캐요, 복잡해요→복짜패요,
        꽃하고→꼬타고, 낮하고→나타고, 젖혀→저처, 꽂혔다→꼬첟따, 닭하고→다카고, 읽히다→일키다
    """),
    # 제13·14항 연음
    "연음": _pairs("""
        깎아→까까, 있어→이써, 낮이→나지, 꽂아→꼬자, 꽃을→꼬츨, 쫓아→쪼차, 밭에→바테,
        덮이다→더피다, 끝을→끄틀, 무릎이→무르피, 부엌에서→부어케서, 몫이→목씨,
        넋이→넉씨, 닭을→달글, 젊어→절머, 곬이→골씨, 핥아→할타, 읊어→을퍼, 값을→갑쓸,
        없어→업써, 밟아→발바, 넓어요→널버요, 짧아요→짤바요, 앉으세요→안즈세요,
        있어요→이써요, 재미있어요→재미이써요, 맛있어요→마시써요, 읽었어요→일거써요,
        없었어요→업써써요, 강아지→강아지, 고양이→고양이
    """),
    # 제17항 구개음화
    "구개음화": _pairs("""
        곧이듣다→고지듣따, 미닫이→미다지, 땀받이→땀바지, 벼훑이→벼훌치, 끝이→끄치,
        굳히다→구치다, 닫히다→다치다, 묻히다→무치다, 붙이다→부치다, 해돋이→해도지,
        붙여요→부처요, 닫혀→다처, 굳혔다→구첟따, 같아→가타, 밭을→바틀
    """),
    # 제23~25항 된소리되기
    "경음화": _pairs("""
        깎다→깍따, 넋받이→넉빠지, 삯돈→삭똔, 닭장→닥짱, 뻗대다→뻗때다, 옷고름→옫꼬름,
        있던→읻떤, 꽂고→꼳꼬, 꽃다발→꼳따발, 낯설다→낟썰다, 밭갈이→받까리, 솥전→솓쩐,
        곱돌→곱똘, 덮개→덥깨, 옆집→엽찝, 읊조리다→읍쪼리다, 값지다→갑찌다,
        학생→학쌩, 책상→책쌍, 박수→박쑤, 입구→입꾸, 옷걸이→옫꺼리, 꽃병→꼳뼝,
        반갑습니다→반갑씀니다, 앉고→안꼬, 얹다→언따, 닮고→담꼬, 젊지→점찌,
        삶다→삼따, 삶과→삼과, 안기다→안기다, 감기다→감기다, 굶기다→굼기다,
        옮기다→옴기다, 넓게→널께, 훑소→훌쏘, 떫지→떨찌, 여덟도→여덜도
    """),
    # 제27항 붙임: 어절 끝 '-(으)ㄹ' 어미 (ㄹ 어간 부사형 '-게'·연결어미 '-지'는 제외)
    "ㄹ어미": _pairs("""
        할게요→할께요, 먹을게요→머글께요, 갈걸→갈껄, 할거야→할꺼야, 갈수록→갈쑤록,
        알게→알게, 먹을게→머글께, 할게→할께, 갈게→갈께, 할지→할찌, 먹을지→머글찌, 갈지도→갈찌도,
        할지라도→할찌라도, 할지언정→할찌언정, 할진대→할찐대, 할세라→할쎄라, 알지→알지, 길게→길게,
        만들게→만들게, 물밖에→물바께
    """),
    # 제24항 다만: ㄻ 용언의 피·사동 '-기-'와 그 활용(겨·겼·긴·길·김)은 된소리가 아니다
    "ㄻ사동": _pairs("""
        옮겨→옴겨, 옮겨요→옴겨요, 옮겼다→옴겯따, 옮긴→옴긴, 옮길→옴길, 옮김→옴김, 굶겨요→굼겨요,
        삶겼다→삼겯따, 젊게→점께, 옮기다→옴기다
    """),
    # 어휘 사전(data/pron_lexicon.json)
    "사전": _pairs("""
        솜이불→솜니불, 꽃잎→꼰닙, 홑이불→혼니불, 깻잎→깬닙, 나뭇잎→나문닙, 담요→담뇨, 색연필→생년필,
        식용유→시굥뉴, 서울역→서울력, 휘발유→휘발류, 한여름→한녀름, 물약→물략, 늑막염→능망념, 뒷일→뒨닐,
        안고→안꼬, 신다→신따, 감다→감따, 넘고→넘꼬, 껴안다→껴안따,
        발달→발딸, 갈등→갈뜽, 출장→출짱, 열정→열쩡, 발전→발쩐, 물질→물찔, 일시→일씨, 절도→절또,
        문고리→문꼬리, 줄넘기→줄럼끼, 발바닥→발빠닥, 물고기→물꼬기, 눈동자→눈똥자, 손등→손뜽, 길가→길까,
        아침밥→아침빱, 비빔밥→비빔빱, 볶음밥→보끔밥,
        겉옷→거돋, 맛없다→마덥따, 첫인상→처딘상, 값어치→가버치,
        의견란→의견난, 생산량→생산냥, 상견례→상견녜, 입원료→이붠뇨, 결단력→결딴녁, 공권력→공꿘녁,
        싫증→실쯩, 넓적하다→넙쩌카다, 넓적다리→넙쩍따리, 해외출장→해외출짱, 서울역에서→서울려게서,
        성과를→성꽈를, 근성과→근성과, 질문자→질문자, 문자를→문짜를, 한자리에→한자리에, 불안과→부란과,
        특별도→특뼐도, 별도로→별또로
    """),
    # 제18항 비음화
    "비음화": _pairs("""
        먹는→멍는, 깎는→깡는, 키읔만→키응만, 몫몫이→몽목씨, 긁는→긍는, 흙만→흥만,
        닫는→단는, 짓는→진는, 옷맵시→온맵씨, 있는→인는, 맞는→만는, 젖멍울→전멍울,
        쫓는→쫀는, 꽃망울→꼰망울, 붙는→분는, 잡는→잠는, 밥물→밤물, 앞마당→암마당,
        밟는→밤는, 읊는→음는, 없는→엄는, 값매다→감매다, 읽는→잉는, 박물관→방물관
    """),
    # 제19항 ㄹ의 비음화
    "ㄹ비음화": _pairs("""
        담력→담녁, 침략→침냑, 강릉→강능, 항로→항노, 대통령→대통녕,
        막론→망논, 석류→성뉴, 법리→범니, 십리→심니, 목련→몽년, 독립문→동님문
    """),
    # 제20항 유음화
    "유음화": _pairs("""
        천리→철리, 광한루→광할루, 대관령→대괄령, 물난리→물랄리, 할는지→할른지,
        닳는→달른, 핥네→할레, 선릉→설릉
    """),
    # 제5항 모음
    "모음": _pairs("""
        가져→가저, 가져요→가저요, 다쳐요→다처요, 쪄요→쩌요, 쟤→재, 그렇죠→그러초,
        늴리리→닐리리, 닁큼→닝큼, 띄어쓰기→띠어쓰기, 씌어→씨어, 틔어→티어,
        희어→히어, 희떱다→히떱따, 유희→유히, 흰색→힌색,
        의사→의사, 주의→주의, 회의→회의, 협의→혀븨, 편의점→펴늬점,
        시계→시계, 계시다→계시다, 예절→예절
    """),
    # 문장·일상 표현
    "문장": _pairs("""
        생일 축하합니다→생일 추카함니다, 잘 먹겠습니다→잘 먹껟씀니다,
        꽃이 피었어요→꼬치 피어써요, 미안합니다→미안함니다, 사랑해요→사랑해요,
        고마워요→고마워요, 전화→전화, 영화관→영화관, 결혼→결혼
    """),
}

ALL_CASES = REQUIRED + [c for cases in RULE_CASES.values() for c in cases]

# ── 미처리 규칙 (g2p.py docstring '미처리 규칙' 참고) ──────
UNHANDLED = [
    ("냇가", "내까", "사이시옷 원칙 발음(옷고름[옫꼬름]과 철자로 구별 불가)"),
    ("디귿이", "디그시", "자모 이름의 연음(제16항)"),
]


@pytest.mark.parametrize("text,expected", REQUIRED, ids=[t for t, _ in REQUIRED])
def test_required(text, expected):
    assert to_pron(text) == expected


@pytest.mark.parametrize(
    "rule,text,expected",
    [(rule, t, e) for rule, cases in RULE_CASES.items() for t, e in cases],
    ids=[f"{rule}-{t}" for rule, cases in RULE_CASES.items() for t, _ in cases],
)
def test_rules(rule, text, expected):
    assert to_pron(text) == expected


def test_enough_cases():
    extra = sum(len(c) for c in RULE_CASES.values())
    assert extra >= 80


@pytest.mark.parametrize(
    "text,expected",
    [pytest.param(t, e, marks=pytest.mark.xfail(reason=f"미처리 규칙: {why}"), id=t)
     for t, e, why in UNHANDLED],
)
def test_unhandled_rules(text, expected):
    assert to_pron(text) == expected


# ── 입출력 형식 ───────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("", ""),
    ("   ", ""),
    ("123 abc !?", ""),
    ("국물!", "궁물"),
    ("국물.", "궁물"),
    ("3번 국물", "번 궁물"),
    ("Hello, 좋아요", "조아요"),
    ("  국물   먹었어요  ", "궁물 머거써요"),
    ("국물\n먹었어요\t좋아요", "궁물 머거써요 조아요"),
    ("ㅋㅋ 좋아", "조아"),
    ("안녕,하세요", "안녕 하세요"),
])
def test_format(text, expected):
    assert to_pron(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("옷 이", "옫 이"),          # 어절 사이 연음 없음
    ("밥 국", "밥 국"),          # 어절 사이 경음화 없음
    ("국 물", "국 물"),          # 어절 사이 비음화 없음
    ("좋 다", "졷 다"),          # 어절 사이 격음화 없음
    ("신 라", "신 라"),          # 어절 사이 유음화 없음
])
def test_no_rules_across_eojeol(text, expected):
    assert to_pron(text) == expected


def test_returns_str():
    assert isinstance(to_pron("국물"), str)


# ── 불변식: 결과 받침은 대표음 7개뿐, pron_to_phones 가 받을 수 있어야 함 ──
def _assert_valid_pron(pron: str):
    for ch in pron:
        if ch == " ":
            continue
        d = decompose(ch)
        assert d is not None, f"한글 음절이 아닌 문자: {ch!r} in {pron!r}"
        assert d[2] == "" or d[2] in CODA_PHONE, f"대표음이 아닌 받침: {ch} in {pron!r}"
    pron_to_phones(pron)


@pytest.mark.parametrize("text,_", ALL_CASES, ids=[t for t, _ in ALL_CASES])
def test_outputs_are_valid_pron(text, _):
    _assert_valid_pron(to_pron(text))


def test_random_hangul_is_valid_pron():
    rng = random.Random(20261014)
    for _ in range(3000):
        n = rng.randint(1, 6)
        text = "".join(chr(0xAC00 + rng.randrange(11172)) for _ in range(n))
        if rng.random() < 0.3:
            text += " " + "".join(chr(0xAC00 + rng.randrange(11172)) for _ in range(2))
        out = to_pron(text)
        _assert_valid_pron(out)
        # 음절 수는 바뀌지 않는다(규칙은 자모만 바꾼다)
        assert len(out.replace(" ", "")) == len(text.replace(" ", ""))


def test_all_codas_and_clusters():
    """모든 받침(겹받침 포함) × 대표 초성 조합이 예외 없이 처리된다."""
    from server.phones import JONG, compose
    onsets = ["ㅇ", "ㄱ", "ㄷ", "ㅂ", "ㅅ", "ㅈ", "ㄴ", "ㅁ", "ㄹ", "ㅎ"]
    for jong in JONG:
        for on in onsets:
            for vowel in ("ㅏ", "ㅣ", "ㅕ"):
                text = compose("ㅂ", "ㅏ", jong) + compose(on, vowel)
                _assert_valid_pron(to_pron(text))


# ── pron_options: 허용 발음·이어 말하기·사전 대안 ─────────
def _reach(text: str) -> set[str]:
    o = pron_options(text)
    return {o.render(c) for c in (o.combos(4096) or [o.zero])}


@pytest.mark.parametrize("text,alt", [
    ("시계", "시게"), ("혜택", "헤택"), ("계세요", "게세요"),                 # 제5항 다만2: ㅖ→ㅔ
    ("주의", "주이"), ("회의", "회이"), ("협의", "혀비"), ("강의", "강이"),     # 제5항 다만4: 비어두 '의'→ㅣ
    ("우리의", "우리에"), ("나라의", "나라에"),                               # 조사 '의'→ㅔ
    ("되어", "되여"), ("피어", "피여"), ("아니오", "아니요"),                  # 제22항
    ("학생이에요", "학쌩이예요"),                                            # ㅣ 뒤 모음 이음
    ("몇 월", "며 둴"), ("꽃 위", "꼬 뒤"),                                   # 제15항(어절 사이)
    ("밥 먹어요", "밤 머거요"), ("책 넣어요", "챙 너어요"),                   # 제18항 붙임
    ("먹을 거예요", "머글 꺼예요"), ("할 수 있어요", "할 쑤 이써요"),         # 제27항
    ("못 해요", "모 태요"), ("밥 줘", "밥 쭤"),                                # 격음화·경음화(이어 말하기)
    ("할 일", "할 릴"), ("옷 입어요", "온 니버요"),                            # 제29항 붙임2
    ("일 년", "일 련"), ("할 내용", "할 래용"), ("한 라인", "할 라인"),        # 제20항 유음화(어절 사이, 사람 낭독 실측)
    ("신고", "신꼬"), ("안다", "안따"), ("김밥", "김빱"),                      # 사전: 둘 다 표준
    ("살게", "살께"), ("갈밖에", "갈빠께"),                                   # 뜻에 따라 둘 다
])
def test_variants_reachable(text, alt):
    assert alt in _reach(text)
    assert pron_options(text).canonical == to_pron(text)


@pytest.mark.parametrize("text,not_alt", [
    ("의자", "이자"), ("예절", "에절"), ("실례", "실레"),        # 어두 '의', '예·례'는 허용 대상 아님
    ("주의", "주에"),                                           # 명사 끝 '의'는 [ㅔ] 아님(조사만)
    ("시월 구일", "시월 꾸일"), ("물 주세요", "물 쭈세요"),       # ㄹ 받침 명사 뒤는 경음화 대안 없음
    ("밥 국", "밤 국"), ("책을 보다", "채글 뽀다"),
])
def test_variants_not_overgenerated(text, not_alt):
    assert not_alt not in _reach(text)


def test_cross_eojeol_lateralization_is_only_an_option():
    """어절 사이 유음화는 이어 말한 경우의 대안일 뿐, 원칙형(to_pron)은 계약대로 어절 사이 규칙을 적용하지 않는다."""
    assert to_pron("일 년") == "일 년" and to_pron("한 라인") == "한 라인"
    o = pron_options("일 년")
    assert [s.kind for s in o.slots] == ["connected"]
    ch = o.find("일 련")
    assert ch is not None and "이어 말해" in o.describe(ch)[0] and "[일련]" in o.describe(ch)[0]


def test_guess_slots_give_check_notes():
    o = pron_options("결속")            # 사전에 없는 한자어 ㄹ+ㅅ → 제26항 추정 대안 + 안내
    assert o.canonical == "결속" and "결쏙" in o.alternatives()
    assert o.notes() and "발음형을 확인해 주세요" in o.notes()[0]
    o = pron_options("금이빨")          # 합성어로 보이는 'ㄴ' 첨가 후보
    assert "금니빨" in o.alternatives()
    assert pron_options("출장").notes() == []          # 사전에 있으면 안내 없음
    assert pron_options("팔다리").slots == []         # '다'는 어미일 수 있어 추정하지 않음(팔다리[팔다리])
    assert pron_options("놀다").slots == [] and pron_options("책이").slots == []


def test_find_and_describe():
    o = pron_options("밥 먹었어요?")
    ch = o.find("밤 머거써요")
    assert ch is not None and o.render(ch) == "밤 머거써요"
    assert o.find("궁물") is None
    msg = o.describe(ch)
    assert msg and "이어 말해" in msg[0] and "[밤머거써요]" in msg[0]
    back = o.describe(o.zero, base=ch)
    assert back and "끊어 말한" in back[0]
    o = pron_options("시계")
    assert "허용 발음" in o.describe(o.find("시게"))[0]
    # 어절 사이 이어 말하기(빡)와 허용 발음(헤)을 함께 고른 경우: 허용 발음 문장에는 그 자리 변화만 보여 준다
    o = pron_options("만약 박근혜")
    ch = next(c for c in o.combos(64) if o.render(c) == "마냑 빡끈헤")
    msgs = o.describe(ch)
    assert any("이어 말해" in m and "[마냑빡끈헤]" in m for m in msgs)
    assert any("허용 발음" in m and "[박끈헤]" in m for m in msgs) and not any("[빡끈헤]" in m for m in msgs)


def test_random_variants_are_valid_prons():
    rng = random.Random(7)
    for _ in range(400):
        n = rng.randint(1, 4)
        text = " ".join("".join(chr(0xAC00 + rng.randrange(11172)) for _ in range(rng.randint(1, 3)))
                        for _ in range(n))
        o = pron_options(text)
        assert o.canonical == to_pron(text)
        for ch in (o.combos(64) or o.single_changes()):
            out = o.render(ch)
            _assert_valid_pron(out)
            assert len(out.replace(" ", "")) == len(text.replace(" ", ""))
