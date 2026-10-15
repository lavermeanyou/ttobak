// lips.js — MediaPipe FaceLandmarker 로 입술 특징 추출 + 미리보기 오버레이
//
// 프레임 특징(계약 6절):
//   얼굴 크기 = 랜드마크 33 ↔ 263 (양 눈 바깥꼬리) 거리
//   open  = |13 − 14| / 크기   (윗입술·아랫입술 안쪽 가운데)
//   width = |61 − 291| / 크기  (입꼬리 양끝)
//   pucker / funnel / jaw / close = 블렌드셰이프 mouthPucker / mouthFunnel / jawOpen / mouthClose
// 거리는 화면 픽셀 기준(정규화 좌표 × 영상 가로/세로)으로 잰다 — 가로세로 비율이 달라도 비가 맞도록.
//
// 시간: 각 프레임의 perf = requestVideoFrameCallback metadata.captureTime(없으면 콜백 now),
// 둘 다 performance.now() 축. 녹음 기준 t 는 recorder.js 주석 참고(오디오도 입력 기준으로 옮김).

const LOCAL_BUNDLE = new URL('./vendor/tasks-vision/vision_bundle.mjs', import.meta.url).href;
const LOCAL_WASM = new URL('./vendor/tasks-vision', import.meta.url).href; // 끝 슬래시 없이(라이브러리가 '/' 붙임)
const LOCAL_MODEL = new URL('./vendor/face_landmarker.task', import.meta.url).href;
const CDN_BASE = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14';
const CDN_MODEL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';

// 입술 윤곽 랜드마크(시계 방향, 닫힌 고리)
export const LIPS_OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146];
export const LIPS_INNER = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95];
const CORNERS = [61, 291];

export const PREP_SEC = 0.6;   // 녹음 직후 '입 다물고 기다리기' 구간

/** 라이브러리 로드 — 로컬 vendor 우선, 실패하면 CDN */
async function loadVision() {
  try {
    const mod = await import(LOCAL_BUNDLE);
    return { mod, wasm: LOCAL_WASM, model: LOCAL_MODEL };
  } catch (e) {
    console.warn('[lips] 로컬 vendor 로드 실패, CDN 시도', e);
    const mod = await import(`${CDN_BASE}/vision_bundle.mjs`);
    return { mod, wasm: `${CDN_BASE}/wasm`, model: CDN_MODEL };
  }
}

function dist(a, b, w, h) {
  const dx = (a.x - b.x) * w, dy = (a.y - b.y) * h;
  return Math.hypot(dx, dy);
}

