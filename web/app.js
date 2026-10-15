// app.js — 또박 화면 조립: 단어 목록 · 연습 카드 · 카메라/녹음 · 분석 결과
import { Recorder } from './recorder.js';
import { LipTracker, buildLipsPayload, classifyLive, PREP_SEC } from './lips.js';
import { renderProsody, renderFormants, renderLips, timeWindow, vowelHint, vowelName, vowelState, cleanIntensity, sparklineSVG } from './charts.js';

const MAX_SEC = 8;
const params = new URLSearchParams(location.search);
const MOCK = params.get('mock') === '1';
const mock = MOCK ? await import('./dev/mock.js') : null;

// ── 작은 도구 ──────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c instanceof Node ? c : String(c));
  return el;
}
const SVGNS = 'http://www.w3.org/2000/svg';
function svg(tag, attrs = {}) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}
function icon(name, cls = 'i') {
  const s = svg('svg', { class: cls, 'aria-hidden': 'true', focusable: 'false' });
  s.appendChild(svg('use', { href: `#i-${name}` }));
  return s;
}

const store = {
  get(k, fb) { try { const v = localStorage.getItem(k); return v == null ? fb : JSON.parse(v); } catch { return fb; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 저장 불가(사생활 보호 모드 등) — 무시 */ } },
  raw(k) { try { return localStorage.getItem(k); } catch { return null; } },
  setRaw(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* 무시 */ } },
};

// ── 한글·음소 ─────────────────────────────────────────────
const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'.split('');
const JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'.split('');
const JONG = ['', ...'ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'.split('')];
const PHONE_JAMO = {
  B: 'ㅂ', BB: 'ㅃ', Ph: 'ㅍ', D: 'ㄷ', DD: 'ㄸ', Th: 'ㅌ', G: 'ㄱ', GG: 'ㄲ', Kh: 'ㅋ', J: 'ㅈ', JJ: 'ㅉ', CHh: 'ㅊ',
  S: 'ㅅ', SS: 'ㅆ', H: 'ㅎ', M: 'ㅁ', N: 'ㄴ', NG: 'ㅇ', R: 'ㄹ', L: 'ㄹ', p: 'ㅂ', t: 'ㄷ', k: 'ㄱ',
  A: 'ㅏ', E: 'ㅔ', I: 'ㅣ', O: 'ㅗ', U: 'ㅜ', EO: 'ㅓ', EU: 'ㅡ', iA: 'ㅑ', iE: 'ㅖ', iEO: 'ㅕ', iO: 'ㅛ', iU: 'ㅠ',
  oA: 'ㅘ', oE: 'ㅙ', uEO: 'ㅝ', uI: 'ㅟ', euI: 'ㅢ',
};
const VOWELS = new Set(['A', 'E', 'I', 'O', 'U', 'EO', 'EU', 'iA', 'iE', 'iEO', 'iO', 'iU', 'oA', 'oE', 'uEO', 'uI', 'euI']);
const BILABIAL = new Set(['B', 'BB', 'Ph', 'M', 'p']);

function decompose(ch) {
  const c = ch.charCodeAt(0) - 0xac00;
  if (c < 0 || c >= 11172) return null;
  return [CHO[Math.floor(c / 588)], JUNG[Math.floor((c % 588) / 28)], JONG[c % 28]];
}
function compose(cho, jung, jong = '') {
  const a = CHO.indexOf(cho), b = JUNG.indexOf(jung), c = JONG.indexOf(jong);
  if (a < 0 || b < 0 || c < 0) return null;
  return String.fromCharCode(0xac00 + a * 588 + b * 28 + c);
}
const bare = (s) => (s || '').replace(/[^가-힣]/g, '');
/** '[궁물]로' / '[밥]으로' — 받침 있으면(ㄹ 제외) '으로' */
function roParticle(word) {
  const d = lastSyllable(word);
  return d && d[2] && d[2] !== 'ㄹ' ? '으로' : '로';
}
function detectType(text) {
  const t = (text || '').trim();
  if (/[?？]$/.test(t)) return 'question';
  if (/\s/.test(t) || /[.!。]$/.test(t)) return 'statement';
  return 'word';
}
// 의문사(server/words.py _WH_WORDS 와 같은 목록): 어절이 이것으로 시작하면 설명 의문문(wh)
const WH_WORDS = ['뭐', '무엇', '무슨', '뭘', '뭔', '어디', '언제', '누구', '누가', '누굴', '왜', '어떻게', '어떤',
  '어느', '얼마', '몇', '어때', '어땠', '어떠', '웬', '어째'];
function inferQuestionKind(text) {
  const ws = (text || '').replace(/[^가-힣\s]/g, ' ').split(/\s+/).filter(Boolean);
  return ws.some((w) => WH_WORDS.some((q) => w.startsWith(q))) ? 'wh' : 'yn';
}
const TUNES = ['rise', 'fall', 'free'];
/** 끝 억양 기대(서버 feedback.resolve_tune 과 같은 규칙): rise | fall | free | null(단어) */
function targetTune(t) {
  if (!t) return null;
  if (TUNES.includes(t.tune)) return t.tune;
  if (TUNES.includes(t.end_tune)) return t.end_tune;
  const type = t.type || t.sentence_type;
  if (type === 'question') return (t.question_kind === 'wh' || t.question_kind === 'yn' ? t.question_kind : inferQuestionKind(t.text)) === 'wh' ? 'free' : 'rise';
  if (type === 'statement') return 'fall';
  return null;
}

/** 받침 자리에 올 수 있는 음소(받침 대표음). 이 밖의 음소(ㅍ·ㅅ·ㅈ·ㄲ…)가 받침 자리에서 들리면
 *  받침으로 끝내지 못하고 터뜨리거나 다음 음절처럼 낸 것이라, 받침 글자로 조립하면 안 된다. */
const CODA_OK = new Set(['p', 't', 'k', 'N', 'M', 'NG', 'L']);
const BURST = new Set(['B', 'BB', 'Ph', 'D', 'DD', 'Th', 'G', 'GG', 'Kh', 'J', 'JJ', 'CHh']);

/** 마지막 한글 음절의 [초성, 중성, 종성] (없으면 null) */
function lastSyllable(word) {
  const hs = bare(word);
  return hs ? decompose(hs[hs.length - 1]) : null;
}
/** 받침 유무로 조사 고르기: josa('사과', '을', '를') → '를'. 한글이 없으면 '을(를)' */
function josa(word, withCoda, noCoda) {
  const d = lastSyllable(word);
  if (!d) return `${withCoda}(${noCoda})`;
  return d[2] ? withCoda : noCoda;
}

/**
 * 결과의 음소 판정으로 '들린 음절'을 조립(표시용).
 * @returns {{text?:string, note?:string}|null}  text = 들린 음절, note = 음절로 못 쓰는 경우의 음소 표기
 */
function heardSyllable(result, syl) {
  let onset = 'ㅇ', vowel = null, coda = null, codaT = null, seenV = false;
  const idxs = syl.phones || [];
  for (const i of idxs) {
    const p = result.phones[i];
    if (!p) return null;
    const isV = VOWELS.has(p.phone);
    const sym = p.status === 'del' ? null : p.status === 'sub' ? p.heard : p.phone;
    if (sym != null && VOWELS.has(sym) !== isV) return null;
    if (isV) { seenV = true; if (sym == null) return null; vowel = PHONE_JAMO[sym]; }
    else if (!seenV) onset = sym == null || sym === 'NG' ? 'ㅇ' : PHONE_JAMO[sym];
    else { coda = sym; codaT = p; }
  }
  if (!vowel) return null;
  const open = compose(onset, vowel, '');
  if (coda == null) return open ? { text: open } : null;
  // 받침 뒤에 모음(대개 ㅡ)이 끼어들었으면 받침이 다음 음절의 첫소리가 된 것: 앞 → [아프]
  const last = idxs[idxs.length - 1];
  const insV = (result.insertions || []).find((x) => x.after === last && VOWELS.has(x.phone));
  if (insV && coda !== 'NG') {
    const rel = compose(PHONE_JAMO[coda], PHONE_JAMO[insV.phone], '');
    if (open && rel) return { text: open + rel };
  }
  if (CODA_OK.has(coda)) {
    const t = compose(onset, vowel, PHONE_JAMO[coda]);
    return t ? { text: t } : null;
  }
  // 받침 자리에 올 수 없는 소리: 받침 ㅂ→ㅍ(터짐)처럼 음소로 적는다
  const tj = codaT.jamo || PHONE_JAMO[codaT.phone] || codaT.phone;
  const hj = PHONE_JAMO[coda] || coda;
  const how = BURST.has(coda) ? '(터짐)' : coda === 'R' ? '(튕김)' : '';
  return { note: `받침 ${tj}→${hj}${how}` };
}

