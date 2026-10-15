// recorder.js — 마이크 → AudioWorklet(Float32 수집) → 16 kHz mono PCM16 WAV
//
// ── 시간 기준(중요) ─────────────────────────────────────────────
// 이 앱의 모든 시각은 performance.now() (ms) 하나로 통일한다. 오디오는 '입력' 기준으로만 옮긴다.
//  - 워클릿은 메시지마다 그 렌더 퀀텀의 끝 프레임 번호(qEnd = currentFrame + 128)를 붙여 보낸다.
//    메인 스레드는 도착 시각과 짝지어 offset = performance.now() − qEnd/sampleRate 를 구하고,
//    녹음 중 받은 메시지 가운데 가장 작은 값을 쓴다(메시지 전달 지연은 항상 0 이상이므로
//    가장 작은 값이 '그 샘플이 처리된 순간'에 가장 가깝다).
//  - 녹음 첫 샘플 시각 t0Perf = startFrame/sampleRate + offset − 입력 장치 지연(알 수 있으면).
//    getOutputTimestamp(출력 장치 기준)는 쓰지 않는다 — 출력 지연(블루투스면 약 250 ms)만큼
//    입술 시간축이 밀리기 때문이다.
//  - start() 는 첫 메시지로 만든 잠정값을 돌려주고, stop() 결과의 t0Perf 가 녹음 전체로 다듬은 최종값이다.
//  - 영상: lips.js 가 requestVideoFrameCallback 의 captureTime(없으면 콜백 now)을 쓴다 —
//    둘 다 performance.now() 축이다.
//  - 입술 프레임 t(초) = (프레임 시각 − t0Perf) / 1000  → 계약 6절 "녹음 시작 기준 초".
// 남는 오차는 입력 지연을 모르는 경우의 마이크 지연(보통 10–40 ms)으로 영상 한 프레임(33 ms) 수준이라
// 음소 구간(50–200 ms) 단위 입술 판정에는 영향이 작다.

export const TARGET_RATE = 16000;

// 워클릿은 Blob URL 인라인 모듈로 올린다(별도 파일·빌드 불필요).
const WORKLET_SRC = `
class TtobakCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.on = false;
    this.pendingStart = false;
    this.buf = new Float32Array(2048);
    this.n = 0;
    this.qEnd = 0;
    this.lvSum = 0; this.lvPeak = 0; this.lvN = 0;
    this.lvEvery = Math.round(sampleRate * 0.05);   // 50 ms마다 레벨 보고
    this.port.onmessage = (e) => {
      const m = e.data || {};
      if (m.cmd === 'start') { this.n = 0; this.on = true; this.pendingStart = true; }
      else if (m.cmd === 'stop') { this.flush(); this.on = false; this.port.postMessage({ type: 'stopped' }); }
    };
  }
  flush() {
    if (this.n > 0) { this.port.postMessage({ type: 'data', samples: this.buf.slice(0, this.n), qEnd: this.qEnd }); this.n = 0; }
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const len = input[0].length, chs = input.length;
    this.qEnd = currentFrame + len;               // 이 렌더 퀀텀의 끝 프레임(입력 샘플 번호)
    if (this.on && this.pendingStart) {
      this.pendingStart = false;
      // frame = 녹음에 들어가는 첫 샘플의 프레임 번호
      this.port.postMessage({ type: 'started', frame: currentFrame, qEnd: this.qEnd });
    }
    for (let i = 0; i < len; i++) {
      let v = 0;
      for (let c = 0; c < chs; c++) v += input[c][i];
      v /= chs;                                    // 스테레오 장치면 다운믹스
      if (this.on) { this.buf[this.n++] = v; if (this.n === this.buf.length) this.flush(); }
      const a = v < 0 ? -v : v;
      this.lvSum += v * v; if (a > this.lvPeak) this.lvPeak = a;
      if (++this.lvN >= this.lvEvery) {
        this.port.postMessage({ type: 'level', rms: Math.sqrt(this.lvSum / this.lvN), peak: this.lvPeak, qEnd: this.qEnd });
        this.lvSum = 0; this.lvPeak = 0; this.lvN = 0;
      }
    }
    return true;
  }
}
registerProcessor('ttobak-capture', TtobakCapture);
`;

/** 0~1 레벨(−60 dBFS → 0, 0 dBFS → 1) */
export function levelFromRms(rms) {
  const db = 20 * Math.log10(Math.max(rms, 1e-6));
  return Math.min(1, Math.max(0, (db + 60) / 60));
}

