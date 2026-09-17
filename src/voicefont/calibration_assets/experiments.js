/* Isolated opt-in acoustic ML panel. No microphone ownership or remote assets. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const storageKey = 'voicefont-last-acoustic-experiment';
  let available = false, busy = false, job = null, timer = null, loaded = false;
  let sessions = [], minimum = 8;

  function error(message = '') {
    $('experiment-error').textContent = message;
    $('experiment-error').hidden = !message;
  }
  async function api(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(path, {
        method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
        headers: body === undefined ? {} : {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Local experiment request failed.');
      return data;
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('Request timed out. Check status before starting another experiment.');
      throw e;
    } finally { clearTimeout(timeout); }
  }
  function distinct(session) {
    const selected = new Set(Object.values(session.accepted));
    return new Set(session.takes.filter(take => selected.has(take.id)).map(take => take.sha256)).size;
  }
  function controls() {
    const selected = sessions.find(session => session.id === $('experiment-session').value);
    const active = busy || ['queued', 'running'].includes(job?.status);
    $('experiment-train').disabled = active || !available || !$('experiment-consent').checked || !selected || distinct(selected) < minimum;
    $('experiment-session').disabled = active;
    $('experiment-consent').disabled = active;
    $('experiment-refresh-sessions').disabled = active;
  }
  async function refresh() {
    error();
    const [capability, saved] = await Promise.all([api('/experiments/capabilities'), api('/calibration/sessions')]);
    available = capability.available;
    minimum = capability.minimum_distinct_recordings;
    $('experiment-capability').textContent = capability.message + ' One background experiment at a time; no automatic training.';
    sessions = saved;
    const previous = $('experiment-session').value;
    $('experiment-session').replaceChildren(new Option('Choose a saved session', ''));
    for (const session of saved) {
      const count = distinct(session);
      const option = new Option(session.name + ' · ' + count + ' distinct selected WAVs' + (count < minimum ? ' (need ' + minimum + ')' : ''), session.id);
      $('experiment-session').add(option);
    }
    if (saved.some(session => session.id === previous)) $('experiment-session').value = previous;
    loaded = true;
    controls();
  }
  function render(result) {
    job = result;
    $('experiment-output').hidden = false;
    $('experiment-id').textContent = 'Experiment ' + result.id + ' · session ' + result.session_id;
    $('experiment-status').textContent = result.status === 'completed' ? 'Completed · ' + (result.gate_passed ? 'gate passed' : 'gate rejected') : result.status === 'failed' ? result.error : result.status + ' · extracting features, training and evaluating locally. You can leave this panel.';
    $('experiment-results').hidden = result.status !== 'completed';
    if (result.status === 'completed') {
      const metrics = result.report.metrics;
      $('experiment-mse').textContent = Number(metrics.validation_mse).toPrecision(6);
      $('experiment-baseline').textContent = Number(metrics.baseline_mse).toPrecision(6);
      $('experiment-gate').textContent = result.gate_passed ? 'PASS · numeric model published locally, not a TTS voice' : 'REJECTED · no model published';
      $('experiment-split').textContent = result.dataset.distinct_recordings + ' distinct original WAVs · ' + result.dataset.train_hashes.length + ' training / ' + result.dataset.heldout_hashes.length + ' heldout · ' + result.dataset.feature_version + ' · ' + result.dataset.feature_dimensions + ' descriptors per WAV · seed ' + result.dataset.seed;
      $('experiment-stages').textContent = result.report.stages.join(' → ');
      $('experiment-run').textContent = result.report.run_id;
    }
    try { localStorage.setItem(storageKey, result.id); } catch (_) { /* Server results remain durable. */ }
    clearTimeout(timer);
    if (['queued', 'running'].includes(result.status)) timer = setTimeout(() => check().catch(e => error(e.message)), 1000);
    controls();
  }
  async function check() {
    if (!job?.id) return;
    clearTimeout(timer);
    error();
    render(await api('/experiments/' + encodeURIComponent(job.id)));
  }
  async function open() {
    if (!loaded) await refresh();
    if (!job) {
      let previous;
      try { previous = localStorage.getItem(storageKey); } catch (_) { /* Storage may be disabled. */ }
      if (/^[0-9a-f]{32}$/.test(previous || '')) {
        job = {id: previous};
        $('experiment-output').hidden = false;
        await check();
      }
    }
  }
  function handle(fn) { return event => Promise.resolve(fn(event)).catch(e => { error(e.message); controls(); }); }
  $('experiment-form').addEventListener('submit', handle(async event => {
    event.preventDefault();
    if ($('experiment-train').disabled) return;
    busy = true; controls(); error(); clearTimeout(timer);
    try {
      render(await api('/experiments', {session_id: $('experiment-session').value, consent: $('experiment-consent').checked}));
      $('experiment-consent').checked = false;
    } finally { busy = false; controls(); }
  }));
  $('experiment-session').addEventListener('change', () => { $('experiment-consent').checked = false; controls(); });
  $('experiment-consent').addEventListener('change', controls);
  $('experiment-refresh-sessions').addEventListener('click', handle(refresh));
  $('experiment-check').addEventListener('click', handle(check));
  $('experiments-details').addEventListener('toggle', handle(() => $('experiments-details').open ? open() : undefined));
  $('nav-experiments').addEventListener('click', () => {
    // Use the existing Stop control; never reach into recorder internals.
    if (!$('stop').disabled) $('stop').click();
    $('take-audio').pause(); $('speech-audio').pause();
    $('experiments-details').open = true;
    $('experiments-panel').focus();
  });
  window.addEventListener('pagehide', () => clearTimeout(timer));
})();