// ── 입모양 아이콘(SVG) ─────────────────────────────────────
const LIP_TEXT = { round: '동그랗게', spread: '옆으로', open: '크게 벌리기', closed: '입술 닫기', neutral: '편하게' };
function lipIcon(kind, cls = 'lip-icon') {
  const s = svg('svg', { viewBox: '0 0 64 40', class: cls, 'aria-hidden': 'true', focusable: 'false' });
  const add = (tag, a) => s.appendChild(svg(tag, a));
  switch (kind) {
    case 'open':
      add('ellipse', { class: 'lips', cx: 32, cy: 20, rx: 15, ry: 17 });
      add('ellipse', { class: 'mouth', cx: 32, cy: 20, rx: 9.5, ry: 11.5 });
      break;
    case 'round':
      add('circle', { class: 'lips', cx: 32, cy: 20, r: 11 });
      add('circle', { class: 'mouth', cx: 32, cy: 20, r: 4.2 });
      add('path', { class: 'cue', d: 'M8 20h7M56 20h-7M12 16.5l3 3.5-3 3.5M52 16.5l-3 3.5 3 3.5' });
      break;
    case 'spread':
      add('path', { class: 'lips', d: 'M3 20Q32 8 61 20Q32 32 3 20Z' });
      add('path', { class: 'mouth', d: 'M10 20Q32 16.2 54 20Q32 23.8 10 20Z' });
      break;
    case 'closed':
      add('path', { class: 'lips', d: 'M8 20Q32 9 56 20Q32 31 8 20Z' });
      add('path', { class: 'seam', d: 'M9.5 20Q32 22 54.5 20' });
      break;
    default:
      add('path', { class: 'lips', d: 'M9 20Q32 8.5 55 20Q32 31.5 9 20Z' });
      add('path', { class: 'mouth', d: 'M16 20Q32 15.5 48 20Q32 24.5 16 20Z' });
  }
  return s;
}

// ── API (목업 전환 포함) ──────────────────────────────────
async function getJSON(url) {
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  let body = null;
  try { body = await res.json(); } catch { /* 본문 없음 */ }
  if (!res.ok) { const e = new Error(body && body.message ? body.message : `HTTP ${res.status}`); e.status = res.status; e.body = body; throw e; }
  return body;
}
const api = {
  health: () => (MOCK ? mock.health() : getJSON('/api/health')),
  words: () => (MOCK ? mock.words() : getJSON('/api/words')),
  target: (text) => (MOCK ? mock.target(text) : getJSON('/api/target?text=' + encodeURIComponent(text))),
  /** @returns {Promise<{status:number, body:any}>} */
  async analyze(form) {
    if (MOCK) return mock.analyze(form);
    const res = await fetch('/api/analyze', { method: 'POST', body: form });
    let body = null;
    try { body = await res.json(); } catch { /* 본문 없음 */ }
    return { status: res.status, body };
  },
  async samples() {
    if (MOCK) return mock.samples();              // 목업 모드는 목업 응답에 맞는 목업 샘플만
    try {
      const res = await fetch(new URL('samples/samples.json', document.baseURI), { cache: 'no-cache' });
      if (res.ok) { const d = await res.json(); if (d && Array.isArray(d.samples) && d.samples.length) return d; }
    } catch { /* 샘플 없음 */ }
    return null;
  },
};

// ── 상태 ──────────────────────────────────────────────────
const state = {
  categories: [],
  words: [],
  cat: store.get('ttobak.cat', null),
  current: null,          // 지금 연습 중인 목표
  voice: store.get('ttobak.voice', 'female'),
  phase: 'idle',          // idle | starting | prep | speak | stopping | analyzing
  lastResult: null,
  lastCtx: null,
  liveNeutral: null,
  samples: [],
};
const media = {
  ready: false, pending: null,
  stream: null,          // 마이크 스트림
  videoStream: null,     // 카메라 스트림(따로 요청 — 거부돼도 마이크는 쓴다)
  recorder: null, lips: null, hasVideo: false,
  lipsFailed: false,     // 입술 인식 모델을 불러오지 못함
  standing: { text: '', tone: '' },   // 녹음이 끝난 뒤 다시 보여 줄 기본 안내
};
let koVoice = null;
let replayUrl = null;

// ── 상단: 목소리·테마·서버 상태 ─────────────────────────────
function initVoice() {
  if (!['female', 'male', 'child'].includes(state.voice)) state.voice = 'female';
  for (const r of document.querySelectorAll('input[name="voice"]')) {
    r.checked = r.value === state.voice;
    r.addEventListener('change', () => {
      if (!r.checked) return;
      state.voice = r.value;
      store.set('ttobak.voice', state.voice);
    });
  }
}

const THEME_LABEL = { auto: '테마: 자동', light: '테마: 밝게', dark: '테마: 어둡게' };
function initTheme() {
  const btn = $('theme-btn');
  const cur = () => store.raw('ttobak.theme') || 'auto';
  const apply = (t) => {
    if (t === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', t);
    $('theme-label').textContent = THEME_LABEL[t];   // 보이는 라벨 = 접근 가능한 이름(상태 포함)
  };
  apply(['light', 'dark'].includes(cur()) ? cur() : 'auto');
  btn.addEventListener('click', () => {
    const order = ['auto', 'light', 'dark'];
    const next = order[(order.indexOf(cur()) + 1) % 3];
    store.setRaw('ttobak.theme', next === 'auto' ? null : next);
    apply(next);
  });
}

async function checkHealth() {
  const el = $('server-state');
  if (MOCK) { el.textContent = '목업 데이터'; el.dataset.state = 'loading'; return; }
  try {
    const hres = await api.health();
    if (hres && hres.model === 'loaded') { el.textContent = '분석 준비됨'; el.dataset.state = 'ok'; return; }
    if (hres && hres.model === 'error') { el.textContent = '분석 모델 오류'; el.dataset.state = 'down'; return; }
    el.textContent = '분석 모델 준비 중'; el.dataset.state = 'loading';
    setTimeout(checkHealth, 3000);
  } catch {
    el.textContent = '서버 연결 안 됨'; el.dataset.state = 'down';
    setTimeout(checkHealth, 8000);
  }
}

// ── 단어 목록 ─────────────────────────────────────────────
async function loadWords() {
  try {
    const data = await api.words();
    state.categories = (data.categories || []).filter((c) => (data.words || []).some((w) => w.category === c.id));
    state.words = data.words || [];
  } catch (e) {
    $('word-list').replaceChildren(h('p', { class: 'muted small', text: '단어 목록을 불러오지 못했어요. 서버가 켜져 있는지 확인해 주세요. 아래 「직접 입력」은 쓸 수 있어요.' }));
    console.warn(e);
    return;
  }
  // 카테고리에 없는 단어가 있으면 '기타'로
  if (state.words.some((w) => !state.categories.find((c) => c.id === w.category))) {
    state.categories.push({ id: '__etc', name: '기타', desc: '' });
    for (const w of state.words) if (!state.categories.find((c) => c.id === w.category)) w.category = '__etc';
  }
  const fromHash = new URLSearchParams(location.hash.slice(1)).get('w');
  const remembered = store.get('ttobak.word', null);
  const pick = state.words.find((w) => w.id === fromHash) || state.words.find((w) => w.id === remembered) || state.words[0];
  if (pick) state.cat = pick.category;
  if (!state.categories.find((c) => c.id === state.cat)) state.cat = state.categories[0] && state.categories[0].id;
  renderTabs();
  renderWordList();
  if (pick) selectWord(pick, { quiet: true });
}

function renderTabs() {
  const box = $('cat-tabs');
  box.replaceChildren(...state.categories.map((c) => h('button', {
    type: 'button', role: 'tab', class: 'tab', id: `tab-${c.id}`,
    'aria-selected': String(c.id === state.cat), 'aria-controls': 'word-panel', tabindex: c.id === state.cat ? '0' : '-1',
    onclick: () => setCategory(c.id),
    text: c.name,
  })));
  box.onkeydown = (e) => {
    const i = state.categories.findIndex((c) => c.id === state.cat);
    let j = null;
    if (e.key === 'ArrowRight') j = (i + 1) % state.categories.length;
    else if (e.key === 'ArrowLeft') j = (i - 1 + state.categories.length) % state.categories.length;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = state.categories.length - 1;
    if (j == null) return;
    e.preventDefault();
    setCategory(state.categories[j].id);
    $(`tab-${state.categories[j].id}`).focus();
  };
}

function setCategory(id) {
  state.cat = id;
  store.set('ttobak.cat', id);
  for (const b of $('cat-tabs').children) {
    const on = b.id === `tab-${id}`;
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
  }
  renderWordList();
}

function wordButton(w, showFocus) {
  const showPron = w.pron && bare(w.pron) !== bare(w.text);
  return h('button', {
    type: 'button', class: 'word-btn', 'data-id': w.id,
    'aria-pressed': String(!!(state.current && state.current.id === w.id)),
    onclick: () => selectWord(w),
  },
  h('span', { class: 'word-text', lang: 'ko', text: w.text }),
  showPron ? h('span', { class: 'word-pron', text: `[${w.pron}]` }) : null,
  showFocus && w.focus && w.focus.length ? h('span', { class: 'word-focus', text: w.focus.map((f) => PHONE_JAMO[f] || f).join(' ') }) : null);
}

function renderWordList() {
  const cat = state.categories.find((c) => c.id === state.cat);
  $('cat-desc').textContent = (cat && cat.desc) || '';
  $('word-panel').setAttribute('aria-labelledby', `tab-${state.cat}`);
  const ws = state.words.filter((w) => w.category === state.cat);
  const blocks = [];
  const seen = new Set();
  let singles = [];
  const flush = () => { if (singles.length) { blocks.push(h('div', { class: 'singles' }, singles)); singles = []; } };
  for (const w of ws) {
    if (w.group) {
      if (seen.has(w.group)) continue;
      seen.add(w.group);
      const members = ws.filter((x) => x.group === w.group);
      if (members.length > 1) {
        flush();
        const foci = members.map((m) => (m.focus || []).map((f) => PHONE_JAMO[f] || f).join('')).filter(Boolean);
        blocks.push(h('div', { class: 'pair', role: 'group', 'aria-label': `짝 비교: ${members.map((m) => m.text).join(', ')}` },
          h('span', { class: 'pair-label' }, '짝 비교', foci.length ? h('span', { class: 'mono', text: foci.join(' / ') }) : null),
          h('div', { class: 'pair-row' }, members.map((m) => wordButton(m, true)))));
        continue;
      }
    }
    singles.push(wordButton(w, false));
  }
  flush();
  $('word-list').replaceChildren(...(blocks.length ? blocks : [h('p', { class: 'muted small', text: '이 묶음에 단어가 없어요.' })]));
}

function markSelected() {
  for (const b of document.querySelectorAll('.word-btn')) {
    b.setAttribute('aria-pressed', String(!!(state.current && state.current.id && b.dataset.id === state.current.id)));
  }
}

function selectWord(w, { quiet = false, keepResult = false } = {}) {
  if (state.phase !== 'idle') return;
  state.current = { ...w, type: w.type || detectType(w.text), source: 'list' };
  store.set('ttobak.word', w.id);
  try { history.replaceState(null, '', `${location.pathname}${location.search}#w=${encodeURIComponent(w.id)}`); } catch { /* 무시 */ }
  if (w.category && w.category !== state.cat) setCategory(w.category);
  markSelected();
  renderTarget();
  if (!keepResult) resetResult();
  if (!quiet && matchMedia('(max-width: 900px)').matches) $('practice').scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' });
}

function initFreeInput() {
  const form = $('free-form'), input = $('free-text'), msg = $('free-msg');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (state.phase !== 'idle') return;
    const text = input.value.trim();
    msg.dataset.tone = '';
    if (!bare(text)) { msg.textContent = '한글로 단어나 짧은 문장을 입력해 주세요.'; msg.dataset.tone = 'error'; return; }
    msg.textContent = '발음을 확인하는 중…';
    try {
      const t = await api.target(text);
      state.current = { ...t, text: t.text || text, type: detectType(text), source: 'free', category: null, id: undefined };
      try { history.replaceState(null, '', `${location.pathname}${location.search}`); } catch { /* 무시 */ }
      markSelected();
      renderTarget();
      resetResult();
      msg.textContent = t.pron && bare(t.pron) !== bare(text) ? `[${t.pron}]${roParticle(t.pron)} 소리 나요. 녹음해 보세요.` : '준비됐어요. 녹음해 보세요.';
    } catch (err) {
      msg.dataset.tone = 'error';
      msg.textContent = (err.body && err.body.message) || '발음을 만들지 못했어요. 다른 말로 해 보세요.';
    }
  });
}

