// charts.js — 라이브러리 없이 canvas 로 그리는 결과 차트 3종
//  (a) renderProsody : 음높이(F0, 점) 패널 + 크기(강도, 선) 패널 — 축이 다른 두 값은 패널을 나눈다(이중 축 금지)
//                      x축 아래에 음소 구간 띠(자모)와 음절 줄
//  (b) renderFormants: 모음 포먼트 — x = F2(오른쪽이 작음), y = F1(아래로 증가), 참고치는 모음 글자, 내 값은 점 + 화살표
//  (c) renderLips    : 입 벌림/너비/동그랗게 시계열(레인 3개) + 음소 구간 띠 + 입모양 판정
// 색·글꼴은 전부 CSS 토큰(getComputedStyle)에서 읽고, 테마가 바뀌면 다시 그린다.
// 포인터·키보드(←/→)로 값 읽기 가능. 같은 값은 표/문장으로도 따로 제공(툴팁만으로 막지 않음).

export const FORMANT_REF = { // server/phones.py FORMANT_REF 와 같은 값(시각화용 참고치)
  male: { A: [740, 1310], EO: [560, 990], O: [400, 760], U: [340, 890], EU: [370, 1500], I: [290, 2200], E: [480, 1880] },
  female: { A: [930, 1560], EO: [680, 1180], O: [470, 870], U: [400, 1000], EU: [430, 1680], I: [340, 2700], E: [590, 2300] },
  child: { A: [1050, 1750], EO: [780, 1320], O: [540, 980], U: [460, 1130], EU: [490, 1900], I: [390, 3000], E: [680, 2600] },
};
const VOWEL_JAMO = { A: 'ㅏ', EO: 'ㅓ', O: 'ㅗ', U: 'ㅜ', EU: 'ㅡ', I: 'ㅣ', E: 'ㅔ', iA: 'ㅑ', iE: 'ㅖ', iEO: 'ㅕ', iO: 'ㅛ', iU: 'ㅠ', oA: 'ㅘ', oE: 'ㅙ', uEO: 'ㅝ', uI: 'ㅟ', euI: 'ㅢ' };
const ROUNDED = new Set(['O', 'U', 'iO', 'iU']);
const STATUS_TEXT = { ok: '좋음', weak: '약함', sub: '다르게 들림', del: '빠짐' };
const EXPECT_TEXT = { round: '동그랗게', spread: '옆으로', open: '크게 벌리기', closed: '입술 닫기', neutral: '편하게' };

// ── 토큰 ─────────────────────────────────────────────────────
function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const g = (n, fb) => (cs.getPropertyValue(n) || '').trim() || fb;
  return {
    surface: g('--surface', '#fbfcfc'),
    ink: g('--ink', '#101a1a'),
    ink2: g('--ink-2', '#43514f'),
    muted: g('--muted', '#66736f'),
    grid: g('--grid', '#e3e9e7'),
    axis: g('--axis', '#c4cecb'),
    band: g('--band', '#eef3f2'),
    band2: g('--band-2', '#e3eae8'),
    data1: g('--data-1', '#00908a'),
    data2: g('--data-2', '#5b5fc7'),
    ok: g('--ok', '#177533'),
    warn: g('--warn', '#a35f00'),
    error: g('--error', '#c0322f'),
    okSoft: g('--ok-soft', '#e3f3e7'),
    warnSoft: g('--warn-soft', '#fbf0d9'),
    errorSoft: g('--error-soft', '#fae6e4'),
    sans: g('--font-sans', 'system-ui, sans-serif'),
    mono: g('--font-mono', 'ui-monospace, monospace'),
  };
}

// ── 등록·다시 그리기·상호작용 ───────────────────────────────────
const charts = new Map();
let ro = null;

function ensureGlobal() {
  if (ro) return;
  ro = new ResizeObserver(() => scheduleAll());
  try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => scheduleAll()); } catch { /* 구형 */ }
  new MutationObserver(() => scheduleAll()).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => scheduleAll());
}

let pending = false;
function scheduleAll() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => { pending = false; repaintAll(); });
}

export function repaintAll() {
  for (const [canvas, st] of charts) {
    if (!canvas.isConnected) { charts.delete(canvas); continue; }
    paint(canvas, st);
  }
}

function mount(canvas, height, draw, label) {
  ensureGlobal();
  let st = charts.get(canvas);
  if (!st) {
    st = {};
    charts.set(canvas, st);
    bind(canvas, st);
    ro.observe(canvas.parentElement || canvas);
  }
  st.height = height;
  st.draw = draw;
  st.hover = null;
  st.focusIdx = -1;
  canvas.tabIndex = 0;
  canvas.setAttribute('role', 'img');
  if (label) canvas.setAttribute('aria-label', label);
  paint(canvas, st);
}

function paint(canvas, st) {
  const w = Math.floor(canvas.clientWidth || (canvas.parentElement && canvas.parentElement.clientWidth) || 0);
  if (w < 40) return;
  const h = st.height;
  const dpr = Math.min(window.devicePixelRatio || 1, 3);
  canvas.style.height = h + 'px';
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const T = tokens();
  st.model = st.draw(ctx, w, h, T, st.hover) || null;
  updateTip(canvas, st);
}

