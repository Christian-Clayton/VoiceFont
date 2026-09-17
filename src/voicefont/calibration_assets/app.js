/* Same-origin workspace. No remote assets or HTML interpolation. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const recorder = new window.VoiceFontRecorder();
  const state = {corpus: null, session: null, prompt: null, draft: null, url: null, busy: false, job: null, poll: null, available: false};
  const enc = encodeURIComponent;
  const base = () => '/calibration/sessions/' + enc(state.session.id);
  function message(text, error = false) {
    $('message').textContent = text;
    $('message').hidden = !text;
    $('message').classList.toggle('error', error);
  }
  async function api(path, body, raw = false) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60000);
    try {
      const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', signal: controller.signal,
        headers: body === undefined ? {} : {'Content-Type': raw ? 'audio/wav' : 'application/json'},
        body: body === undefined ? undefined : raw ? body : JSON.stringify(body)});
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : JSON.stringify(data?.detail || 'Local service error ' + response.status));
      if (data === null) throw new Error('The local service returned an unreadable response.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The request timed out. Your unsaved take is kept. Retry, or refresh the session before trying again.');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  function element(tag, text, cls) {
    const node = document.createElement(tag); node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
  function action(text, fn) {
    const node = element('button', text); node.type = 'button';
    node.addEventListener('click', () => run(fn)); return node;
  }
  async function run(fn) {
    try { await fn(); } catch (error) { message(error.message, true); }
  }
  function elapsed(seconds) { return Math.floor(seconds / 60) + ':' + String(Math.floor(seconds % 60)).padStart(2, '0'); }
  function blocked() { return state.busy || recorder.active || recorder.pending; }
  function canLeave() {
    if (blocked()) { message('Stop the microphone or wait for the current operation first.', true); return false; }
    if (state.draft) { message('Save the unsaved take, or choose Re-record to discard it first.', true); return false; }
    return true;
  }
  function controls() {
    const locked = blocked();
    const editable = state.session?.status === 'active';
    $('record').disabled = !editable || locked || !!state.draft;
    $('stop').disabled = !recorder.active && !recorder.pending;
    $('save').disabled = !editable || locked || !state.draft;
    $('replay').disabled = locked || !$('take-audio').getAttribute('src');
    $('rerecord').disabled = !editable || locked || (!state.draft && !state.session?.accepted[state.prompt?.id]);
    for (const id of ['skip', 'next', 'import-wav', 'show-finalize']) $(id).disabled = locked || !!state.draft || !editable;
    $('leave-session').disabled = locked;
    $('start-session').disabled = state.busy || !state.corpus;
    document.querySelectorAll('.prompt-choice').forEach(b => { b.disabled = locked || !!state.draft; });
  }
  function clearAudio() {
    $('take-audio').pause(); $('take-audio').removeAttribute('src'); $('take-audio').hidden = true;
    if (state.url) URL.revokeObjectURL(state.url);
    state.url = null;
  }
  function audioSource(source) {
    clearAudio();
    const url = source instanceof Blob ? (state.url = URL.createObjectURL(source)) : source;
    $('take-audio').src = url; $('take-audio').hidden = false;
  }
  function discard() {
    state.draft = null; clearAudio(); $('import-wav').value = '';
    $('recorder-status').textContent = 'Ready when you are';
    $('recording-time').textContent = '0:00'; controls();
  }
  function setDraft(blob, seconds) {
    state.draft = {blob, id: 'take-' + crypto.randomUUID(), prompt: state.prompt.id};
    audioSource(blob); $('recording-time').textContent = elapsed(seconds);
    $('recorder-status').textContent = 'Unsaved take. Replay, then save or re-record.'; controls();
  }
  function updateCoverage() {
    const coverage = state.session?.coverage;
    $('coverage').max = state.corpus.prompts.length;
    $('coverage').value = coverage?.completed || 0;
    $('coverage-count').textContent = (coverage?.completed || 0) + ' / ' + state.corpus.prompts.length + ' accepted';
    $('coverage-label').textContent = coverage?.label || 'Not started';
    $('coverage-detail').textContent = 'Progress is saved after each accepted take. Optional prompts can be skipped.';
    const host = $('checklist'); host.textContent = '';
    for (const category of state.corpus.categories) {
      const prompts = state.corpus.prompts.filter(p => p.category === category.id);
      const completed = prompts.filter(p => state.session?.accepted[p.id]).length;
      const detail = element('details', ''); detail.open = state.prompt?.category === category.id;
      const summary = element('summary', category.title);
      summary.append(element('span', completed + '/' + prompts.length, 'category-count')); detail.append(summary);
      for (const prompt of prompts) {
        const button = action(prompt.id + ' · ' + prompt.text.slice(0, 42) + '…', () => { if (canLeave()) choosePrompt(prompt.id); });
        button.className = 'prompt-choice'; button.title = prompt.text;
        if (state.session?.accepted[prompt.id]) button.classList.add('accepted');
        if (state.session?.skipped.includes(prompt.id)) button.classList.add('skipped');
        if (state.prompt?.id === prompt.id) { button.classList.add('current'); button.setAttribute('aria-current', 'step'); }
        detail.append(button);
      }
      host.append(detail);
    }
  }
  function choosePrompt(id) {
    state.prompt = state.corpus.prompts.find(p => p.id === id) || state.corpus.prompts[0];
    const prompt = state.prompt;
    clearAudio();
    $('prompt-category').textContent = state.corpus.categories.find(c => c.id === prompt.category).title;
    $('prompt-index').textContent = (state.corpus.prompts.indexOf(prompt) + 1) + ' of ' + state.corpus.prompts.length + (prompt.optional ? ' · optional' : '');
    $('prompt-text').textContent = prompt.text;
    $('prompt-instruction').textContent = prompt.instruction;
    $('prompt-dimensions').textContent = 'Intended dimensions: ' + prompt.dimensions.join(', ');
    $('recorder-status').textContent = 'Ready when you are'; $('recording-time').textContent = '0:00';
    updateCoverage(); renderTakes(); controls();
  }
  function showSession(session) {
    state.session = session;
    $('setup').hidden = true; $('studio').hidden = false;
    $('session-title').textContent = session.name;
    $('export-session').href = base() + '/export';
    $('finalize-form').hidden = true;
    choosePrompt(session.next_prompt_id || state.corpus.prompts[0].id);
  }
  async function listSessions() {
    const sessions = await api('/calibration/sessions');
    const host = $('sessions-list'); host.textContent = '';
    if (!sessions.length) host.append(element('p', 'No saved sessions yet.', 'muted'));
    for (const session of sessions) {
      const row = element('div', '', 'session-row');
      const info = element('div', ''); info.append(element('strong', session.name), element('p', (session.coverage?.completed || 0) + ' accepted · ' + session.status + ' · ' + session.mode, 'small muted'));
      row.append(info, action(session.status === 'finalized' ? 'View session' : 'Resume', async () => {
        if (!canLeave()) return;
        showSession(await api('/calibration/sessions/' + enc(session.id)));
      })); host.append(row);
    }
  }
  function renderTakes() {
    const host = $('takes-list'); host.textContent = '';
    if (!state.session) return;
    const takes = state.session.takes.filter(t => t.prompt_id === state.prompt.id);
    if (!takes.length) host.append(element('p', 'No saved takes for this prompt yet.', 'small muted'));
    for (const [index, take] of takes.entries()) {
      const selected = state.session.accepted[state.prompt.id] === take.id;
      const row = element('div', '', 'take-row');
      const info = element('div', '');
      info.append(element('strong', 'Take ' + (index + 1) + (selected ? ' · selected' : '')),
        element('p', take.duration_seconds.toFixed(1) + ' seconds · ' + take.style, 'small muted'));
      const play = action('Replay saved', async () => {
        if (!canLeave()) return;
        audioSource(base() + '/takes/' + enc(take.id) + '/audio'); controls();
        await $('take-audio').play();
      });
      const select = action(selected ? 'Selected' : 'Use this take', async () => {
        if (!canLeave()) return;
        state.busy = true; controls();
        try {
          state.session = await api(base() + '/select', {prompt_id: state.prompt.id, take_id: take.id});
          renderTakes(); updateCoverage(); message('Selected take updated. All saved takes are kept.');
        } finally { state.busy = false; controls(); }
      });
      select.disabled = selected || state.session.status !== 'active';
      row.append(info, play, select); host.append(row);
    }
  }
  function nextPrompt() {
    const next = state.session.next_prompt_id;
    const index = state.corpus.prompts.indexOf(state.prompt);
    choosePrompt(next && next !== state.prompt.id ? next : state.corpus.prompts[(index + 1) % state.corpus.prompts.length].id);
  }
  async function saveTake() {
    if (!state.draft || blocked()) return;
    const draft = state.draft;
    state.busy = true; controls();
    try {
      state.session = await api(base() + '/takes?prompt_id=' + enc(draft.prompt) + '&take_id=' + enc(draft.id), draft.blob, true);
      state.draft = null; clearAudio(); $('import-wav').value = '';
      nextPrompt(); message('Take saved locally. Earlier takes are kept.');
    } catch (error) {
      message('Save failed. Your take is still here. ' + error.message + ' For clipping, lower input gain; for silence, check the input device or move closer.', true);
    } finally { state.busy = false; controls(); }
  }
  async function startSession(event) {
    event.preventDefault();
    if (!state.corpus || state.busy) return;
    if (!$('consent').checked) throw new Error('Confirm permission before recording.');
    state.busy = true; controls();
    try {
      showSession(await api('/calibration/sessions', {name: $('session-name').value.trim(), consent: true, mode: $('session-mode').value}));
      message('Session started. Read only the prompt, not the delivery instruction.');
    } finally { state.busy = false; controls(); }
  }
  async function finalize(event) {
    event.preventDefault();
    if (!canLeave()) return;
    state.busy = true; controls();
    const submit = $('finalize-form').querySelector('[type=submit]'); submit.disabled = true;
    try {
      const sessionPath = base();
      const profile = await api(sessionPath + '/finalize', {voice_id: $('voice-id').value.trim(), name: $('voice-name').value.trim()});
      state.session = await api(sessionPath);
      $('finalize-form').hidden = true; updateCoverage(); renderTakes();
      message('Profile created: ' + profile.name + '. Your full recording session is preserved.');
      await switchView('library');
    } finally { state.busy = false; submit.disabled = false; controls(); }
  }
  function captured(capture, reason) {
    $('recording-indicator').classList.remove('live'); $('level').value = 0;
    if (capture?.frames >= capture?.sampleRate * 0.1) {
      setDraft(new Blob([recorder.encodeWav(capture)], {type: 'audio/wav'}), capture.frames / capture.sampleRate);
      if (reason) message(reason === 'device' ? 'Microphone disconnected. The captured take is preserved; reconnect or import a WAV.' : 'Stopped at the 180 second limit. Replay before saving.');
    } else { $('recorder-status').textContent = 'Take too short. Record at least 0.1 seconds, or import a WAV.'; controls(); }
  }
  recorder.onfinish = captured;
  recorder.onlevel = level => { $('level').value = Math.min(1, level * 4); };
  recorder.onduration = seconds => { $('recording-time').textContent = elapsed(seconds); };
  async function record() {
    if (blocked() || state.draft || state.session?.status !== 'active') return;
    clearAudio(); $('recorder-status').textContent = 'Waiting for microphone permission. Stop cancels this request.';
    const starting = recorder.start(); controls();
    try {
      if (await starting) { $('recording-indicator').classList.add('live'); $('recorder-status').textContent = 'Recording. Read naturally, then press Stop.'; }
    } catch (error) {
      $('recorder-status').textContent = 'Microphone unavailable';
      const permission = ['NotAllowedError', 'SecurityError'].includes(error.name);
      message(permission ? 'Allow microphone access for this localhost page in browser site settings, then retry. You can also import a PCM WAV below.' : 'Check that a microphone is connected and not busy in another app. ' + error.message + ' You can import a PCM WAV below.', true);
    } finally { controls(); }
  }
  async function importTake() {
    const file = $('import-wav').files[0];
    if (!file || blocked() || state.draft || state.session?.status !== 'active') return;
    if (file.size > 50 * 1024 * 1024) throw new Error('WAV file exceeds 50 MB. Choose a shorter recording before importing.');
    state.busy = true; controls();
    try {
      const buffer = await file.arrayBuffer();
      $('take-audio').pause();
      const metadata = window.VoiceFontWav.validate(buffer);
      setDraft(new Blob([buffer], {type: 'audio/wav'}), metadata.seconds);
      message('WAV imported for this prompt, not yet saved. Replay it, then Save take & next.');
    } finally { state.busy = false; controls(); $('import-wav').value = ''; }
  }
  async function switchView(view) {
    $('take-audio').pause(); $('speech-audio').pause();
    for (const name of ['calibrate', 'library', 'speech']) {
      $('view-' + name).hidden = name !== view;
      $('nav-' + name).classList.toggle('active', name === view);
      if (name === view) $('nav-' + name).setAttribute('aria-current', 'page');
      else $('nav-' + name).removeAttribute('aria-current');
    }
    if (view === 'library' || view === 'speech') await library();
    if (view === 'speech') {
      state.available = false; speechControls();
      const capabilities = await api('/synthesis/capabilities');
      state.available = capabilities.available;
      $('capability').textContent = (capabilities.available ? 'Engine ready: ' + capabilities.backend + ' · ' + capabilities.device + '. ' : 'Engine unavailable. ') + capabilities.message;
      speechControls();
    }
  }
  async function library() {
    const profiles = await api('/profiles');
    const host = $('profiles-list'); host.textContent = '';
    const selected = $('speech-voice').value;
    $('speech-voice').replaceChildren(new Option('Choose a profile', ''));
    if (!profiles.length) host.append(element('p', 'No voice profiles yet. Record a session and create a profile to begin.', 'empty-state'));
    for (const profile of profiles) {
      $('speech-voice').add(new Option(profile.name, profile.voice_id));
      const row = element('div', '', 'profile-row'), info = element('div', '');
      info.append(element('h2', profile.name), element('p', profile.voice_id + ' · ' + (profile.created_at || '').slice(0, 10), 'small muted'));
      row.append(info, action('Create speech', async () => { await switchView('speech'); $('speech-voice').value = profile.voice_id; $('speech-text').focus(); }));
      host.append(row);
    }
    if (profiles.some(p => p.voice_id === selected)) $('speech-voice').value = selected;
  }
  function speechControls() {
    const running = state.job && ['queued', 'running', 'submitting'].includes(state.job.status);
    $('generate').disabled = !state.available || !!running;
    $('cancel-job').disabled = !running || !state.job?.id;
  }
  function jobResult(job) {
    state.job = job;
    $('job-panel').hidden = false;
    $('job-status').textContent = 'Status: ' + job.status + (job.error ? '. ' + job.error : '');
    if (job.status === 'completed') {
      const url = '/synthesis/jobs/' + enc(job.id) + '/audio';
      $('speech-audio').src = url; $('speech-audio').hidden = false;
      $('download-speech').href = url; $('download-speech').hidden = false;
    }
    speechControls();
  }
  async function checkJob(budget = 240) {
    clearTimeout(state.poll);
    const id = state.job?.id;
    if (!id) return;
    try {
      const job = await api('/synthesis/jobs/' + enc(id));
      if (state.job?.id !== id) return;
      jobResult(job); $('check-job').hidden = true;
      if (['queued', 'running'].includes(job.status)) {
        if (budget > 0) state.poll = setTimeout(() => run(() => checkJob(budget - 1)), 1500);
        else { $('check-job').hidden = false; message('Automatic status checks paused. The job may still be running. Check status or cancel.'); }
      }
    } catch (error) { $('check-job').hidden = false; message('Status check failed: ' + error.message + ' You can check again or cancel the job.', true); }
  }
  async function synthesize(event) {
    event.preventDefault();
    if ($('generate').disabled) return;
    const text = $('speech-text').value.trim();
    if (!text || text.length > 1000) throw new Error('Enter between 1 and 1,000 characters.');
    clearTimeout(state.poll); state.job = {status: 'submitting'}; speechControls();
    $('speech-audio').pause(); $('speech-audio').removeAttribute('src'); $('speech-audio').hidden = true;
    $('download-speech').hidden = true; $('check-job').hidden = true;
    $('job-panel').hidden = false; $('job-status').textContent = 'Submitting local speech job…';
    try {
      jobResult(await api('/synthesis/jobs', {voice_id: $('speech-voice').value, text, style: 'neutral', speed: Number($('speech-speed').value)}));
      await checkJob();
    } catch (error) { state.job = null; $('job-status').textContent = error.message; throw error; }
    finally { speechControls(); }
  }
  function on(id, event, fn) { $(id).addEventListener(event, e => run(() => fn(e))); }
  on('start-form', 'submit', startSession);
  on('refresh-sessions', 'click', listSessions);
  on('leave-session', 'click', async () => {
    if (!canLeave()) return;
    clearAudio(); state.session = null;
    $('studio').hidden = true; $('setup').hidden = false; updateCoverage(); controls(); await listSessions();
  });
  on('record', 'click', record);
  on('stop', 'click', () => captured(recorder.stop()));
  on('replay', 'click', async () => { $('take-audio').currentTime = 0; await $('take-audio').play(); });
  on('save', 'click', saveTake);
  on('rerecord', 'click', () => {
    if (blocked()) return;
    if (state.draft && !confirm('Discard this unsaved take? All saved takes will be kept.')) return;
    discard(); $('recorder-status').textContent = 'Ready for a new take. All earlier saved takes are kept.'; $('record').focus();
  });
  on('next', 'click', () => { if (canLeave()) nextPrompt(); });
  on('skip', 'click', async () => {
    if (!canLeave()) return;
    state.busy = true; controls();
    try { state.session = await api(base() + '/skip', {prompt_id: state.prompt.id}); nextPrompt(); message('Prompt skipped. Return using the checklist whenever you like.'); }
    finally { state.busy = false; controls(); }
  });
  on('import-wav', 'change', importTake);
  on('show-finalize', 'click', () => {
    if (!canLeave()) return;
    const categories = Object.values(state.session.coverage.by_category).filter(c => c.completed > 0).length;
    $('finalize-summary').textContent = state.session.coverage.completed + ' accepted prompts across ' + categories + ' categories. A partial profile needs at least 3 prompts across 2 categories. The server chooses the best neutral reference and preserves this session.';
    $('voice-name').value = state.session.name; $('finalize-form').hidden = false; $('voice-id').focus();
  });
  on('cancel-finalize', 'click', () => { $('finalize-form').hidden = true; });
  on('finalize-form', 'submit', finalize);
  for (const view of ['calibrate', 'library', 'speech']) on('nav-' + view, 'click', async () => {
    if (recorder.active || recorder.pending) captured(recorder.stop());
    if (canLeave()) await switchView(view);
  });
  on('new-calibration', 'click', async () => {
    if (!canLeave()) return;
    await switchView('calibrate'); $('studio').hidden = true; $('setup').hidden = false;
    state.session = null; updateCoverage(); controls(); await listSessions();
  });
  on('refresh-library', 'click', library);
  on('synthesis-form', 'submit', synthesize);
  on('cancel-job', 'click', async () => {
    if (!state.job?.id) return;
    clearTimeout(state.poll); $('cancel-job').disabled = true;
    try { jobResult(await api('/synthesis/jobs/' + enc(state.job.id) + '/cancel', {})); }
    finally { speechControls(); }
  });
  on('check-job', 'click', () => checkJob());
  on('speech-text', 'input', () => { $('text-count').textContent = $('speech-text').value.length + ' / 1,000 characters'; });
  on('speech-speed', 'input', () => { $('speed-value').textContent = Number($('speech-speed').value).toFixed(2) + '×'; });
  window.addEventListener('beforeunload', event => {
    if (state.draft || recorder.active || recorder.pending || state.busy) { event.preventDefault(); event.returnValue = ''; }
  });
  window.addEventListener('pagehide', () => {
    if (recorder.active || recorder.pending) captured(recorder.stop());
    clearTimeout(state.poll); $('take-audio').pause(); $('speech-audio').pause();
  });
  run(async () => {
    controls();
    state.corpus = await api('/calibration/corpus');
    updateCoverage(); controls(); await listSessions();
  });
})();
