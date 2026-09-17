/* Bounded mono PCM capture, exported without compressed intermediates. */
const global = window;
  'use strict';
  function encodeWav(capture) {
    const frames = capture.frames;
    const buffer = new ArrayBuffer(44 + frames * 2);
    const view = new DataView(buffer);
    const tag = (offset, text) => [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
    tag(0, 'RIFF'); view.setUint32(4, 36 + frames * 2, true); tag(8, 'WAVE');
    tag(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, capture.sampleRate, true);
    view.setUint32(28, capture.sampleRate * 2, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); tag(36, 'data'); view.setUint32(40, frames * 2, true);
    let index = 0;
    for (const chunk of capture.chunks) {
      for (const value of chunk) {
        if (index >= frames) break;
        const sample = Math.max(-1, Math.min(1, value));
        view.setInt16(44 + index++ * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
      }
    }
    return new Uint8Array(buffer);
  }
  class VoiceFontRecorder {
    constructor() { this.active = false; this.pending = false; this.generation = 0; }
    async start() {
      if (this.active || this.pending) throw new Error('Recording is already starting.');
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone unavailable. Open this page on localhost or import a PCM WAV.');
      this.pending = true;
      const generation = ++this.generation;
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false}});
        if (generation !== this.generation) { stream.getTracks().forEach(t => t.stop()); return false; }
        this.stream = stream;
        const Context = global.AudioContext || global.webkitAudioContext;
        this.context = new Context({sampleRate: 48000});
        await this.context.resume();
        if (generation !== this.generation) { this.cleanup(); return false; }
        if (this.context.sampleRate < 8000 || this.context.sampleRate > 96000) throw new Error('Unsupported microphone rate. Import an 8–96 kHz PCM WAV instead.');
        this.sampleRate = this.context.sampleRate;
        this.frames = 0; this.chunks = [];
        this.source = this.context.createMediaStreamSource(stream);
        this.processor = this.context.createScriptProcessor(4096, 1, 1);
        this.sink = this.context.createGain(); this.sink.gain.value = 0;
        this.processor.onaudioprocess = event => {
          if (!this.active) return;
          const input = event.inputBuffer.getChannelData(0);
          const length = Math.min(input.length, 180 * this.sampleRate - this.frames);
          if (length > 0) this.chunks.push(input.slice(0, length));
          this.frames += length;
          let energy = 0;
          for (let i = 0; i < length; i++) energy += input[i] ** 2;
          this.onlevel?.(Math.sqrt(energy / Math.max(1, length)));
          this.onduration?.(this.frames / this.sampleRate);
          if (this.frames >= 180 * this.sampleRate) this.finish('limit');
        };
        this.source.connect(this.processor); this.processor.connect(this.sink); this.sink.connect(this.context.destination);
        this.active = true; this.pending = false;
        stream.getTracks().forEach(track => track.addEventListener('ended', () => {
          if (this.active) this.finish('device');
        }));
        this.timer = setTimeout(() => { if (this.active) this.finish('limit'); }, 180000);
        return true;
      } catch (error) {
        stream?.getTracks().forEach(t => t.stop()); this.cleanup(); throw error;
      } finally { this.pending = false; }
    }
    finish(reason) { const capture = this.stop(); this.onfinish?.(capture, reason); }
    stop() {
      ++this.generation;
      const capture = this.active ? {sampleRate: this.sampleRate, frames: this.frames, chunks: this.chunks} : null;
      this.active = false; this.cleanup();
      // Keep a pending permission request locked until its promise settles.
      return capture;
    }
    cleanup() {
      clearTimeout(this.timer);
      if (this.processor) this.processor.onaudioprocess = null;
      for (const node of [this.source, this.processor, this.sink]) { try { node?.disconnect(); } catch (_) {} }
      this.stream?.getTracks().forEach(t => t.stop());
      if (this.context && this.context.state !== 'closed') this.context.close().catch(() => {});
      this.stream = this.context = this.source = this.processor = this.sink = null;
      this.chunks = []; this.frames = 0;
    }
    encodeWav(capture) { return encodeWav(capture); }
  }
export { VoiceFontRecorder, encodeWav };