export class Recorder {
  /**
   * @param {{onLevel?: (level:number, peak:number)=>void}} opts
   */
  constructor({ onLevel } = {}) {
    this.onLevel = onLevel || (() => {});
    this.ctx = null;
    this.node = null;
    this.source = null;
    this.chunks = [];
    this.samples = 0;
    this.recording = false;
    this.t0Perf = null;
    this.startFrame = null;     // 녹음 첫 샘플의 프레임 번호(AudioContext 입력 기준)
    this.offMin = Infinity;     // min(performance.now() − qEnd/sampleRate) [ms]
    this.inputLatencyMs = 0;    // 입력 장치 지연(트랙 설정에 있으면)
    this._startWaiter = null;
    this._stopWaiter = null;
  }

  /** 스트림 연결. 사용자 제스처 안에서 불러야 AudioContext 가 바로 돈다. 실패하면 만든 AudioContext 를 닫는다. */
  async open(stream) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC || !('AudioWorkletNode' in window)) throw new Error('이 브라우저는 AudioWorklet 을 지원하지 않아요');
    this.ctx = new AC({ latencyHint: 'interactive' });
    try {
      const url = URL.createObjectURL(new Blob([WORKLET_SRC], { type: 'text/javascript' }));
      try {
        await this.ctx.audioWorklet.addModule(url);
      } finally {
        URL.revokeObjectURL(url);
      }
      this.source = this.ctx.createMediaStreamSource(stream);
      this.node = new AudioWorkletNode(this.ctx, 'ttobak-capture', {
        numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
        channelCount: 1, channelCountMode: 'explicit', channelInterpretation: 'speakers',
      });
      // 그래프가 destination 까지 이어져야 process()가 꾸준히 불린다. 소리는 내보내지 않는다(gain 0).
      const mute = this.ctx.createGain();
      mute.gain.value = 0;
      this.source.connect(this.node).connect(mute).connect(this.ctx.destination);
      this.node.port.onmessage = (e) => this._onMessage(e.data);
      if (this.ctx.state === 'suspended') await this.ctx.resume();
    } catch (e) {
      await this.close().catch(() => {});
      throw e;
    }
    // 입력 장치 지연(초) — 브라우저가 알려 줄 때만 쓴다
    try {
      const tr = stream.getAudioTracks()[0];
      const lat = tr && tr.getSettings ? Number(tr.getSettings().latency) : NaN;
      this.inputLatencyMs = Number.isFinite(lat) && lat > 0 && lat < 0.5 ? lat * 1000 : 0;
    } catch { this.inputLatencyMs = 0; }
  }

  get sampleRate() { return this.ctx ? this.ctx.sampleRate : 0; }
  /** 녹음 시작 후 경과(초) — 실제로 받은 샘플 수 기준이라 정확하다 */
  get elapsed() { return this.ctx ? this.samples / this.ctx.sampleRate : 0; }

  _onMessage(m) {
    if (!m) return;
    // 입력 기준 시계 대응: 녹음 중 받은 메시지마다 offset 후보를 갱신
    if (this.recording && typeof m.qEnd === 'number' && this.ctx) {
      const off = performance.now() - (m.qEnd / this.ctx.sampleRate) * 1000;
      if (off < this.offMin) this.offMin = off;
    }
    if (m.type === 'level') {
      this.onLevel(levelFromRms(m.rms), m.peak);
    } else if (m.type === 'data') {
      if (this.recording) { this.chunks.push(m.samples); this.samples += m.samples.length; }
    } else if (m.type === 'started') {
      this.startFrame = m.frame;
      this.t0Perf = this._frameToPerf(m.frame) ?? performance.now();
      if (this._startWaiter) { this._startWaiter(this.t0Perf); this._startWaiter = null; }
    } else if (m.type === 'stopped') {
      if (this._stopWaiter) { this._stopWaiter(); this._stopWaiter = null; }
    }
  }

  /** 입력 프레임 번호 → performance.now() 축(ms). 녹음 중 모은 offset 최솟값을 쓴다. */
  _frameToPerf(frame) {
    if (!this.ctx || !Number.isFinite(this.offMin)) return null;
    return (frame / this.ctx.sampleRate) * 1000 + this.offMin - this.inputLatencyMs;
  }

  /** 녹음 시작. 첫 샘플의 performance.now() 시각(ms, 잠정값)으로 resolve */
  async start() {
    if (!this.node) throw new Error('recorder not opened');
    if (this.ctx.state === 'suspended') await this.ctx.resume();
    this.chunks = [];
    this.samples = 0;
    this.t0Perf = null;
    this.startFrame = null;
    this.offMin = Infinity;
    this.recording = true;
    const fallback = performance.now();
    const p = new Promise((resolve) => {
      this._startWaiter = resolve;
      // 워클릿이 응답하지 않으면(입력 트랙 끊김 등) 지금 시각으로 대체
      setTimeout(() => { if (this._startWaiter) { this._startWaiter(fallback); this._startWaiter = null; this.t0Perf = fallback; } }, 400);
    });
    this.node.port.postMessage({ cmd: 'start' });
    return p;
  }

  /** 정지 → 16 kHz mono PCM16 WAV */
  async stop() {
    if (!this.recording) return null;
    const stopped = new Promise((resolve) => {
      this._stopWaiter = resolve;
      setTimeout(() => { if (this._stopWaiter) { this._stopWaiter(); this._stopWaiter = null; } }, 600);
    });
    this.node.port.postMessage({ cmd: 'stop' });
    await stopped;
    this.recording = false;
    // 녹음 전체에서 모은 offset 으로 첫 샘플 시각을 다듬는다(입력 기준)
    if (this.startFrame != null) {
      const refined = this._frameToPerf(this.startFrame);
      if (refined != null) this.t0Perf = refined;
    }
    const raw = concat(this.chunks, this.samples);
    this.chunks = [];
    const pcm = await resampleTo16k(raw, this.ctx.sampleRate);
    return {
      blob: encodeWav(pcm, TARGET_RATE),
      samples: pcm,
      sampleRate: TARGET_RATE,
      duration: pcm.length / TARGET_RATE,
      t0Perf: this.t0Perf,
    };
  }

  /** 녹음을 버리고 멈춘다 */
  cancel() {
    if (!this.recording) return;
    this.node.port.postMessage({ cmd: 'stop' });
    this.recording = false;
    this.chunks = [];
    this.samples = 0;
  }

  async close() {
    this.cancel();
    try { this.source && this.source.disconnect(); } catch { /* 무시 */ }
    try { this.node && this.node.disconnect(); } catch { /* 무시 */ }
    if (this.ctx && this.ctx.state !== 'closed') await this.ctx.close();
    this.ctx = null; this.node = null; this.source = null;
  }
}