function bind(canvas, st) {
  const pos = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  canvas.addEventListener('pointermove', (e) => {
    if (!st.model || !st.model.hit) return;
    const [x, y] = pos(e);
    st.hover = st.model.hit(x, y);
    paint(canvas, st);
  });
  canvas.addEventListener('pointerleave', () => { st.hover = null; paint(canvas, st); });
  canvas.addEventListener('keydown', (e) => {
    const list = st.model && st.model.focus;
    if (!list || !list.length) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') st.focusIdx = (st.focusIdx + 1) % list.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') st.focusIdx = (st.focusIdx - 1 + list.length) % list.length;
    else if (e.key === 'Escape') { st.focusIdx = -1; st.hover = null; paint(canvas, st); return; }
    else return;
    e.preventDefault();
    st.hover = list[st.focusIdx];
    paint(canvas, st);
  });
  canvas.addEventListener('blur', () => { st.focusIdx = -1; st.hover = null; paint(canvas, st); });
}

function updateTip(canvas, st) {
  const host = canvas.parentElement;
  if (!host) return;
  let tip = host.querySelector(':scope > .chart-tip');
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'chart-tip';
    tip.setAttribute('aria-live', 'polite');
    host.appendChild(tip);
  }
  const info = st.hover && st.model && st.model.tip ? st.model.tip(st.hover) : null;
  if (!info) { tip.hidden = true; return; }
  tip.replaceChildren();
  const title = document.createElement('div');
  title.className = 'chart-tip-title';
  title.textContent = info.title;
  tip.appendChild(title);
  for (const r of info.rows) {
    const row = document.createElement('div');
    row.className = 'chart-tip-row';
    const v = document.createElement('strong');
    v.textContent = r.value;
    const l = document.createElement('span');
    l.textContent = r.label;
    row.append(v, l);
    tip.appendChild(row);
  }
  tip.hidden = false;
  const cw = canvas.clientWidth;
  const tw = tip.offsetWidth || 180;
  let left = info.x + 14;
  if (left + tw > cw) left = Math.max(0, info.x - tw - 14);
  tip.style.left = left + 'px';
  tip.style.top = Math.max(0, info.y - 10) + 'px';
}

// ── 공용 그리기 도구 ─────────────────────────────────────────
function niceTicks(min, max, count = 4) {
  if (!(max > min)) { max = min + 1; }
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const e = raw / mag;
  const step = (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-6; v += step) ticks.push(+v.toFixed(10));
  return { ticks, step };
}

function fmt(v, step) {
  const d = step >= 1 ? 0 : Math.min(3, Math.ceil(-Math.log10(step)));
  return v.toFixed(d);
}

function font(T, size, weight = 400, mono = false) {
  return `${weight} ${size}px ${mono ? T.mono : T.sans}`;
}

function hline(ctx, x0, x1, y, color) {
  ctx.strokeStyle = color; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x0, Math.round(y) + 0.5); ctx.lineTo(x1, Math.round(y) + 0.5); ctx.stroke();
}
function vline(ctx, x, y0, y1, color) {
  ctx.strokeStyle = color; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, y0); ctx.lineTo(Math.round(x) + 0.5, y1); ctx.stroke();
}

