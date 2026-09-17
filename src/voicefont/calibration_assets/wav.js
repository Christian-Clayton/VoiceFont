/* Structural import checks only. The backend additionally validates signal quality. */
(() => {
  'use strict';
  function validate(buffer) {
    const fail = () => { throw new Error('Use a complete integer PCM WAV: mono/stereo, 8–96 kHz, 8/16/24/32-bit, 0.1–180 seconds, at most 50 MB.'); };
    if (buffer.byteLength < 44 || buffer.byteLength > 50 * 1024 * 1024) fail();
    const view = new DataView(buffer);
    const tag = offset => String.fromCharCode(...new Uint8Array(buffer, offset, 4));
    if (tag(0) !== 'RIFF' || tag(8) !== 'WAVE' || view.getUint32(4, true) + 8 !== buffer.byteLength) fail();
    let format = null, dataBytes = null, offset = 12;
    while (offset + 8 <= buffer.byteLength) {
      const kind = tag(offset), size = view.getUint32(offset + 4, true), start = offset + 8;
      if (start + size > buffer.byteLength) fail();
      if (kind === 'fmt ') {
        if (format || size < 16 || view.getUint16(start, true) !== 1) fail();
        format = {channels: view.getUint16(start + 2, true), rate: view.getUint32(start + 4, true), byteRate: view.getUint32(start + 8, true), align: view.getUint16(start + 12, true), bits: view.getUint16(start + 14, true)};
      }
      if (kind === 'data') { if (dataBytes !== null || !format) fail(); dataBytes = size; }
      offset = start + size + size % 2;
    }
    if (!format || dataBytes === null || ![1, 2].includes(format.channels) || ![8, 16, 24, 32].includes(format.bits) || format.rate < 8000 || format.rate > 96000) fail();
    if (format.align !== format.channels * format.bits / 8 || format.byteRate !== format.rate * format.align || dataBytes % format.align) fail();
    const seconds = dataBytes / format.byteRate;
    if (seconds < 0.1 || seconds > 180) fail();
    return {...format, seconds};
  }
  window.VoiceFontWav = {validate};
})();
