"""음소 인식기 — wav2vec2 CTC 방출확률, 자유 인식, 강제정렬, GOP (CONTRACT 3절).

모델: slplab/wav2vec2-xls-r-300m_phone-mfa_korean (models/ko-phone, Wav2Vec2ForCTC).
토크나이저 클래스(Wav2Vec2PhonemeCTCTokenizer)는 phonemizer 의존이라 쓰지 않고 vocab.json 을
직접 읽어 id↔기호를 매핑한다. blank = "[PAD]"(42), 단어 경계 = "|"(40).

설계 요약
---------
* emissions(): 음성 앞뒤에 0.5초 무음 문맥(PAD_FRAMES)을 덧대 모델에 넣고, 덧댄 프레임까지
  포함한 log-softmax (T, V) 를 돌려준다. 프레임 f 의 시각은 (f − PAD_FRAMES) × frame_sec 이며
  decode()/force_align() 이 이 보정과 [0, 음성 길이] 자르기를 해서 초 단위로 돌려준다.
  왜 덧대나: TTS·짧은 녹음처럼 앞뒤 무음 없이 꽉 찬 음성에서 모델이 첫·끝 음소를 놓친다.
  실측(say -v Yuna 단어 20개, greedy 편집거리 합): 덧대기 없음 45 → 0.1초 37 → 0.3초 33 → 0.5초 31
  → 0.6초 29 → 1.0초 32. 0.5초를 쓴다(시간 비용 대비 충분).
  또 모델은 첫 자음 스파이크를 음성 시작 '직전'(덧댄 구간)에 내는 일이 많아서, 덧댄 프레임을
  잘라 버리면 첫 자음이 통째로 사라진다 → 자르지 않고 시각만 보정한다.
* 모델 버릇: 마지막 음절(또는 마지막 음소들)의 스파이크를 실제 발화 끝이 아니라 '입력의 맨 끝
  프레임'에 몰아서 낸다(뒤 무음이 0.1초든 2초든 마지막 1~2프레임). 그래서 시각은 스파이크를 그대로
  쓰지 않고, 에너지로 잡은 '소리 구간' 안에서만 음소가 나올 수 있게 제한한 비터비 정렬로 정한다
  (_timing_path). GOP·post 는 제한 없는 원래 확률로 계산한다.
* decode(): greedy CTC — 프레임별 최댓값, 연속 반복 축약, blank·"|"·특수토큰 제거.
  위 버릇 때문에 생기는 '끝 무음 구간의 중복 토큰'(예: 사과 → S A G oA … oA)은 걸러 내고,
  시각은 인식된 음소열을 같은 방식(소리 구간 제한 비터비)으로 다시 정렬해 매긴다.
* force_align(): CTC 비터비 강제정렬을 numpy 로 직접 구현(torchaudio.functional.forced_align 은
  최신 torchaudio 에서 제거 예정이라 의존하지 않음). blank 프레임 분배 규칙은 _assign_spans().
* GOP: 'CTC 기반 GOP'. torch.nn.functional.ctc_loss 를 배치로 한 번 호출해 log P(정준 음소열) 과,
  위치 i 마다 (a) 삭제 변형 (b) 다른 모든 음소 q(40개 중 39개)로의 치환 변형의 log P 를 구한다.
  margin_i = log P(정준) − max log P(변형_i)   (자연로그, 단위 nat; 양수면 정준이 더 그럴듯함)
  gop      = 100 · sigmoid(GOP_K · (margin_i − GOP_C))
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .phones import PHONES

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DIR = "models/ko-phone"
MODEL_NAME = "slplab/wav2vec2-xls-r-300m_phone-mfa_korean"

SAMPLE_RATE = 16000
PAD_FRAMES = 25            # 앞뒤 무음 문맥 = 25 프레임 × 20ms = 0.5초 (프레임 간격 320샘플의 배수)

# ── GOP 사상 상수 ───────────────────────────────────────────
# gop = 100 / (1 + exp(-GOP_K * (margin - GOP_C)))
# 실측 (macOS `say -v Yuna`, 16k, 위 무음 덧대기; tests/test_recognizer.py docstring 에 표):
#   * 정상 발음 20단어·93음소의 margin: 중앙값 3.7, 75백분위 6.3, 25백분위 −0.9.
#     모델이 '제대로 들은' 음소는 대체로 +2 ~ +9. 단, 이 TTS 의 특정 발음은 모델이 실제로
#     다른 소리로 듣는다(어두 평음 ㄷ/ㅈ/ㅂ → 격음 Th/CHh/Ph, 단독 단어 끝 받침 ㄹ → "R I"/"I",
#     "국"의 ㅜ → ㅡ) — 이런 위치는 −2 ~ −8 로, 하위 25% 가 −0.9 인 이유다.
#   * 최소대립쌍 치환(목표 단어 ≠ 음성 단어, 24쌍)의 해당 위치 margin: 중앙값 −3.4,
#     대부분 −1.7 ~ −9.3. (예: 목표 '불'+'풀' 음성 → B −4.1 alt Ph,
#     목표 '사과'+'다과' 음성 → S −2.7 alt Th, 목표 '짜다'+'자다' 음성 → JJ −6.1 alt CHh)
#   * 위 합성음만으로는 두 분포를 가르는 지점이 margin ≈ +0.5 였다(예전 GOP_C = 0.5).
#   * 사람 낭독으로 다시 맞춤(scripts/eval_human.py, zeroth-korean 240문장 22,296음소): 정상 음소 margin 은
#     중앙값 6.4 지만 아래 꼬리가 길다(10 백분위 0.7, 5 백분위 −1.9, 3 백분위 −3.9). 예전 사상에서는 정상 낭독
#     음소의 9 %가 gop < 45(weak 이하)였다. 사람 정상 분포와 합성음 오류 흉내 분포(중앙값 −4.8)의
#     오거부·오수용이 비슷해지는 곳이 margin ≈ −1 근처라 GOP_C = −1.0 (50점).
#   * GOP_K = 1.0: margin +2 → 95점, 0 → 73점, −1.2 → 45점(파이프라인 weak 기준), −3 → 12점(sub 기준),
#     −5.5 → 1점(데모 오류 흉내 샘플).
GOP_K = 1.0
GOP_C = -1.0

# 강제정렬 구간 분배 상수(프레임 단위, 1프레임 = 20ms)
EDGE_LEAD_MAX = 10         # 첫 음소를 스파이크 앞으로 늘릴 수 있는 최대 길이(0.2초)
EDGE_TAIL_MAX = 15         # 끝 음소를 스파이크 뒤로 늘릴 수 있는 최대 길이(0.3초)
NOENERGY_LEAD = 2          # 에너지 정보가 없을 때 첫 음소 앞 확장
NOENERGY_TAIL_V = 8        # 에너지 정보가 없을 때 끝 음소(모음·공명음) 뒤 확장
NOENERGY_TAIL_C = 3        # 에너지 정보가 없을 때 끝 음소(장애음) 뒤 확장
MIN_SIL_RUN = 3            # 이만큼(60ms) 이어진 무음은 '쉼'으로 보고 경계로 쓴다
CLOSURE_MAX = 6            # 파열·파찰음 앞 폐쇄 무음 / 받침 불파음 뒤 무음을 그 음소에 줄 최대 길이(120ms)

SPEECH_ABS_FLOOR_DB = -65.0  # 이보다 작은 프레임 에너지(dBFS)는 항상 무음
SPEECH_DILATE = 2          # 음소 스파이크 허용 구간 = 소리 프레임 ± 2프레임
_DISALLOW = -1.0e4         # 허용 구간 밖 비-blank 로그확률 (사실상 금지)

_STOPLIKE = {"stop", "affricate"}
_CACHE_SIZE = 16


def _resolve_dir(model_dir: str | Path) -> Path:
    p = Path(model_dir)
    return p if p.is_absolute() else ROOT / p


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def margin_to_gop(margin: float) -> int:
    """CTC margin(nat) → 0~100 정수 점수."""
    if math.isnan(margin):
        return 0
    if margin == math.inf:
        return 100
    if margin == -math.inf:
        return 0
    return int(round(100.0 * _sigmoid(GOP_K * (margin - GOP_C))))


def _em_key(em: np.ndarray) -> bytes:
    a = np.ascontiguousarray(em, dtype=np.float32)
    return hashlib.blake2b(a.tobytes(), digest_size=16).digest() + repr(a.shape).encode()


class Recognizer:
    sample_rate: int = SAMPLE_RATE

    def __init__(self, model_dir: str = DEFAULT_MODEL_DIR, device: str | None = None):
        from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

        self.model_dir = _resolve_dir(model_dir)
        if not (self.model_dir / "vocab.json").exists():
            raise FileNotFoundError(f"모델 폴더를 찾을 수 없습니다: {self.model_dir}")

        # ── 어휘 (vocab.json + added_tokens.json) ──
        vocab: dict[str, int] = json.loads((self.model_dir / "vocab.json").read_text(encoding="utf-8"))
        added = self.model_dir / "added_tokens.json"
        if added.exists():
            for k, v in json.loads(added.read_text(encoding="utf-8")).items():
                vocab.setdefault(k, int(v))
        self.vocab: dict[str, int] = dict(sorted(vocab.items(), key=lambda kv: kv[1]))
        self.id2sym: dict[int, str] = {i: s for s, i in self.vocab.items()}
        self.blank_id: int = self.vocab["[PAD]"]
        self.sep_id: int = self.vocab.get("|", -1)
        # 음소 토큰 = phones.PHONES 에 있는 기호(40개). 나머지("|", [PAD], [UNK], <s>, </s>)는 특수토큰.
        self.phone_ids: list[int] = sorted(self.vocab[s] for s in PHONES if s in self.vocab)
        self._phone_id_set = set(self.phone_ids)

        # ── 모델 ──
        self.feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(str(self.model_dir))
        self.model = Wav2Vec2ForCTC.from_pretrained(str(self.model_dir)).eval()
        cfg = self.model.config
        self._hop = int(np.prod(cfg.conv_stride))            # 320 샘플
        rf = 1
        for k, s in zip(reversed(cfg.conv_kernel), reversed(cfg.conv_stride)):
            rf = (rf - 1) * s + k
        self._win = rf                                       # 400 샘플 (프레임 하나가 보는 구간)
        self.frame_sec: float = self._hop / self.sample_rate  # 0.02초
        self.offset_frames: int = PAD_FRAMES                 # em 앞쪽 무음 문맥 프레임 수

        self._lock = threading.Lock()        # 모델 추론
        self._cache_lock = threading.Lock()  # em → 메타(음성 길이, 프레임별 소리 유무)
        self._meta: OrderedDict[bytes, dict] = OrderedDict()

        self.device: str = self._pick_device(device)
        self.model.to(self.device)
        self.emissions(np.zeros(self.sample_rate // 2, dtype=np.float32))  # 워밍업
        log.info("recognizer ready on %s", self.device)

    # ── 장치 선택 ───────────────────────────────────────────
    def _probe_signal(self) -> np.ndarray:
        """장치 점검용 결정적 신호: 포먼트를 흉내 낸 조화음 모음 3개 + 잡음 파열 (약 1.1초)."""
        sr = self.sample_rate
        rng = np.random.default_rng(1234)
        t = np.arange(int(sr * 0.25)) / sr
        parts = [np.zeros(int(sr * 0.1))]
        for f0, (f1, f2) in [(120, (750, 1300)), (180, (300, 2300)), (140, (350, 800))]:
            sig = np.zeros_like(t)
            for h in range(1, 60):
                f = f0 * h
                if f > 7000:
                    break
                amp = (np.exp(-((f - f1) / 120) ** 2) + 0.6 * np.exp(-((f - f2) / 180) ** 2) + 0.02) / h ** 0.5
                sig += amp * np.sin(2 * np.pi * f * t)
            parts.append(0.2 * sig / np.abs(sig).max())
            parts.append(0.05 * rng.standard_normal(int(sr * 0.08)))
        parts.append(np.zeros(int(sr * 0.1)))
        return np.concatenate(parts).astype(np.float32)

    def _pick_device(self, requested: str | None) -> str:
        """requested(또는 환경변수 TTOBAK_DEVICE)가 없으면 mps 를 시도하되,
        같은 입력의 cpu 결과와 프레임별 argmax 가 98% 이상 일치할 때만 쓴다(1회 자가점검)."""
        requested = requested or os.environ.get("TTOBAK_DEVICE") or None
        if requested:
            if requested == "mps" and not torch.backends.mps.is_available():
                return "cpu"
            return requested
        if not torch.backends.mps.is_available():
            return "cpu"
        try:
            probe = self._pad(self._probe_signal())
            self.model.to("cpu")
            ref = self._forward(probe, "cpu")
            self.model.to("mps")
            got = self._forward(probe, "mps")
            agree = float((ref.argmax(-1) == got.argmax(-1)).mean())
            if np.isfinite(got).all() and agree >= 0.98:
                return "mps"
            log.warning("mps 결과가 cpu 와 달라 cpu 사용 (argmax 일치율 %.3f)", agree)
        except Exception as e:  # pragma: no cover - 장치 문제
            log.warning("mps 사용 불가, cpu 로 대체: %s", e)
        self.model.to("cpu")
        return "cpu"

    # ── 방출확률 ────────────────────────────────────────────
    def _n_frames(self, n_samples: int) -> int:
        if n_samples < self._win:
            return 0
        return (n_samples - self._win) // self._hop + 1

    def _pad(self, w: np.ndarray) -> np.ndarray:
        z = np.zeros(PAD_FRAMES * self._hop, dtype=np.float32)
        return np.concatenate([z, w, z])

    def _forward(self, wav: np.ndarray, device: str) -> np.ndarray:
        x = self.feature_extractor(wav, sampling_rate=self.sample_rate, return_tensors="pt").input_values
        with torch.inference_mode():
            logits = self.model(x.to(device)).logits[0]
            lp = torch.log_softmax(logits.float(), dim=-1)
        return lp.cpu().numpy().astype(np.float32)

    @staticmethod
    def _as_mono_float(wav: np.ndarray) -> np.ndarray:
        w = np.asarray(wav, dtype=np.float32)
        if w.ndim == 2:
            w = w.mean(axis=1) if w.shape[1] <= 8 else w.mean(axis=0)
        w = np.nan_to_num(w.reshape(-1), nan=0.0, posinf=1.0, neginf=-1.0)
        return np.clip(w, -1.0, 1.0)

    def emissions(self, wav: np.ndarray) -> np.ndarray:
        """16k mono float32 [-1,1] → (T, V) log-softmax float32.

        T 는 앞뒤 무음 문맥(offset_frames 개씩)을 포함한 프레임 수. 프레임 f 의 시각 =
        (f − offset_frames) × frame_sec. decode()/force_align() 은 원 음성 기준 초를 돌려준다.
        """
        w = self._as_mono_float(wav)
        padded = self._pad(w)
        with self._lock:
            em = np.ascontiguousarray(self._forward(padded, self.device))
        T = em.shape[0]
        n_orig = self._n_frames(len(w))
        # 프레임별 소리 유무(원 음성 구간만 에너지로 판정, 덧댄 구간은 무음)
        speech = np.zeros(T, dtype=bool)
        lo = PAD_FRAMES
        hi = min(T, PAD_FRAMES + n_orig)
        if hi > lo:
            speech[lo:hi] = self._speech_mask(padded, lo, hi)
        self._remember(em, {"offset": PAD_FRAMES, "n_frames": hi - lo,
                            "dur": len(w) / self.sample_rate, "speech": speech})
        return em

    def _speech_mask(self, padded: np.ndarray, lo: int, hi: int) -> np.ndarray:
        """프레임 [lo, hi) 의 '소리 있음' 판정. 최댓값 대비 35dB 아래(잡음이 크면 바닥+6dB, 최소 −65dBFS)를 무음으로."""
        db = np.empty(hi - lo)
        for j, f in enumerate(range(lo, hi)):
            seg = padded[f * self._hop: f * self._hop + self._win].astype(np.float64)
            db[j] = 10.0 * math.log10(float(np.mean(seg * seg)) + 1e-12) if len(seg) else -120.0
        peak = float(np.percentile(db, 98))
        floor = float(np.percentile(db, 5))
        thr = min(max(peak - 35.0, floor + 6.0), peak - 12.0)
        thr = max(thr, SPEECH_ABS_FLOOR_DB)   # 완전 무음·거의 무음 녹음은 전부 무음으로
        return db > thr

    def _remember(self, em: np.ndarray, meta: dict) -> None:
        key = _em_key(em)
        with self._cache_lock:
            self._meta[key] = meta
            self._meta.move_to_end(key)
            while len(self._meta) > _CACHE_SIZE:
                self._meta.popitem(last=False)

    def _meta_of(self, em: np.ndarray) -> dict:
        """em 의 시간 정보. emissions() 가 만든 em 이면 저장해 둔 값을, 아니면 추정값을 쓴다."""
        with self._cache_lock:
            m = self._meta.get(_em_key(em))
        if m is not None:
            return m
        T = em.shape[0]
        off = PAD_FRAMES if T > 2 * PAD_FRAMES else 0
        n = T - 2 * off
        return {"offset": off, "n_frames": n, "dur": n * self.frame_sec, "speech": None}

    def _sec(self, f: int, meta: dict) -> float:
        return round(min(max((f - meta["offset"]) * self.frame_sec, 0.0), meta["dur"]), 3)

    # ── 자유 인식 ───────────────────────────────────────────
    def decode(self, em: np.ndarray) -> list[dict]:
        """greedy CTC 자유 인식. [{"phone","start","end","conf"}] (특수토큰 제외).

        conf = 그 음소가 최댓값인 프레임들에서 해당 음소 확률 평균.
        start/end = 인식 음소열을 소리 구간 제한 비터비로 다시 정렬한 구간(force_align 과 같은 규칙).
        에너지 정보가 없는 em 이면 최댓값 프레임 구간을 그대로 쓴다.
        """
        em = np.asarray(em, dtype=np.float32)
        if em.ndim != 2 or em.shape[0] == 0:
            return []
        meta = self._meta_of(em)
        speech = meta.get("speech")
        ids = em.argmax(axis=1)
        T = len(ids)
        runs: list[tuple[int, int, int]] = []          # (토큰, 첫 프레임, 끝 프레임 배타)
        t = 0
        while t < T:
            k = int(ids[t])
            t2 = t + 1
            while t2 < T and int(ids[t2]) == k:
                t2 += 1
            if k in self._phone_id_set:
                runs.append((k, t, t2))
            t = t2
        if speech is not None and speech.any() and runs:
            # 끝 무음 구간(마지막 소리 프레임 + 여유 이후)에 나온 토큰이 바로 앞 토큰과 같으면 중복으로 버림
            last_speech = int(np.nonzero(speech)[0][-1]) + SPEECH_DILATE
            kept = [runs[0]]
            for r in runs[1:]:
                if r[1] > last_speech and r[0] == kept[-1][0]:
                    continue
                kept.append(r)
            runs = kept
        if not runs:
            return []
        seq = [r[0] for r in runs]
        conf = [float(np.exp(em[a:b, k]).mean()) for k, a, b in runs]
        phones = [self.id2sym[k] for k in seq]
        lo, hi = meta["offset"], meta["offset"] + meta["n_frames"]
        path = self._timing_path(em, seq, speech, lo, hi)
        if path is not None:
            starts, ends, _ = self._assign_spans(em, seq, phones, path, speech)
        else:
            starts, ends = [r[1] for r in runs], [r[2] for r in runs]
        if hi > lo:
            starts, ends = self._fit_spans(starts, ends, lo, hi)
        return [{"phone": p, "start": self._sec(s0, meta), "end": self._sec(e0, meta), "conf": round(c, 3)}
                for p, s0, e0, c in zip(phones, starts, ends, conf)]

    # ── 강제정렬 ────────────────────────────────────────────
    def _ids(self, phones: list[str]) -> list[int]:
        ids = []
        for p in phones:
            if self.vocab.get(p, -1) not in self._phone_id_set:
                raise ValueError(f"모델 어휘에 없는 음소: {p!r}")
            ids.append(self.vocab[p])
        return ids

    @staticmethod
    def _min_frames(ids: list[int]) -> int:
        """CTC 로 ids 를 내기 위한 최소 프레임 수(같은 음소가 이어지면 사이에 blank 1프레임 필요)."""
        return len(ids) + sum(1 for a, b in zip(ids, ids[1:]) if a == b)

    def _viterbi(self, lp: np.ndarray, ids: list[int]) -> np.ndarray:
        """CTC 비터비. 반환: 프레임별 확장상태 s (짝수 = blank, 홀수 = 토큰 (s-1)//2)."""
        T = lp.shape[0]
        ext = [self.blank_id]
        for k in ids:
            ext += [k, self.blank_id]
        S = len(ext)
        emit = lp[:, ext].astype(np.float64)          # (T, S)
        skip_ok = np.zeros(S, dtype=bool)
        for s in range(2, S):
            skip_ok[s] = ext[s] != self.blank_id and ext[s] != ext[s - 2]
        NEG = -1e30
        alpha = np.full(S, NEG)
        alpha[0] = emit[0, 0]
        if S > 1:
            alpha[1] = emit[0, 1]
        bp = np.zeros((T, S), dtype=np.int8)          # 0 머묾, 1 한 칸, 2 두 칸(blank 건너뜀)
        cand = np.empty((3, S))
        cols = np.arange(S)
        for t in range(1, T):
            cand[0] = alpha
            cand[1, 0] = NEG
            cand[1, 1:] = alpha[:-1]
            cand[2, :2] = NEG
            cand[2, 2:] = alpha[:-2]
            cand[2, ~skip_ok] = NEG
            choice = cand.argmax(axis=0)
            alpha = cand[choice, cols] + emit[t]
            bp[t] = choice
        s = S - 1 if S == 1 or alpha[S - 1] >= alpha[S - 2] else S - 2
        path = np.empty(T, dtype=np.int64)
        for t in range(T - 1, -1, -1):
            path[t] = s
            s -= int(bp[t, s])
        return path

    def _timing_path(self, lp: np.ndarray, ids: list[int], speech: np.ndarray | None,
                     lo: int, hi: int) -> np.ndarray | None:
        """시각용 비터비 경로: 음소(비-blank)는 소리 프레임 ±SPEECH_DILATE 안, 원 음성 구간 [lo, hi) 안에서만.

        모델이 마지막 음절 스파이크를 입력 끝 무음에 몰아 내는 버릇을 바로잡는다. 소리 정보가 없거나
        허용 프레임이 모자라면 None (호출 측이 제한 없는 경로를 쓴다).
        """
        if speech is None or len(speech) != lp.shape[0] or not ids:
            return None
        allowed = speech.copy()
        for d in range(1, SPEECH_DILATE + 1):
            allowed[d:] |= speech[:-d]
            allowed[:-d] |= speech[d:]
        allowed[:lo] = False
        allowed[hi:] = False
        if int(allowed.sum()) < self._min_frames(ids):
            return None
        lpc = np.array(lp, dtype=np.float32, copy=True)
        blank = lpc[:, self.blank_id].copy()
        lpc[~allowed] = _DISALLOW
        lpc[:, self.blank_id] = blank
        return self._viterbi(lpc, ids)

    def _assign_spans(self, lp: np.ndarray, ids: list[int], phones: list[str], path: np.ndarray,
                      speech: np.ndarray | None) -> tuple[list[int], list[int], list[list[int]]]:
        """비터비 경로 → 음소별 [시작, 끝) 프레임.

        CTC 는 음소마다 1~2 프레임 '스파이크'만 내고 나머지는 blank 라서, blank 프레임을 이렇게 나눈다.
          1) 음소 i 의 핵심 구간 = 경로가 그 토큰 상태에 머문 프레임(스파이크). post 는 여기서 잰다.
          2) 이웃한 두 음소 사이 blank 구간은 한 점에서 둘로 가른다. 가르는 점은
             Σ_{앞쪽 프레임} log p(음소 i) + Σ_{뒤쪽 프레임} log p(음소 i+1) 이 최대인 곳
             (blank 가 지배하는 프레임에서도 남은 비-blank 확률이 어느 쪽 소리에 가까운지 알려 준다).
          3) 에너지 정보가 있으면(emissions() 로 만든 em) 사이 구간의 60ms 이상 무음을 '쉼'으로 보아
             경계로 쓴다: 무음 앞 소리 프레임은 앞 음소, 뒤 소리 프레임은 뒤 음소. 무음 자체는
             뒤 음소가 (초성) 파열·파찰음이면 그 폐쇄 구간으로(최대 120ms), 앞 음소가 받침 불파음
             (p t k)이면 그 음소로(최대 120ms) 주고, 나머지(어절 사이 쉼)는 어느 음소에도 넣지 않는다.
          4) 첫 음소는 스파이크 앞쪽 소리 구간(최대 0.2초), 끝 음소는 스파이크 뒤쪽 소리 구간(최대 0.3초)
             까지 늘린다. 에너지 정보가 없으면 앞 2프레임, 뒤 8(모음·공명음)/3(장애음)프레임.
        반환: starts, ends(배타적), core(음소별 스파이크 프레임 목록) — 모두 em 프레임 좌표.
        """
        T = lp.shape[0]
        N = len(ids)
        core: list[list[int]] = [[] for _ in range(N)]
        for t, s in enumerate(path):
            if s % 2 == 1:
                core[(s - 1) // 2].append(t)
        a = [c[0] for c in core]           # 스파이크 첫 프레임
        b = [c[-1] + 1 for c in core]      # 스파이크 끝(배타)
        starts, ends = a[:], b[:]

        for i in range(N - 1):
            g0, g1 = b[i], a[i + 1]        # 사이 blank 구간 [g0, g1)
            L = g1 - g0
            if L <= 0:
                continue
            if ids[i] == ids[i + 1]:
                split = L // 2
            else:
                cl = np.concatenate([[0.0], np.cumsum(lp[g0:g1, ids[i]], dtype=np.float64)])
                cr = np.concatenate([[0.0], np.cumsum(lp[g0:g1, ids[i + 1]], dtype=np.float64)])
                split = int(np.argmax(cl + (cr[-1] - cr)))
            ends[i] = starts[i + 1] = g0 + split
            if speech is None:
                continue
            s0 = s1 = g0                   # 사이 구간에서 가장 긴 무음 [s0, s1)
            t = g0
            while t < g1:
                if speech[t]:
                    t += 1
                    continue
                u = t
                while u < g1 and not speech[u]:
                    u += 1
                if u - t > s1 - s0:
                    s0, s1 = t, u
                t = u
            if s1 - s0 < MIN_SIL_RUN:
                continue
            ends[i], starts[i + 1] = s0, s1
            nxt, prv = PHONES[phones[i + 1]], PHONES[phones[i]]
            if nxt.manner in _STOPLIKE and not nxt.coda:
                starts[i + 1] = max(s0, s1 - CLOSURE_MAX)
            elif prv.coda and prv.manner == "stop":
                ends[i] = min(s1, s0 + CLOSURE_MAX)

        if speech is not None:
            t, lim = a[0], max(0, a[0] - EDGE_LEAD_MAX)
            while t - 1 >= lim and speech[t - 1]:
                t -= 1
            starts[0] = t
            t, lim = b[-1], min(T, b[-1] + EDGE_TAIL_MAX)
            while t < lim and speech[t]:
                t += 1
            ends[-1] = t
        else:
            starts[0] = max(0, a[0] - NOENERGY_LEAD)
            last = PHONES[phones[-1]]
            sonorous = last.kind == "V" or last.manner in ("nasal", "liquid")
            ends[-1] = min(T, b[-1] + (NOENERGY_TAIL_V if sonorous else NOENERGY_TAIL_C))
        return starts, ends, core

    @staticmethod
    def _fit_spans(starts: list[int], ends: list[int], lo: int, hi: int) -> tuple[list[int], list[int]]:
        """구간을 원 음성 프레임 [lo, hi) 안으로 자르고, 겹치지 않게·가능하면 1프레임 이상이 되게 다듬는다."""
        N = len(starts)
        s = [min(max(x, lo), hi) for x in starts]
        e = [min(max(x, lo), hi) for x in ends]
        for i in range(N):                    # 앞에서부터: 단조 + 최소 1프레임
            if i:
                s[i] = max(s[i], e[i - 1])
            e[i] = max(e[i], s[i] + 1)
        for i in range(N - 1, -1, -1):        # 뒤에서부터: hi 안으로 밀어 넣기
            cap = hi if i == N - 1 else s[i + 1]
            e[i] = min(e[i], cap)
            s[i] = max(lo, min(s[i], e[i] - 1))
        return s, e

    def _ctc_logps(self, lp: np.ndarray, seqs: list[list[int]]) -> np.ndarray:
        """여러 음소열의 log P(seq | 음성) — ctc_loss(reduction='none') 배치 호출."""
        T, V = lp.shape
        B = len(seqs)
        maxlen = max(1, max(len(s) for s in seqs))
        tg = torch.zeros((B, maxlen), dtype=torch.long)
        for j, s in enumerate(seqs):
            if s:
                tg[j, :len(s)] = torch.tensor(s, dtype=torch.long)
        tl = torch.tensor([len(s) for s in seqs], dtype=torch.long)
        lpt = torch.from_numpy(np.ascontiguousarray(lp, dtype=np.float32))
        out = np.empty(B, dtype=np.float64)
        chunk = max(1, 16_000_000 // max(1, T * V))   # 펼친 입력이 64MB 를 넘지 않게 나눔
        with torch.inference_mode():
            for j0 in range(0, B, chunk):
                j1 = min(B, j0 + chunk)
                nb = j1 - j0
                nll = F.ctc_loss(lpt.unsqueeze(1).expand(T, nb, V), tg[j0:j1],
                                 torch.full((nb,), T, dtype=torch.long), tl[j0:j1],
                                 blank=self.blank_id, reduction="none", zero_infinity=False)
                out[j0:j1] = -nll.double().numpy()
        out[~np.isfinite(out)] = -np.inf
        return out

    def seq_logps(self, em: np.ndarray, seqs: list[list[str]]) -> list[float]:
        """음소열마다 CTC log P(음소열 | 음성) (nat). 계약 외 보조 함수 — 파이프라인이
        자유 인식의 '삽입' 후보를 확인할 때 쓴다(삽입한 음소열이 목표 음소열보다 그럴듯한가).
        빈 음소열은 '전부 blank' 확률. 불가능한 음소열은 -inf."""
        if not seqs:
            return []
        ids = [self._ids(s) for s in seqs]
        return [float(v) for v in self._ctc_logps(np.asarray(em, dtype=np.float32), ids)]

    def gop_margins(self, em: np.ndarray, phones: list[str]) -> list[dict]:
        """음소별 CTC margin. [{"margin", "alt", "logp", "alt_logp"}] — alt 는 음소 기호 또는 "<del>".

        배치 = 정준 1 + 위치마다 (삭제 1 + 치환 39) → 1 + 40·N 개 음소열을 ctc_loss 한 번(큰 입력은 나눠서)에.
        """
        ids = self._ids(phones)
        N = len(ids)
        seqs: list[list[int]] = [ids]
        meta: list[tuple[int, str]] = []
        for i in range(N):
            seqs.append(ids[:i] + ids[i + 1:])
            meta.append((i, "<del>"))
            for q in self.phone_ids:
                if q != ids[i]:
                    seqs.append(ids[:i] + [q] + ids[i + 1:])
                    meta.append((i, self.id2sym[q]))
        logps = self._ctc_logps(np.asarray(em, dtype=np.float32), seqs)
        canon = float(logps[0])
        best: list[tuple[float, str]] = [(-math.inf, "<del>")] * N
        for (i, sym), v in zip(meta, logps[1:]):
            if v > best[i][0]:
                best[i] = (float(v), sym)
        res = []
        for i in range(N):
            alt_lp, alt = best[i]
            if canon == -math.inf:
                margin = -math.inf
            elif alt_lp == -math.inf:
                margin = math.inf
            else:
                margin = canon - alt_lp
            res.append({"margin": margin, "alt": alt, "logp": canon, "alt_logp": alt_lp})
        return res

    def force_align(self, em: np.ndarray, phones: list[str]) -> list[dict]:
        """목표 음소열 강제정렬 + GOP.

        반환(목표 음소마다, 목표 순서):
          {"phone", "start", "end", "gop", "post", "alt", "alt_margin"}
          start/end : 초(원 음성 기준). blank 프레임 분배 규칙은 _assign_spans().
          post      : (제한 없는) 비터비 경로가 그 음소 토큰에 머문 비-blank 프레임에서 목표 음소 확률 평균(0~1).
          gop       : 0~100 정수. CTC margin 의 시그모이드 사상(모듈 상단 GOP_K/GOP_C 주석).
          alt       : 정준 음소 대신 가장 그럴듯한 대안(음소 기호, 또는 빠진 것이 더 그럴듯하면 "<del>").
          alt_margin: log P(정준) − log P(대안) (nat). 음수면 대안이 더 그럴듯함 = 그 소리로 들림.
        음성이 음소 수보다 짧아 정렬이 불가능하면 균등 분할 + gop 0, alt None 으로 돌려준다.
        em 은 emissions() 가 돌려준 배열을 그대로 넘길 것(dtype 변환·복사는 괜찮음). 잘라 내거나 값을
        바꾸면 저장해 둔 소리 구간 정보를 못 찾아 '에너지 없는' 추정 규칙으로 시각을 매긴다.
        """
        if not phones:
            return []
        ids = self._ids(phones)
        lp = np.asarray(em, dtype=np.float32)
        meta = self._meta_of(lp)
        lo, hi = meta["offset"], meta["offset"] + meta["n_frames"]
        T, N = lp.shape[0], len(ids)
        fs = self.frame_sec

        if T < self._min_frames(ids) or hi <= lo:
            dur = meta["dur"]
            return [{"phone": p, "start": round(dur * i / N, 3), "end": round(dur * (i + 1) / N, 3),
                     "gop": 0, "post": 0.0, "alt": None, "alt_margin": None} for i, p in enumerate(phones)]

        speech = meta.get("speech")
        if speech is not None and len(speech) != T:
            speech = None
        free_path = self._viterbi(lp, ids)                       # 모델 확률 그대로의 정렬 → post
        core = [[] for _ in ids]
        for t, s in enumerate(free_path):
            if s % 2 == 1:
                core[(s - 1) // 2].append(t)
        path = self._timing_path(lp, ids, speech, lo, hi)        # 소리 구간 제한 정렬 → 시각
        if path is None:
            path, speech = free_path, None
        starts, ends, _ = self._assign_spans(lp, ids, phones, path, speech)
        starts, ends = self._fit_spans(starts, ends, lo, hi)
        margins = self.gop_margins(lp, phones)

        out = []
        for i, p in enumerate(phones):
            post = float(np.exp(lp[core[i], ids[i]]).mean()) if core[i] else 0.0
            m = margins[i]["margin"]
            out.append({"phone": p,
                        "start": round((starts[i] - lo) * fs, 3),
                        "end": round(min((ends[i] - lo) * fs, meta["dur"]), 3),
                        "gop": margin_to_gop(m),
                        "post": round(post, 3),
                        "alt": margins[i]["alt"],
                        "alt_margin": round(m, 3) if math.isfinite(m) else (99.0 if m > 0 else -99.0)})
        return out


# ── 프로세스 단일 인스턴스 ──────────────────────────────────
_INSTANCE: Recognizer | None = None
_INSTANCE_LOCK = threading.Lock()


def get_recognizer() -> Recognizer:
    """프로세스당 하나의 Recognizer (처음 호출 때 로드, 스레드 안전)."""
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = Recognizer()
    return _INSTANCE


def is_loaded() -> bool:
    """모델이 이미 메모리에 올라왔는지 (/api/health 의 "loaded"|"loading" 판단용)."""
    return _INSTANCE is not None