function withAlpha(color, a) {
  // #rrggbb 또는 rgb() → rgba
  const c = color.trim();
  if (c.startsWith('#')) {
    let h = c.slice(1);
    if (h.length === 3) h = h.split('').map((x) => x + x).join('');
    const n = parseInt(h.slice(0, 6), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  const m = c.match(/rgba?\(([^)]+)\)/);
  if (m) { const p = m[1].split(/[ ,/]+/).filter(Boolean).slice(0, 3); return `rgba(${p.join(',')},${a})`; }
  return c;
}

function iconCheck(ctx, cx, cy, s, color) {
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.beginPath(); ctx.moveTo(cx - s * 0.5, cy); ctx.lineTo(cx - s * 0.12, cy + s * 0.4); ctx.lineTo(cx + s * 0.55, cy - s * 0.42); ctx.stroke();
}
function iconCross(ctx, cx, cy, s, color) {
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(cx - s / 2, cy - s / 2); ctx.lineTo(cx + s / 2, cy + s / 2);
  ctx.moveTo(cx + s / 2, cy - s / 2); ctx.lineTo(cx - s / 2, cy + s / 2); ctx.stroke();
}
function iconTriangle(ctx, cx, cy, s, color) {
  ctx.fillStyle = color;
  ctx.beginPath(); ctx.moveTo(cx, cy - s * 0.55); ctx.lineTo(cx + s * 0.6, cy + s * 0.45); ctx.lineTo(cx - s * 0.6, cy + s * 0.45); ctx.closePath(); ctx.fill();
}

function statusColors(T, status) {
  if (status === 'sub' || status === 'del') return { fill: T.errorSoft, mark: T.error };
  if (status === 'weak') return { fill: T.warnSoft, mark: T.warn };
  return null;
}

/** 강도 곡선의 아래 한계: 가장 큰 값보다 이만큼(dB) 넘게 작은 값은 무음으로 보고 끊는다 */
export const INTENSITY_RANGE_DB = 50;

/**
 * 강도(dB) 배열 정리 → 같은 길이 배열. Praat 바닥값(−300 dB 등, ≤ −200)과
 * 최댓값보다 50 dB 넘게 작은 값은 null(선이 끊김)로 바꾼다. {db, max, min} 반환.
 */
export function cleanIntensity(db) {
  const arr = Array.isArray(db) ? db : [];
  const ok = (v) => typeof v === 'number' && Number.isFinite(v) && v > -200;
  let max = -Infinity;
  for (const v of arr) if (ok(v) && v > max) max = v;
  if (!Number.isFinite(max)) return { db: arr.map(() => null), max: null, min: null };
  const lo = max - INTENSITY_RANGE_DB;
  const out = arr.map((v) => (ok(v) && v >= lo ? v : null));
  return { db: out, max, min: lo };
}

/** 말한 구간만 확대: 첫 음소 시작 −0.2초 ~ 마지막 음소 끝 +0.25초 */
export function timeWindow(result) {
  const dur = (result && result.acoustic && result.acoustic.duration) || 0;
  const ph = ((result && result.phones) || []).filter((p) => p.start != null && p.end != null);
  if (!ph.length) return [0, Math.max(dur, 0.5)];
  const s = Math.min(...ph.map((p) => p.start));
  const e = Math.max(...ph.map((p) => p.end));
  const t0 = Math.max(0, s - 0.2);
  const t1 = Math.min(dur > 0 ? dur : e + 0.25, e + 0.25);
  return [t0, Math.max(t1, t0 + 0.3)];
}

/** 음소 띠 + 음절 줄 + 시간 눈금 (x축 아래) */
function drawTimeFooter(ctx, T, d, x, plotL, plotR, yBand, bandH, sylH, hoverPhone) {
  const phones = (d.phones || []).filter((p) => p.start != null && p.end != null && p.end > d.win[0] && p.start < d.win[1]);
  // 음소 띠
  for (const p of phones) {
    const x0 = Math.max(plotL, x(p.start)), x1 = Math.min(plotR, x(p.end));
    const w = x1 - x0 - 2;              // 2px 표면 간격
    if (w <= 0) continue;
    const sc = statusColors(T, p.status);
    ctx.fillStyle = sc ? sc.fill : (p.syl % 2 ? T.band2 : T.band);
    ctx.fillRect(x0 + 1, yBand, w, bandH);
    if (sc) { ctx.fillStyle = sc.mark; ctx.fillRect(x0 + 1, yBand + bandH - 3, w, 3); }
    if (hoverPhone === p.idx) { ctx.strokeStyle = T.ink; ctx.lineWidth = 1.5; ctx.strokeRect(x0 + 1.5, yBand + 0.5, w - 1, bandH - 1); }
    // 글자
    let label = p.jamo || '';
    if (p.status === 'sub' && p.heard_jamo) label = `${p.jamo}→${p.heard_jamo}`;
    ctx.font = font(T, 14, 600);
    let tw = ctx.measureText(label).width;
    if (tw > w - 4 && p.status === 'sub') { label = p.jamo; tw = ctx.measureText(label).width; }
    if (tw <= w - 2) {
      ctx.fillStyle = p.status === 'del' ? T.muted : T.ink;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      const cx = x0 + 1 + w / 2, cy = yBand + bandH / 2 - 1;
      ctx.fillText(label, cx, cy);
      if (p.status === 'del') { hline(ctx, cx - tw / 2 - 1, cx + tw / 2 + 1, cy, T.muted); }
    }
    // 상태 표시(색만으로 구분하지 않도록 모양 추가)
    if (sc && w > 12) {
      const mx = x0 + w - 4, my = yBand + 6;
      if (p.status === 'weak') iconTriangle(ctx, mx, my, 6, sc.mark);
      else iconCross(ctx, mx, my, 5, sc.mark);
    }
  }
  // 음절 줄
  const sylls = d.syllables || [];
  const ySyl = yBand + bandH;
  ctx.font = font(T, 13, 500);
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  sylls.forEach((s, si) => {
    const ps = phones.filter((p) => p.syl === si);
    if (!ps.length) return;
    const a = Math.max(plotL, x(Math.min(...ps.map((p) => p.start))));
    const b = Math.min(plotR, x(Math.max(...ps.map((p) => p.end))));
    if (b - a < 6) return;
    hline(ctx, a + 2, b - 2, ySyl + 3, T.axis);
    ctx.fillStyle = T.ink2;
    ctx.fillText(s.text || '', (a + b) / 2, ySyl + sylH / 2 + 3);
  });
  // 시간 눈금
  const yAx = ySyl + sylH;
  const { ticks, step } = niceTicks(d.win[0], d.win[1], Math.max(2, Math.floor((plotR - plotL) / 90)));
  ctx.font = font(T, 11, 400, true);
  ctx.fillStyle = T.muted;
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  for (const t of ticks) {
    const xx = x(t);
    if (xx < plotL - 1 || xx > plotR + 1) continue;
    vline(ctx, xx, yAx, yAx + 4, T.axis);
    ctx.fillText(fmt(t, step) + 's', xx, yAx + 6);
  }
}

function phoneAt(d, t) {
  return (d.phones || []).find((p) => p.start != null && t >= p.start && t < p.end) || null;
}

function nearestIdx(arr, v) {
  let lo = 0, hi = arr.length - 1;
  if (hi < 0) return -1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < v) lo = mid + 1; else hi = mid; }
  if (lo > 0 && Math.abs(arr[lo - 1] - v) < Math.abs(arr[lo] - v)) lo--;
  return lo;
}

function phoneLabel(p) {
  if (!p) return '—';
  const st = STATUS_TEXT[p.status] || '';
  if (p.status === 'sub' && p.heard_jamo) return `${p.jamo} → ${p.heard_jamo} (${st})`;
  return `${p.jamo} (${st})`;
}

