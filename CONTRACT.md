# 또박 — 모듈 계약서 (구현 전 고정)

청각장애(인공와우) 사용자의 한국어 발음 연습 데모. **음성 = 오류 판정의 본체, 입술 = 보조 판정 + 따라하기 피드백.**

```
ttobak/
  CONTRACT.md            ← 이 문서. 모든 모듈은 여기 정의된 함수 시그니처/JSON 모양을 지킨다
  models/ko-phone/       ← slplab/wav2vec2-xls-r-300m_phone-mfa_korean (로컬 다운로드됨)
  server/
    phones.py            ← [완성] 음소 인벤토리·자질·자모 매핑·pron_to_phones()
    g2p.py               ← 철자 → 표준발음 한글 (음운규칙)
    recognizer.py        ← wav2vec2 로드, CTC 방출확률, 자유 인식, 강제정렬, GOP
    align.py             ← 목표 음소열 vs 인식 음소열 정렬(편집 연산)
    acoustic.py          ← parselmouth: F0, 강도, 모음 포먼트
    lips.py              ← 프런트에서 받은 입술 시계열 → 음소 구간별 입모양 판정
    feedback.py          ← 오류 → 한국어 교정 안내 문구, 점수 산출, 우선순위
    words.py             ← data/words.json 로드 + 목표 음소열 생성
    pipeline.py          ← 위 모듈 조립: analyze(wav, target, lips, voice) → 결과 JSON
    app.py               ← FastAPI. /api/*, web/ 정적 서빙
    data/words.json      ← 연습 단어 세트
    tests/               ← pytest
  web/                   ← 빌드 없는 정적 프런트(ES 모듈)
    index.html, styles.css, app.js, recorder.js, lips.js, charts.js
    samples/             ← 데모용 샘플 음성(wav 16k mono) + samples.json
  scripts/make_samples.sh← macOS `say`로 샘플 생성
```

실행: `.venv/bin/uvicorn server.app:app --port 8765` (프로젝트 루트에서). Python 3.12, `.venv`에 torch/torchaudio/transformers/fastapi/parselmouth/soundfile/numpy/pytest/httpx 설치됨. ffmpeg 있음.

---

## 1. 음소 표기 (server/phones.py — 이미 완성, 수정 금지·추가만 허용)

모델 어휘(42개 음소 + `|` `[PAD]` `[UNK]`)를 그대로 쓴다.

- 자음: `B BB Ph D DD Th G GG Kh J JJ CHh S SS H M N NG R L p t k`
- 모음: `A E I O U EO EU iA iE iEO iO iU oA oE uEO uI euI`
- 초성 ㄹ=`R`, 받침 ㄹ=`L`, 받침 파열음=`p t k`, ㅇ받침=`NG`
- `PHONES[sym]` → `Phone(sym, jamo, kind, place, manner, phonation, coda, height, backness, rounded, glide, lip)`
- `pron_to_phones("궁물")` → `(["G","U","NG","M","U","L"], [0,0,0,1,1,1])`
- `FORMANT_REF[voice][vowel] = (F1, F2)`  voice ∈ male|female|child

## 2. g2p.py

