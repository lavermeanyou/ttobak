// dev/mock.js — ?mock=1 일 때 /api/* 대신 쓰는 목업 (백엔드 없이 화면 확인용)
//  ?mock=1&mockerror=no_speech  → 분석 요청이 422 no_speech 로 실패하는 경우 확인
//  ?mock=1&mockdelay=0          → 분석 대기 시간(ms) 조절(기본 900)
const base = new URL('./', import.meta.url);
const params = new URLSearchParams(location.search);

const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'.split('');
const JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'.split('');
const JONG = ['', ...'ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'.split('')];
const ONSET = { ㄱ: 'G', ㄲ: 'GG', ㅋ: 'Kh', ㄷ: 'D', ㄸ: 'DD', ㅌ: 'Th', ㅂ: 'B', ㅃ: 'BB', ㅍ: 'Ph', ㅈ: 'J', ㅉ: 'JJ', ㅊ: 'CHh', ㅅ: 'S', ㅆ: 'SS', ㅎ: 'H', ㅁ: 'M', ㄴ: 'N', ㄹ: 'R', ㅇ: null };
const VOWEL = { ㅏ: 'A', ㅐ: 'E', ㅑ: 'iA', ㅒ: 'iE', ㅓ: 'EO', ㅔ: 'E', ㅕ: 'iEO', ㅖ: 'iE', ㅗ: 'O', ㅘ: 'oA', ㅙ: 'oE', ㅚ: 'oE', ㅛ: 'iO', ㅜ: 'U', ㅝ: 'uEO', ㅞ: 'oE', ㅟ: 'uI', ㅠ: 'iU', ㅡ: 'EU', ㅢ: 'euI', ㅣ: 'I' };
// 목업은 g2p 가 없으므로 받침을 대표음으로만 단순화한다
const CODA = { ㄱ: 'k', ㄲ: 'k', ㅋ: 'k', ㄳ: 'k', ㄺ: 'k', ㄷ: 't', ㅅ: 't', ㅆ: 't', ㅈ: 't', ㅊ: 't', ㅌ: 't', ㅎ: 't', ㅂ: 'p', ㅍ: 'p', ㅄ: 'p', ㄿ: 'p', ㄴ: 'N', ㄵ: 'N', ㄶ: 'N', ㄹ: 'L', ㄼ: 'L', ㄽ: 'L', ㄾ: 'L', ㅀ: 'L', ㅁ: 'M', ㄻ: 'M', ㅇ: 'NG' };
const LIP = { A: 'open', iA: 'open', E: 'spread', I: 'spread', EU: 'spread', iE: 'spread', euI: 'spread', O: 'round', U: 'round', iO: 'round', iU: 'round', oA: 'round', oE: 'round', uEO: 'round', uI: 'round', EO: 'neutral', iEO: 'neutral' };

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const json = async (name) => (await fetch(new URL(name, base))).json();

export async function health() { return { ok: true, model: 'loaded', mock: true }; }
export async function words() { return json('mock-words.json'); }

export async function target(text) {
  await wait(120);
  const phones = [], phoneSyl = [], syllables = [];
  let si = 0;
  for (const ch of text) {
    const code = ch.charCodeAt(0) - 0xac00;
    if (code < 0 || code >= 11172) continue;
    const cho = CHO[Math.floor(code / 588)], jung = JUNG[Math.floor((code % 588) / 28)], jong = JONG[code % 28];
    const idx = [];
    if (ONSET[cho]) { idx.push(phones.length); phones.push(ONSET[cho]); phoneSyl.push(si); }
    const v = VOWEL[jung];
    idx.push(phones.length); phones.push(v); phoneSyl.push(si);
    if (jong && CODA[jong]) { idx.push(phones.length); phones.push(CODA[jong]); phoneSyl.push(si); }
    syllables.push({ text: ch, pron: ch, phones: idx, lip: LIP[v] || 'neutral' });
    si++;
  }
  if (!phones.length) {
    const e = new Error('empty_target');
    e.status = 422;
    e.body = { error: 'empty_target', message: '연습할 한글이 없어요. 한글 단어나 문장을 입력해 주세요.' };
    throw e;
  }
  return { text, pron: text, phones, phone_syl: phoneSyl, syllables, mock_note: '목업: 발음 규칙(g2p) 미적용' };
}

/** @returns {{status:number, body:object}} */
export async function analyze(form) {
  await wait(Number(params.get('mockdelay') ?? 900));
  const err = params.get('mockerror');
  if (err) {
    const msgs = {
      no_speech: '말소리가 거의 들리지 않았어요. 마이크에 조금 더 가까이 대고 또박또박 말해 주세요.',
      bad_audio: '녹음 파일을 읽지 못했어요. 다시 녹음해 주세요.',
      empty_target: '연습할 글자가 비어 있어요.',
    };
    return { status: 422, body: { error: err, message: msgs[err] || '분석하지 못했어요.' } };
  }
  const body = await json('mock-analyze.json');
  body.meta = { ...(body.meta || {}), mock: true, sent_text: form.get('text'), sent_voice: form.get('voice'), sent_lips: form.has('lips') };
  return { status: 200, body };
}

export async function samples() { return json('mock-samples.json'); }