function concat(chunks, total) {
  const out = new Float32Array(total);
  let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out;
}

/**
 * 원본 레이트 → 16 kHz. 브라우저의 AudioBufferSourceNode 리샘플은 보간 위주라
 * 고역이 접혀 들어올 수 있어, 먼저 원본 레이트에서 7 kHz 저역통과(윈도 싱크 FIR)를 건다.
 */
export async function resampleTo16k(samples, srcRate) {
  if (!samples.length) return new Float32Array(0);
  if (srcRate === TARGET_RATE) return samples;
  const filtered = srcRate > TARGET_RATE ? firLowpass(samples, srcRate, 7000) : samples;
  const outLen = Math.max(1, Math.round(samples.length * TARGET_RATE / srcRate));
  const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const off = new OAC(1, outLen, TARGET_RATE);
  const buf = off.createBuffer(1, filtered.length, srcRate);
  buf.copyToChannel ? buf.copyToChannel(filtered, 0) : buf.getChannelData(0).set(filtered);
  const src = off.createBufferSource();
  src.buffer = buf;
  src.connect(off.destination);
  src.start(0);
  const rendered = await off.startRendering();
  return rendered.getChannelData(0).slice();
}

function firLowpass(x, rate, cutoff, taps = 95) {
  const h = new Float32Array(taps);
  const m = (taps - 1) / 2;
  const fc = cutoff / rate;
  let sum = 0;
  for (let i = 0; i < taps; i++) {
    const k = i - m;
    const sinc = k === 0 ? 2 * fc : Math.sin(2 * Math.PI * fc * k) / (Math.PI * k);
    // Blackman 윈도
    const w = 0.42 - 0.5 * Math.cos((2 * Math.PI * i) / (taps - 1)) + 0.08 * Math.cos((4 * Math.PI * i) / (taps - 1));
    h[i] = sinc * w;
    sum += h[i];
  }
  for (let i = 0; i < taps; i++) h[i] /= sum;
  const n = x.length;
  const y = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let acc = 0;
    const lo = Math.max(0, i - m), hi = Math.min(n - 1, i + m);
    for (let j = lo; j <= hi; j++) acc += x[j] * h[j - i + m];
    y[i] = acc;
  }
  return y;
}

/** Float32 [-1,1] → PCM16 WAV Blob */
export function encodeWav(samples, rate) {
  const n = samples.length;
  const buf = new ArrayBuffer(44 + n * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); str(8, 'WAVE');
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, 'data'); v.setUint32(40, n * 2, true);
  let o = 44;
  for (let i = 0; i < n; i++, o += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}