```python
def to_pron(text: str) -> str
```
철자 한글 → 표준발음 한글. 공백은 어절 경계로 유지(어절 사이에는 연음·경음화 등 적용하지 않음 — 단, 같은 어절 안에서는 모두 적용).
반드시 다룰 규칙: 겹받침 단순화, 받침 대표음화(7종성), 연음(ㅇ 초성 앞), ㅎ 관련(격음화 ㄱ/ㄷ/ㅂ/ㅈ+ㅎ, ㅎ+ㄱ/ㄷ/ㅈ, ㅎ탈락 ㅎ+모음, ㅎ+ㄴ→ㄴㄴ, ㅎ+ㅅ→ㅆ), 경음화(장애음 받침 뒤 평음→경음), 비음화(장애음 받침+ㄴ/ㅁ, ㅁ/ㅇ+ㄹ→ㄴ, ㄱ/ㅂ+ㄹ→ㅇ/ㅁ+ㄴ), 유음화(ㄴ+ㄹ, ㄹ+ㄴ → ㄹㄹ), 구개음화(ㄷ/ㅌ+이), 'ㅢ' 처리(자음 뒤 ㅢ→ㅣ, 어두 외 '의'는 그대로 둠), 결과는 항상 받침이 대표음 7개(ㄱㄴㄷㄹㅁㅂㅇ)뿐인 한글.
예: 국물→궁물, 밥 먹었어요→밥 머거써요, 고맙습니다→고맙씀니다, 같이→가치, 좋아요→조아요, 신라→실라, 닭→닥, 앉아→안자, 많다→만타, 학교→학꾜, 희망→히망, 의자→의자.

## 3. recognizer.py

```python
class Recognizer:
    def __init__(self, model_dir: str = "models/ko-phone", device: str | None = None)  # mps 가능하면 mps, 아니면 cpu
    sample_rate: int  # 16000
    frame_sec: float  # 방출 프레임 간격(초) ≈ 0.02
    def emissions(self, wav: np.ndarray) -> np.ndarray          # (T, V) log-softmax, float32, wav는 16k mono float32 [-1,1]
    def decode(self, em: np.ndarray) -> list[dict]               # 자유 인식(greedy CTC): [{"phone": "G", "start": s, "end": s, "conf": 0~1}], 특수토큰 제외
    def force_align(self, em: np.ndarray, phones: list[str]) -> list[dict]
        # 목표 음소열 강제정렬(torchaudio.functional.forced_align). 반환: 목표 음소마다
        # {"phone", "start", "end", "gop", "post"}  — start/end 초,
        # post = 해당 구간에서 목표 음소의 평균 사후확률(0~1),
        # gop = 0~100 점수: 구간 프레임별 (log p(target) - max_q log p(q)) 평균을 시그모이드류로 사상(완벽=100)
    vocab: dict[str, int]
```
단일 인스턴스를 프로세스에 캐시(`get_recognizer()`). 음성 앞뒤 무음은 정렬에 맡긴다.

## 4. align.py

```python
def align(target: list[str], heard: list[str]) -> list[dict]
```
Needleman–Wunsch(치환 비용은 음소 자질 거리 기반: 같은 조음위치·방식에서 발성유형만 다르면 저비용 등) 결과를 연산 목록으로:
`{"op": "match"|"sub"|"del"|"ins", "t": 목표 인덱스|None, "h": 인식 인덱스|None}` — 목표 순서대로, ins는 해당 위치에 끼워 넣음.

## 5. acoustic.py

```python
def analyze(wav: np.ndarray, sr: int, vowel_segments: list[dict], voice: str) -> dict
```
`vowel_segments`: `[{"idx": 목표음소 인덱스, "phone": "A", "start": s, "end": s}]` (강제정렬 결과 중 모음).
반환:
```json
{"duration": 1.42,
 "f0": {"t": [..], "hz": [.. 무성구간 null]},
 "intensity": {"t": [..], "db": [..]},
 "f0_stats": {"mean": 182.3, "min": 150.1, "max": 230.0, "range_st": 7.4, "voiced_ratio": 0.62},
 "loudness": {"mean_db": 68.1, "max_db": 76.0},
 "vowels": [{"idx": 1, "phone": "A", "f1": 750, "f2": 1320, "ref": {"f1": 740, "f2": 1310}, "ok": true}]}
```
배열은 최대 ~200포인트로 다운샘플. 이중모음은 구간 후반 1/3 기준으로 도착 모음의 참고치(phones.PHONES 의 height/backness로 대응하는 단모음 기준)와 비교. 참고치가 없는 모음은 `ref: null`.

## 6. lips.py