// ── 연습 카드 ─────────────────────────────────────────────
const TYPE_TEXT = { word: '단어', statement: '문장', question: '물음' };
/** 끝 억양 안내(연습 카드). 색이 아니라 화살표 아이콘과 문장으로 알린다 */
function tuneGuide(t) {
  const tune = targetTune(t);
  const type = t.type || t.sentence_type;
  if (!tune) return null;
  if (tune === 'rise') return { icon: 'rise', text: '끝을 올려요', sub: '예/아니요로 답하는 물음이에요. 마지막 음절에서 목소리를 올려요.' };
  if (tune === 'free') {
    return type === 'question'
      ? { icon: 'free', text: '끝을 내려도 돼요', sub: '묻는 말(뭐·어디 등)이 든 물음이라 끝을 내려도, 올려도 자연스러워요.' }
      : { icon: 'free', text: '끝은 자유롭게', sub: '끝을 편하게 내려도, 살짝 올려도 괜찮아요.' };
  }
  return { icon: 'fall', text: '끝을 편하게 내려요', sub: '말하는 문장이에요. 끝이 크게 올라가면 물음처럼 들려요.' };
}
function renderTarget() {
  const t = state.current;
  if (!t) return;
  const cat = state.categories.find((c) => c.id === t.category);
  const meta = [];
  if (t.source === 'free') meta.push(h('span', { class: 'tag', text: '직접 입력' }));
  else if (cat) meta.push(h('span', { class: 'tag', text: cat.name }));
  meta.push(h('span', { text: TYPE_TEXT[t.type] || '단어' }));
  if (t.focus && t.focus.length) meta.push(h('span', { text: `연습 소리 ${t.focus.map((f) => PHONE_JAMO[f] || f).join(' ')}` }));
  if (t.mock_note) meta.push(h('span', { text: t.mock_note }));
  $('target-meta').replaceChildren(...meta);

  const word = $('target-word');
  word.textContent = t.text;
  word.classList.toggle('long', bare(t.text).length > 5);

  const pron = $('target-pron');
  if (t.pron && bare(t.pron) !== bare(t.text)) {
    pron.replaceChildren(h('b', { lang: 'ko', text: `[${t.pron}]` }), `${roParticle(t.pron)} 소리 나요`);
    pron.hidden = false;
  } else pron.hidden = true;

  // 문장이면 끝 억양 안내
  const tg = tuneGuide(t);
  const tuneEl = $('target-tune');
  tuneEl.hidden = !tg;
  if (tg) tuneEl.replaceChildren(icon(tg.icon, 'i tune-icon'), h('strong', { text: tg.text }), h('span', { class: 'tune-sub', text: tg.sub }));

  // 발음형 안내: 추정한 발음(notes) + 다르게 말해도 맞는 발음(alt_prons)
  const notes = Array.isArray(t.notes) ? t.notes.filter((x) => typeof x === 'string' && x.trim()) : [];
  const alts = Array.isArray(t.alt_prons) ? t.alt_prons.filter((x) => typeof x === 'string' && x.trim()) : [];
  const nb = $('target-notes');
  const items = [];
  if (notes.length) {
    items.push(h('p', { class: 'note-title' }, icon('warn'), '실제 발음이 다를 수 있어요'));
    items.push(h('ul', {}, notes.map((n) => h('li', { lang: 'ko', text: n }))));
  }
  if (alts.length) {
    items.push(h('p', { class: 'note-alt', lang: 'ko' }, '이렇게 소리 나도 맞게 봐요: ',
      alts.slice(0, 3).map((a, i) => [i ? ', ' : '', h('b', { text: `[${a}]` })]),
      alts.length > 3 ? ` 외 ${alts.length - 3}개` : ''));
  }
  nb.replaceChildren(...items);
  nb.hidden = !items.length;
  nb.dataset.tone = notes.length ? 'warn' : 'info';

  const guide = $('lip-guide');
  const sylls = t.syllables || [];
  guide.replaceChildren(...sylls.map((s) => {
    const phs = (s.phones || []).map((i) => (t.phones || [])[i]).filter(Boolean);
    const vi = phs.findIndex((p) => VOWELS.has(p));
    const onsetLab = phs.slice(0, Math.max(0, vi)).some((p) => BILABIAL.has(p));
    const codaLab = vi >= 0 && phs.slice(vi + 1).some((p) => BILABIAL.has(p));
    const spelled = s.text && s.text !== s.pron ? s.text : null;
    return h('li', { class: 'lip-item' },
      h('span', { class: 'lip-syl', lang: 'ko' }, s.pron || s.text, spelled ? h('small', { text: `글자 ${spelled}` }) : null),
      lipIcon(s.lip),
      h('span', { class: 'lip-text', text: LIP_TEXT[s.lip] || LIP_TEXT.neutral }),
      onsetLab ? h('span', { class: 'lip-extra' }, lipIcon('closed', 'lip-icon lip-icon-sm'), '붙였다 떼기') : null,
      codaLab ? h('span', { class: 'lip-extra' }, lipIcon('closed', 'lip-icon lip-icon-sm'), '끝에 닫기') : null);
  }));
  guide.hidden = !sylls.length;

  const hint = $('target-hint');
  hint.textContent = t.hint || '';
  hint.hidden = !t.hint;
  renderHistoryInline();
}