function median(arr) {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** 녹음 프레임에서 neutral(open/width 중앙값)을 잡는다: 준비 구간 [0.1, PREP_SEC] 초 */
export function computeNeutral(frames, upTo = PREP_SEC) {
  const sel = frames.filter((f) => f.t >= 0.1 && f.t <= upTo);
  if (sel.length < 5) return null;
  return { open: round4(median(sel.map((f) => f.open))), width: round4(median(sel.map((f) => f.width))) };
}

const round4 = (v) => Math.round(v * 10000) / 10000;

/** 계약 6절 lips JSON 만들기. 프레임이 너무 적으면 null(서버가 입술 판정 생략) */
export function buildLipsPayload(frames) {
  if (!frames || frames.length < 8) return null;
  const span = frames[frames.length - 1].t - frames[0].t;
  const fps = span > 0 ? Math.round(((frames.length - 1) / span) * 10) / 10 : 30;
  const out = {
    fps,
    frames: frames.map((f) => ({
      t: round4(f.t), open: round4(f.open), width: round4(f.width),
      pucker: round4(f.pucker), funnel: round4(f.funnel), jaw: round4(f.jaw), close: round4(f.close),
    })),
  };
  const neutral = computeNeutral(frames);
  if (neutral) out.neutral = neutral;
  return out;
}

/**
 * 실시간 입모양 추정(화면 표시용, 대략값). 서버 판정과는 별개.
 * @returns {'open'|'round'|'spread'|'closed'|'neutral'}
 */
export function classifyLive(f, neutral) {
  const n = neutral || { open: 0.02, width: 0.5 };
  if (f.open > n.open + 0.11 || f.jaw > 0.45) return 'open';
  if (f.width < n.width * 0.9 || f.pucker > 0.45 || f.funnel > 0.35) return 'round';
  if (f.open < 0.012 || f.close > 0.5) return 'closed';
  if (f.width > n.width * 1.05) return 'spread';
  return 'neutral';
}

export class LipTracker {
  /**
   * @param {HTMLVideoElement} video
   * @param {HTMLCanvasElement} overlay  영상 위 오버레이(같은 크기·같은 좌우반전)
   * @param {{onFrame?: (f:object|null)=>void, colors?: ()=>object}} opts
   */
  constructor(video, overlay, { onFrame, colors } = {}) {
    this.video = video;
    this.overlay = overlay;
    this.onFrame = onFrame || (() => {});
    this.colors = colors || (() => ({ line: '#ffffff', halo: 'rgba(0,0,0,.55)', dot: '#ffffff' }));
    this.landmarker = null;
    this.running = false;
    this.capturing = false;
    this.frames = [];
    this.recent = [];          // 녹음 시작 직전 프레임 보관(시작 메시지 지연 보정)
    this.t0Perf = 0;
    this.lastTs = -1;
    this._cb = null;
    this.ready = false;
  }

  async init() {
    const { mod, wasm, model } = await loadVision();
    const { FaceLandmarker, FilesetResolver } = mod;
    const fileset = await FilesetResolver.forVisionTasks(wasm);
    const opts = (delegate) => ({
      baseOptions: { modelAssetPath: model, delegate },
      runningMode: 'VIDEO',
      numFaces: 1,
      outputFaceBlendshapes: true,
      outputFacialTransformationMatrixes: false,
    });
    try {
      this.landmarker = await FaceLandmarker.createFromOptions(fileset, opts('GPU'));
    } catch (e) {
      console.warn('[lips] GPU 위임 실패, CPU 로 재시도', e);
      this.landmarker = await FaceLandmarker.createFromOptions(fileset, opts('CPU'));
    }
    this.ready = true;
    return true;
  }

  start() {
    if (!this.ready || this.running) return;
    this.running = true;
    this._schedule();
  }

  stop() {
    this.running = false;
    const ctx = this.overlay.getContext('2d');
    ctx && ctx.clearRect(0, 0, this.overlay.width, this.overlay.height);
  }

  _schedule() {
    if (!this.running) return;
    const v = this.video;
    if ('requestVideoFrameCallback' in HTMLVideoElement.prototype) {
      v.requestVideoFrameCallback((now, meta) => this._tick(meta && meta.captureTime ? meta.captureTime : now));
    } else {
      // rAF 폴백: 약 30 fps 로 솎는다
      requestAnimationFrame((now) => {
        if (now - (this._lastRaf || 0) < 30) return this._schedule();
        this._lastRaf = now;
        this._tick(now);
      });
    }
  }

  _tick(perf) {
    if (!this.running) return;
    const v = this.video;
    if (v.readyState >= 2 && v.videoWidth > 0 && !document.hidden) {
      // detectForVideo 의 타임스탬프는 단조 증가해야 한다
      let ts = Math.round(perf);
      if (ts <= this.lastTs) ts = this.lastTs + 1;
      this.lastTs = ts;
      let res = null;
      try { res = this.landmarker.detectForVideo(v, ts); } catch (e) { console.warn('[lips] detect 실패', e); }
      const f = res ? this._features(res, v.videoWidth, v.videoHeight, perf) : null;
      this._draw(res, v.videoWidth, v.videoHeight);
      if (f) {
        this.recent.push(f);
        if (this.recent.length > 20) this.recent.shift();
        if (this.capturing) this.frames.push({ ...f, t: (f.perf - this.t0Perf) / 1000 });
      }
      this.onFrame(f);
    }
    this._schedule();
  }

  _features(res, w, h, perf) {
    const lm = res.faceLandmarks && res.faceLandmarks[0];
    if (!lm) return null;
    const size = dist(lm[33], lm[263], w, h);
    if (size < 1) return null;
    const bs = {};
    const cats = res.faceBlendshapes && res.faceBlendshapes[0] && res.faceBlendshapes[0].categories;
    if (cats) for (const c of cats) bs[c.categoryName] = c.score;
    return {
      perf,
      open: dist(lm[13], lm[14], w, h) / size,
      width: dist(lm[61], lm[291], w, h) / size,
      pucker: bs.mouthPucker ?? 0,
      funnel: bs.mouthFunnel ?? 0,
      jaw: bs.jawOpen ?? 0,
      close: bs.mouthClose ?? 0,
    };
  }

  _draw(res, w, h) {
    const c = this.overlay;
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    const lm = res && res.faceLandmarks && res.faceLandmarks[0];
    if (!lm) return;
    const col = this.colors();
    const path = (idx) => {
      ctx.beginPath();
      idx.forEach((i, k) => { const p = lm[i]; k ? ctx.lineTo(p.x * w, p.y * h) : ctx.moveTo(p.x * w, p.y * h); });
      ctx.closePath();
    };
    const lw = Math.max(2, w / 260);
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    for (const ring of [LIPS_OUTER, LIPS_INNER]) {
      path(ring);
      ctx.strokeStyle = col.halo; ctx.lineWidth = lw + 3; ctx.stroke();
      ctx.strokeStyle = col.line; ctx.lineWidth = ring === LIPS_OUTER ? lw : lw * 0.7; ctx.stroke();
    }
    for (const i of CORNERS) {
      const p = lm[i];
      ctx.beginPath(); ctx.arc(p.x * w, p.y * h, lw * 2.4, 0, Math.PI * 2);
      ctx.fillStyle = col.halo; ctx.fill();
      ctx.beginPath(); ctx.arc(p.x * w, p.y * h, lw * 1.6, 0, Math.PI * 2);
      ctx.fillStyle = col.dot; ctx.fill();
    }
  }

  /** 녹음 시작: t0Perf(performance.now 축, ms — 잠정값) 이후 프레임을 모은다.
   *  최종 t0 는 녹음이 끝난 뒤 다듬어지므로(recorder.js) 직전 0.3초 프레임도 함께 보관한다. */
  beginCapture(t0Perf) {
    this.t0Perf = t0Perf;
    this.frames = this.recent.filter((f) => f.perf >= t0Perf - 300).map((f) => ({ ...f, t: (f.perf - t0Perf) / 1000 }));
    this.capturing = true;
  }

  /** 녹음 정지: 모은 프레임(t 오름차순) 반환. t0Perf 를 주면 그 기준으로 t 를 다시 계산한다. */
  endCapture(maxT = Infinity, t0Perf = null) {
    this.capturing = false;
    const base = Number.isFinite(t0Perf) ? t0Perf : this.t0Perf;
    const out = this.frames
      .map((f) => ({ ...f, t: (f.perf - base) / 1000 }))
      .filter((f) => f.t >= 0 && f.t <= maxT);
    this.frames = [];
    return out;
  }

  /** 지금까지 모은 프레임(복사 없이 참조) */
  get captured() { return this.frames; }

  close() {
    this.stop();
    try { this.landmarker && this.landmarker.close(); } catch { /* 무시 */ }
    this.landmarker = null;
    this.ready = false;
  }
}