프런트가 보내는 입술 데이터(JSON):
```json
{"fps": 30, "frames": [{"t": 0.033, "open": 0.12, "width": 0.92, "pucker": 0.1, "funnel": 0.05, "jaw": 0.2, "close": 0.0}],
 "neutral": {"open": 0.02, "width": 0.95}}
```
- `t`: 녹음 시작 기준 초. `open`/`width`: 얼굴 크기(양 눈 바깥꼬리 거리)로 정규화한 입 벌림·입 너비. `pucker`/`funnel`/`jaw`/`close`: MediaPipe 블렌드셰이프 0~1.
- `neutral`: 녹음 직후 무발화 구간에서 잡은 기준값(없으면 프레임 하위 분위수로 추정).

```python
def analyze(lips: dict | None, segments: list[dict]) -> dict
```
`segments`: 강제정렬 결과 전체 `[{"idx", "phone", "start", "end"}]`.
`PHONES[p].lip` 목표별 판정: `round`(너비 감소 or pucker/funnel↑), `spread`(너비 유지/증가, pucker 낮음), `open`(open/jaw 큼), `closed`(양순음 구간 근처에서 입술이 닫힘, open≈0 또는 close↑), `neutral`/None은 판정 안 함.
반환:
```json
{"available": true,
 "series": {"t": [..], "open": [..], "width": [..], "round": [..]},
 "checks": [{"idx": 3, "phone": "O", "expect": "round", "ok": false, "measured": {"width_ratio": 0.98, "pucker": 0.05}, "msg": "입술을 더 동그랗게 모아 앞으로 내밀어 보세요"}],
 "score": 0~100 | null}
```
입술 데이터가 없거나 프레임이 부족하면 `{"available": false, "series": null, "checks": [], "score": null}`.

## 7. feedback.py

```python
def phone_tip(target: str, heard: str | None, status: str) -> str | None   # 음소 하나에 대한 교정 문구(한국어, 1~2문장, 구체적 조음 지시)
def summarize(phones: list[dict], acoustic: dict, lips: dict, sentence_type: str) -> dict
```
`summarize` 반환: `{"scores": {...}, "feedback": [...]}` (아래 API 응답 참고). 우선순위: 대비 오류(평음/격음/경음, ㅅ/ㅆ) > 탈락 > 모음 오류 > 입모양 > 억양/크기. 최대 4개.
`sentence_type`: "statement" | "question" | "word" — question이면 끝 억양 상승 여부 확인.

## 8. words.py + data/words.json

```json
{"categories": [{"id": "contrast", "name": "평음·격음·경음", "desc": "..."}],
 "words": [{"id": "bul", "text": "불", "category": "contrast", "focus": ["B"], "group": "bul-pul-ppul", "type": "word", "hint": "..."}]}
```
`pron`은 생략 가능(없으면 g2p.to_pron). `group`이 같은 단어는 최소대립쌍 세트로 묶어 보여준다. `type`: word | statement | question.
```python
def load_words() -> list[dict]   # 각 단어에 pron, phones, syllables 채워서 반환
def build_target(text: str, pron: str | None = None) -> dict
  # {"text", "pron", "phones": [...], "phone_syl": [...], "syllables": [{"text": "궁", "pron": "궁", "phones": [0,1,2], "lip": "round"}]}
  # syllables[i].lip = 그 음절 모음의 PHONES[v].lip  (화면 입모양 가이드용)
```
음절 표시 텍스트는 철자(text) 기준이 아니라 발음형(pron) 기준으로 맞추되, 철자 음절 수와 같으면 `text` 필드에 철자 음절도 넣는다.

## 9. pipeline.py

