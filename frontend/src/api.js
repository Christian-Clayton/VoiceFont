export async function api(path, body, raw = false) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin', signal: controller.signal,
      headers: body === undefined ? {} : {'Content-Type': raw ? 'audio/wav' : 'application/json'},
      body: body === undefined ? undefined : raw ? body : JSON.stringify(body)});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Request failed (' + response.status + ')');
    return result;
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('Request timed out. Saved recordings are preserved; retry to recover.');
    throw e;
  } finally { clearTimeout(timer); }
}
export const sessionPath = id => '/calibration/sessions/' + encodeURIComponent(id);
export const jobPath = id => '/synthesis/jobs/' + encodeURIComponent(id);
export function captureMatches(binding, sessionId, promptId) {
  return !!binding && binding.sessionId === sessionId && binding.promptId === promptId;
}
