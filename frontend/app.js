/* KAY AI Movie Recap — SPA */
const $ = id => document.getElementById(id);
let token = localStorage.getItem('kay_token') || '';
let user = null, project = null, caps = null, jobTimer = null, lastJobId = null;

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json',
      ...(token ? { 'Authorization': 'Bearer ' + token } : {}),
      ...(opts.headers || {}) },
  });
  if (r.status === 401) { doLogout(true); throw new Error('session'); }
  const t = await r.text();
  let j = {};
  try { j = t ? JSON.parse(t) : {}; } catch (e) { j = { detail: t }; }
  if (!r.ok) throw new Error(j.detail || ('HTTP ' + r.status));
  return j;
}
function err(e, el) { if (el) $(el).textContent = e.message || String(e); }
async function apiForm(path, formData) {
  const r = await fetch(path, {
    method: 'POST',
    body: formData,
    headers: { ...(token ? { 'Authorization': 'Bearer ' + token } : {}) },
  });
  if (r.status === 401) { doLogout(true); throw new Error('session'); }
  const t = await r.text();
  let j = {};
  try { j = t ? JSON.parse(t) : {}; } catch (e) { j = { detail: t }; }
  if (!r.ok) throw new Error(j.detail || ('HTTP ' + r.status));
  return j;
}

/* ---------- auth ---------- */
function showAuthTab(t) {
  $('tab-login').classList.toggle('active', t === 'login');
  $('tab-register').classList.toggle('active', t === 'register');
  $('auth-login').style.display = t === 'login' ? '' : 'none';
  $('auth-register').style.display = t === 'register' ? '' : 'none';
}
async function doLogin() {
  try { const j = await api('/api/auth/login', { method: 'POST',
    body: JSON.stringify({ username: $('login-user').value, password: $('login-pass').value }) });
    setSession(j); } catch (e) { err(e, 'auth-err'); }
}
async function doRegister() {
  try { const j = await api('/api/auth/register', { method: 'POST',
    body: JSON.stringify({ username: $('reg-user').value, password: $('reg-pass').value }) });
    setSession(j); } catch (e) { err(e, 'auth-err'); }
}
function setSession(j) { token = j.token; localStorage.setItem('kay_token', token); user = j.user; boot(); }
function doLogout(silent) {
  token = ''; user = null; project = null; localStorage.removeItem('kay_token');
  clearInterval(jobTimer);
  $('app-view').style.display = 'none'; $('auth-view').style.display = '';
  if (!silent) $('auth-err').textContent = '';
}

/* ---------- nav ---------- */
function nav(name) {
  document.querySelectorAll('.navbtn').forEach(b => b.classList.toggle('active', b.dataset.nav === name));
  ['create', 'projects', 'voice', 'admin'].forEach(v => $('view-' + v).style.display = v === name ? '' : 'none');
  if (name === 'projects') loadProjects();
  if (name === 'voice') loadVoiceStudio();
  if (name === 'admin') loadAdmin();
}
function itab(name) {
  document.querySelectorAll('[data-itab]').forEach(b => b.classList.toggle('active', b.dataset.itab === name));
  ['upload'].forEach(t => $('itab-' + t).style.display = t === name ? '' : 'none');
}

/* ---------- boot ---------- */
async function boot() {
  $('auth-view').style.display = 'none'; $('app-view').style.display = '';
  $('username').textContent = user.username;
  $('credits').textContent = '💰 ' + user.credits;
  if (user.is_admin) $('nav-admin').style.display = '';
  caps = await api('/api/capabilities');
  const ms = $('set-mode'); ms.innerHTML = '';
  caps.modes.forEach(m => { const o = document.createElement('option'); o.value = m.id; o.textContent = m.label; ms.appendChild(o); });
  $('max-mb').textContent = '500';
  if (!caps.tts) { $('tts-warn').style.display = ''; $('tts-warn').textContent = '⚠️ ' + caps.tts_message; }
  await loadVoices();
  bindSettings();
  nav('create');
}
async function loadVoices() {
  try {
    const j = await api('/api/tts/voices');
    const opts = j.voices || [];
    for (const sel of [$('set-voice'), $('vs-voice')]) {
      sel.innerHTML = '<option value="">—</option>';
      opts.forEach(v => { const o = document.createElement('option'); o.value = v.id; o.textContent = v.name; sel.appendChild(o); });
    }
    if (!j.configured && $('voice-list-warn')) {
      $('voice-list-warn').style.display = ''; $('voice-list-warn').textContent = '⚠️ ' + (j.message || '');
    }
  } catch (e) { /* voices endpoint never hard-fails */ }
}