```python
def analyze(wav: np.ndarray, sr: int, target_text: str, pron: str | None, lips: dict | None,
            voice: str = "female", sentence_type: str = "word") -> dict   # → API 응답 그대로
```
순서: 리샘플(16k mono) → 목표 생성 → emissions → decode(자유) → force_align(목표) → align(target, heard) → 음소별 상태 결정 → acoustic → lips → feedback.summarize.
음소 상태 규칙: align이 `sub`/`del`이면 그 상태, `match`인데 gop < 45 이면 `weak`, 아니면 `ok`. 음성이 거의 없으면(유성 비율·강도 기준) `{"error": "no_speech", ...}`.

## 10. HTTP API (app.py)

- `GET /api/health` → `{"ok": true, "model": "loaded"|"loading"}`
- `GET /api/words` → `{"categories": [...], "words": [load_words() 결과]}`
- `GET /api/target?text=...` → `build_target(text)` (자유 입력 미리보기)
- `POST /api/analyze` multipart:
  - `audio`: wav 파일(가능하면 16k mono PCM16; 아니면 서버가 soundfile/ffmpeg로 변환)
  - `text` (필수), `pron` (선택), `word_id` (선택), `voice` (male|female|child, 기본 female), `sentence_type`, `lips` (JSON 문자열, 선택)
- `GET /` 및 정적 파일 → `web/`

`POST /api/analyze` 응답:
```json
{"target": {"text": "국물", "pron": "궁물", "phones": ["G","U","NG","M","U","L"], "syllables": [...]},
 "heard": {"phones": ["G","U","NG","M","U","L"], "pron_guess": "궁물"},
 "phones": [{"idx": 0, "phone": "G", "jamo": "ㄱ", "syl": 0, "start": 0.31, "end": 0.36,
             "status": "ok"|"weak"|"sub"|"del", "heard": "G"|null, "heard_jamo": "ㄱ"|null,
             "gop": 92, "tip": null | "교정 문구"}],
 "insertions": [{"after": 2, "phone": "EU", "jamo": "ㅡ"}],
 "syllables": [{"text": "궁", "status": "ok"|"warn"|"error", "phones": [0,1,2]}],
 "acoustic": {...5절...},
 "lips": {...6절...},
 "scores": {"overall": 0~100, "accuracy": 0~100, "clarity": 0~100, "intonation": 0~100|null, "lips": 0~100|null},
 "feedback": [{"level": "error"|"warn"|"info", "title": "ㄱ이 ㄲ처럼 들려요", "body": "…", "phones": [0]}],
 "meta": {"elapsed_ms": 812, "model": "slplab/wav2vec2-xls-r-300m_phone-mfa_korean"}}
```
`heard.pron_guess`: 인식 음소열을 한글 음절로 대충 조립한 것(표시용, 실패 시 null).
에러: `{"error": "no_speech"|"bad_audio"|"empty_target", "message": "한국어 설명"}` + HTTP 422.

## 11. 프런트(web/) 화면 계약

한 화면 앱. 왼쪽(또는 위): 단어 목록(카테고리 탭, 최소대립쌍 그룹) + 자유 입력. 가운데: 연습 카드 — 목표 단어, 발음형, 음절별 입모양 가이드, 카메라 미리보기(입술 랜드마크 오버레이), 녹음 버튼/레벨 미터, "기준 발음 듣기"(speechSynthesis ko-KR). 결과: 음절 블록 색칠(ok/warn/error), 음소 상세(목표 vs 들린 소리 + 교정 문구), 피드백 카드, 점수, 차트(F0·강도 곡선, 모음 포먼트 차트(F2 가로·F1 세로 반전, 참고치 표시), 입술 시계열 + 음소 구간 띠), 시도 기록(localStorage).
데모 모드: `web/samples/samples.json`의 샘플을 "샘플로 분석" 버튼으로 같은 /api/analyze에 보낸다(입술 데이터 없음).
청각장애 사용자 대상이므로: 소리 대신 **시각 피드백**이 주, 글자 크게, 색만으로 상태를 구분하지 않기(아이콘/문구 병기), 자막 같은 명확한 문장.
