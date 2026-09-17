import {describe,it,expect} from 'vitest';
import {captureMatches,sessionPath} from './api';
describe('immutable recording attribution',()=>{
 it('allows the original context',()=>expect(captureMatches({sessionId:'a',promptId:'p'},'a','p')).toBe(true));
 it('rejects another session',()=>expect(captureMatches({sessionId:'a',promptId:'p'},'b','p')).toBe(false));
 it('rejects another prompt',()=>expect(captureMatches({sessionId:'a',promptId:'p'},'a','q')).toBe(false));
 it('encodes session identifiers',()=>expect(sessionPath('session name')).toBe('/calibration/sessions/session%20name'));
});