function historyKey(t) { return t.id ? `w:${t.id}` : `t:${t.text}`; }
function getHistory(t) {
  const all = store.get('ttobak.history.v1', {});
  return (all && Array.isArray(all[historyKey(t)]) ? all[historyKey(t)] : []);
}
function pushHistory(t, scores) {
  if (!scores || scores.overall == null) return;
  const all = store.get('ttobak.history.v1', {}) || {};
  const k = historyKey(t);
  const list = Array.isArray(all[k]) ? all[k] : [];
  list.push({ at: Date.now(), overall: Math.round(scores.overall), accuracy: scores.accuracy == null ? null : Math.round(scores.accuracy) });
  all[k] = list.slice(-12);
  store.set('ttobak.history.v1', all);
}
function renderHistoryInline() {
  const el = $('history-inline');
  const t = state.current;
  const list = t ? getHistory(t) : [];
  el.textContent = list.length ? `최근 점수 ${list.slice(-5).map((x) => x.overall).join(' · ')}` : '';
}

// ── 기준 발음(speechSynthesis) ──────────────────────────────
function initTTS() {
  const btn = $('tts-btn');
  if (!('speechSynthesis' in window)) return;
  const pick = () => {
    const vs = speechSynthesis.getVoices().filter((v) => /^ko([-_]|$)/i.test(v.lang));
    if (!vs.length) return;
    koVoice = vs.find((v) => /yuna|유나|google/i.test(v.name)) || vs.find((v) => v.localService) || vs[0];
    btn.hidden = false;
  };
  pick();
  speechSynthesis.addEventListener ? speechSynthesis.addEventListener('voiceschanged', pick) : (speechSynthesis.onvoiceschanged = pick);
  btn.addEventListener('click', () => {
    if (!koVoice || !state.current || state.phase !== 'idle') return;
    if (speechSynthesis.speaking) { speechSynthesis.cancel(); return; }
    const u = new SpeechSynthesisUtterance(state.current.text);
    u.lang = 'ko-KR';
    u.voice = koVoice;
    u.rate = 0.8;
    const label = btn.querySelector('span');
    u.onstart = () => { label.textContent = '재생 중 — 누르면 멈춤'; };
    u.onend = u.onerror = () => { label.textContent = '기준 발음 듣기'; };
    speechSynthesis.speak(u);
  });
}

// ── 카메라·마이크 ──────────────────────────────────────────
const AUDIO_C = { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false };
const VIDEO_C = { facingMode: 'user', width: 640 };

/** 카메라 아래 안내 한 줄. key 로 어떤 안내인지 표시해 두면 나중에 그 안내만 지울 수 있다 */
function mediaNote(text, tone = '', key = '') {
  const el = $('media-note');
  el.textContent = text || '';
  el.dataset.tone = tone;
  el.dataset.key = key;
}
/** 계속 유지할 기본 안내(예: 카메라 없이 소리만) 설정 + 표시 */
function standingNote(text, tone = '') {
  media.standing = { text, tone };
  mediaNote(text, tone, 'standing');
}
function restoreNote() { mediaNote(media.standing.text, media.standing.tone, 'standing'); }

function noMic(reason) {
  const hasSamples = state.samples.length > 0;
  standingNote(`${reason} ${hasSamples ? '「샘플로 체험」에서 미리 녹음된 소리로 분석을 볼 수 있어요.' : ''}`.trim(), 'error');
  const empty = $('camera-empty');
  empty.replaceChildren(
    h('p', { class: 'camera-empty-title', text: '마이크를 쓸 수 없어요' }),
    h('p', { class: 'muted small', text: hasSamples ? '샘플로 체험 모드를 이용해 주세요.' : '브라우저 권한 설정을 확인해 주세요.' }),
    ...(hasSamples ? [h('button', { type: 'button', class: 'btn btn-primary', text: '샘플 목록으로', onclick: focusSamples })] : []),
  );
  if (hasSamples) $('samples').dataset.attention = 'true';
}

function focusSamples() {
  const sec = $('samples');
  sec.dataset.attention = 'true';
  sec.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'center' });
  const first = sec.querySelector('button');
  if (first) first.focus({ preventScroll: true });
}

function overlayColors() {
  const cs = getComputedStyle(document.documentElement);
  const g = (n, fb) => (cs.getPropertyValue(n) || '').trim() || fb;
  return { line: g('--overlay-line', '#8af3e9'), halo: g('--overlay-halo', 'rgba(0,0,0,.6)'), dot: g('--overlay-dot', '#fff') };
}

async function ensureMedia() {
  if (media.ready) return true;
  if (media.pending) return media.pending;
  media.pending = (async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      noMic('이 브라우저(또는 https가 아닌 주소)에서는 마이크를 쓸 수 없어요.');
      return false;
    }
    // 1) 마이크 먼저 따로 요청 — 카메라를 거부해도 소리 분석은 할 수 있게
    mediaNote('마이크 사용을 허용해 주세요.', '', 'ask');
    let audio = null;
    try {
      audio = await navigator.mediaDevices.getUserMedia({ audio: AUDIO_C });
    } catch (e) {
      console.warn('[media] 마이크 실패', e);
      noMic(e && e.name === 'NotAllowedError' ? '마이크 권한이 거부됐어요.' : '마이크를 찾지 못했어요.');
      return false;
    }
    const recorder = new Recorder({ onLevel: (lv) => { $('lv-fill').style.width = `${Math.round(lv * 100)}%`; } });
    try {
      await recorder.open(audio);            // 실패하면 recorder 가 자기 AudioContext 를 닫는다
    } catch (e) {
      console.warn(e);
      audio.getTracks().forEach((t) => t.stop());
      noMic(`녹음 장치를 시작하지 못했어요(${e.message}).`);
      return false;
    }
    media.stream = audio;
    media.recorder = recorder;

    // 2) 카메라는 따로 요청 — 실패하거나 거부해도 소리만으로 진행
    mediaNote('카메라를 허용하면 입모양도 함께 봐요. 거부해도 소리 분석은 할 수 있어요.', '', 'ask');
    let video = null;
    try {
      video = await navigator.mediaDevices.getUserMedia({ video: VIDEO_C });
    } catch (e) {
      console.warn('[media] 카메라 실패', e);
    }
    const vt = video ? video.getVideoTracks() : [];
    media.hasVideo = vt.length > 0;
    media.videoStream = media.hasVideo ? video : null;
    if (media.hasVideo) {
      const el = $('cam-video');
      el.srcObject = video;
      try { await el.play(); } catch { /* autoplay 정책 — muted 라 대개 통과 */ }
      $('camera-empty').hidden = true;
      $('dock').dataset.video = 'on';
      standingNote('');
      mediaNote('입술 인식 모델을 불러오는 중이에요…', '', 'lips-loading');
      startLips(el);
    } else {
      if (video) video.getTracks().forEach((t) => t.stop());
      $('dock').dataset.video = 'off';
      $('camera-empty').replaceChildren(
        h('p', { class: 'camera-empty-title', text: '카메라 없이 소리만 녹음해요' }),
        h('p', { class: 'muted small', text: '입모양 분석은 빠지고, 소리 분석은 그대로 해요.' }),
      );
      standingNote('카메라를 쓸 수 없어 소리만 분석해요.', 'warn');
    }
    media.ready = true;
    return true;
  })();
  const ok = await media.pending;
  media.pending = null;
  return ok;
}

function startLips(video) {
  const tracker = new LipTracker(video, $('cam-overlay'), { onFrame: onLipFrame, colors: overlayColors });
  tracker.init().then(() => {
    media.lips = tracker;
    tracker.start();
    $('live').hidden = false;
    if ($('media-note').dataset.key === 'lips-loading') mediaNote('');   // 다른 안내는 지우지 않는다
  }).catch((e) => {
    console.warn('[lips] 초기화 실패', e);
    media.lips = null;
    media.lipsFailed = true;
    $('live').hidden = true;
    if (state.phase === 'idle') standingNote('입술 인식을 불러오지 못했어요 — 소리만 분석해요.', 'warn');
    else media.standing = { text: '입술 인식을 불러오지 못했어요 — 소리만 분석해요.', tone: 'warn' };
  });
}