// ── (a) 음높이 + 크기 ─────────────────────────────────────────
export function renderProsody(canvas, d) {
  // d: {acoustic, phones, syllables, win:[t0,t1]}
  const L = { l: 50, r: 14, top: 24, f0H: 118, gap: 30, inH: 76, bandGap: 12, bandH: 30, sylH: 22, axisH: 22 };
  const H = L.top + L.f0H + L.gap + L.inH + L.bandGap + L.bandH + L.sylH + L.axisH;
  mount(canvas, H, (ctx, W, _h, T, hover) => {
    const ac = d.acoustic || {};
    const [t0, t1] = d.win;
    const pl = L.l, pr = W - L.r;
    const x = (t) => pl + ((t - t0) / (t1 - t0)) * (pr - pl);
    const tx = (px) => t0 + ((px - pl) / (pr - pl)) * (t1 - t0);
    const yF0 = L.top, yIn = yF0 + L.f0H + L.gap, yBand = yIn + L.inH + L.bandGap;

    const ft = (ac.f0 && ac.f0.t) || [], fh = (ac.f0 && ac.f0.hz) || [];
    const it = (ac.intensity && ac.intensity.t) || [];
    const ci = cleanIntensity(ac.intensity && ac.intensity.db);   // −300 같은 바닥값은 끊김(null)
    const idb = ci.db;
    const inWin = (t) => t >= t0 && t <= t1;

    // 음절 경계(옅은 세로선) — 음높이·크기를 음절과 맞춰 보기
    const sylEdges = new Set();
    (d.phones || []).forEach((p, i, arr) => { if (i > 0 && p.syl !== arr[i - 1].syl && p.start != null) sylEdges.add(p.start); });
    for (const t of sylEdges) if (inWin(t)) vline(ctx, x(t), yF0, yIn + L.inH, T.grid);

    // F0 패널
    const voiced = fh.map((v, i) => [ft[i], v]).filter(([t, v]) => v != null && inWin(t));
    panelTitle(ctx, T, '음높이', 'Hz', pl, yF0 - 9);
    let yf = null;
    if (voiced.length) {
      let lo = Math.min(...voiced.map((v) => v[1])), hi = Math.max(...voiced.map((v) => v[1]));
      const pad = Math.max(10, (hi - lo) * 0.2);
      lo -= pad; hi += pad;
      const { ticks, step } = niceTicks(lo, hi, 3);
      lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
      yf = (v) => yF0 + L.f0H - ((v - lo) / (hi - lo)) * L.f0H;
      ctx.font = font(T, 11, 400, true); ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      for (const tk of ticks) { hline(ctx, pl, pr, yf(tk), T.grid); ctx.fillStyle = T.muted; ctx.fillText(fmt(tk, step), pl - 6, yf(tk)); }
      ctx.fillStyle = T.data1;
      for (const [t, v] of voiced) { ctx.beginPath(); ctx.arc(x(t), yf(v), 2.4, 0, Math.PI * 2); ctx.fill(); }
    } else {
      hline(ctx, pl, pr, yF0 + L.f0H, T.axis);
      ctx.font = font(T, 13); ctx.fillStyle = T.muted; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('목소리 높이를 잡지 못했어요(무성음·속삭임)', (pl + pr) / 2, yF0 + L.f0H / 2);
    }

    // 크기 패널
    panelTitle(ctx, T, '크기', 'dB', pl, yIn - 9);
    const ipts = idb.map((v, i) => [it[i], v]).filter(([t, v]) => v != null && inWin(t));
    let yi = null;
    if (ipts.length) {
      const floor = ci.min;                                           // 하한 = 최댓값 − 50 dB
      let lo = Math.max(floor, Math.min(...ipts.map((v) => v[1])) - 2), hi = Math.max(...ipts.map((v) => v[1])) + 2;
      const { ticks: tk0, step } = niceTicks(lo, hi, 2);
      const ticks = tk0.filter((v) => v >= floor - 1e-9);
      if (!ticks.length) ticks.push(Math.ceil(lo));
      lo = Math.max(floor, Math.min(lo, ticks[0])); hi = Math.max(hi, ticks[ticks.length - 1]);
      yi = (v) => yIn + L.inH - ((v - lo) / (hi - lo)) * L.inH;
      ctx.font = font(T, 11, 400, true); ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      for (const tk of ticks) { hline(ctx, pl, pr, yi(tk), T.grid); ctx.fillStyle = T.muted; ctx.fillText(fmt(tk, step), pl - 6, yi(tk)); }
      // 면(10%) + 선(2px)
      const segs = [];
      let cur = [];
      idb.forEach((v, i) => { const t = it[i]; if (!inWin(t)) return; if (v == null) { if (cur.length) segs.push(cur); cur = []; } else cur.push([x(t), yi(v)]); });
      if (cur.length) segs.push(cur);
      for (const s of segs) {
        ctx.beginPath(); s.forEach(([a, b], k) => (k ? ctx.lineTo(a, b) : ctx.moveTo(a, b)));
        ctx.lineTo(s[s.length - 1][0], yIn + L.inH); ctx.lineTo(s[0][0], yIn + L.inH); ctx.closePath();
        ctx.fillStyle = withAlpha(T.data2, 0.1); ctx.fill();
        ctx.beginPath(); s.forEach(([a, b], k) => (k ? ctx.lineTo(a, b) : ctx.moveTo(a, b)));
        ctx.strokeStyle = T.data2; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke();
      }
    }
    hline(ctx, pl, pr, yIn + L.inH, T.axis);

    const hp = hover ? phoneAt(d, hover.t) : null;
    drawTimeFooter(ctx, T, d, x, pl, pr, yBand, L.bandH, L.sylH, hp ? hp.idx : null);

    // 십자선
    if (hover) {
      const hx = x(hover.t);
      vline(ctx, hx, yF0 - 4, yBand + L.bandH, T.ink2);
      if (yf && hover.f0 != null) dot(ctx, hx, yf(hover.f0), 4.5, T.data1, T.surface);
      if (yi && hover.db != null) dot(ctx, hx, yi(hover.db), 4.5, T.data2, T.surface);
    }

    const sample = (t) => {
      const fi = nearestIdx(ft, t), ii = nearestIdx(it, t);
      return { t, f0: fi >= 0 ? fh[fi] : null, db: ii >= 0 ? idb[ii] : null };
    };
    return {
      hit: (px, py) => (px < pl || px > pr || py > yBand + L.bandH + L.sylH ? null : sample(tx(px))),
      focus: (d.phones || []).filter((p) => p.start != null && inWin((p.start + p.end) / 2)).map((p) => sample((p.start + p.end) / 2)),
      tip: (h) => ({
        title: `${h.t.toFixed(2)}초`,
        rows: [
          { label: '음높이', value: h.f0 != null ? `${Math.round(h.f0)} Hz` : '무성(높이 없음)' },
          { label: '크기', value: h.db != null ? `${Math.round(h.db)} dB` : '—' },
          { label: '소리', value: phoneLabel(phoneAt(d, h.t)) },
        ],
        x: x(h.t), y: yF0,
      }),
    };
  }, '음높이와 크기 변화 그래프. 방향키로 소리마다 값을 읽을 수 있어요.');
}

