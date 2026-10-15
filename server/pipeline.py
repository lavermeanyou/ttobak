"""모듈 조립: 음성 + 목표 문장 → API 응답 JSON (CONTRACT 9절).

순서
----
리샘플(16k mono) → 무음 판정 → 목표 생성(words.build_target) → emissions → decode(자유 인식)
→ force_align(목표, CTC-GOP·대안 음소 포함) → align(목표, 자유 인식) → 음소별 상태 → acoustic → lips
→ feedback.summarize

음소 상태 규칙 (계약 9절의 상태 이름·gop<45 → weak 은 그대로, 근거는 CTC-GOP 로 — 실측 근거는 아래)
-------------------------------------------------------------------------------------------
  margin = force_align 의 alt_margin = log P(목표 음소열) − max log P(그 자리 하나만 바꾼/뺀 음소열)  (nat)
  0) alt 가 '정상 변이'(accepted_variant)이면 → ok  (예: 받침 ㄷ 뒤 ㄸ 이 ㄷ 으로 들림, 모음 사이 ㅎ 약화)
  1) margin < SUB_MARGIN(−3.0)  → 대안이 뚜렷이(e³ ≈ 20배) 더 그럴듯함: alt 가 "<del>" 이면 del, 아니면 sub(heard = alt)
  2) gop < WEAK_GOP(45)         → weak  (gop = 100·σ(margin − GOP_C), GOP_C = −1.0 → margin < −1.2)
  3) 나머지                     → ok
  자유 인식(greedy CTC, align 결과)은 상태를 정하지 않는다(free_op 로만 남긴다).
근거 (scripts/eval_human.py, 사람 낭독 zeroth-korean 240문장 = 보정셋 117 + 검증셋 123, 화자가 겹치지 않게 나눔):
  * 예전 규칙(SUB_MARGIN −0.5, gop<45 이고 자유 인식이 sub/del 이면 sub/del)은 정상 낭독 음소의 8.2 %를
    sub/del 로 잡았다. 정상 음소 margin 분포의 아래 꼬리가 길어(5 백분위 −1.9, 3 백분위 −3.9) 문턱 −0.5 는
    너무 민감하다. 자유 인식 규칙만 켜도 보정셋 sub+del 이 2.9 % → 6.7 % 로 늘었다(프레임별 최댓값이라 흔들림).
  * 오류 흉내 데모 샘플 9개의 오류 자리 margin 은 −5.5 ~ −8.6 이라 −3.0 에서도 모두 잡힌다. 합성음 9종 × 최소대립쌍
    44개(오류 낱말을 말한 음성 vs 같은 음성의 정상 낱말)에서 '오류는 잡고 정상은 통과'한 쌍의 비율은 −0.5 에서 43 %,
    −2.5 ~ −3.5 에서 51 % 로 가장 높았다(정상 합성음도 그 자리를 오류로 듣는 경우가 많아 문턱을 낮춘다고 더 잘 가르지 않음).
  * 정상 변이(accepted_variant): 사람 낭독 오탐 가운데 표준발음·자연스러운 이어 말하기로 설명되는 것.
    - 장애음 받침(ㄱㄷㅂ) 뒤 예사소리↔된소리(했다[핻따]의 ㄸ 을 ㄷ 으로 들음: 예전 오탐 1위, 240문장에서 102건, margin 중앙값 −5.2)
    - 공명음 받침 뒤 '된소리되기 자리'(철자는 예사소리)의 예사소리(결정[결쩡]의 ㅉ → ㅈ)
    - 모음·공명음 뒤 ㅎ 약화·탈락(전화[저놔], 결혼[겨론]) — 단 발화 첫 ㅎ 은 그대로 판정
    - 받침 ㄱㄷㅂ 이 뒤 된소리·거센소리와 겹쳐 빠지거나 위치가 바뀜(있고[익꼬]), 받침 ㄴ·ㅁ 의 위치 동화(연구[영구])
    - 어절 끝 조사 '에'↔'의'(둘 다 실제로는 [에])
  * 삽입: 문장 안쪽 삽입은 INS_MARGIN(4.0 nat), ㅡ 는 INS_MARGIN_EU(1.0). 발화 맨 앞·맨 뒤 삽입은 숨소리·입술
    소리·잡음과 구별할 수 없어 판정하지 않는다 — 단 '받침 뒤 ㅡ 덧붙이기'(앞 → 아프, 실측 2.5 nat)는 실제 오류라 예외.
    사람 낭독 문장의 안쪽 삽입 후보(정상인데 끼워 넣은 음소열이 더 그럴듯한 경우)는 문장당 1.0 nat 초과 0.94개,
    3.0 초과 0.58개, 4.0 초과 0.40개였다. 데모 합성음의 '아녕하세요' 속 ㄹ(3.5)·'어이' 뒤 받침 ㅇ(3.1)은 합성 문장에
    없는 소리(합성음은 글자대로만 소리 낸다)라 확실한 거짓 삽입이고, 3~4 nat 구간에 몰려 있어 4.0 으로 둔다.
  * weak 카드는 정보(info) 수준으로 낮췄다(feedback). 음절 색은 그대로 '주의'.
  * 결과(보정셋/검증셋 sub+del): 8.8 % → 2.8 % / 7.7 % → 2.9 %. 표와 한계는 README '판정 방식 6절'.

발음 변이 선택 (choose_variant)
------------------------------
g2p.to_pron 은 원칙 발음 하나만 만든다. 그런데 표준발음법이 허용하는 발음(시계[시게], 주의[주이],
우리의[우리에])이나 어절을 이어 말할 때 나는 소리(밥 먹어요[밤머거요], 몇 월[며둴], 먹을 거예요[머글꺼예요])를
원칙형과 비교하면 정상 발음이 오류로 판정된다. 그래서 emissions 를 구한 뒤 g2p.pron_options 의 대안 조합을
CTC log P(음소열 | 음성)로 비교해 가장 그럴듯한 것을 목표로 쓴다(같으면 요청한 발음형 유지).
조합이 VARIANT_MAX_COMBOS 이하면 모두, 넘으면 자리별 좌표 상승(최대 3회)으로 고른다.
요청 발음형(pron)이 그 문장의 대안 조합으로 만들 수 없는 값이면(사용자 지정 발음) 바꾸지 않는다.
응답 target 에 pron_requested(요청 발음형)와 variant_notes(무엇을 어떻게 인정했는지 한국어 설명)를 붙인다.

받침 ㄹ 뒤 ㄹ: '달리기'의 둘째 ㄹ 은 설측음 [l] 이라 모델이 받침 ㄹ(L)로 들어도 정상이므로 ok 로 둔다.
heard.phones: 위 판정을 반영한 '들린 음소열'(목표 순서, sub 는 들린 음소, del 은 뺌, 채택된 삽입 포함).
  자유 인식 원본은 heard.free 에 따로 둔다(계약 외 추가 필드). 화면의 음절 블록·음소 목록과 [들린 소리]가
  서로 어긋나지 않게 하기 위해서다.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Any

import numpy as np

from . import acoustic as acoustic_mod
from . import align as align_mod
from . import feedback
from . import g2p
from . import lips as lips_mod
from . import recognizer as recognizer_mod
from . import words
from .phones import JONG, PHONES, compose, decompose, jamo_of, pron_to_phones

log = logging.getLogger(__name__)

SR = 16000
MODEL_NAME = recognizer_mod.MODEL_NAME

# ── 판정 상수 (모듈 docstring 의 근거 참고) ─────────────────
WEAK_GOP = 45          # 계약 9절: match 인데 gop < 45 → weak (recognizer.GOP_C = −1.0 이라 margin < −1.2)
SUB_MARGIN = -3.0      # alt_margin 이 이보다 작으면 sub/del
INS_MARGIN = 4.0       # 삽입 채택(ㅡ 외): log P(삽입한 음소열) − log P(목표 음소열) > 4.0 nat
INS_MARGIN_EU = 1.0    # ㅡ 삽입(받침 뒤 ㅡ 덧붙이기)은 실제로 흔한 오류라 낮게
VARIANT_MAX_COMBOS = 64   # 발음 변이 조합이 이 이하면 전부 비교, 넘으면 자리별 좌표 상승

# 음소 판정이 ok 인 모음의 포먼트가 참고치에서 이만큼 벗어나면(비율) 포먼트 측정 실패로 본다(f1/f2 → null).
# 인식 모델이 그 모음으로 똑똑히 들었는데 F1 이 참고치의 0.6배 미만·1.6배 초과이면 다른 모음 자리이므로
# 대개 짧은 구간에서 창이 자음에 걸린 경우다. 실측(Yuna, 정상 판정): 부부 ㅜ (1370, 1863), 그네 ㅡ (900, 2128),
# 학교 ㅏ (358, 1429) — 모두 60~80 ms 구간.
GROSS_F1 = (0.6, 1.6)
GROSS_F2 = (0.5, 2.5)
GROSS_MIN_GOP = 60

# ── 입력 오디오 한계 ───────────────────────────────────────
MIN_SEC = 0.15         # 이보다 짧으면 bad_audio
MAX_SEC = 30.0         # 이보다 길면 bad_audio (데모 연습 단위는 단어·짧은 문장)

# ── 무음 판정 (계약 9절: 유성 비율·강도 기준) ──────────────
# 25 ms 창 RMS(dBFS). 노트북·휴대폰 마이크로 30 cm 안팎에서 평소 크기로 말하면 말소리 창의 최대 RMS 는
# 대략 −30 ~ −12 dBFS 다. 최대가 −50 dBFS 미만이면 사실상 배경 소음뿐이라 '말소리 없음'으로 본다.
NO_SPEECH_PEAK_DBFS = -50.0
# 유성(성대 진동) 구간이 0.08초 미만이면 모음이 하나도 없다고 본다. 한국어 음절은 모두 모음을 가지며
# 가장 짧은 단음절 단어의 모음도 보통 0.1초 이상이다. 유성 판정은 최대값에서 30 dB 이내 창만 센다(잡음 속 오검출 방지).
MIN_VOICED_SEC = 0.08
VOICED_REL_DB = 30.0
# 인식기의 자유 인식이 목표 음소 수의 30 % 미만만 찾으면 말소리가 아니라고 본다. 실측: 120 Hz 험(−20 dBFS)은 유성으로
# 잡혀 무음 판정을 통과했는데 자유 인식 0개(목표 '소리' 4음소) — 엄격해진 sub 문턱 아래에서 '모든 소리가 정확'으로
# 나왔다. 사람 낭독 문장·잘라 낸 단어 2,500여 건과 합성음 750건의 자유 인식/목표 비율은 최소 0.43 이었다.
NO_SPEECH_FREE_RATIO = 0.3
# 인식기 입력 자르기(trim_for_recognizer): 최대 창보다 40 dB 넘게 작은 창은 무음으로 보고, 말소리 앞뒤 0.75초만 남긴다.
# 40 dB: 어두 ㅅ·ㅎ 같은 약한 마찰음도 모음 최대보다 25~35 dB 아래라 말소리 안에 든다.
# 0.75초: 보통 녹음(앞뒤 무음 0.3~0.7초)은 건드리지 않고 '버튼을 늦게 뗀' 긴 무음만 자른다. 이 모델은 무음 문맥
# 길이에 민감해서(정상 '소리'의 ㅗ margin: 남긴 무음 0.15초 +0.9, 0.3초 −1.5, 0.4초 이상 +1.6) 짧게 자르면 오히려 흔들린다.
TRIM_REL_DB = 40.0
TRIM_KEEP_SEC = 0.75

ERROR_MESSAGES = {
    "no_speech": "말소리가 거의 들리지 않았어요. 마이크에 조금 더 가까이 대고, 목소리를 내서 또박또박 말해 주세요.",
    "bad_audio": "녹음 파일을 읽지 못했어요. 다시 녹음해 주세요.",
    "empty_target": "연습할 한글 낱말이 없어요. 한글로 입력해 주세요.",
}


class PipelineError(Exception):
    """API 422 로 돌려줄 오류. code ∈ no_speech | bad_audio | empty_target."""

    def __init__(self, code: str, message: str | None = None):
        super().__init__(code)
        self.code = code
        self.message = message or ERROR_MESSAGES.get(code, "분석하지 못했어요.")

    def as_dict(self) -> dict:
        return {"error": self.code, "message": self.message}


# ── 오디오 정규화 ─────────────────────────────────────────
DOWNMIX_CANCEL = 0.3   # 채널 평균의 크기가 가장 큰 채널의 이 비율보다 작으면 채널끼리 상쇄된 것(위상 반전)


def _downmix(ch: np.ndarray) -> np.ndarray:
    """(표본, 채널) → 모노. 보통은 채널 평균. 채널끼리 위상이 반대라 평균이 상쇄되면(L = −R 인 스테레오 마이크·
    가상 장치) 평균은 거의 무음이 되므로 가장 큰 채널 하나를 쓴다(실측: L=−R 입력이 no_speech 로 거절되던 문제)."""
    mono = ch.mean(axis=1)
    if ch.shape[1] > 1:
        rms_ch = np.sqrt(np.mean(ch * ch, axis=0))
        top = float(rms_ch.max())
        if top > 0 and float(np.sqrt(np.mean(mono * mono))) < DOWNMIX_CANCEL * top:
            mono = ch[:, int(np.argmax(rms_ch))]
    return mono


def prepare_audio(wav: Any, sr: int) -> np.ndarray:
    """임의의 배열(int/float, 모노/스테레오, 임의 표본율) → 16 kHz mono float32 [-1, 1]."""
    try:
        sr = int(sr)
    except (TypeError, ValueError):
        raise PipelineError("bad_audio", "녹음 파일의 표본율을 알 수 없어요. 다시 녹음해 주세요.")
    if sr < 4000 or sr > 384000:
        raise PipelineError("bad_audio", f"지원하지 않는 표본율이에요({sr} Hz). 다시 녹음해 주세요.")
    a = np.asarray(wav)
    if a.size == 0:
        raise PipelineError("bad_audio", "녹음된 소리가 비어 있어요. 다시 녹음해 주세요.")
    if a.dtype.kind == "u":            # 8비트 PCM 등 부호 없는 정수
        info = np.iinfo(a.dtype)
        a = (a.astype(np.float64) - (info.max + 1) / 2.0) / ((info.max + 1) / 2.0)
    elif a.dtype.kind == "i":          # int16/int32 PCM
        a = a.astype(np.float64) / float(np.iinfo(a.dtype).max + 1)
    elif a.dtype.kind in "fc":
        a = np.real(a).astype(np.float64)
    else:
        raise PipelineError("bad_audio")
    if a.ndim == 2:                    # (표본, 채널) 또는 (채널, 표본)
        a = _downmix(a if a.shape[1] <= a.shape[0] else a.T)
    elif a.ndim != 1:
        a = a.reshape(-1)
    a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
    if len(a) / sr < MIN_SEC:
        raise PipelineError("bad_audio", "녹음이 너무 짧아요. 버튼을 누른 뒤 낱말을 끝까지 말해 주세요.")
    if len(a) / sr > MAX_SEC:
        raise PipelineError("bad_audio", f"녹음이 너무 길어요({len(a) / sr:.0f}초). {MAX_SEC:.0f}초 안으로 짧게 녹음해 주세요.")
    peak = float(np.max(np.abs(a))) if len(a) else 0.0
    if peak > 1.0:                     # 정수 범위 값이 float 로 들어온 경우 등
        a = a / peak
    a = a - float(np.mean(a))          # 직류 성분 제거
    if sr != SR:
        import torch
        import torchaudio.functional as AF
        t = torch.from_numpy(a.astype(np.float32))
        a = AF.resample(t, sr, SR, lowpass_filter_width=16, rolloff=0.95,
                        resampling_method="sinc_interp_kaiser", beta=14.769656459379492).numpy()
    return np.clip(a, -1.0, 1.0).astype(np.float32)


def speech_presence(x: np.ndarray, sr: int = SR) -> dict:
    """{"peak_dbfs", "voiced_sec", "ok"} — 말소리가 있는지(강도·유성 구간 기준)."""
    win, hop = int(0.025 * sr), int(0.010 * sr)
    if len(x) < win:
        return {"peak_dbfs": None, "voiced_sec": 0.0, "ok": False}
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx].astype(np.float64)
    db = 10.0 * np.log10(np.mean(frames * frames, axis=1) + 1e-12)
    peak = float(db.max())
    voiced_sec = 0.0
    if peak >= NO_SPEECH_PEAK_DBFS:
        try:
            import parselmouth
            pitch = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr).to_pitch_ac(
                time_step=0.01, pitch_floor=75.0, pitch_ceiling=600.0)
            ts = np.asarray(pitch.xs())
            f0 = np.asarray(pitch.selected_array["frequency"])
            j = np.clip(np.round((ts - win / 2 / sr) / (hop / sr)).astype(int), 0, n - 1)
            loud = db[j] >= peak - VOICED_REL_DB
            voiced_sec = float(np.sum((f0 > 0) & loud)) * 0.01
        except Exception as e:  # pragma: no cover - parselmouth 문제 시 강도만으로 판단
            log.warning("유성 판정 실패, 강도만 사용: %s", e)
            voiced_sec = float(np.sum(db >= peak - 20.0)) * hop / sr
    ok = peak >= NO_SPEECH_PEAK_DBFS and voiced_sec >= MIN_VOICED_SEC
    return {"peak_dbfs": round(peak, 1), "voiced_sec": round(voiced_sec, 2), "ok": bool(ok)}


def speech_span(x: np.ndarray, sr: int = SR) -> tuple[float, float]:
    """말소리가 있는 구간(초) [처음, 끝]. 25 ms 창 RMS 가 max(최대 − TRIM_REL_DB, 바닥 + 6 dB) 를 넘는 첫·끝 창.
    소리가 없거나 너무 짧으면 (0, 길이)."""
    dur = len(x) / sr
    win, hop = int(0.025 * sr), int(0.010 * sr)
    if len(x) < win:
        return 0.0, dur
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx].astype(np.float64)
    db = 10.0 * np.log10(np.mean(frames * frames, axis=1) + 1e-12)
    peak, floor = float(db.max()), float(np.percentile(db, 10))
    on = np.nonzero(db > max(peak - TRIM_REL_DB, floor + 6.0))[0]
    if not len(on):
        return 0.0, dur
    return float(on[0] * hop / sr), float(min(dur, (on[-1] * hop + win) / sr))


def trim_for_recognizer(x: np.ndarray, sr: int = SR) -> tuple[float, np.ndarray]:
    """인식기에 넣을 구간: 말소리 구간 앞뒤로 TRIM_KEEP_SEC 만 남긴다. 반환 (잘라 낸 앞 길이 초, 잘린 음성).

    왜: 이 모델은 앞뒤 무음이 길수록 margin 이 줄어 정상 발음이 오류로 뒤집힌다. 실측(정상 '소리'): 원래
    (앞뒤 0.4초) ㅗ margin +1.6 → 뒤 무음 6.6초 −0.2(예전 문턱에서 sub, ㅗ→ㅜ), 앞 3초 + 뒤 2초 +0.3(weak),
    억양 점수도 사라졌다. 녹음 버튼을 늦게 떼는 일은 흔하므로 긴 무음은 잘라 같은 조건으로 맞춘다.
    시각은 호출 측이 앞 길이를 더해 원래 녹음 기준으로 되돌린다(입술 시계열·차트와 같은 시간축)."""
    s, e = speech_span(x, sr)
    a = max(0, int((s - TRIM_KEEP_SEC) * sr))
    b = min(len(x), int(math.ceil((e + TRIM_KEEP_SEC) * sr)))
    if b - a < int(MIN_SEC * sr) or (a == 0 and b == len(x)):
        return 0.0, x
    return a / sr, x[a:b]


# ── 한글 조립 ─────────────────────────────────────────────
_CODA_OK = frozenset({"k", "t", "p", "N", "L", "M", "NG", "G", "D", "B"})


def phones_to_hangul(seq: list[str]) -> str:
    """음소열 → 한글(탐욕 조립: (초성?)(모음)(받침?)). 모음 없이 남은 자음은 자모 그대로 둔다."""
    out: list[str] = []
    syms = [p for p in seq if p in PHONES]
    n = len(syms)
    i = 0
    while i < n:
        P = PHONES[syms[i]]
        if P.is_vowel:
            onset, vowel = "ㅇ", P.jamo
            i += 1
        elif i + 1 < n and PHONES[syms[i + 1]].is_vowel:
            onset, vowel = P.jamo, PHONES[syms[i + 1]].jamo
            i += 2
        else:
            out.append(P.jamo)
            i += 1
            continue
        coda = ""
        # 받침 자리에서 실제로 날 수 있는 소리만 받침으로 조립한다. 받침에서 ㅍ처럼 터뜨린 소리를 '앞'으로
        # 조립하면 정답 철자와 똑같아 보이므로, 그런 자음은 위 분기에서 'ㅍ'처럼 낱자로 남긴다.
        if i < n and syms[i] in _CODA_OK and not (i + 1 < n and PHONES[syms[i + 1]].is_vowel):
            cj = PHONES[syms[i]].jamo
            if cj in JONG:
                coda = cj
                i += 1
        try:
            out.append(compose(onset, vowel, coda))
        except ValueError:
            out.append(onset + vowel + coda)
    return "".join(out)


# ── 음소 상태 ─────────────────────────────────────────────
_TENSE_OF = {"B": "BB", "D": "DD", "G": "GG", "S": "SS", "J": "JJ"}
_LENIS_OF = {v: k for k, v in _TENSE_OF.items()}
_OBS_CODA = frozenset({"p", "t", "k"})
_SON_CODA = frozenset({"N", "L", "M", "NG"})
_TENSE_ASP = frozenset({"BB", "DD", "GG", "SS", "JJ", "Ph", "Th", "Kh", "CHh"})
_OBSTRUENT = _TENSE_ASP | frozenset({"B", "D", "G", "S", "J", "H"})
_VELAR = frozenset({"G", "GG", "Kh", "k"})
_LABIAL = frozenset({"B", "BB", "Ph", "M", "p"})


def accepted_variant(target: str, alt: str | None, ctx: dict | None) -> str | None:
    """alt(가장 그럴듯한 대안)가 target 의 '정상 변이'면 그 이유(짧은 한국어), 아니면 None.

    ctx: {"idx", "prev", "next", "coda"(받침 자리), "word_last"(어절 끝 음소), "tensified"(철자는 예사소리인데
    된소리되기로 된소리가 된 자리)}. 모듈 docstring 의 '정상 변이' 근거 참고."""
    if not alt or not ctx:
        return None
    prev, nxt = ctx.get("prev"), ctx.get("next")
    if prev in _OBS_CODA and ((target in _LENIS_OF and alt == _LENIS_OF[target])
                              or (target in _TENSE_OF and alt == _TENSE_OF[target])):
        return "받침 뒤 된소리"
    if prev in _SON_CODA and ctx.get("tensified") and target in _LENIS_OF and alt == _LENIS_OF[target]:
        return "된소리되기 자리의 예사소리"
    if target == "H" and (ctx.get("idx") or 0) > 0 and prev is not None \
            and (prev in _SON_CODA or PHONES[prev].is_vowel) and (alt == "<del>" or alt == prev):
        return "ㅎ 약화"
    if target in _OBS_CODA and nxt is not None:
        if alt == "<del>" and nxt in _TENSE_ASP:
            return "받침이 뒤 된소리·거센소리와 겹침"
        if alt in _OBS_CODA and nxt in _OBSTRUENT:
            return "받침 위치 동화"
    if ctx.get("coda") and nxt is not None and (
            (target == "N" and ((alt == "NG" and nxt in _VELAR) or (alt == "M" and nxt in _LABIAL)))
            or (target == "M" and alt == "NG" and nxt in _VELAR)):
        return "받침 위치 동화"
    if ctx.get("word_last") and ((target == "E" and alt == "euI") or (target == "euI" and alt in ("E", "I"))):
        return "조사 '에'·'의'"
    return None


def decide_status(fa: dict, nw_op: str, nw_heard: str | None, target: str,
                  ctx: dict | None = None) -> tuple[str, str | None]:
    """(status, heard 음소). 규칙은 모듈 docstring. nw_op/nw_heard(자유 인식 정렬)는 판정에 쓰지 않는다
    (사람 낭독에서 오탐을 두 배로 늘렸다) — 호환을 위해 인자는 남겨 둔다."""
    margin = fa.get("alt_margin")
    gop = fa.get("gop")
    alt = fa.get("alt")
    if isinstance(margin, (int, float)) and margin < 0 and accepted_variant(target, alt, ctx):
        return "ok", target
    if isinstance(margin, (int, float)) and margin < SUB_MARGIN and alt:
        if alt == "<del>":
            return "del", None
        if alt in PHONES:
            return "sub", alt
    if gop is not None and gop < WEAK_GOP:
        return "weak", target
    return "ok", target


def _r_after_l(t_phones: list[str], i: int, status: str, heard: str | None) -> tuple[str, str | None]:
    """받침 ㄹ 바로 뒤의 ㄹ(달리기·칼날·실라)은 설측음 [l] 이라 받침 ㄹ(L)로 들려도 정상."""
    if t_phones[i] == "R" and i > 0 and t_phones[i - 1] == "L" and status == "sub" and heard == "L":
        return "ok", t_phones[i]
    return status, heard


def _set_status(ph: dict, status: str, heard: str | None, t_phones: list[str] | None = None) -> None:
    i = ph.get("idx", 0)
    prev = t_phones[i - 1] if t_phones and isinstance(i, int) and 0 < i <= len(t_phones) else None
    ph["status"] = status
    ph["heard"] = heard
    if not heard:
        ph["heard_jamo"] = None
    elif heard == ph["phone"]:
        ph["heard_jamo"] = ph.get("jamo") or jamo_of(heard)
    else:
        ph["heard_jamo"] = jamo_of(heard)
    ph["tip"] = (feedback.phone_tip(ph["phone"], heard, status, coda=ph.get("coda"), prev=prev,
                                    initial=bool(ph.get("initial")), jamo=ph.get("jamo"))
                 if status != "ok" else None)


def _fix_twin_deletions(rec, em, t_phones: list[str], phones_out: list[dict],
                        nw: dict[int, tuple[str, str | None]], ctxs: list[dict] | None = None) -> None:
    """같은 음소가 붙어 있으면(안녕의 ㄴㄴ, 엄마의 ㅁㅁ) 어느 쪽을 빼도 같은 음소열이라 CTC 대안이 둘 다
    '<del>' 로 나온다. 실제로는 하나만 빠진 것이므로: 자유 인식이 del 로 짝지은 쪽을, 그런 정보가 없으면
    앞쪽(받침 — 받침 탈락이 첫소리 탈락보다 흔하다)을 뺀 것으로 보고, 남은 쪽은 '하나 뺀 음소열'을
    기준으로 GOP 를 다시 재서 판정한다(둘 다 빠졌으면 다시 del 로 나온다)."""
    N = len(t_phones)
    i = 0
    while i < N - 1:
        a, b = phones_out[i], phones_out[i + 1]
        twin = (t_phones[i] == t_phones[i + 1] and a["status"] == "del" and b["status"] == "del"
                and a.get("alt") == "<del>" and b.get("alt") == "<del>")
        if not twin:
            i += 1
            continue
        gone, keep = (i + 1, i) if (nw.get(i + 1, ("",))[0] == "del" and nw.get(i, ("",))[0] != "del") else (i, i + 1)
        base = t_phones[:gone] + t_phones[gone + 1:]
        k = keep if keep < gone else keep - 1
        try:
            m = rec.gop_margins(em, base)[k]
        except Exception as e:  # pragma: no cover
            log.warning("짝 음소 GOP 재계산 실패: %s", e)
            i += 2
            continue
        margin = m["margin"]
        gop = recognizer_mod.margin_to_gop(margin)
        am = round(margin, 3) if math.isfinite(margin) else (99.0 if margin > 0 else -99.0)
        op, h = nw.get(keep, ("match", None))
        if op == "del":      # 자유 인식은 이쪽을 뺐다고 봤지만 짝 음소를 이미 뺐으므로 남은 쪽은 들린 것으로 본다
            op, h = "match", t_phones[keep]
        ctx = dict(ctxs[keep]) if ctxs else {}
        ctx.update(prev=base[k - 1] if k > 0 else None, next=base[k + 1] if k + 1 < len(base) else None)
        status, heard = decide_status({"alt_margin": am, "gop": gop, "alt": m["alt"]}, op, h, t_phones[keep], ctx)
        status, heard = _r_after_l(t_phones, keep, status, heard)
        ph = phones_out[keep]
        ph.update({"gop": int(gop), "alt": m["alt"], "alt_margin": am, "twin_of": gone})
        _set_status(ph, status, heard, t_phones)
        i += 2


def _coda_flags(phones: list[str], phone_syl: list[int]) -> list[bool]:
    """음소마다 '받침 자리인가'(같은 음절 안에서 모음 뒤의 자음)."""
    out = []
    for k, p in enumerate(phones):
        prev_v = any(PHONES[phones[j]].is_vowel for j in range(k) if phone_syl[j] == phone_syl[k])
        out.append(not PHONES[p].is_vowel and prev_v)
    return out


def _initial_flags(phones: list[str], phone_syl: list[int], syl_word: list[int]) -> list[bool]:
    """음소마다 '어절 첫소리 자음인가'(평음/격음/경음의 시작 음높이 단서용)."""
    out = []
    for k, p in enumerate(phones):
        s = phone_syl[k]
        first_syl = s == 0 or (0 < s < len(syl_word) and syl_word[s - 1] != syl_word[s])
        first_phone = k == 0 or phone_syl[k - 1] != s
        out.append(bool(first_syl and first_phone and not PHONES[p].is_vowel))
    return out


def _syl_words(pron: str) -> list[int]:
    """발음형 음절마다 어절 번호."""
    out: list[int] = []
    for w, word in enumerate(pron.split()):
        out += [w] * sum(1 for ch in word if "가" <= ch <= "힣")
    return out


_TENSE_JAMO = {"ㄱ": "ㄲ", "ㄷ": "ㄸ", "ㅂ": "ㅃ", "ㅅ": "ㅆ", "ㅈ": "ㅉ"}


def _tensified_flags(target: dict) -> list[bool]:
    """음소마다 '철자는 예사소리인데 발음형에서 된소리가 된 첫소리인가'(된소리되기 자리: 결정[결쩡], 물고기[물꼬기])."""
    out = [False] * len(target["phones"])
    for syl in target.get("syllables") or []:
        orth, pr, idxs = syl.get("text"), syl.get("pron"), syl.get("phones") or []
        if not orth or not pr or orth == pr or not idxs:
            continue
        do, dp = decompose(orth), decompose(pr)
        if do and dp and _TENSE_JAMO.get(do[0]) == dp[0] and not PHONES[target["phones"][idxs[0]]].is_vowel:
            out[idxs[0]] = True
    return out


def _contexts(t_phones: list[str], t_syl: list[int], syl_word: list[int], coda: list[bool],
              tensified: list[bool]) -> list[dict]:
    """음소마다 accepted_variant 에 넘길 문맥."""
    N = len(t_phones)

    def word_of(k: int) -> int:
        s = t_syl[k]
        return syl_word[s] if s < len(syl_word) else 0
    return [{"idx": i, "prev": t_phones[i - 1] if i else None, "next": t_phones[i + 1] if i + 1 < N else None,
             "coda": bool(coda[i]), "word_last": i == N - 1 or word_of(i + 1) != word_of(i),
             "tensified": bool(tensified[i])} for i in range(N)]


def _jsonable(o: Any) -> Any:
    """numpy 타입·NaN·inf 를 순수 파이썬 값으로 (JSON 직렬화 보장)."""
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        v = float(o)
        return v if math.isfinite(v) else None
    if isinstance(o, np.ndarray):
        return _jsonable(o.tolist())
    return o


def choose_variant(rec, em: np.ndarray, text: str, target: dict) -> tuple[dict, list[str]]:
    """target(요청 발음형) 대신 음성에 가장 그럴듯한 표준·자연 발음형을 고른다(모듈 docstring).
    반환: (쓸 목표, 바꾼 내용 설명 목록). 바꾸지 않으면 (target, [])."""
    if not hasattr(rec, "seq_logps") or not text:
        return target, []
    try:
        opts = g2p.pron_options(text)
    except Exception as e:  # pragma: no cover
        log.warning("발음 변이 계산 실패: %s", e)
        return target, []
    if not opts.slots:
        return target, []
    start = opts.find(target["pron"])
    if start is None:
        return target, []
    lp: dict[tuple, float] = {}

    def evaluate(choices: list[tuple]) -> None:
        new = [c for c in dict.fromkeys(choices) if c not in lp]
        seqs: list[list[str]] = []
        keep: list[tuple] = []
        for c in new:
            try:
                ph = pron_to_phones(opts.render(c))[0]
            except ValueError:
                ph = []
            if ph:
                seqs.append(ph)
                keep.append(c)
            else:
                lp[c] = -math.inf
        if seqs:
            for c, v in zip(keep, rec.seq_logps(em, seqs)):
                lp[c] = v if math.isfinite(v) else -math.inf

    try:
        allc = opts.combos(VARIANT_MAX_COMBOS)
        if allc is not None:
            evaluate(allc)
            best = max(allc, key=lambda c: (lp[c], c == start))
        else:
            best = start
            evaluate([best])
            for _ in range(3):
                cands = opts.single_changes(best)
                evaluate(cands)
                better = [c for c in cands if lp[c] > lp[best] + 1e-9]
                if not better:
                    break
                merged = list(best)            # 자리끼리는 거의 독립: 자리별 최선을 합쳐 본다
                for si in range(len(best)):
                    alts = [c for c in better if c[si] != best[si]]
                    if alts:
                        merged[si] = max(alts, key=lambda c: lp[c])[si]
                merged_t = tuple(merged)
                evaluate([merged_t])
                single = max(better, key=lambda c: lp[c])
                best = merged_t if lp[merged_t] >= lp[single] else single
    except Exception as e:  # pragma: no cover - 변이 선택 실패가 분석을 막지 않게
        log.warning("발음 변이 선택 실패: %s", e)
        return target, []
    if best == start or not lp.get(best, -math.inf) > lp.get(start, -math.inf):
        return target, []
    pron = opts.render(best)
    try:
        new = words.build_target(text, pron)
    except ValueError:  # pragma: no cover
        return target, []
    return new, opts.describe(best, base=start)


def _reconcile_vowels(vowels: list[dict], phones_out: list[dict]) -> None:
    """음소 판정이 ok(GOP 높음)인데 포먼트가 다른 모음 자리로 크게 튄 경우 → 측정 실패로 보고 숨긴다."""
    by_idx = {p["idx"]: p for p in phones_out}
    for v in vowels or []:
        p = by_idx.get(v.get("idx"))
        ref = v.get("ref")
        if not p or not ref or v.get("f1") is None or v.get("f2") is None:
            continue
        if p["status"] != "ok" or (p.get("gop") or 0) < GROSS_MIN_GOP:
            continue
        r1, r2 = v["f1"] / ref["f1"], v["f2"] / ref["f2"]
        if not (GROSS_F1[0] <= r1 <= GROSS_F1[1]) or not (GROSS_F2[0] <= r2 <= GROSS_F2[1]):
            v["f1_raw"], v["f2_raw"] = v["f1"], v["f2"]
            v["f1"] = v["f2"] = None
            v["ok"] = None
            v["unreliable"] = "measure"


def _build_target(text: str, pron: str | None) -> dict:
    try:
        return words.build_target(text, pron)
    except words.EmptyTargetError as e:
        raise PipelineError("empty_target", str(e) or None)
    except ValueError:
        # pron 에 대표음이 아닌 받침이 있는 등 잘못된 발음형 → 철자에서 다시 만든다
        if pron:
            try:
                return words.build_target(text, None)
            except words.EmptyTargetError as e:
                raise PipelineError("empty_target", str(e) or None)
        raise PipelineError("empty_target")


# ── 진입점 ────────────────────────────────────────────────
def analyze(wav: np.ndarray, sr: int, target_text: str, pron: str | None, lips: dict | None,
            voice: str = "female", sentence_type: str = "word", *,
            question_kind: str | None = None, end_tune: str | None = None) -> dict:
    """음성 + 목표 → API 응답(dict). 처리할 수 없으면 {"error", "message"} (HTTP 422 용).

    (계약 외 선택 인자) question_kind: 의문문 종류 'yn' | 'wh' (없으면 문장에서 의문사로 추정),
    end_tune: 'free' 면 끝 억양을 올려도 내려도 됨(인사 '안녕하세요' 등). feedback.resolve_tune 참고.
    """
    t0 = time.perf_counter()
    try:
        return _analyze(wav, sr, target_text, pron, lips, voice, sentence_type, t0, question_kind, end_tune)
    except PipelineError as e:
        return e.as_dict()


def _analyze(wav, sr, target_text, pron, lips, voice, sentence_type, t0, question_kind=None, end_tune=None) -> dict:
    voice = voice if voice in ("male", "female", "child") else "female"
    stype = (sentence_type or "word").lower()
    if stype not in ("word", "statement", "question"):
        stype = "word"
    qkind = None
    if stype == "question":
        qkind = question_kind if question_kind in ("yn", "wh") else words.infer_question_kind(target_text or "")
    tune = feedback.resolve_tune(stype, qkind, end_tune if end_tune in ("rise", "fall", "free") else None)

    # 1) 목표 (오디오보다 먼저: 빈 목표면 모델을 돌릴 필요가 없다)
    target = _build_target(target_text or "", pron)

    # 2) 오디오 → 16k mono, 무음 판정
    x = prepare_audio(wav, sr)
    presence = speech_presence(x)
    if not presence["ok"]:
        raise PipelineError("no_speech")

    # 3) 인식 (+ 허용 발음·이어 말하기 변이 중 음성에 가장 그럴듯한 목표 선택)
    rec = recognizer_mod.get_recognizer()
    off, xr = trim_for_recognizer(x)            # 긴 앞뒤 무음 제거(시각은 아래에서 off 만큼 되돌림)
    em = rec.emissions(xr)
    pron_requested = target["pron"]
    target, variant_notes = choose_variant(rec, em, target_text or "", target)
    t_phones: list[str] = target["phones"]
    t_syl: list[int] = target["phone_syl"]
    N = len(t_phones)
    dec = rec.decode(em)
    free = [d["phone"] for d in dec]
    if N and len(free) < NO_SPEECH_FREE_RATIO * N:
        # 강도·유성 기준은 통과했지만 인식기가 말소리를 거의 못 찾음(험·윙 소리 같은 순음, 콧노래 등)
        raise PipelineError("no_speech")
    fa = rec.force_align(em, t_phones)
    if off:
        dur = len(x) / SR
        for f in fa:
            f["start"] = round(min(dur, f["start"] + off), 3)
            f["end"] = round(min(dur, f["end"] + off), 3)
    ops = align_mod.align(t_phones, free)

    # 4) 음소별 상태
    nw: dict[int, tuple[str, str | None]] = {}
    ins_cands: list[tuple[int, str]] = []          # (after, phone)
    last_t = -1
    for o in ops:
        if o["t"] is not None:
            last_t = o["t"]
            nw[o["t"]] = (o["op"], free[o["h"]] if o["h"] is not None else None)
        else:
            ins_cands.append((last_t, free[o["h"]]))

    coda = _coda_flags(t_phones, t_syl)
    syl_word = _syl_words(target["pron"])
    initial = _initial_flags(t_phones, t_syl, syl_word)
    ctxs = _contexts(t_phones, t_syl, syl_word, coda, _tensified_flags(target))
    disp = target.get("jamo") or [jamo_of(p) for p in t_phones]
    phones_out: list[dict] = []
    for i, p in enumerate(t_phones):
        f = fa[i]
        op, h_nw = nw.get(i, ("del", None))
        status, heard = decide_status(f, op, h_nw, p, ctxs[i])
        status, heard = _r_after_l(t_phones, i, status, heard)
        ph = {
            "idx": i, "phone": p, "jamo": disp[i] if i < len(disp) else jamo_of(p), "syl": int(t_syl[i]),
            "start": f["start"], "end": f["end"],
            "status": status, "heard": heard, "heard_jamo": None,
            "gop": int(f["gop"]), "tip": None,
            # 계약 외: 판정 근거
            "post": f.get("post"), "alt": f.get("alt"), "alt_margin": f.get("alt_margin"),
            "free_op": op, "coda": bool(coda[i]), "initial": initial[i],
        }
        am = f.get("alt_margin")
        if status == "ok" and isinstance(am, (int, float)) and am < 0:
            v = accepted_variant(p, f.get("alt"), ctxs[i])
            if v:
                ph["variant"] = v        # 계약 외: 정상 변이로 보고 ok 로 둔 이유
        _set_status(ph, status, heard, t_phones)
        phones_out.append(ph)
    _fix_twin_deletions(rec, em, t_phones, phones_out, nw, ctxs)

    # 5) 삽입: CTC 로 확인된 것만
    insertions: list[dict] = []
    if ins_cands:
        seqs = [t_phones[:a + 1] + [q] + t_phones[a + 1:] for a, q in ins_cands]
        try:
            lps = rec.seq_logps(em, [t_phones] + seqs)
        except Exception as e:  # pragma: no cover
            log.warning("삽입 확인 실패: %s", e)
            lps = []
        if lps:
            base = lps[0]
            last_cons = bool(N) and not PHONES[t_phones[-1]].is_vowel
            for (a, q), lp in zip(ins_cands, lps[1:]):
                gain = lp - base if math.isfinite(lp) and math.isfinite(base) else -math.inf
                if a < 0 or a >= N - 1:
                    # 발화 맨 앞·맨 뒤: 숨소리·입술 소리·잡음과 구별할 수 없어 판정하지 않는다
                    # (사람 낭독에서 잘라 낸 단어의 가장자리 삽입은 거의 모두 이웃 소리·잡음이었다).
                    # 단 받침으로 끝나는 말 뒤의 ㅡ(앞 → 아프)는 실제로 흔한 오류라 판정한다.
                    if not (q == "EU" and a >= N - 1 and last_cons):
                        continue
                need = INS_MARGIN_EU if q == "EU" else INS_MARGIN
                if gain > need:
                    insertions.append({"after": int(a), "phone": q, "jamo": jamo_of(q),
                                       "margin": round(gain, 2) if math.isfinite(gain) else None})

    # 6) 들린 음소열 + 한글 추정
    def word_of(k: int) -> int:
        s = t_syl[k] if 0 <= k < N else (t_syl[0] if N else 0)
        return syl_word[s] if s < len(syl_word) else 0
    by_word: dict[int, list[str]] = {}
    heard_seq: list[str] = []
    ins_after: dict[int, list[str]] = {}
    for ins in insertions:
        ins_after.setdefault(ins["after"], []).append(ins["phone"])
    for q in ins_after.get(-1, []):
        heard_seq.append(q)
        by_word.setdefault(word_of(0), []).append(q)
    for k, ph in enumerate(phones_out):
        sym = None if ph["status"] == "del" else (ph["heard"] or ph["phone"])
        if sym:
            heard_seq.append(sym)
            by_word.setdefault(word_of(k), []).append(sym)
        for q in ins_after.get(k, []):
            heard_seq.append(q)
            by_word.setdefault(word_of(k), []).append(q)
    try:
        pron_guess = " ".join(phones_to_hangul(by_word[w]) for w in sorted(by_word)) or None
    except Exception:  # pragma: no cover
        pron_guess = None
    try:
        free_guess = phones_to_hangul(free) or None
    except Exception:  # pragma: no cover
        free_guess = None

    # 7) 음절 상태
    warn_syl = {t_syl[a] for a in ins_after if 0 <= a < N}
    if -1 in ins_after and N:
        warn_syl.add(t_syl[0])
    syllables = []
    for s, syl in enumerate(target["syllables"]):
        sts = [phones_out[k]["status"] for k in syl["phones"]]
        if any(x in ("sub", "del") for x in sts):
            st = "error"
        elif "weak" in sts or s in warn_syl:
            st = "warn"
        else:
            st = "ok"
        syllables.append({"text": syl["pron"], "orth": syl["text"], "status": st,
                          "phones": list(syl["phones"]), "lip": syl.get("lip")})

    # 8) 음향·입술
    segs = [{"idx": i, "phone": p, "start": fa[i]["start"], "end": fa[i]["end"]} for i, p in enumerate(t_phones)]
    try:
        # 자음 구간도 넘긴다: acoustic 은 모음만 결과에 넣고 자음은 앞뒤 문맥(치조·경구개 자음 옆)으로만 쓴다
        ac = acoustic_mod.analyze(x, SR, segs, voice)
        _reconcile_vowels(ac.get("vowels"), phones_out)
    except Exception as e:  # pragma: no cover - 음향 분석 실패가 전체 결과를 막지 않게
        log.exception("acoustic 분석 실패: %s", e)
        ac = {"duration": round(len(x) / SR, 3), "f0": {"t": [], "hz": []}, "intensity": {"t": [], "db": []},
              "f0_stats": {"mean": None, "min": None, "max": None, "range_st": None, "voiced_ratio": 0.0},
              "loudness": {"mean_db": None, "max_db": None}, "vowels": []}
    try:
        lp = lips_mod.analyze(lips if isinstance(lips, dict) else None, segs)
    except Exception as e:  # pragma: no cover
        log.exception("lips 분석 실패: %s", e)
        lp = {"available": False, "series": None, "checks": [], "score": None}

    # 9) 점수·피드백
    summ = feedback.summarize(phones_out, ac, lp, stype, insertions=insertions, question_kind=qkind, tune=tune)

    tgt = dict(target)
    tgt["sentence_type"] = stype
    tgt["question_kind"] = qkind
    tgt["tune"] = tune
    tgt["pron_requested"] = pron_requested
    tgt["variant_notes"] = variant_notes
    result = {
        "target": tgt,
        "heard": {"phones": heard_seq, "pron_guess": pron_guess,
                  "free": free, "free_pron_guess": free_guess},
        "phones": phones_out,
        "insertions": insertions,
        "syllables": syllables,
        "acoustic": ac,
        "lips": lp,
        "scores": summ["scores"],
        "feedback": summ["feedback"],
        "meta": {
            "elapsed_ms": int(round((time.perf_counter() - t0) * 1000)),
            "model": MODEL_NAME,
            "device": getattr(rec, "device", None),
            "audio_sec": round(len(x) / SR, 3),
            "analyzed_span": [round(off, 3), round(off + len(xr) / SR, 3)],
            "sr_in": int(sr),
            "voice": voice,
            "speech": presence,
        },
    }
    return _jsonable(result)
