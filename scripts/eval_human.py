"""사람 낭독 음성으로 '정상 발음 오탐률'을 잰다 (재실행 가능).

데이터: Hugging Face  Bingsu/zeroth-korean  test split (CC BY 4.0, 16 kHz, 한국어 성인 뉴스·소설 낭독).
        datasets-server API 로 행(텍스트 + flac 주소)을 받아 .review/human/ 에 저장한다(.gitignore 대상).
        flac 주소는 서명이 만료되므로 받은 즉시 내려받는다.

    .venv/bin/python -I scripts/eval_human.py download [--n 240]   # 문장 n개(행 번호를 고르게 퍼뜨림)
    .venv/bin/python -I scripts/eval_human.py eval [--tag _x]       # 문장·단어 분석 → .review/human/sent_x.jsonl 등
    .venv/bin/python -I scripts/eval_human.py sens [--tag _x]       # 합성음 오류 흉내 검출률(macOS say, 아래 4)
    .venv/bin/python -I scripts/eval_human.py report [--tag _x]     # 요약 표(보정셋·검증셋)
    .venv/bin/python -I scripts/eval_human.py all                   # 위 단계 전부(약 20분)

평가 방식
--------
* 문장: pipeline.analyze(sentence_type='statement'). 낭독은 정상 발음이라고 보고, 음소 상태가 ok 가 아닌 비율
  (sub/del/weak 각각)과 채택된 삽입 수, '오류 카드'(소리(음소·삽입)에 대한 error·warn 카드 — 칭찬·억양·크기·입술·
  정보 카드 제외) 수를 잰다.
* 단어: 문장의 강제정렬 시각으로 어절을 잘라(앞뒤 0.15초 여유) 단독 입력으로 다시 분석한다(sentence_type='word').
  고르는 어절: words.json 에 있는 낱말이거나 2~3음절 어절(문장마다 최대 5개). 이어 말하기로 어절 가장자리 소리가
  바뀐 어절('삼 월'[사뭘], '밥 먹어요'[밤머거요])은 단독 발음과 비교할 수 없으므로 뺀다. 두 조건을 같이 잰다:
    raw   — 잘라 낸 그대로(여유 0.15초에 이웃 어절 소리가 섞일 수 있음)
    clean — 어절 구간 ±0.02초 밖의 이웃 어절 소리는 30 ms 에 걸쳐 줄여 무음으로(단독 녹음에 더 가까움)
  같은 어절을 문장 속에서 판정한 결과와도 비교한다(잘라 내기 자체의 영향).
* 보정셋/검증셋: 행 번호 SPLIT_ROW 앞쪽을 보정셋, 뒤쪽을 검증셋으로 쓴다. 이 test split 은 화자별로 묶여 있어
  (F0 중앙값으로 본 묶음: 남 ~130 Hz, 여 ~240 Hz, 남 ~105 Hz | 여 ~240 Hz, 여 ~200 Hz, 남 ~120 Hz) 경계에서
  나누면 화자가 겹치지 않는다.
* 원인 분류(오탐 음소마다, 휴리스틱):
    connect  어절 경계(앞 어절 끝 받침 / 뒤 어절 첫소리)에서 이어 말하기 규칙으로 설명되는 대치·탈락
    g2p      같은 어절 안에서 표준발음법의 다른 실현(경음화·ㅎ 약화·ㄴ/ㄹ 동화 등)으로 설명되는 것
    threshold margin 이 문턱 근처(−1.5 < margin < 문턱)이거나 weak — 문턱 조정으로 바뀔 수 있는 것
    model    그 밖(모델이 뚜렷하게 다른 소리로 들음)
* 검출률(sens): 사람 오류 녹음이 없어 macOS 합성음 9종 × 최소대립쌍 44개(목표 낱말 대신 오류 낱말을 말함)로
  근사한다. 같은 음성의 정상 낱말도 함께 분석해 '오류 쪽만 잡은 짝'의 비율(구별)을 낸다.

내려받은 오디오는 신뢰할 수 없는 데이터로 다룬다: 파일 이름은 행 번호로 직접 정하고, soundfile 로 읽기만 한다.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / ".review" / "human"
AUDIO = DATA / "audio"
ROWS = DATA / "rows.jsonl"

DATASET = "Bingsu/zeroth-korean"
API = "https://datasets-server.huggingface.co/rows"
TOTAL_ROWS = 457            # test split 행 수 (API 의 num_rows_total)
SPLIT_ROW = 222             # 이 행 번호 미만 = 보정셋, 이상 = 검증셋(실측 F0 로 본 화자 묶음의 경계)
PAD_SEC = 0.15              # 단어 자르기 앞뒤 여유
GUARD_SEC = 0.02            # clean 조건: 어절 구간 밖으로 그대로 남길 소리
TAPER_SEC = 0.03            # clean 조건: 그 바깥을 이 시간 동안 줄여 0 으로
WORDS_PER_SENT = 5          # 문장마다 단어 평가 최대 개수(words.json 낱말 먼저, 나머지는 고르게)
HANGUL_ONLY = re.compile(r"^[가-힣 ]+$")
CARD_EXCLUDE = {"praise", "intonation", "loudness", "lips"}


def _jl_read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _jl_write(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(p)


# ── 1) 내려받기 ───────────────────────────────────────────
def _fetch_page(offset: int, length: int) -> list[dict]:
    q = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": "test",
                                "offset": offset, "length": length})
    with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    out = []
    for row in d.get("rows", []):
        rr = row.get("row") or {}
        audio = rr.get("audio") or []
        src = audio[0].get("src") if audio and isinstance(audio[0], dict) else None
        out.append({"row": int(row["row_idx"]), "text": str(rr.get("text") or "").strip(), "src": src})
    return out


def download(n: int) -> None:
    from server import words as W
    AUDIO.mkdir(parents=True, exist_ok=True)
    have = {r["row"]: r for r in _jl_read(ROWS)}
    # 행 번호를 고르게 퍼뜨린 후보(화자가 다양하도록). 쓸 수 없는 문장(숫자·영문)은 이웃 행으로 채운다.
    step = TOTAL_ROWS / max(1, n)
    wanted = sorted({int(i * step) for i in range(n)})
    pages: dict[int, list[dict]] = {}

    def row_info(i: int) -> dict | None:
        p0 = (i // 100) * 100
        if p0 not in pages:
            pages[p0] = _fetch_page(p0, 100)
            time.sleep(0.3)
        return next((r for r in pages[p0] if r["row"] == i), None)

    def usable(text: str) -> bool:
        if not HANGUL_ONLY.match(text):
            return False
        try:
            W.build_target(text)
        except ValueError:
            return False
        return True

    chosen: list[int] = []
    taken: set[int] = set(have)
    for i in wanted:
        for j in [i] + [i + d for d in (1, -1, 2, -2, 3, -3)]:
            if 0 <= j < TOTAL_ROWS and j not in chosen:
                if j in have:
                    chosen.append(j)
                    break
                info = row_info(j)
                if info and info["src"] and usable(info["text"]):
                    chosen.append(j)
                    break
    rows = dict(have)
    for j in chosen:
        if j in rows and (DATA / rows[j]["file"]).exists():
            continue
        info = row_info(j)
        dst = AUDIO / f"{j:05d}.flac"
        # 서명 주소는 만료되므로 페이지를 받은 즉시 내려받는다(실패하면 페이지를 다시 받아 한 번 더)
        for attempt in range(2):
            try:
                with urllib.request.urlopen(info["src"], timeout=60) as r:
                    data = r.read()
                dst.write_bytes(data)
                break
            except Exception as e:  # noqa: BLE001
                if attempt:
                    print(f"  행 {j} 내려받기 실패: {e}")
                    dst = None
                    break
                pages.pop((j // 100) * 100, None)
                info = row_info(j)
        if dst is None:
            continue
        rows[j] = {"row": j, "text": info["text"], "file": str(dst.relative_to(DATA))}
        taken.add(j)
    _jl_write(ROWS, [rows[k] for k in sorted(rows)])
    print(f"문장 {len(rows)}개 저장: {ROWS}  (오디오 {AUDIO})")



# ── 2) 분석 ───────────────────────────────────────────────
def _split(row: int) -> str:
    return "cal" if row < SPLIT_ROW else "val"


def _voice(x, sr) -> str:
    """성별 참고치(포먼트용)만 고른다 — 음소 판정에는 영향 없음."""
    import numpy as np
    import parselmouth
    f = parselmouth.Sound(x.astype("float64"), sampling_frequency=sr).to_pitch_ac(
        pitch_floor=60, pitch_ceiling=500).selected_array["frequency"]
    f = f[f > 0]
    return "female" if len(f) and float(np.median(f)) > 165 else "male"


def _word_index(pron: str) -> list[int]:
    from server import pipeline
    return pipeline._syl_words(pron)


def _issue(card: dict) -> bool:
    """'오류 카드' = 소리(음소·삽입)에 대한 error/warn 카드. 칭찬·억양·크기·입술 카드와 정보(info) 카드는 뺀다."""
    return card.get("kind") not in CARD_EXCLUDE and card.get("level") in ("error", "warn")


def _raw_record(res: dict, em, rec) -> dict:
    """판정 결과 + 다시 판정해 볼 수 있는 근거(대안 음소·margin·자유 인식 짝·삽입 후보 gain)."""
    from server import align as align_mod
    t = res["target"]
    tp = t["phones"]
    syl_word = _word_index(t["pron"])
    free = res["heard"]["free"]
    ops = align_mod.align(tp, free)
    nw: dict[int, tuple] = {}
    cands: list[tuple[int, str]] = []
    last = -1
    for o in ops:
        if o["t"] is not None:
            last = o["t"]
            nw[o["t"]] = (o["op"], free[o["h"]] if o["h"] is not None else None)
        else:
            cands.append((last, free[o["h"]]))
    gains: list[float | None] = []
    if cands and em is not None:
        seqs = [tp[:a + 1] + [q] + tp[a + 1:] for a, q in cands]
        lps = rec.seq_logps(em, [tp] + seqs)
        gains = [round(v - lps[0], 3) if math.isfinite(v) and math.isfinite(lps[0]) else None for v in lps[1:]]
    N = len(tp)
    phones = []
    for p in res["phones"]:
        i = p["idx"]
        w = syl_word[p["syl"]] if p["syl"] < len(syl_word) else 0
        wprev = syl_word[res["phones"][i - 1]["syl"]] if i > 0 else -1
        wnext = syl_word[res["phones"][i + 1]["syl"]] if i + 1 < N else -1
        phones.append({
            "idx": i, "phone": p["phone"], "jamo": p["jamo"], "syl": p["syl"], "word": w,
            "wfirst": wprev != w, "wlast": wnext != w, "coda": p.get("coda"), "initial": p.get("initial"),
            "status": p["status"], "heard": p["heard"], "gop": p["gop"], "alt": p.get("alt"),
            "alt_margin": p.get("alt_margin"), "free_op": nw.get(i, ("del", None))[0],
            "free_heard": nw.get(i, ("del", None))[1], "start": p["start"], "end": p["end"],
            "variant": p.get("variant"),
            "prev": tp[i - 1] if i else None, "next": tp[i + 1] if i + 1 < N else None,
        })
    cards = [{"kind": f.get("kind"), "level": f["level"], "title": f["title"]} for f in res["feedback"]]
    return {
        "pron": t["pron"], "pron_requested": t.get("pron_requested"), "variant_notes": t.get("variant_notes", []),
        "phones": phones,
        "insertions": [{"after": x["after"], "phone": x["phone"], "margin": x.get("margin")} for x in res["insertions"]],
        "ins_cands": [{"after": a, "phone": q, "gain": g, "edge": a < 0 or a >= N - 1}
                      for (a, q), g in zip(cands, gains or [None] * len(cands))],
        "cards": cards,
        "n_cards": sum(1 for c in cards if _issue(c)),
        "n_err_cards": sum(1 for c in cards if _issue(c) and c["level"] == "error"),
        "scores": res["scores"],
        "free": free,
    }


def _word_clips(x, sr: int, text: str, res: dict, wordset: set[str]) -> list[dict]:
    """문장 분석 결과의 시각으로 어절을 잘라 단독 입력 후보를 만든다."""
    import numpy as np
    from server import g2p
    orth = g2p._words(text)
    pron_words = res["target"]["pron"].split()
    if len(orth) != len(pron_words):
        return []
    syl_word = _word_index(res["target"]["pron"])
    spans: dict[int, list[float]] = {}
    for p in res["phones"]:
        w = syl_word[p["syl"]]
        s = spans.setdefault(w, [p["start"], p["end"]])
        s[0], s[1] = min(s[0], p["start"]), max(s[1], p["end"])
    dur = len(x) / sr
    out = []
    for k, ow in enumerate(orth):
        nsyl = len(ow)
        if not (ow in wordset or 2 <= nsyl <= 3):
            continue
        iso = g2p.to_pron(ow)
        sp = pron_words[k]
        if len(iso) != len(sp) or not iso:
            continue
        # 이어 말하기로 어절 가장자리(첫 음절 첫소리·끝 음절 받침)가 바뀐 어절은 단독 발음과 비교할 수 없다
        from server.phones import decompose
        a0, b0 = decompose(iso[0]), decompose(sp[0])
        a1, b1 = decompose(iso[-1]), decompose(sp[-1])
        if a0[0] != b0[0] or a1[2] != b1[2]:
            continue
        s, e = spans[k]
        if e - s < 0.08:
            continue
        lo, hi = max(0.0, s - PAD_SEC), min(dur, e + PAD_SEC)
        i0, i1 = int(lo * sr), int(hi * sr)
        raw = x[i0:i1].astype("float32").copy()
        # clean: 어절 구간 ±GUARD 밖은 TAPER 동안 줄여 0 으로
        t = (np.arange(i1 - i0) + i0) / sr
        g = np.ones_like(raw)
        left, right = s - GUARD_SEC, e + GUARD_SEC
        g = np.where(t < left, np.clip(1 - (left - t) / TAPER_SEC, 0, 1), g)
        g = np.where(t > right, np.clip(1 - (t - right) / TAPER_SEC, 0, 1), g)
        out.append({"k": k, "text": ow, "in_words": ow in wordset, "nsyl": nsyl,
                    "span": [round(s, 3), round(e, 3)], "raw": raw, "clean": (raw * g).astype("float32")})
    if len(out) > WORDS_PER_SENT:
        first = [c for c in out if c["in_words"]][:WORDS_PER_SENT]
        rest = [c for c in out if not c["in_words"]]
        need = WORDS_PER_SENT - len(first)
        pick = [rest[round(i * (len(rest) - 1) / max(1, need - 1))] for i in range(need)] if need > 0 else []
        keep = {id(c) for c in first + pick}
        out = [c for c in out if id(c) in keep]
    return out


def _rec_input(x, sr: int):
    """파이프라인이 인식기에 넣는 것과 같은 음성(16k mono, 긴 앞뒤 무음 자름) — 삽입 후보 gain 재계산용."""
    from server import pipeline
    y = pipeline.prepare_audio(x, sr)
    return pipeline.trim_for_recognizer(y)[1] if hasattr(pipeline, "trim_for_recognizer") else y


def evaluate(limit: int | None = None, words_too: bool = True, tag: str = "") -> None:
    import soundfile as sf
    from server import pipeline, recognizer
    from server import words as W
    rec = recognizer.get_recognizer()
    wordset = {w["text"] for w in W.load_words() if " " not in w["text"]}
    rows = _jl_read(ROWS)[:limit] if limit else _jl_read(ROWS)
    sent_out: list[dict] = []
    word_out: list[dict] = []
    t0 = time.time()
    for n, r in enumerate(rows):
        x, sr = sf.read(DATA / r["file"], dtype="float32", always_2d=False)
        voice = _voice(x, sr)
        res = pipeline.analyze(x, sr, r["text"], None, None, voice=voice, sentence_type="statement")
        base = {"row": r["row"], "split": _split(r["row"]), "text": r["text"], "voice": voice,
                "sec": round(len(x) / sr, 2)}
        if "error" in res:
            sent_out.append({**base, "error": res["error"]})
            continue
        em = rec.emissions(_rec_input(x, sr))
        sent_out.append({**base, **_raw_record(res, em, rec), "elapsed_ms": res["meta"]["elapsed_ms"]})
        if words_too:
            for c in _word_clips(x, sr, r["text"], res, wordset):
                for cond in ("raw", "clean"):
                    wr = pipeline.analyze(c[cond], sr, c["text"], None, None, voice=voice, sentence_type="word")
                    wb = {"row": r["row"], "split": base["split"], "k": c["k"], "text": c["text"],
                          "cond": cond, "in_words": c["in_words"], "nsyl": c["nsyl"], "span": c["span"]}
                    if "error" in wr:
                        word_out.append({**wb, "error": wr["error"]})
                        continue
                    wem = rec.emissions(_rec_input(c[cond], sr))
                    word_out.append({**wb, **_raw_record(wr, wem, rec)})
        if (n + 1) % 20 == 0:
            print(f"  {n + 1}/{len(rows)} 문장 ({time.time() - t0:.0f}초)", flush=True)
    _jl_write(DATA / f"sent{tag}.jsonl", sent_out)
    if words_too:
        _jl_write(DATA / f"words{tag}.jsonl", word_out)
    print(f"분석 끝: 문장 {len(sent_out)}, 단어 {len(word_out)} ({time.time() - t0:.0f}초)")


# ── 3) 요약 ───────────────────────────────────────────────
BAD = ("sub", "del", "weak")


def _label(p: dict) -> str:
    from server.phones import jamo_of
    t = ("받침" if p.get("coda") else "") + p["jamo"]
    if p["status"] == "sub":
        return f"{t}→{jamo_of(p['heard']) if p['heard'] else '?'}"
    if p["status"] == "del":
        return f"{t}→(빠짐)"
    return f"{t}(약함)"


def cause(p: dict, sub_margin: float) -> str:
    """오탐 원인 분류(휴리스틱, 모듈 docstring)."""
    from server.phones import PHONES
    st, t, h = p["status"], p["phone"], p.get("heard")
    m = p.get("alt_margin")
    T = PHONES.get(t)
    H = PHONES.get(h) if h else None
    edge = (p.get("wlast") and T is not None and not T.is_vowel and p.get("coda")) or \
           (p.get("wfirst") and T is not None and not T.is_vowel)
    if edge and st in ("sub", "del") and p.get("word", 0) is not None:
        # 어절 경계의 자음: 앞 어절 끝 받침 / 뒤 어절 첫 자음 — 이어 말하기(경음화·비음화·연음·격음화·ㅎ 약화)
        if (p.get("wfirst") and p.get("idx", 0) > 0) or (p.get("wlast") and p.get("next") is not None):
            return "connect"
    if T is not None and not T.is_vowel:
        if t == "H" and st in ("del", "sub"):
            return "g2p"            # 공명음·모음 사이 ㅎ 약화(표준발음은 ㅎ 유지, 실제로는 흔히 약화)
        if H is not None and not H.is_vowel and T.place == H.place and T.manner == H.manner \
                and {T.phonation, H.phonation} == {"lenis", "tense"} and p.get("prev") in ("L", "N", "M", "NG", "t", "p", "k"):
            return "g2p"            # 경음화 여부(한자어·사이시옷·관형형 등)
        if st == "sub" and t in ("N", "R", "L") and h in ("N", "R", "L"):
            return "g2p"            # ㄴ·ㄹ 동화(유음화·ㄹ 비음화) 실현 차이
    if st == "weak" or (isinstance(m, (int, float)) and -1.5 < m < sub_margin):
        return "threshold"
    return "model"


def _rate(recs: list[dict]) -> dict:
    n = Counter()
    for r in recs:
        for p in r["phones"]:
            n["N"] += 1
            if p["status"] != "ok":
                n[p["status"]] += 1
        n["ins"] += len(r["insertions"])
        n["items"] += 1
        nc = sum(1 for c in r["cards"] if _issue(c))
        ne = sum(1 for c in r["cards"] if _issue(c) and c["level"] == "error")
        n["cards"] += nc
        n["err_cards"] += ne
        n["any_card"] += nc > 0
        n["any_err_card"] += ne > 0
        n["variant"] += sum(1 for p in r["phones"] if p.get("variant"))
    return n


def _fmt_rate(n: Counter) -> str:
    N = max(1, n["N"])
    I = max(1, n["items"])
    return (f"항목 {n['items']:4d} 음소 {n['N']:6d} | sub {100 * n['sub'] / N:4.1f}% del {100 * n['del'] / N:4.1f}% "
            f"weak {100 * n['weak'] / N:4.1f}% (sub+del {100 * (n['sub'] + n['del']) / N:4.1f}%) "
            f"| 삽입/항목 {n['ins'] / I:.2f} | 카드/항목 {n['cards'] / I:.2f} "
            f"| 오류카드≥1 {100 * n['any_card'] / I:4.1f}% (error 수준≥1 {100 * n['any_err_card'] / I:4.1f}%)"
            + (f" | 정상 변이로 인정 {100 * n['variant'] / N:3.1f}%" if n["variant"] else ""))


def report(tag: str = "", top: int = 25) -> None:
    from server import pipeline
    sents = [r for r in _jl_read(DATA / f"sent{tag}.jsonl") if "error" not in r]
    errs = [r for r in _jl_read(DATA / f"sent{tag}.jsonl") if "error" in r]
    wrecs = _jl_read(DATA / f"words{tag}.jsonl")
    words_ok = [r for r in wrecs if "error" not in r]
    print(f"== 사람 낭독(zeroth-korean test) 정상 발음 오탐 — 문장 {len(sents)}개 (분석 거부 {len(errs)}) ==")
    for sp in ("cal", "val", None):
        sub = [r for r in sents if sp is None or r["split"] == sp]
        print(f"  문장 {'보정셋' if sp == 'cal' else '검증셋' if sp == 'val' else '전체 '}: {_fmt_rate(_rate(sub))}")
    if words_ok:
        for cond in ("raw", "clean"):
            for sp in ("cal", "val", None):
                sub = [r for r in words_ok if r["cond"] == cond and (sp is None or r["split"] == sp)]
                print(f"  단어[{cond:5s}] {'보정셋' if sp == 'cal' else '검증셋' if sp == 'val' else '전체 '}: {_fmt_rate(_rate(sub))}")
        rej = Counter(r["error"] for r in wrecs if "error" in r)
        if rej:
            print("  단어 분석 거부:", dict(rej))
        inw = [r for r in words_ok if r["in_words"] and r["cond"] == "clean"]
        if inw:
            print(f"  (words.json 낱말만, clean) {_fmt_rate(_rate(inw))}")
        # 같은 어절을 문장 속에서 판정했을 때와 잘라 내 단독으로 판정했을 때 비교(잘라 내기 자체의 영향)
        by_row = {r["row"]: r for r in sents}
        for cond in ("raw", "clean"):
            c = Counter()
            for w in (x for x in words_ok if x["cond"] == cond and x["row"] in by_row):
                ph_in = [p for p in by_row[w["row"]]["phones"] if p["word"] == w["k"]]
                bad_in = sum(p["status"] in ("sub", "del") for p in ph_in)
                bad_w = [p for p in w["phones"] if p["status"] in ("sub", "del")]
                N = len(w["phones"])
                c["items"] += 1
                c["n_in"] += len(ph_in)
                c["b_in"] += bad_in
                c["any_in"] += bad_in > 0
                c["n_w"] += N
                c["b_w"] += len(bad_w)
                c["any_w"] += bool(bad_w)
                c["edge"] += sum(p["idx"] in (0, N - 1) for p in bad_w)
            if c["items"]:
                print(f"  같은 어절 비교[{cond}]: 문장 속 sub+del {100 * c['b_in'] / max(1, c['n_in']):.1f}% "
                      f"(어절에 1개 이상 {100 * c['any_in'] / c['items']:.1f}%) → 잘라 낸 단독 {100 * c['b_w'] / max(1, c['n_w']):.1f}% "
                      f"(1개 이상 {100 * c['any_w'] / c['items']:.1f}%), 단독 오탐 중 첫·끝 음소 {100 * c['edge'] / max(1, c['b_w']):.0f}%")

    def patterns(recs: list[dict], title: str) -> None:
        pat = Counter()
        ctx: dict[str, Counter] = defaultdict(Counter)
        causes = Counter()
        by_cause_ex: dict[str, Counter] = defaultdict(Counter)
        tot = 0
        for r in recs:
            for p in r["phones"]:
                if p["status"] == "ok":
                    continue
                tot += 1
                lab = _label(p)
                pat[lab] += 1
                pos = "어절첫" if p["wfirst"] else ("어절끝" if p["wlast"] else "어절안")
                ctx[lab][f"{p['prev'] or '#'}_{p['next'] or '#'}/{pos}"] += 1
                c = cause(p, pipeline.SUB_MARGIN)
                causes[c] += 1
                by_cause_ex[c][lab] += 1
        print(f"\n  [{title}] 오탐 음소 {tot}개 — 원인 분류:",
              ", ".join(f"{k} {v} ({100 * v / max(1, tot):.0f}%)" for k, v in causes.most_common()))
        for c, ex in by_cause_ex.items():
            print(f"     {c:9s}: {', '.join(f'{k} {v}' for k, v in ex.most_common(8))}")
        print(f"  [{title}] 상위 오탐 패턴(목표→들림: 건수, 대표 문맥 앞_뒤/위치)")
        for lab, c in pat.most_common(top):
            print(f"     {lab:14s} {c:4d}  {', '.join(f'{k}×{v}' for k, v in ctx[lab].most_common(3))}")
        ins = Counter(f"+{x['phone']}" for r in recs for x in r["insertions"])
        if ins:
            print(f"  [{title}] 채택된 삽입: {', '.join(f'{k} {v}' for k, v in ins.most_common(10))}")

    var = Counter(p["variant"] for r in sents for p in r["phones"] if p.get("variant"))
    if var:
        print("\n  [문장] 정상 변이로 인정(ok)한 음소:", ", ".join(f"{k} {v}" for k, v in var.most_common()))
    patterns(sents, "문장")
    if words_ok:
        patterns([r for r in words_ok if r["cond"] == "clean"], "단어 clean")


# ── 4) 검출률(민감도) 확인: macOS 합성음 9종 × 오류 흉내 44쌍 ─────────────
# 사람 오류 녹음이 없어서, 목표 낱말 대신 오류 낱말을 합성음으로 말하게 해 '잡아야 할 오류'의 근사로 쓴다.
# 'Eddy (한국어(대한민국))'처럼 전체 이름을 써야 한국어로 말한다(짧은 이름은 영어 음성으로 해석돼 빈 파일).
TTS_DIR = DATA / "tts"
TTS_VOICES = ["Yuna", "Eddy", "Flo", "Reed", "Sandy", "Shelley", "Grandma", "Grandpa", "Rocko"]
TTS_MALE = {"Eddy", "Reed", "Grandpa", "Rocko"}
# (key, 목표 철자, 목표 pron, 말할 텍스트, 오류 위치 idx, 기대 판정 (sub, 들린 음소) | (del,) | (ins, 음소))
PAIRS = [
    ("bul_pul", "불", "불", "풀", [0], ("sub", "Ph")), ("bul_ppul", "불", "불", "뿔", [0], ("sub", "BB")),
    ("pul_bul", "풀", "풀", "불", [0], ("sub", "B")), ("dal_tal", "달", "달", "탈", [0], ("sub", "Th")),
    ("ttal_dal", "딸", "딸", "달", [0], ("sub", "D")), ("kkul_gul", "꿀", "꿀", "굴", [0], ("sub", "G")),
    ("jada_chada", "자다", "자다", "차다", [0], ("sub", "CHh")), ("jjada_jada", "짜다", "짜다", "자다", [0], ("sub", "J")),
    ("ppang_bang", "빵", "빵", "방", [0], ("sub", "B")), ("ssal_sal", "쌀", "쌀", "살", [0], ("sub", "S")),
    ("sal_ssal", "살", "살", "쌀", [0], ("sub", "SS")), ("sori_dori", "소리", "소리", "도리", [0], ("sub", "D")),
    ("saja_daja", "사자", "사자", "다자", [0], ("sub", "D")), ("sagwa_dagwa", "사과", "사과", "다과", [0], ("sub", "D")),
    ("ssaum_ttaum", "싸움", "싸움", "따움", [0], ("sub", "DD")), ("bada_mada", "바다", "바다", "마다", [0], ("sub", "M")),
    ("bal_mal", "발", "발", "말", [0], ("sub", "M")), ("da_na", "다", "다", "나", [0], ("sub", "N")),
    ("mal_bal", "말", "말", "발", [0], ("sub", "B")), ("na_da", "나", "나", "다", [0], ("sub", "D")),
    ("gak_gang", "각", "각", "강", [2], ("sub", "NG")), ("bap_bam", "밥", "밥", "밤", [2], ("sub", "M")),
    ("gang_ga", "강", "강", "가", [2], ("del",)), ("bam_ba", "밤", "밤", "바", [2], ("del",)),
    ("nun_nu", "눈", "눈", "누", [2], ("del",)), ("gom_go", "곰", "곰", "고", [2], ("del",)),
    ("hello_coda", "안녕하세요", "안녕하세요", "아녕하세요", [1], ("del",)), ("bap_ba", "밥", "밥", "바", [2], ("del",)),
    ("yagu_agu", "야구", "야구", "아구", [0], ("sub", "A")), ("gwaja_gaja", "과자", "과자", "가자", [1], ("sub", "A")),
    ("byeol_beol", "별", "별", "벌", [1], ("sub", "EO")), ("yeou_eou", "여우", "여우", "어우", [0], ("sub", "EO")),
    ("gwi_gi", "귀", "귀", "기", [1], ("sub", "I")), ("mwo_meo", "뭐", "뭐", "머", [1], ("sub", "EO")),
    ("uyu_uu", "우유", "우유", "우우", [1], ("sub", "U")), ("oi_eoi", "오이", "오이", "어이", [0], ("sub", "EO")),
    ("gogi_geogi", "고기", "고기", "거기", [1], ("sub", "EO")), ("gudu_godu", "구두", "구두", "고두", [1], ("sub", "O")),
    ("geune_gune", "그네", "그네", "구네", [1], ("sub", "U")), ("ima_ime", "이마", "이마", "이메", [2], ("sub", "E")),
    ("ai_ae", "아이", "아이", "아에", [1], ("sub", "E")), ("nara_nada", "나라", "나라", "나다", [2], ("sub", "D")),
    ("dari_dadi", "다리", "다리", "다디", [2], ("sub", "D")), ("ap_apeu", "앞", "압", "아프", [1], ("ins", "EU")),
]


def _tts_wav(voice: str, key: str, text: str, pad: float = 0.4) -> Path | None:
    """say(macOS) → 16 kHz mono wav (앞뒤 0.4초 무음). 이미 있으면 그대로."""
    import shutil
    import subprocess
    d = TTS_DIR / voice
    wav = d / f"{key}.wav"
    if wav.exists() and wav.stat().st_size > 8000:
        return wav
    if not (shutil.which("say") and shutil.which("ffmpeg")):
        return None
    d.mkdir(parents=True, exist_ok=True)
    aiff = d / f"{key}.aiff"
    name = "Yuna" if voice == "Yuna" else f"{voice} (한국어(대한민국))"
    subprocess.run(["say", "-v", name, "-o", str(aiff), "--", text], check=True, timeout=60)
    ms = int(pad * 1000)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(aiff), "-af", f"adelay={ms}:all=1,apad=pad_dur={pad}",
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True, timeout=60)
    aiff.unlink(missing_ok=True)
    return wav if wav.stat().st_size > 8000 else None


def sens_eval(tag: str = "") -> None:
    import soundfile as sf
    from server import pipeline, recognizer
    rec = recognizer.get_recognizer()
    out = []
    t0 = time.time()
    for v in TTS_VOICES:
        voice = "male" if v in TTS_MALE else "female"
        for key, text, pron, said, idxs, exp in PAIRS:
            for kind, spoken in (("err", said), ("ok", text)):
                wav = _tts_wav(v, f"{'p' if kind == 'err' else 'pok'}_{key}", spoken)
                if wav is None:
                    continue
                x, sr = sf.read(wav, dtype="float32", always_2d=False)
                res = pipeline.analyze(x, sr, text, pron, None, voice=voice, sentence_type="word")
                base = {"voice": v, "key": key, "kind": kind, "idxs": idxs, "exp": list(exp), "text": text}
                if "error" in res:
                    out.append({**base, "error": res["error"]})
                    continue
                em = rec.emissions(_rec_input(x, sr))
                out.append({**base, **_raw_record(res, em, rec)})
    _jl_write(DATA / f"sens{tag}.jsonl", out)
    print(f"합성음 오류 흉내 분석 끝: {len(out)}건 ({time.time() - t0:.0f}초)")


def _detected(r: dict) -> tuple[bool, bool]:
    """(오류로 잡음, 기대한 소리까지 맞힘)."""
    exp = r["exp"]
    if exp[0] == "ins":
        hit = any(x["phone"] == exp[1] for x in r["insertions"])
        return hit, hit
    got = exact = False
    for i in r["idxs"]:
        p = r["phones"][i]
        if p["status"] in ("sub", "del"):
            got = True
            exact = exact or (p["status"] == exp[0] and (exp[0] == "del" or p["heard"] == exp[1]))
    return got, exact


def sens_report(tag: str = "") -> None:
    recs = [r for r in _jl_read(DATA / f"sens{tag}.jsonl") if "error" not in r]
    if not recs:
        return
    err = [r for r in recs if r["kind"] == "err"]
    ok = [r for r in recs if r["kind"] == "ok"]
    det = [_detected(r) for r in err]
    yuna = [d for r, d in zip(err, det) if r["voice"] == "Yuna"]
    print(f"\n== 검출률(합성음 오류 흉내 {len(err)}건 = 음성 {len({r['voice'] for r in err})}종 × {len(PAIRS)}쌍) ==")
    print(f"  오류로 잡음(sub/del/삽입) {100 * sum(d[0] for d in det) / max(1, len(det)):.1f}%, "
          f"들린 소리까지 맞힘 {100 * sum(d[1] for d in det) / max(1, len(det)):.1f}%  "
          f"(Yuna 만: {100 * sum(d[0] for d in yuna) / max(1, len(yuna)):.1f}%)")
    n = _rate(ok)
    print(f"  같은 낱말의 정상 합성음 {len(ok)}건: {_fmt_rate(n)}")
    # 같은 음성의 (오류 흉내, 정상) 짝: 오류 자리를 오류 쪽에서만 잡았나(정상 합성음도 그 자리를 다르게 듣는 일이 많다)
    by = {(r["voice"], r["key"], r["kind"]): r for r in recs}
    c = Counter()
    for (v, k, kind), r in by.items():
        o = by.get((v, k, "ok"))
        if kind != "err" or o is None or r["exp"][0] == "ins":
            continue
        e1 = any(r["phones"][i]["status"] in ("sub", "del") for i in r["idxs"])
        o1 = any(o["phones"][i]["status"] in ("sub", "del") for i in o["idxs"])
        c["n"] += 1
        c["disc"] += e1 and not o1
        c["both"] += e1 and o1
        c["none"] += not e1 and not o1
    if c["n"]:
        print(f"  짝 {c['n']}개: 오류 쪽만 잡음(구별) {100 * c['disc'] / c['n']:.1f}%, 둘 다 오류 {100 * c['both'] / c['n']:.1f}%, "
              f"둘 다 통과 {100 * c['none'] / c['n']:.1f}%")
    miss = Counter(r["key"] for r, d in zip(err, det) if not d[0])
    if miss:
        print("  놓친 쌍(음성 수):", ", ".join(f"{k} {v}" for k, v in miss.most_common(12)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="사람 낭독 음성 오탐률 평가")
    ap.add_argument("cmd", choices=["download", "eval", "report", "sens", "all"])
    ap.add_argument("--n", type=int, default=240, help="download: 받을 문장 수")
    ap.add_argument("--limit", type=int, default=None, help="eval: 앞에서부터 이 수만")
    ap.add_argument("--no-words", action="store_true", help="eval: 단어 단위 평가 생략")
    ap.add_argument("--tag", default="", help="결과 파일 이름 꼬리표(sent<tag>.jsonl)")
    a = ap.parse_args()
    if a.cmd in ("download", "all"):
        download(a.n)
    if a.cmd in ("eval", "all"):
        evaluate(a.limit, not a.no_words, a.tag)
    if a.cmd in ("sens", "all"):
        sens_eval(a.tag)
    if a.cmd in ("report", "sens", "all"):
        report(a.tag)
        sens_report(a.tag)