function panelTitle(ctx, T, title, unit, x, y) {
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.font = font(T, 12, 600); ctx.fillStyle = T.ink2;
  ctx.fillText(title, x, y);
  const w = ctx.measureText(title).width;
  ctx.font = font(T, 11, 400, true); ctx.fillStyle = T.muted;
  ctx.fillText(unit, x + w + 6, y);
}

function dot(ctx, x, y, r, fill, ring) {
  ctx.beginPath(); ctx.arc(x, y, r + 2, 0, Math.PI * 2); ctx.fillStyle = ring; ctx.fill();
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = fill; ctx.fill();
}

// ── (b) 모음 포먼트 ───────────────────────────────────────────
/**
 * 모음 측정 상태(서버 acoustic.vowels[] 기준)
 *  'short'   : 구간이 짧아 측정 안 함(unreliable: "short")
 *  'unmeasured': 값이 없거나 튀어서 숨김(f1/f2 null, unreliable: "measure" 등)
 *  'noref'   : 참고치가 없는 모음(ㅛ·ㅠ 등, ref null) — 비교 안 함
 *  'in' / 'out': 참고 범위 안 / 밖 (ok true / false)
 */
export function vowelState(v) {
  if (!v) return 'unmeasured';
  if (v.f1 == null || v.f2 == null) return v.unreliable === 'short' ? 'short' : 'unmeasured';
  if (!v.ref || v.ok == null) return 'noref';
  return v.ok ? 'in' : 'out';
}

/** 참고 범위 밖일 때 가까워지는 방향 → 짧은 힌트(참고용). 서버 accept 범위가 있으면 그 기준 */
export function vowelHint(v) {
  if (!v || !v.ref || v.f1 == null || v.f2 == null) return null;
  const a = v.accept || null;
  const f1lo = a && a.f1 ? a.f1[0] : v.ref.f1 * 0.88, f1hi = a && a.f1 ? a.f1[1] : v.ref.f1 * 1.12;
  const f2lo = a && a.f2 ? a.f2[0] : v.ref.f2 * 0.9;
  const f2hi = a && a.f2 ? a.f2[1] : v.ref.f2 * 1.1;           // null 이면 위쪽 제한 없음(치조·경구개 옆)
  const out = [];
  if (f2hi != null && v.f2 > f2hi) out.push(ROUNDED.has(v.phone) ? '입술을 더 동그랗게 모으고 혀를 뒤로' : '혀를 조금 더 뒤로');
  else if (f2lo != null && v.f2 < f2lo) out.push(ROUNDED.has(v.phone) ? '혀를 조금 더 앞으로' : '입꼬리를 옆으로 당기며 혀를 앞으로');
  if (f1hi != null && v.f1 > f1hi) out.push('입을 조금 덜 벌리기');
  else if (f1lo != null && v.f1 < f1lo) out.push('입을 조금 더 벌리기');
  return out.length ? out.join(' · ') : '참고 범위 가까이에 있어요';
}

export function vowelName(v, d) {
  const jamo = VOWEL_JAMO[v.phone] || v.phone;
  const p = (d.phones || [])[v.idx];
  const s = p && d.syllables && d.syllables[p.syl];
  return s ? `${jamo} (${s.text})` : jamo;
}

