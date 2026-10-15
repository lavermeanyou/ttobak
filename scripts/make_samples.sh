#!/usr/bin/env bash
# 데모용 샘플 음성 생성: macOS `say`(한국어 TTS) → 16 kHz mono PCM16 wav (web/samples/*.wav)
#
#   bash scripts/make_samples.sh            # 없는 파일만 만든다
#   FORCE=1 bash scripts/make_samples.sh    # 전부 다시 만든다
#   VOICE=Yuna bash scripts/make_samples.sh # 목소리 바꾸기(기본 Yuna)
#
# 샘플 목록과 화면 문구는 web/samples/samples.json 에 있다(id 가 이 표의 id 와 같아야 한다).
# '오류 흉내' 샘플은 목표 단어 대신 오류가 난 단어를 TTS 로 말하게 해서 대표 오류를 재현한다
# (예: 목표 '소리'에 '도리' 음성 → ㅅ 이 ㄷ 으로 들리는 오류).
#
# 주의(실측):
#  - 이 환경에서 실제로 소리가 나는 한국어 음성은 Yuna 뿐이다. Eddy/Flo/Reed/Sandy/Shelley/Grandma/Grandpa/Rocko 는
#    빈 파일(약 590바이트)을 만든다. 그래서 만든 파일 크기를 검사한다.
#  - 인식 모델은 Yuna 의 일부 발음을 체계적으로 다르게 듣는다(어두 ㅂ/ㄷ/ㄱ → ㅌ/ㅋ, 단어 끝 받침 ㄹ → '리',
#    ㄱ 뒤 ㅗ/ㅜ → ㅡ, ㅁ → ㄴ). 그래서 '정상 발음' 샘플은 모델이 정확히 알아듣는 단어로 골랐다
#    (불·국물·과자·바다의 정상 발음은 이 TTS 로는 오류로 판정된다 → 정상 샘플에서 뺐다).
#  - 말소리 앞뒤에 0.4초 무음을 붙인다(실제 녹음처럼 버튼을 누른 뒤 말하기 시작하는 상황).
#  - 말 빠르기(rate)를 지정한 것은 기본 빠르기에서 모델이 모음을 다르게 들었던 경우다(사과의 ㅏ → ㅔ 등).
#  - 억양 샘플: '예/아니요'로 답하는 판정 의문문(좋아요?·괜찮아요?)만 끝 올림을 요구한다. 의문사가 든
#    설명 의문문(이름이 뭐예요?)은 끝을 내리는 것이 기본이라 '이름이 뭐예요.'(끝 −5 반음)는 정상 샘플이다.
#    억양 오류 샘플은 목표 '좋아요?'에 평서 억양 '좋아요.'(끝 약 −10 반음)를 합성해 만든다.
#    (Yuna 실측 끝 억양: 좋아요? +8.7, 괜찮아요? +6.4 반음 — 모두 음소 오류 없이 인식됨)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/web/samples"
VOICE="${VOICE:-Yuna}"
PAD_SEC="0.4"
MIN_BYTES=8000   # 16k mono 16bit 기준 0.25초. 이보다 작으면 TTS 가 소리를 내지 못한 것

command -v say >/dev/null || { echo "macOS 'say' 명령이 필요합니다" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg 가 필요합니다" >&2; exit 1; }
mkdir -p "$OUT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# id | TTS 로 말할 문장 | 말 빠르기(단어/분, '-' 는 기본값)
SAMPLES=$(cat <<'EOF'
ok-jjada|짜다|-
ok-sori|소리|-
ok-oi|오이|-
ok-nara|나라|-
ok-yagu|야구|-
ok-sagwa|사과|150
ok-ap|앞|150
ok-ot|옷|-
ok-uija|의자|-
ok-where|어디 가요?|-
ok-name-fall|이름이 뭐예요.|-
ok-okay|괜찮아요?|-
ok-like|좋아요?|-
err-jjada-chada|차다|-
err-sori-dori|도리|-
err-oi-eoi|어이|-
err-nara-nada|나다|-
err-yagu-agu|아구|-
err-bada-mada|마다|-
err-ap-apeu|아프|150
err-hello-coda|아녕하세요|-
err-like-flat|좋아요.|-
EOF
)

made=0
while IFS='|' read -r id text rate; do
  [ -z "$id" ] && continue
  wav="$OUT/$id.wav"
  if [ -f "$wav" ] && [ -z "${FORCE:-}" ]; then
    continue
  fi
  aiff="$TMP/$id.aiff"
  if [ "$rate" = "-" ]; then
    say -v "$VOICE" -o "$aiff" -- "$text"
  else
    say -v "$VOICE" -r "$rate" -o "$aiff" -- "$text"
  fi
  ms=$(awk "BEGIN{print int($PAD_SEC*1000)}")
  ffmpeg -loglevel error -y -i "$aiff" \
    -af "adelay=${ms}:all=1,apad=pad_dur=${PAD_SEC}" \
    -ar 16000 -ac 1 -c:a pcm_s16le "$wav"
  size=$(wc -c < "$wav" | tr -d ' ')
  if [ "$size" -lt "$MIN_BYTES" ]; then
    rm -f "$wav"
    echo "실패: $id ('$text') — '$VOICE' 음성이 소리를 내지 못했습니다(${size}바이트). VOICE=Yuna 로 다시 실행하세요." >&2
    exit 1
  fi
  echo "만듦: $id.wav  ($text, ${size}바이트)"
  made=$((made + 1))
done <<< "$SAMPLES"

# samples.json 이 가리키는 파일이 모두 있는지 확인
if [ -f "$OUT/samples.json" ]; then
  missing=0
  for f in $(grep -o '"file": *"[^"]*"' "$OUT/samples.json" | sed 's/.*"file": *"\(.*\)"/\1/'); do
    if [ ! -f "$ROOT/web/$f" ]; then
      echo "samples.json 에 있지만 파일이 없음: web/$f" >&2
      missing=1
    fi
  done
  [ "$missing" -eq 0 ] || exit 1
fi
echo "완료: 새로 만든 파일 ${made}개 → $OUT"