let lastShape = null;
function onLipFrame(f) {
  const openFill = $('open-fill'), widthFill = $('width-fill');
  const n = state.liveNeutral;
  if (!f) {
    openFill.style.width = '0%'; widthFill.style.width = '0%';
    if (lastShape !== 'none') { lastShape = 'none'; $('live-shape-icon').replaceChildren(); $('live-shape-text').textContent = '얼굴을 화면 가운데에'; }
    return;
  }
  const clamp = (v) => Math.max(0, Math.min(1, v));
  const oPos = (v) => clamp(v / 0.35), wPos = (v) => clamp((v - 0.3) / 0.45);
  openFill.style.width = `${(oPos(f.open) * 100).toFixed(1)}%`;
  widthFill.style.width = `${(wPos(f.width) * 100).toFixed(1)}%`;
  if (n) {
    const ot = $('open-tick'), wt = $('width-tick');
    ot.hidden = false; wt.hidden = false;
    ot.style.left = `${(oPos(n.open) * 100).toFixed(1)}%`;
    wt.style.left = `${(wPos(n.width) * 100).toFixed(1)}%`;
  }
  const shape = classifyLive(f, n);
  if (shape !== lastShape) {
    lastShape = shape;
    $('live-shape-icon').replaceChildren(lipIcon(shape));
    $('live-shape-text').textContent = LIP_TEXT[shape];
  }
}

// ── 녹음 ──────────────────────────────────────────────────
function setCaption(kind) {
  const cap = $('caption');
  if (!kind) { cap.hidden = true; cap.replaceChildren(); return; }
  cap.hidden = false;
  if (kind === 'prep') {
    cap.replaceChildren('준비 — 입을 다물고 기다리세요', h('small', { text: '평소 입모양을 재는 중이에요' }), h('div', { class: 'caption-progress' }, h('span', { id: 'cap-prog' })));
  } else if (kind === 'speak') {
    cap.replaceChildren(`지금 말하세요 · ${state.current ? state.current.text : ''}`, h('small', { text: '다 말했으면 정지(스페이스바)' }), h('div', { class: 'caption-progress' }, h('span', { id: 'cap-prog' })));
  } else if (kind === 'stopping') {
    cap.replaceChildren('녹음을 마무리하는 중…');
  }
}

function updateRecUI() {
  const btn = $('rec-btn'), label = $('rec-label');
  const recording = state.phase === 'prep' || state.phase === 'speak';
  btn.dataset.state = recording ? 'recording' : state.phase;
  btn.querySelector('use').setAttribute('href', recording ? '#i-stop' : '#i-mic');
  label.textContent = recording ? '정지' : state.phase === 'analyzing' ? '분석 중…' : state.phase === 'starting' ? '준비 중…' : state.phase === 'stopping' ? '마무리 중…' : '녹음 시작';
  // disabled 대신 aria-disabled: 키보드 포커스가 버튼에 남아 있게(클릭은 각 처리기가 상태를 보고 무시)
  setBusy(btn, state.phase === 'analyzing' || state.phase === 'starting' || state.phase === 'stopping');
  setBusy($('tts-btn'), state.phase !== 'idle');
  for (const b of document.querySelectorAll('.sample-item .btn, #free-form button')) setBusy(b, state.phase !== 'idle');
}
function setBusy(el, busy) {
  if (!el) return;
  if (busy) el.setAttribute('aria-disabled', 'true');
  else el.removeAttribute('aria-disabled');
}

async function toggleRecording() {
  if (state.phase === 'idle') return startRecording();
  if (state.phase === 'prep' || state.phase === 'speak') return stopRecording();
}