export function renderFormants(canvas, d) {
  // d: {acoustic, voice, phones, syllables}
  const H = 340;
  mount(canvas, H, (ctx, W, _h, T, hover) => {
    const refs = FORMANT_REF[d.voice] || FORMANT_REF.female;
    const vowels = (((d.acoustic || {}).vowels) || []).filter((v) => v.f1 != null && v.f2 != null);
    const f1s = [], f2s = [];
    for (const k in refs) { f1s.push(refs[k][0]); f2s.push(refs[k][1]); }
    for (const v of vowels) { f1s.push(v.f1); f2s.push(v.f2); if (v.ref) { f1s.push(v.ref.f1); f2s.push(v.ref.f2); } }
    let f2lo = Math.min(...f2s) * 0.86, f2hi = Math.max(...f2s) * 1.07;
    let f1lo = Math.min(...f1s) * 0.84, f1hi = Math.max(...f1s) * 1.1;
    const m = { l: 58, r: 18, t: 22, b: 52 };
    const pl = m.l, pr = W - m.r, pt = m.t, pb = H - m.b;
    const xt = niceTicks(f2lo, f2hi, Math.max(3, Math.floor((pr - pl) / 80)));
    const yt = niceTicks(f1lo, f1hi, 4);
    f2lo = Math.min(f2lo, xt.ticks[0]); f2hi = Math.max(f2hi, xt.ticks[xt.ticks.length - 1]);
    f1lo = Math.min(f1lo, yt.ticks[0]); f1hi = Math.max(f1hi, yt.ticks[yt.ticks.length - 1]);
    const x = (f2) => pl + ((f2hi - f2) / (f2hi - f2lo)) * (pr - pl);   // 오른쪽이 작다(반전)
    const y = (f1) => pt + ((f1 - f1lo) / (f1hi - f1lo)) * (pb - pt);   // 아래로 증가

    // 격자·눈금
    ctx.font = font(T, 11, 400, true);
    ctx.fillStyle = T.muted;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (const v of xt.ticks) { const xx = x(v); if (xx < pl - 1 || xx > pr + 1) continue; vline(ctx, xx, pt, pb, T.grid); ctx.fillText(String(Math.round(v)), xx, pb + 6); }
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (const v of yt.ticks) { const yy = y(v); if (yy < pt - 1 || yy > pb + 1) continue; hline(ctx, pl, pr, yy, T.grid); ctx.fillText(String(Math.round(v)), pl - 6, yy); }
    hline(ctx, pl, pr, pb, T.axis);
    vline(ctx, pl, pt, pb, T.axis);
    // 축 제목(쉬운 말 병기)
    ctx.font = font(T, 12, 500); ctx.fillStyle = T.ink2; ctx.textBaseline = 'alphabetic';
    ctx.textAlign = 'left'; ctx.fillText('← 혀 앞쪽', pl, H - 10);
    ctx.textAlign = 'right'; ctx.fillText('혀 뒤쪽 →', pr, H - 10);
    ctx.textAlign = 'center'; ctx.font = font(T, 11, 400, true); ctx.fillStyle = T.muted; ctx.fillText('F2 (Hz)', (pl + pr) / 2, H - 10);
    ctx.save();
    ctx.translate(14, (pt + pb) / 2); ctx.rotate(-Math.PI / 2);
    ctx.font = font(T, 12, 500); ctx.fillStyle = T.ink2; ctx.textAlign = 'left';
    ctx.fillText('← 입 크게', -(pb - pt) / 2, 0);          // 회전 좌표: 읽는 방향이 위쪽이라 ←가 아래를 가리킴
    ctx.textAlign = 'right'; ctx.fillText('입 작게 →', (pb - pt) / 2, 0);
    ctx.textAlign = 'center'; ctx.font = font(T, 11, 400, true); ctx.fillStyle = T.muted; ctx.fillText('F1 (Hz)', 0, 0);
    ctx.restore();

    // 참고 모음: 범위(±10%) + 글자
    const targetSet = new Set(vowels.map((v) => (v.ref ? `${v.ref.f1},${v.ref.f2}` : '')));
    for (const k in refs) {
      const [f1, f2] = refs[k];
      const cx = x(f2), cy = y(f1);
      const rx = Math.abs(x(f2 * 0.9) - x(f2 * 1.1)) / 2, ry = Math.abs(y(f1 * 1.1) - y(f1 * 0.9)) / 2;
      const isTarget = targetSet.has(`${f1},${f2}`);
      ctx.beginPath(); ctx.ellipse(cx, cy, Math.max(rx, 14), Math.max(ry, 14), 0, 0, Math.PI * 2);
      ctx.fillStyle = isTarget ? T.band2 : T.band; ctx.fill();
      ctx.font = font(T, isTarget ? 22 : 18, isTarget ? 700 : 500);
      ctx.fillStyle = isTarget ? T.ink : T.muted;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(VOWEL_JAMO[k], cx, cy);
    }

    // 내 모음: 점 + (참고 범위 밖일 때만) 참고치까지 화살표
    const pts = vowels.map((v) => ({ v, px: x(v.f2), py: y(v.f1) }));
    for (const p of pts) {
      if (!p.v.ref || p.v.ok !== false) continue;
      const tx2 = x(p.v.ref.f2), ty2 = y(p.v.ref.f1);
      const dx = tx2 - p.px, dy = ty2 - p.py, len = Math.hypot(dx, dy);
      if (len < 26) continue;
      const ux = dx / len, uy = dy / len;
      const sx = p.px + ux * 10, sy = p.py + uy * 10, ex = tx2 - ux * 16, ey = ty2 - uy * 16;
      ctx.strokeStyle = T.warn; ctx.lineWidth = 1.5; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.stroke();
      ctx.fillStyle = T.warn;
      ctx.beginPath(); ctx.moveTo(ex + ux * 2, ey + uy * 2);
      ctx.lineTo(ex - ux * 8 - uy * 5, ey - uy * 8 + ux * 5); ctx.lineTo(ex - ux * 8 + uy * 5, ey - uy * 8 - ux * 5); ctx.closePath(); ctx.fill();
    }
    for (const p of pts) {
      const hot = hover && hover.v === p.v;
      const out = p.v.ok === false;
      if (out) { ctx.beginPath(); ctx.arc(p.px, p.py, hot ? 11 : 10, 0, Math.PI * 2); ctx.strokeStyle = T.warn; ctx.lineWidth = 2; ctx.stroke(); }
      dot(ctx, p.px, p.py, hot ? 7 : 5.5, T.data1, T.surface);
      const label = vowelName(p.v, d) + (out ? ' · 범위 밖' : '');
      ctx.font = font(T, 13, 600);
      const tw = ctx.measureText(label).width;
      const right = p.px + 14 + tw < pr;
      ctx.fillStyle = T.ink; ctx.textBaseline = 'middle';
      ctx.textAlign = right ? 'left' : 'right';
      ctx.fillText(label, right ? p.px + 14 : p.px - 14, p.py - 1);
    }
    if (!pts.length) {
      ctx.font = font(T, 13); ctx.fillStyle = T.muted; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('측정된 모음이 없어요', (pl + pr) / 2, pt + 18);
    }

    const toHover = (p) => ({ v: p.v, px: p.px, py: p.py });
    return {
      hit: (hx, hy) => {
        let best = null, bd = 26;
        for (const p of pts) { const dd = Math.hypot(p.px - hx, p.py - hy); if (dd < bd) { bd = dd; best = p; } }
        return best ? toHover(best) : null;
      },
      focus: pts.map(toHover),
      tip: (h) => {
        const st = vowelState(h.v);
        return {
          title: vowelName(h.v, d),
          rows: [
            { label: '내 소리 F1 · F2', value: `${Math.round(h.v.f1)} · ${Math.round(h.v.f2)} Hz` },
            ...(h.v.ref ? [{ label: '참고 F1 · F2', value: `${Math.round(h.v.ref.f1)} · ${Math.round(h.v.ref.f2)} Hz` }] : []),
            st === 'noref' ? { label: '참고치가 없는 모음', value: '비교 안 함' }
              : st === 'in' ? { label: '참고 범위 안', value: '좋아요' }
                : { label: '참고 범위 밖(참고용)', value: vowelHint(h.v) || '—' },
          ],
          x: h.px, y: h.py,
        };
      },
    };
  }, '모음 위치 그래프. 글자는 참고 모음(평균값), 점은 내 모음이에요. 참고 범위 밖인 모음만 화살표로 가까워지는 방향을 보여 줘요.');
}

