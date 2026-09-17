/* Isolated mechanical tests, not speech quality evidence. Run with node. */
const assert = require('node:assert/strict');
global.window = global;
require('./recorder.js');
const recorder = new VoiceFontRecorder();
const samples = new Float32Array(4800).fill(0.1);
const wav = recorder.encodeWav({sampleRate: 48000, frames: 4800, chunks: [samples]});
// Known PCM mono/48 kHz/16-bit RIFF header for 4,800 frames.
const expected = Buffer.from('52494646a425000057415645666d7420100000000100010080bb000000770100020010006461746180250000', 'hex');
assert.equal(expected.length, 44);
assert.deepEqual(Buffer.from(wav.slice(0, 44)), expected);
const view = new DataView(wav.buffer);
assert.equal(view.getUint16(20, true), 1);
assert.equal(view.getUint16(22, true), 1);
assert.equal(view.getUint32(24, true), 48000);
assert.equal(view.getUint16(34, true), 16);
assert.equal(view.getUint32(40, true), 9600);
assert.equal(wav.length, 9644);
assert.equal(view.getInt16(44, true), 3277);
const extremes = recorder.encodeWav({sampleRate: 8000, frames: 4, chunks: [Float32Array.from([-2, -1, 0, 2])]});
assert.deepEqual([...new Int16Array(extremes.buffer, 44)], [-32768, -32768, 0, 32767]);
console.log('PASS: exact 44-byte PCM header, little-endian fields, sample encoding and saturation');
require('./wav.js');
assert.equal(VoiceFontWav.validate(wav.buffer).seconds, 0.1);
for (const offset of [0, 8, 20, 22, 24, 32, 34, 40]) {
  const invalid = wav.slice(); invalid[offset] ^= 255;
  assert.throws(() => VoiceFontWav.validate(invalid.buffer), /PCM WAV/);
}
assert.throws(() => VoiceFontWav.validate(new ArrayBuffer(12)), /PCM WAV/);
assert.throws(() => VoiceFontWav.validate(wav.slice(0, -2).buffer), /PCM WAV/);
console.log('PASS: import accepts valid PCM and rejects malformed/truncated headers');
const stopped = [];
recorder.active = true; recorder.sampleRate = 48000; recorder.frames = 4800; recorder.chunks = [samples];
recorder.stream = {getTracks: () => [{stop: () => stopped.push('track')}]};
recorder.source = {disconnect: () => stopped.push('source')};
recorder.processor = {onaudioprocess: () => {}, disconnect: () => stopped.push('processor')};
recorder.sink = {disconnect: () => stopped.push('sink')};
recorder.context = {state: 'running', close: () => { stopped.push('context'); return Promise.resolve(); }};
const capture = recorder.stop();
assert.equal(capture.frames, 4800);
assert.equal(capture.chunks[0], samples);
assert.deepEqual(stopped.sort(), ['context', 'processor', 'sink', 'source', 'track']);
assert.equal(recorder.active, false);
assert.equal(recorder.stream, null);
assert.equal(recorder.stop(), null);
console.log('PASS: stop preserves samples, releases tracks and nodes, and is idempotent');
if (process.argv[2]) require('node:fs').writeFileSync(process.argv[2], Buffer.from(wav));