async function startRecording() {
  if (!state.current) return;
  state.phase = 'starting';
  updateRecUI();
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  const ok = await ensureMedia();
  if (!ok || !media.recorder) { state.phase = 'idle'; updateRecUI(); return; }
  let t0;
  try { t0 = await media.recorder.start(); } catch (e) { console.warn(e); mediaNote('녹음을 시작하지 못했어요.', 'error'); state.phase = 'idle'; updateRecUI(); return; }
  // 녹음을 시작한 순간 준비된 입술 추적기만 쓴다(녹음 중에 모델이 늦게 올라와도 그 녹음에는 안 씀)
  state.capTracker = media.lips || null;
  if (state.capTracker) state.capTracker.beginCapture(t0);
  state.phase = 'prep';
  setCaption('prep');
  updateRecUI();
  // 좁은 화면에서 카메라·자막·녹음 버튼이 화면 밖이면 보이게
  $('dock').scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'nearest' });
  $('sr-live').textContent = '녹음 시작. 입을 다물고 잠깐 기다리세요.';
  const tick = () => {
    if (state.phase !== 'prep' && state.phase !== 'speak') return;
    const el = media.recorder.elapsed;
    $('rec-time').textContent = `${el.toFixed(1)} / ${MAX_SEC}초`;
    const prog = $('cap-prog');
    if (state.phase === 'prep') {
      if (prog) prog.style.width = `${Math.min(100, (el / PREP_SEC) * 100)}%`;
      if (el >= PREP_SEC) { state.phase = 'speak'; setCaption('speak'); $('sr-live').textContent = '지금 말하세요.'; }
    } else if (prog) prog.style.width = `${Math.min(100, ((el - PREP_SEC) / (MAX_SEC - PREP_SEC)) * 100)}%`;
    if (el >= MAX_SEC) { stopRecording(); return; }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

async function stopRecording() {
  if (state.phase !== 'prep' && state.phase !== 'speak') return;
  state.phase = 'stopping';
  setCaption('stopping');
  updateRecUI();
  let rec = null;
  try { rec = await media.recorder.stop(); } catch (e) { console.warn(e); }
  const tracker = state.capTracker;
  state.capTracker = null;
  // 녹음 전체로 다듬은 입력 기준 t0 로 입술 프레임 시각을 다시 맞춘다
  const frames = tracker ? tracker.endCapture(rec ? rec.duration + 0.05 : Infinity, rec ? rec.t0Perf : null) : [];
  setCaption(null);
  $('rec-time').textContent = rec ? `${rec.duration.toFixed(1)} / ${MAX_SEC}초` : `0.0 / ${MAX_SEC}초`;
  if (!rec || rec.duration < PREP_SEC + 0.35) {
    state.phase = 'idle';
    updateRecUI();
    mediaNote('녹음이 너무 짧았어요. 준비 표시가 끝난 뒤에 말해 주세요.', 'warn');
    return;
  }
  const lips = buildLipsPayload(frames);
  if (lips && lips.neutral) state.liveNeutral = lips.neutral;
  setReplay(rec.blob);
  // 입모양이 빠진 이유(안내와 결과 화면에 같이 씀)
  let lipsSkip = null;
  if (!lips) {
    if (!media.hasVideo) lipsSkip = 'no-camera';
    else if (!tracker) lipsSkip = media.lipsFailed ? 'lips-failed' : 'loading';
    else lipsSkip = 'no-face';
  }
  if (lipsSkip === 'loading') mediaNote('입술 인식 모델을 아직 불러오는 중이라 이번에는 소리만 분석해요.', 'warn');
  else if (lipsSkip === 'no-face') mediaNote('얼굴이 잘 보이지 않아 이번에는 입모양 없이 분석해요.', 'warn');
  else restoreNote();
  state.phase = 'analyzing';
  updateRecUI();
  await analyze({ blob: rec.blob, lips, target: state.current, lipsSkip });
  state.phase = 'idle';
  updateRecUI();
}

function setReplay(blob) {
  if (replayUrl) URL.revokeObjectURL(replayUrl);
  replayUrl = URL.createObjectURL(blob);
  const audio = $('replay-audio');
  audio.src = replayUrl;
  $('replay-btn').disabled = false;
}

function initReplay() {
  const btn = $('replay-btn'), audio = $('replay-audio'), label = btn.querySelector('span'), use = btn.querySelector('use');
  btn.addEventListener('click', () => {
    if (!audio.src) return;
    if (!audio.paused) { audio.pause(); return; }
    audio.currentTime = 0;
    audio.play().catch((e) => console.warn(e));
  });
  audio.addEventListener('play', () => { label.textContent = '멈춤'; use.setAttribute('href', '#i-stop'); });
  const reset = () => { label.textContent = '다시 듣기'; use.setAttribute('href', '#i-play'); };
  audio.addEventListener('pause', reset);
  audio.addEventListener('ended', reset);
}

function initKeys() {
  // 스페이스바 = 녹음 시작·정지. 단, 포커스가 상호작용 요소(버튼·탭·라디오·summary·입력칸·링크 등)에
  // 있으면 그 요소의 스페이스 동작을 그대로 둔다(키보드 사용자가 버튼을 누르거나 고를 수 있게).
  const INTERACTIVE = [
    'a[href]', 'button', 'input', 'select', 'textarea', 'summary', 'label',
    'audio[controls]', 'video[controls]', '[contenteditable]:not([contenteditable="false"])',
    '[role="button"]', '[role="tab"]', '[role="radio"]', '[role="checkbox"]', '[role="switch"]',
    '[role="menuitem"]', '[role="option"]', '[role="slider"]', '[role="link"]',
    '[tabindex]:not([tabindex="-1"])',
  ].join(',');
  const interactive = (t) => !!(t && t !== document.body && t !== document.documentElement && t.closest && t.closest(INTERACTIVE));
  const isSpace = (e) => e.code === 'Space' || e.key === ' ';
  document.addEventListener('keydown', (e) => {
    if (!isSpace(e) || e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented) return;
    if (interactive(e.target)) return;
    e.preventDefault();                  // 페이지가 스크롤되지 않게
    if (e.repeat) return;
    toggleRecording();
  });
}

// ── 샘플(데모 모드) ────────────────────────────────────────
async function loadSamples() {
  const data = await api.samples().catch(() => null);
  if (!data || !data.samples || !data.samples.length) return;
  state.samples = data.samples;
  $('sample-list').replaceChildren(...data.samples.map((s) => h('li', { class: 'sample-item' },
    h('button', { type: 'button', class: 'btn btn-line', 'aria-label': `${s.label} 샘플로 분석`, onclick: () => runSample(s) }, icon('play'), '분석'),
    h('span', { class: 'sample-label', text: s.label || s.text }),
    h('span', { class: 'sample-note', text: s.note || '' }))));
  $('samples').hidden = false;
}

async function runSample(s) {
  if (state.phase !== 'idle') return;
  const w = state.words.find((x) => x.id === s.word_id);
  if (w) selectWord(w, { quiet: true });
  else {
    state.current = { text: s.text, pron: s.pron, type: s.sentence_type || detectType(s.text), source: 'free', syllables: [] };
    markSelected();
    renderTarget();
    resetResult();
    api.target(s.text).then((t) => { if (state.current && state.current.text === s.text) { state.current = { ...state.current, ...t, pron: s.pron || t.pron }; renderTarget(); } }).catch(() => {});
  }
  const target = {
    id: s.word_id || (w && w.id),
    text: s.text,
    pron: s.pron || (w && w.pron),
    type: s.sentence_type || (w && w.type) || detectType(s.text),
  };
  state.phase = 'analyzing';
  updateRecUI();
  const name = s.label || s.text;
  setResultState('loading', `샘플 「${name}」${josa(name, '을', '를')} 분석하고 있어요…`);
  try {
    const res = await fetch(new URL(s.file, document.baseURI));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    setReplay(blob);
    await analyze({ blob, lips: null, target, sample: s });
  } catch (e) {
    showError('샘플 파일을 불러오지 못했어요', `${s.file} (${e.message})`);
  }
  state.phase = 'idle';
  updateRecUI();
}

// ── 분석 ──────────────────────────────────────────────────
const ERROR_TITLE = {
  no_speech: '말소리가 잘 들리지 않았어요',
  bad_audio: '녹음 파일을 읽지 못했어요',
  empty_target: '연습할 글자가 없어요',
  model_loading: '분석 모델을 준비하고 있어요',
  model_error: '분석 모델을 불러오지 못했어요',
  too_long: '연습할 말이 너무 길어요',
  too_large: '녹음이 너무 커요',
  bad_request: '요청을 처리하지 못했어요',
  not_found: '분석 주소를 찾지 못했어요',
};

async function analyze({ blob, lips, target, sample = null, lipsSkip = null }) {
  const fd = new FormData();
  fd.append('audio', blob, 'speech.wav');
  fd.append('text', target.text);
  if (target.pron) fd.append('pron', target.pron);
  if (target.id) fd.append('word_id', target.id);
  fd.append('voice', state.voice);
  fd.append('sentence_type', target.type || detectType(target.text));
  if (lips) fd.append('lips', JSON.stringify(lips));
  const ctx = { voice: state.voice, neutral: lips ? lips.neutral || null : null, hadLips: !!lips, lipsSkip, sample, target };
  setResultState('loading', sample ? null : '소리를 분석하고 있어요…');
  let res;
  try {
    res = await api.analyze(fd);
  } catch (e) {
    showError('서버에 연결하지 못했어요', `서버가 켜져 있는지 확인해 주세요. (${e.message})`);
    return;
  }
  const { status, body } = res;
  if (status === 422 || (body && body.error)) {
    showError(ERROR_TITLE[body && body.error] || '분석하지 못했어요', (body && body.message) || '다시 녹음해 주세요.');
    return;
  }
  if (status !== 200 || !body || !body.scores) {
    showError('분석 중 문제가 생겼어요', `서버 응답 ${status}. 잠시 뒤 다시 해 주세요.`);
    return;
  }
  state.lastResult = body;
  state.lastCtx = ctx;
  if (!sample) {                       // 샘플 결과는 내 시도 기록에 넣지 않는다
    pushHistory(target, body.scores);
    renderHistoryInline();
  }
  renderResult(body, ctx);
}

// ── 결과 화면 ─────────────────────────────────────────────
function setResultState(kind, loadingText) {
  const body = $('result-body');
  $('result').setAttribute('aria-busy', String(kind === 'loading'));
  $('result-empty').hidden = kind !== 'empty';
  $('result-loading').hidden = kind !== 'loading';
  $('result-error').hidden = kind !== 'error';
  if (kind === 'loading') {
    if (loadingText) $('loading-text').textContent = loadingText;
    body.classList.toggle('stale', !body.hidden);   // 이전 결과는 흐리게 유지(레이아웃 점프 방지)
  } else if (kind === 'shown') {
    body.hidden = false;
    body.classList.remove('stale');
  } else {
    body.hidden = true;
    body.classList.remove('stale');
  }
}

function resetResult() {
  state.lastResult = null;
  setResultState('empty');
}

function showError(title, message) {
  $('error-title').textContent = title;
  $('error-body').textContent = message || '';
  setResultState('error');
  $('sr-live').textContent = `${title}. ${message || ''}`;
}

const SYL_STATUS = { ok: ['ok', '좋아요'], warn: ['warn', '아쉬워요'], error: ['error', '달라요'] };
const PH_STATUS = { ok: ['ok', '좋음', 'chip-ok'], weak: ['warn', '약함', 'chip-warn'], sub: ['error', '다르게 들림', 'chip-error'], del: ['error', '빠짐', 'chip-error'] };
const FB_ICON = { error: 'error', warn: 'warn', info: 'ok' };
const VOICE_TEXT = { female: '성인 여성', male: '성인 남성', child: '아동' };

function renderResult(r, ctx) {
  setResultState('shown');
  renderScores(r, ctx);
  renderTrend(ctx.target, ctx);
  renderCompare(r);
  renderSyllables(r);
  renderFeedback(r);
  renderPhones(r);
  renderCharts(r, ctx);
  const m = r.meta || {};
  $('meta').textContent = [
    m.elapsed_ms != null ? `분석 ${m.elapsed_ms} ms` : null,
    m.model || null,
    `기준 ${VOICE_TEXT[ctx.voice]}`,
    ctx.sample ? `샘플: ${ctx.sample.label || ctx.sample.id}` : null,
    m.mock ? '목업 응답' : null,
  ].filter(Boolean).join(' · ');
  announce(r);
  if (matchMedia('(max-width: 1200px)').matches) $('result').scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' });
}

/** 억양 점수가 없을 때 이유(서버 feedback._intonation_score 가 null 을 내는 조건과 맞춤) */
function intonationWhy(r, ctx) {
  const fs = (r.acoustic && r.acoustic.f0_stats) || {};
  if (fs.voiced_ratio != null && fs.voiced_ratio < 0.05) return '목소리 높이를 거의 잡지 못했어요';
  const tune = targetTune(r.target) || targetTune(ctx.target);
  if (tune === 'rise') return '끝부분의 목소리 높이를 잡지 못했어요';
  return '목소리 높낮이를 잡지 못했어요';
}
const LIPS_SKIP = {
  'no-camera': ['카메라 없이 녹음', '카메라 없이 녹음해서 입모양은 측정하지 않았어요.'],
  loading: ['입술 인식 준비 중이었어요', '입술 인식 모델을 불러오는 중이라 이번에는 입모양 없이 분석했어요. 다시 녹음하면 함께 봐요.'],
  'lips-failed': ['입술 인식을 쓸 수 없었어요', '입술 인식을 불러오지 못해 입모양은 측정하지 않았어요.'],
  'no-face': ['얼굴이 잘 안 보였어요', '얼굴이 잘 보이지 않아 이번에는 입모양 없이 분석했어요. 얼굴이 화면 가운데에 잘 보이게 해 주세요.'],
};
/** 입모양 점수가 없을 때 [짧은 이유, 긴 설명] — 서버 lips.score 가 null 인 조건과 맞춤 */
function lipsWhy(r, ctx) {
  if (ctx.sample) return ['샘플에는 입술 데이터가 없어요', '샘플 음성에는 입술 데이터가 없어요. 카메라를 켜고 직접 녹음하면 입모양도 함께 봐요.'];
  const lp = r.lips || {};
  if (ctx.hadLips) {
    return lp.available
      ? ['판정할 입모양이 없었어요', '이번 말에는 입모양을 판정할 만한 소리 구간이 없었어요.']
      : ['얼굴이 잘 안 보였어요', '입술 데이터가 부족해서 입모양을 판정하지 못했어요. 얼굴이 화면 가운데에 잘 보이게 해 주세요.'];
  }
  return LIPS_SKIP[ctx.lipsSkip] || LIPS_SKIP['no-camera'];
}

function renderScores(r, ctx) {
  const s = r.scores || {};
  const tile = (label, v, why) => h('div', { class: 'tile' },
    h('span', { class: 'label', text: label }),
    v == null
      ? [h('span', { class: 'value na', text: '측정 안 됨' }), why ? h('span', { class: 'muted small', text: why }) : null]
      : [h('span', { class: 'value', text: String(Math.round(v)) }), h('span', { class: 'bar', role: 'presentation' }, h('span', { style: `width:${Math.max(0, Math.min(100, v))}%` }))]);
  $('scores').replaceChildren(
    h('div', { class: 'score-hero' },
      h('span', { class: 'label', text: '종합 점수' }),
      h('span', { class: 'value' }, s.overall == null ? '—' : String(Math.round(s.overall)), h('small', { text: '/ 100' }))),
    h('div', { class: 'score-tiles' },
      tile('정확도', s.accuracy),
      tile('또렷함', s.clarity),
      tile('억양', s.intonation, intonationWhy(r, ctx)),
      tile('입모양', s.lips, lipsWhy(r, ctx)[0]),
    ),
  );
}

function renderTrend(target, ctx = {}) {
  const el = $('trend');
  if (ctx.sample) { el.replaceChildren(h('span', { text: '샘플 결과는 내 시도 기록에 넣지 않아요.' })); return; }
  const list = target ? getHistory(target) : [];
  if (list.length < 2) { el.replaceChildren(list.length ? h('span', { text: '첫 기록이에요. 다시 해 보면 변화가 보여요.' }) : ''); return; }
  const vals = list.map((x) => x.overall);
  const last = vals[vals.length - 1], prev = vals[vals.length - 2];
  const diff = last - prev;
  el.replaceChildren(
    h('span', { text: `이 단어 시도 ${list.length}번` }),
    sparklineSVG(vals.slice(-10)),
    h('span', { class: 'nums', text: vals.slice(-5).join(' → ') }),
    h('span', { text: diff > 0 ? `지난번보다 ${diff}점 올랐어요` : diff < 0 ? `지난번보다 ${-diff}점 낮아요` : '지난번과 같아요' }),
  );
}

function renderCompare(r) {
  const tp = (r.target && r.target.pron) || '';
  const hp = r.heard && r.heard.pron_guess;
  const vn = (r.target && Array.isArray(r.target.variant_notes) ? r.target.variant_notes : []).filter((x) => typeof x === 'string' && x.trim());
  $('compare').replaceChildren(
    h('div', {}, h('span', { class: 'label', text: '목표 소리' }), h('span', { class: 'val', lang: 'ko', text: `[${tp}]` })),
    h('div', {}, h('span', { class: 'label', text: '들린 소리' }),
      h('span', { class: `val${hp && bare(hp) !== bare(tp) ? ' diff' : ''}`, lang: 'ko', text: hp ? `[${hp}]` : '알아듣기 어려워요' })),
    ...(vn.length ? [h('ul', { class: 'variant-notes' }, vn.map((n) => h('li', { lang: 'ko' }, icon('info'), n)))] : []),
  );
}

function renderSyllables(r) {
  $('syl-blocks').replaceChildren(...(r.syllables || []).map((s) => {
    const [cls, txt] = SYL_STATUS[s.status] || SYL_STATUS.warn;
    const heard = s.status !== 'ok' ? heardSyllable(r, s) : null;
    let heardEl = null;
    if (heard && heard.text && heard.text !== s.text) heardEl = h('span', { class: 'syl-heard', lang: 'ko', text: `들림 [${heard.text}]` });
    else if (heard && heard.note) heardEl = h('span', { class: 'syl-heard', lang: 'ko', text: heard.note });
    return h('li', { class: 'syl', dataset: { status: cls } },
      h('span', { class: 'syl-text', lang: 'ko', text: s.text }),
      s.orth && s.orth !== s.text ? h('span', { class: 'syl-orth', lang: 'ko', text: `글자 ${s.orth}` }) : null,
      h('span', { class: 'syl-state' }, icon(cls === 'ok' ? 'ok' : cls === 'warn' ? 'warn' : 'error'), txt),
      heardEl);
  }));
}

function renderFeedback(r) {
  const fb = r.feedback || [];
  // info 카드는 칭찬(kind=praise)만 초록 체크. '약함(weak)' 같은 정보 카드는 체크가 아니라 안내(i) 표시
  const tipCard = (f) => f.level === 'info' && f.kind && f.kind !== 'praise';
  $('feedback').replaceChildren(...(fb.length ? fb.map((f) => h('li', { class: 'fb', dataset: { level: f.level, kind: f.kind || '' } },
    icon(tipCard(f) ? 'info' : FB_ICON[f.level] || 'info'),
    h('p', { class: 'fb-title', text: f.title }),
    f.body ? h('p', { class: 'fb-body', text: f.body }) : null))
    : [h('li', { class: 'fb', dataset: { level: 'info', kind: 'praise' } }, icon('ok'), h('p', { class: 'fb-title', text: '크게 고칠 점이 없어요. 잘했어요!' }))]));
}

function renderPhones(r) {
  const ins = r.insertions || [];
  const rows = [];
  const insRow = (x) => h('li', { class: 'ph ph-ins' },
    h('span', { class: 'ph-pair' }, h('span', { class: 'arrow', text: '+' }), x.jamo || PHONE_JAMO[x.phone] || x.phone, h('span', { class: 'ph-sym', text: x.phone })),
    h('span', { class: 'chip chip-warn' }, icon('warn'), '끼어든 소리'),
    h('span', { class: 'muted small', text: '없어야 할 소리가 더 들렸어요' }));
  for (const x of ins) if (x.after == null || x.after < 0) rows.push(insRow(x));
  for (const p of r.phones || []) {
    const [, txt, chip] = PH_STATUS[p.status] || PH_STATUS.weak;
    const pair = [h('span', { text: p.jamo })];
    if (p.status === 'sub') pair.push(h('span', { class: 'arrow', text: '→' }), h('span', { class: 'heard', text: p.heard_jamo || '?' }));
    if (p.status === 'del') pair.push(h('span', { class: 'arrow', text: '→' }), h('span', { class: 'gone', text: '빠짐' }));
    const gop = p.gop == null ? null : Math.round(p.gop);
    rows.push(h('li', { class: 'ph', dataset: { status: p.status } },
      h('span', { class: 'ph-pair', lang: 'ko' }, pair, h('span', { class: 'ph-sym', text: p.status === 'sub' ? `${p.phone} → ${p.heard}` : p.phone })),
      h('span', { class: `chip ${chip}` }, icon(p.status === 'ok' ? 'ok' : p.status === 'weak' ? 'warn' : 'error'), txt),
      h('span', { class: 'gop', title: '모델이 본 목표 소리 확신도(0–100)' },
        h('span', { class: 'gop-bar', role: 'presentation' }, h('span', { style: `width:${gop == null ? 0 : gop}%` })),
        h('span', { class: 'gop-num', text: gop == null ? '—' : String(gop) })),
      p.tip ? h('p', { class: 'ph-tip', text: p.tip }) : null,
      // 서버가 '정상 변이'로 보고 맞게 둔 소리(계약 외 phones[].variant): 왜 맞게 봤는지 짧게
      p.status === 'ok' && typeof p.variant === 'string' && p.variant
        ? h('p', { class: 'ph-variant' }, icon('info'), `자연스러운 발음 변화(${p.variant})라 맞게 봤어요`) : null));
    for (const x of ins) if (x.after === p.idx) rows.push(insRow(x));
  }
  $('phone-list').replaceChildren(...rows);
}

function meanIn(ts, vs, a, b) {
  let s = 0, n = 0;
  for (let i = 0; i < ts.length; i++) if (ts[i] >= a && ts[i] <= b && vs[i] != null) { s += vs[i]; n++; }
  return n ? s / n : null;
}

function renderCharts(r, ctx) {
  const win = timeWindow(r);
  const ac = r.acoustic || {};
  const base = { phones: r.phones || [], syllables: r.syllables || [], win };

  // (a) 음높이·크기
  renderProsody($('cv-prosody'), { ...base, acoustic: ac });
  const fs = ac.f0_stats || {}, ld = ac.loudness || {};
  const f0t = (ac.f0 && ac.f0.t) || [], f0v = (ac.f0 && ac.f0.hz) || [];
  const it = (ac.intensity && ac.intensity.t) || [], iv = cleanIntensity(ac.intensity && ac.intensity.db).db;   // −300 바닥값 제외
  const num = (v, d = 0) => (v == null ? '—' : Number(v).toFixed(d));
  const statTable = h('table', {},
    h('tbody', {},
      h('tr', {}, h('th', { text: '평균 음높이' }), h('td', { class: 'num', text: `${num(fs.mean)} Hz` }), h('th', { text: '음높이 폭' }), h('td', { class: 'num', text: `${num(fs.range_st, 1)} 반음` })),
      h('tr', {}, h('th', { text: '최저 · 최고' }), h('td', { class: 'num', text: `${num(fs.min)} · ${num(fs.max)} Hz` }), h('th', { text: '유성 비율' }), h('td', { class: 'num', text: fs.voiced_ratio == null ? '—' : `${Math.round(fs.voiced_ratio * 100)}%` })),
      h('tr', {}, h('th', { text: '평균 크기' }), h('td', { class: 'num', text: `${num(ld.mean_db)} dB` }), h('th', { text: '최대 크기' }), h('td', { class: 'num', text: `${num(ld.max_db)} dB` }))));
  const phTable = h('table', {},
    h('thead', {}, h('tr', {}, ['소리', '시간(초)', '상태', '음높이', '크기'].map((t) => h('th', { text: t })))),
    h('tbody', {}, (r.phones || []).filter((p) => p.start != null).map((p) => {
      const f = meanIn(f0t, f0v, p.start, p.end), d = meanIn(it, iv, p.start, p.end);
      return h('tr', {},
        h('td', { text: p.status === 'sub' ? `${p.jamo}→${p.heard_jamo}` : p.jamo }),
        h('td', { class: 'num', text: `${p.start.toFixed(2)}–${p.end.toFixed(2)}` }),
        h('td', { text: (PH_STATUS[p.status] || PH_STATUS.weak)[1] }),
        h('td', { class: 'num', text: f == null ? '무성' : `${Math.round(f)} Hz` }),
        h('td', { class: 'num', text: d == null ? '—' : `${Math.round(d)} dB` }));
    })));
  $('prosody-table').replaceChildren(statTable, phTable);
  const tune = targetTune(r.target) || targetTune(ctx.target);
  $('prosody-desc').textContent = {
    rise: '예/아니요로 답하는 물음이에요 — 마지막 음절에서 점(음높이)이 올라가야 해요. 선은 소리 크기, 아래 띠는 각 소리가 난 시간이에요.',
    free: '이 말은 끝을 내려도, 올려도 자연스러워요. 점은 목소리 높이, 선은 소리 크기, 아래 띠는 각 소리가 난 시간이에요.',
    fall: '말하는 문장은 끝을 편하게 내려요. 끝이 크게 올라가면 물음처럼 들려요. 점은 목소리 높이, 선은 소리 크기예요.',
  }[tune] || '점은 목소리 높이, 선은 소리 크기예요. 아래 띠는 각 소리가 난 시간이에요(말한 구간만 확대).';

  // (b) 모음
  $('formant-ref-label').textContent = `참고 모음(${VOICE_TEXT[ctx.voice] || '성인 여성'})`;
  renderFormants($('cv-formant'), { acoustic: ac, voice: ctx.voice, phones: r.phones || [], syllables: r.syllables || [] });
  const vd = { phones: r.phones || [], syllables: r.syllables || [] };
  const hz = (v) => `F1 ${Math.round(v.f1)} · F2 ${Math.round(v.f2)} Hz`;
  $('vowel-notes').replaceChildren(...(ac.vowels || []).map((v) => {
    const st = vowelState(v);
    const [chip, ic, label, text] = {
      short: ['chip-info', 'info', '짧아서 측정 안 함', '소리가 짧아 모음 위치를 재지 않았어요'],
      unmeasured: ['chip-info', 'info', '측정 안 됨', v.unreliable === 'measure' ? '값이 크게 튀어서 이번에는 보여 주지 않아요' : '목소리가 약하거나 짧아 재지 못했어요'],
      noref: ['chip-info', 'info', '비교 안 함', v.f1 != null ? `${hz(v)} · 참고치가 없는 모음이에요` : '참고치가 없는 모음이에요'],
      in: ['chip-ok', 'ok', '참고 범위 안', v.f1 != null ? hz(v) : ''],
      out: ['chip-warn', 'warn', '참고 범위 밖', `${vowelHint(v) || ''} (참고용)`],
    }[st];
    return h('li', {},
      h('span', { class: 'name', lang: 'ko', text: vowelName(v, vd) }),
      h('span', { class: `chip ${chip}` }, icon(ic), label),
      h('span', { text }));
  }));

  // (c) 입술
  const lips = r.lips || {};
  const has = lips.available && lips.series && (lips.series.t || []).length > 1;
  $('lips-wrap').hidden = !has;
  $('lips-legend').hidden = !has;
  $('lips-empty').hidden = !!has;
  if (has) {
    renderLips($('cv-lips'), { ...base, lips, neutral: ctx.neutral });
  } else {
    $('lips-empty').textContent = lipsWhy(r, ctx)[1];
  }
  if (has && !(lips.checks || []).length) {
    $('lips-empty').hidden = false;
    $('lips-empty').textContent = '이번 말에는 입모양을 판정할 만한 소리 구간이 없었어요. 입술 움직임만 참고로 보세요.';
  }
  $('lip-checks').replaceChildren(...(has ? (lips.checks || []) : []).map((c) => {
    const p = (r.phones || [])[c.idx];
    return h('li', {},
      h('span', { class: 'name', lang: 'ko', text: p ? `${p.jamo} (${(r.syllables[p.syl] || {}).text || ''})` : c.phone }),
      c.ok ? h('span', { class: 'chip chip-ok' }, icon('ok'), '맞음') : h('span', { class: 'chip chip-warn' }, icon('warn'), '아쉬움'),
      h('span', { text: c.msg || LIP_TEXT[c.expect] || '' }));
  }));
}

function announce(r) {
  const s = r.scores || {};
  const parts = [`분석 완료. 종합 ${s.overall == null ? '측정 안 됨' : Math.round(s.overall) + '점'}`];
  const bad = (r.syllables || []).filter((x) => x.status !== 'ok');
  parts.push(bad.length ? bad.map((x) => `${x.text} ${(SYL_STATUS[x.status] || SYL_STATUS.warn)[1]}`).join(', ') : '모든 음절이 좋아요');
  // 고칠 점(error → warn 순)을 먼저 읽는다. 없을 때만 첫 카드(칭찬 등)를 읽는다
  const fb = (r.feedback || []).filter((f) => f && f.title);
  const important = [...fb.filter((f) => f.level === 'error'), ...fb.filter((f) => f.level === 'warn')];
  if (important.length) {
    parts.push(...important.slice(0, 2).map((f) => f.title.replace(/[.!?。]+$/, '')));
    if (important.length > 2) parts.push(`고칠 점이 ${important.length - 2}개 더 있어요`);
  } else if (fb[0]) parts.push(fb[0].title.replace(/[.!?。]+$/, ''));
  $('sr-live').textContent = parts.join('. ') + '.';
}

// ── 시작 ──────────────────────────────────────────────────
function init() {
  if (MOCK) $('mock-banner').hidden = false;
  initTheme();
  initVoice();
  initTTS();
  initFreeInput();
  initReplay();
  initKeys();
  $('rec-btn').addEventListener('click', toggleRecording);
  $('media-btn').addEventListener('click', () => ensureMedia());
  $('dock').dataset.video = 'off';
  $('live').hidden = true;
  updateRecUI();
  checkHealth();
  loadSamples();
  loadWords();
  // 목업 확인용: ?mock=1&autorun=1 이면 첫 샘플을 바로 분석
  if (MOCK && params.get('autorun') === '1') {
    const wait = setInterval(() => {
      if (state.samples.length && state.words.length) { clearInterval(wait); runSample(state.samples[0]); }
    }, 100);
  }
  // 페이지를 떠나면 장치 해제
  addEventListener('pagehide', () => {
    if (media.stream) media.stream.getTracks().forEach((t) => t.stop());
    if (media.videoStream) media.videoStream.getTracks().forEach((t) => t.stop());
    if (media.lips) media.lips.close();
    if (media.recorder) media.recorder.close().catch(() => {});
    // 뒤로 가기 캐시로 다시 돌아오면 장치를 새로 연다
    Object.assign(media, { ready: false, stream: null, videoStream: null, recorder: null, lips: null, hasVideo: false });
    $('dock').dataset.video = 'off';
    $('live').hidden = true;
  });
}

init();