// ── (c) 입술 시계열 ───────────────────────────────────────────
export function renderLips(canvas, d) {
  // d: {lips, phones, syllables, win, neutral}
  const L = { l: 74, r: 14, markH: 26, top: 6, laneH: 54, laneGap: 10, bandGap: 12, bandH: 30, sylH: 22, axisH: 22 };
  const lanes = [
    { key: 'open', label: '입 벌림' },
    { key: 'width', label: '입 너비' },
    { key: 'round', label: '동그랗게' },
  ];
  const yLane0 = L.top + L.markH + 6;
  const lanesBottom = yLane0 + lanes.length * L.laneH + (lanes.length - 1) * L.laneGap;
  const H = lanesBottom + L.bandGap + L.bandH + L.sylH + L.axisH;
  mount(canvas, H, (ctx, W, _h, T, hover) => {
    const s = (d.lips && d.lips.series) || {};
    const ts = s.t || [];
    const [t0, t1] = d.win;
    const pl = L.l, pr = W - L.r;
    const x = (t) => pl + ((t - t0) / (t1 - t0)) * (pr - pl);
    const tx = (px) => t0 + ((px - pl) / (pr - pl)) * (t1 - t0);
    const inWin = (t) => t >= t0 && t <= t1;
    const checks = (d.lips && d.lips.checks) || [];
    const phones = d.phones || [];

    // 판정 구간 음영 + 위쪽 표시
    for (const c of checks) {
      const p = phones[c.idx];
      if (!p || p.start == null) continue;
      const a = Math.max(pl, x(p.start)), b = Math.min(pr, x(p.end));
      if (b - a < 2) continue;
      ctx.fillStyle = c.ok ? T.okSoft : T.warnSoft;
      ctx.fillRect(a + 1, yLane0 - 4, b - a - 2, lanesBottom - yLane0 + 8);
      const cy = L.top + L.markH / 2;
      const col = c.ok ? T.ok : T.warn;
      // 들어가는 만큼만: '자모 + 목표' → '자모' → 아이콘만
      ctx.font = font(T, 12, 600);
      let label = `${p.jamo} ${EXPECT_TEXT[c.expect] || ''}`.trim();
      if (ctx.measureText(label).width + 22 > b - a) label = p.jamo || '';
      if (ctx.measureText(label).width + 22 > b - a) label = '';
      const tw = label ? ctx.measureText(label).width : 0;
      const mid = (a + b) / 2;
      const ix = label ? mid - tw / 2 - 9 : mid;
      if (c.ok) iconCheck(ctx, ix, cy, 10, col); else iconCross(ctx, ix, cy, 9, col);
      if (label) { ctx.fillStyle = T.ink; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(label, ix + 10, cy); }
    }

    // 레인
    const scales = {};
    lanes.forEach((ln, li) => {
      const top = yLane0 + li * (L.laneH + L.laneGap), bot = top + L.laneH;
      const vals = (s[ln.key] || []).map((v, i) => [ts[i], v]).filter(([t, v]) => v != null && inWin(t));
      let lo, hi;
      if (ln.key === 'round') { lo = 0; hi = 1; }
      else if (ln.key === 'open') { lo = 0; hi = Math.max(0.12, ...vals.map((v) => v[1])) * 1.12; }
      else {
        const vs = vals.map((v) => v[1]).concat(d.neutral && d.neutral.width ? [d.neutral.width] : []);
        lo = Math.min(...vs, 1e9); hi = Math.max(...vs, -1e9);
        if (!isFinite(lo)) { lo = 0.3; hi = 0.7; }
        const pad = Math.max(0.02, (hi - lo) * 0.2); lo -= pad; hi += pad;
      }
      const y = (v) => bot - ((v - lo) / (hi - lo)) * L.laneH;
      scales[ln.key] = y;
      hline(ctx, pl, pr, bot, T.axis);
      hline(ctx, pl, pr, top, T.grid);
      ctx.font = font(T, 12, 600); ctx.fillStyle = T.ink2; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      ctx.fillText(ln.label, pl - 10, top + L.laneH / 2 - 7);
      ctx.font = font(T, 10, 400, true); ctx.fillStyle = T.muted;
      ctx.fillText(ln.key === 'round' ? '0–1' : `${lo.toFixed(2)}–${hi.toFixed(2)}`, pl - 10, top + L.laneH / 2 + 9);
      // 평소(준비 구간) 기준선
      const nv = d.neutral && d.neutral[ln.key];
      if (nv != null && nv >= lo && nv <= hi) {
        hline(ctx, pl, pr, y(nv), T.axis);
        ctx.font = font(T, 10, 500); ctx.fillStyle = T.muted; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom';
        ctx.fillText('평소', pr - 2, y(nv) - 2);
      }
      if (vals.length > 1) {
        ctx.beginPath(); vals.forEach(([t, v], k) => (k ? ctx.lineTo(x(t), y(v)) : ctx.moveTo(x(t), y(v))));
        ctx.lineTo(x(vals[vals.length - 1][0]), bot); ctx.lineTo(x(vals[0][0]), bot); ctx.closePath();
        ctx.fillStyle = withAlpha(T.data1, 0.1); ctx.fill();
        ctx.beginPath(); vals.forEach(([t, v], k) => (k ? ctx.lineTo(x(t), y(v)) : ctx.moveTo(x(t), y(v))));
        ctx.strokeStyle = T.data1; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke();
      }
    });

    const hp = hover ? phoneAt(d, hover.t) : null;
    drawTimeFooter(ctx, T, d, x, pl, pr, lanesBottom + L.bandGap, L.bandH, L.sylH, hp ? hp.idx : null);

    const sample = (t) => {
      const i = nearestIdx(ts, t);
      if (i < 0) return { t };
      return { t: ts[i], open: (s.open || [])[i], width: (s.width || [])[i], round: (s.round || [])[i] };
    };
    if (hover) {
      const hx = x(hover.t);
      vline(ctx, hx, yLane0 - 4, lanesBottom + L.bandGap + L.bandH, T.ink2);
      for (const ln of lanes) if (hover[ln.key] != null && scales[ln.key]) dot(ctx, hx, scales[ln.key](hover[ln.key]), 4.5, T.data1, T.surface);
    }
    return {
      hit: (px, py) => (px < pl || px > pr || py > lanesBottom + L.bandGap + L.bandH + L.sylH ? null : sample(tx(px))),
      focus: phones.filter((p) => p.start != null && inWin((p.start + p.end) / 2)).map((p) => sample((p.start + p.end) / 2)),
      tip: (h) => {
        const p = phoneAt(d, h.t);
        const c = p ? checks.find((k) => k.idx === p.idx) : null;
        const n = d.neutral;
        const rows = [
          { label: '입 벌림', value: h.open != null ? h.open.toFixed(3) : '—' },
          { label: '입 너비', value: h.width != null ? h.width.toFixed(3) + (n && n.width ? ` (평소의 ${Math.round((h.width / n.width) * 100)}%)` : '') : '—' },
          { label: '동그랗게', value: h.round != null ? h.round.toFixed(2) : '—' },
          { label: '소리', value: phoneLabel(p) },
        ];
        if (c) rows.push({ label: '입모양 판정', value: `${c.ok ? '맞음' : '아쉬움'} — ${c.msg || ''}` });
        return { title: `${h.t.toFixed(2)}초`, rows, x: x(h.t), y: yLane0 };
      },
    };
  }, '입술 움직임 그래프: 입 벌림, 입 너비, 동그랗게 정도와 소리별 입모양 판정. 방향키로 소리마다 값을 읽을 수 있어요.');
}