/* ---------- ingest ---------- */
async function doUpload() {
  const f = $('upload-file').files[0];
  if (!f) { $('ingest-err').textContent = 'ဖိုင်ရွေးပါ'; return; }
  $('ingest-err').textContent = '';
  const fd = new FormData(); fd.append('file', f);
  $('upload-prog').style.display = '';
  try {
    const r = await fetch('/api/ingest/upload', { method: 'POST',
      headers: token ? { 'Authorization': 'Bearer ' + token } : {}, body: fd });
    const t = await r.text(); const j = t ? JSON.parse(t) : {};
    if (!r.ok) throw new Error(j.detail || 'upload failed');
    openProject(j.id);
  } catch (e) { err(e, 'ingest-err'); }
  $('upload-prog').style.display = 'none';
}

/* ---------- project ---------- */
async function openProject(pid) {
  project = await api('/api/projects/' + pid);
  $('no-project').style.display = 'none';
  $('project-view').style.display = '';
  $('preview').src = '/api/projects/' + pid + '/video-file';
  renderAnalysis(); syncSettings(); renderSegments(); renderExports();
  renderNarrStatus();
  $('job-box').style.display = 'none'; $('dl-box').style.display = project.exports.length ? '' : 'none';
}
function renderAnalysis() {
  const p = project;
  $('analysis').innerHTML = `<h3>📊 VIDEO INFORMATION</h3>
    <div class="grid2">
    <div>Resolution:<br><b>${p.width} × ${p.height}</b></div>
    <div>FPS:<br><b>${p.fps}</b></div>
    <div>Duration:<br><b>${(p.duration_ms / 60000).toFixed(1)} min</b></div>
    <div>Language:<br><b>${p.detected_language || p.language}</b></div>
    <div>Speech:<br><b>${p.has_audio ? 'Detected' : 'None'}</b></div>
    <div>Source:<br><b>${p.source_type}</b></div></div>`;
}
function syncSettings() {
  const p = project, v = id => $(id).value = p[id.replace('set-', '').replace(/-/g, '_')] ?? '';
  $('set-mode').value = p.mode; $('set-lang').value = p.language;
  $('set-voice').value = p.voice_id || ''; $('set-speed').value = String(p.voice_speed);
  $('set-pitch').value = p.voice_pitch; $('set-substyle').value = p.subtitle_style;
  $('set-subpos').value = p.subtitle_position;
  $('set-orig-on').checked = !!p.orig_audio_enabled;
  $('set-orig-vol').value = p.orig_audio_volume; $('orig-vol-v').textContent = p.orig_audio_volume + '%';
  $('set-mask-on').checked = !!p.mask_enabled;
  $('mask-x').value = p.mask_x; $('mask-y').value = p.mask_y; $('mask-w').value = p.mask_w; $('mask-h').value = p.mask_h;
  $('set-mask-type').value = p.mask_type;
  $('set-preset').value = p.export_preset; $('set-fps').value = p.export_fps;
  $('set-aspect').value = p.export_aspect; $('set-quality').value = p.export_quality;
}
let patchTimer = null;
function bindSettings() {
  const map = { 'set-mode': 'mode', 'set-lang': 'language', 'set-voice': 'voice_id', 'set-speed': 'voice_speed',
    'set-pitch': 'voice_pitch', 'set-substyle': 'subtitle_style', 'set-subpos': 'subtitle_position',
    'set-orig-on': 'orig_audio_enabled', 'set-orig-vol': 'orig_audio_volume', 'set-mask-on': 'mask_enabled',
    'mask-x': 'mask_x', 'mask-y': 'mask_y', 'mask-w': 'mask_w', 'mask-h': 'mask_h',
    'set-mask-type': 'mask_type', 'set-preset': 'export_preset', 'set-fps': 'export_fps',
    'set-aspect': 'export_aspect', 'set-quality': 'export_quality' };
  Object.keys(map).forEach(id => {
    $(id).addEventListener('change', () => {
      if (!project) return;
      let val = $(id).type === 'checkbox' ? ($(id).checked ? 1 : 0) : $(id).value;
      if (['voice_speed'].includes(map[id])) val = parseFloat(val);
      if (['orig_audio_volume', 'mask_x', 'mask_y', 'mask_w', 'mask_h'].includes(map[id])) val = parseInt(val);
      if (id === 'set-orig-vol') $('orig-vol-v').textContent = val + '%';
      clearTimeout(patchTimer);
      patchTimer = setTimeout(() => api('/api/projects/' + project.id,
        { method: 'PATCH', body: JSON.stringify({ data: { [map[id]]: val } }) }).catch(() => {}), 400);
    });
  });
}
function renderSegments() {
  const tb = $('seg-table').querySelector('tbody'); tb.innerHTML = '';
  (project.segments || []).forEach((s, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${i + 1}</td>
      <td><input size="6" value="${(s.start_ms / 1000).toFixed(1)}" data-f="start_ms"></td>
      <td><input size="6" value="${(s.end_ms / 1000).toFixed(1)}" data-f="end_ms"></td>
      <td><textarea rows="2" data-f="original_text">${s.original_text || ''}</textarea></td>
      <td><textarea rows="2" data-f="burmese_text">${s.burmese_text || ''}</textarea></td>
      <td><textarea rows="2" data-f="voice_text">${s.voice_text || ''}</textarea></td>
      <td><button class="btn small" data-del>✕</button></td>`;
    tr.querySelectorAll('input,textarea').forEach(el => {
      el.addEventListener('change', async () => {
        let val = el.value;
        if (el.dataset.f === 'start_ms' || el.dataset.f === 'end_ms') val = Math.round(parseFloat(val) * 1000);
        await api(`/api/projects/${project.id}/segments/${s.id}`, { method: 'PATCH', body: JSON.stringify({ [el.dataset.f]: val }) });
      });
    });
    tr.querySelector('[data-del]').onclick = async () => {
      await api(`/api/projects/${project.id}/segments/${s.id}`, { method: 'DELETE' });
      project = await api('/api/projects/' + project.id); renderSegments();
    };
    tb.appendChild(tr);
  });
}
async function addSegment() {
  const dur = project.duration_ms / 1000;
  await api(`/api/projects/${project.id}/segments`, { method: 'POST',
    body: JSON.stringify({ start_ms: 0, end_ms: 2000, burmese_text: 'စာသားအသစ်' }) });
  project = await api('/api/projects/' + project.id); renderSegments();
}
async function autoFix() {
  await api(`/api/projects/${project.id}/segments/autofix`, { method: 'POST' });
  project = await api('/api/projects/' + project.id); renderSegments();
}
function renderExports() {
  const kinds = new Set((project.exports || []).map(e => e.kind));
  $('dl-box').style.display = kinds.size ? '' : 'none';
}

/* ---------- custom narration (self-made MP3) ---------- */
function renderNarrStatus() {
  const n = project && project.narration_mp3;
  $('narr-status').innerHTML = n
    ? '✅ အသံဖိုင်တင်ထားပြီး — pipeline က <b>ဒီအသံကို voiceover အဖြစ်သုံးပါမယ်</b> (Google TTS မလိုပါ)။'
    : '⚪ မတင်ရသေးပါ — မတင်ရင် Google TTS သုံးပါမယ်။';
  $('narr-del').style.display = n ? '' : 'none';
}
async function uploadNarration() {
  if (!project) return;
  const f = $('narr-file').files[0];
  if (!f) { $('narr-err').textContent = 'အသံဖိုင် အရင်ရွေးပါ။'; return; }
  $('narr-err').textContent = ''; $('narr-status').textContent = '⏳ တင်နေသည်…';
  const fd = new FormData(); fd.append('file', f);
  try {
    await apiForm(`/api/projects/${project.id}/narration`, fd);
    project = await api('/api/projects/' + project.id);
    renderNarrStatus();
    $('narr-file').value = '';
  } catch (e) { $('narr-err').textContent = e.message; renderNarrStatus(); }
}
async function removeNarration() {
  if (!project) return;
  await api(`/api/projects/${project.id}/narration`, { method: 'DELETE' });
  project = await api('/api/projects/' + project.id);
  renderNarrStatus();
}

/* ---------- pipeline ---------- */
async function runPipeline() {
  try {
    $('job-err').textContent = ''; $('resume-btn').style.display = 'none';
    const j = await api(`/api/projects/${project.id}/run`, { method: 'POST' });
    lastJobId = j.job_id;
    $('job-box').style.display = ''; $('run-btn').disabled = true;
    clearInterval(jobTimer);
    jobTimer = setInterval(() => pollJob(lastJobId), 1500);
    pollJob(lastJobId);
  } catch (e) { $('job-err').textContent = e.message; }
}
async function pollJob(jid) {
  try {
    const j = await api('/api/jobs/' + jid);
    $('job-stage').textContent = (j.stage_label || j.stage) + '… ' + j.progress + '%';
    $('job-bar').style.width = j.progress + '%';
    if (j.status === 'done') {
      clearInterval(jobTimer); $('run-btn').disabled = false;
      $('job-stage').textContent = '✅ ပြီးပါပြီ!';
      project = await api('/api/projects/' + project.id); renderSegments(); renderExports();
      const u = await api('/api/auth/me'); user = u; $('credits').textContent = '💰 ' + u.credits;
    } else if (j.status === 'failed') {
      clearInterval(jobTimer); $('run-btn').disabled = false;
      $('job-err').textContent = j.error || 'အမှားဖြစ်နေပါတယ်';
      $('resume-btn').style.display = '';
    }
  } catch (e) { /* keep polling */ }
}
async function resumeJob() {
  const j = await api('/api/jobs/' + lastJobId + '/resume', { method: 'POST' });
  lastJobId = j.job_id; $('job-err').textContent = ''; $('resume-btn').style.display = 'none';
  clearInterval(jobTimer); jobTimer = setInterval(() => pollJob(lastJobId), 1500); pollJob(lastJobId);
}
function dl(kind) { window.open(`/api/projects/${project.id}/download/${kind}`, '_blank'); }

/* ---------- projects list ---------- */
async function loadProjects() {
  const list = await api('/api/projects');
  const el = $('proj-list'); el.innerHTML = '';
  list.forEach(p => {
    const d = document.createElement('div'); d.className = 'card';
    d.innerHTML = `<h3>${p.name}</h3><p class="hint">${p.source_type} · ${(p.duration_ms / 60000).toFixed(1)} min · ${p.status}</p>
      <button class="btn small" data-a="open">ဖွင့်ရန်</button>
      <button class="btn small" data-a="dup">ပွားရန်</button>
      <button class="btn small" data-a="del">ဖျက်ရန်</button>`;
    d.querySelector('[data-a=open]').onclick = () => { nav('create'); openProject(p.id); };
    d.querySelector('[data-a=dup]').onclick = async () => { const n = await api(`/api/projects/${p.id}/duplicate`, { method: 'POST' }); loadProjects(); };
    d.querySelector('[data-a=del]').onclick = async () => { if (confirm('ဖျက်မှာလား?')) { await api('/api/projects/' + p.id, { method: 'DELETE' }); loadProjects(); } };
    el.appendChild(d);
  });
  if (!list.length) el.innerHTML = '<p class="hint">Project မရှိသေးပါ။</p>';
}

/* ---------- voice studio ---------- */
async function loadVoiceStudio() { await loadVoices(); }
async function voicePreview() {
  try {
    $('vs-err').textContent = '';
    const r = await fetch('/api/tts/preview', { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify({ text: $('vs-text').value, voice_id: $('vs-voice').value,
        speed: parseFloat($('vs-speed').value), pitch: $('vs-pitch').value }) });
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.detail || 'preview failed'); }
    const blob = await r.blob();
    $('vs-audio').src = URL.createObjectURL(blob); $('vs-audio').style.display = ''; $('vs-audio').play();
  } catch (e) { $('vs-err').textContent = e.message; }
}

/* ---------- admin ---------- */
async function loadAdmin() {
  const users = await api('/api/admin/users');
  const tb = $('admin-users').querySelector('tbody'); tb.innerHTML = '';
  users.forEach(u => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${u.id}</td><td>${u.username}${u.disabled ? ' 🚫' : ''}</td><td>${u.credits}</td><td>${u.is_admin ? '✓' : ''}</td><td></td>`;
    const td = tr.lastChild;
    const b1 = document.createElement('button'); b1.className = 'btn small'; b1.textContent = '+1000';
    b1.onclick = async () => { const a = prompt('Credit ပေါင်းထည့်ရန် ပမာဏ', '1000'); if (a) { await api(`/api/admin/users/${u.id}/credits`, { method: 'POST', body: JSON.stringify({ amount: parseFloat(a) }) }); loadAdmin(); } };
    const b2 = document.createElement('button'); b2.className = 'btn small'; b2.textContent = u.disabled ? 'Enable' : 'Disable';
    b2.onclick = async () => { await api(`/api/admin/users/${u.id}/${u.disabled ? 'enable' : 'disable'}`, { method: 'POST' }); loadAdmin(); };
    td.append(b1, b2); tb.appendChild(tr);
  });
  const jobs = await api('/api/admin/jobs');
  const jt = $('admin-jobs').querySelector('tbody'); jt.innerHTML = '';
  jobs.slice(0, 30).forEach(j => {
    jt.innerHTML += `<tr><td>${j.id}</td><td>${j.username || ''}</td><td>${j.stage}</td><td>${j.status}</td><td>${j.progress}%</td></tr>`;
  });
  const errs = await api('/api/admin/errors');
  $('admin-errors').innerHTML = errs.length ? errs.map(e => `<p class="err">#${e.id} [${e.username}] ${e.stage}: ${e.error}</p>`).join('') : '<p class="hint">Error မရှိပါ။</p>';
  const st = await api('/api/admin/settings');
  const labels = { credit_price_video_per_min: 'Video credit/min', credit_price_voice_per_min: 'Voice credit/min',
    credit_price_recap_per_min: 'Recap credit/min', ai_model: 'AI model', tts_provider: 'TTS provider',
    max_upload_mb: 'Max upload MB', max_video_min: 'Max video minutes' };
  const box = $('admin-settings'); box.innerHTML = '';
  Object.keys(labels).forEach(k => {
    const l = document.createElement('label'); l.innerHTML = labels[k] + `<input data-k="${k}" value="${st[k] ?? ''}">`; box.appendChild(l);
  });
  await loadApiKeys();
}
async function saveApiKeys() {
  const gemini_api_key = $('key-gemini').value.trim();
  const google_tts_api_key = $('key-tts').value.trim();
  await api('/api/admin/api-keys', { method: 'POST', body: JSON.stringify({ gemini_api_key, google_tts_api_key }) });
  $('key-gemini').value = ''; $('key-tts').value = '';
  await loadApiKeys();
  alert('🔑 Key များ သိမ်းပြီးပါပြီ');
}
async function loadApiKeys() {
  try {
    const s = await api('/api/admin/api-keys');
    const row = (label, st) => `<p>${label}: ${st.configured ? '✅ ထည့်ပြီးသား <code>' + st.masked + '</code> (' + st.source + ')' : '❌ မထည့်ရသေးပါ'}</p>`;
    $('api-keys-status').innerHTML = row('Gemini', s.gemini) + row('Google TTS', s.google_tts);
  } catch (e) { $('api-keys-status').textContent = 'Key အခြေအနေ ဖတ်၍မရပါ'; }
}
async function saveAdminSettings() {
  const data = {};
  document.querySelectorAll('#admin-settings input').forEach(i => data[i.dataset.k] = i.value);
  await api('/api/admin/settings', { method: 'PATCH', body: JSON.stringify({ data }) });
  alert('သိမ်းပြီးပါပြီ');
}

/* ---------- init ---------- */
(async function init() {
  if (token) {
    try { user = await api('/api/auth/me'); boot(); return; } catch (e) { doLogout(true); }
  }
  $('auth-view').style.display = '';
})();