// ── 시도 기록 스파크라인(SVG) ─────────────────────────────────
export function sparklineSVG(values, { width = 160, height = 40 } = {}) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);
  svg.setAttribute('class', 'spark');
  svg.setAttribute('aria-hidden', 'true');
  if (!values.length) return svg;
  const pad = 5;
  const x = (i) => (values.length === 1 ? width / 2 : pad + (i / (values.length - 1)) * (width - pad * 2));
  const y = (v) => pad + (1 - v / 100) * (height - pad * 2);
  const base = document.createElementNS(NS, 'line');
  base.setAttribute('x1', 0); base.setAttribute('x2', width); base.setAttribute('y1', y(0)); base.setAttribute('y2', y(0));
  base.setAttribute('class', 'spark-base');
  svg.appendChild(base);
  if (values.length > 1) {
    const pl = document.createElementNS(NS, 'polyline');
    pl.setAttribute('points', values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' '));
    pl.setAttribute('class', 'spark-line');
    svg.appendChild(pl);
  }
  const c = document.createElementNS(NS, 'circle');
  c.setAttribute('cx', x(values.length - 1)); c.setAttribute('cy', y(values[values.length - 1])); c.setAttribute('r', 4);
  c.setAttribute('class', 'spark-dot');
  svg.appendChild(c);
  return svg;
}
