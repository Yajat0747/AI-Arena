'use strict';
let runHistory = [];
let lastResult = null;
const API = () => (document.getElementById('apiBase')?.value || 'https://pool-ai-1.onrender.com').replace(/\/$/,'');

/* ── Canvas Particles ── */
function initCanvas() {
  const canvas = document.getElementById('bgCanvas');
  const ctx = canvas.getContext('2d');
  let particles = [];
  const resize = () => { canvas.width = innerWidth; canvas.height = innerHeight; };
  resize(); window.addEventListener('resize', resize);

  for (let i = 0; i < 40; i++) particles.push({
    x: Math.random() * innerWidth,
    y: Math.random() * innerHeight,
    vx: (Math.random() - .5) * .2,
    vy: (Math.random() - .5) * .2,
    r: Math.random() * 1.2 + .4,
    a: Math.random() * .3 + .08,
    c: Math.random() > .5 ? '91,156,246' : '52,211,153'
  });

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > canvas.width)  p.vx *= -1;
      if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${p.c},${p.a})`;
      ctx.fill();
    });
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < 130) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(91,156,246,${.035 * (1 - d / 130)})`;
          ctx.lineWidth = .5;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
}

/* ── Boot ── */
window.addEventListener('DOMContentLoaded', () => {
  initCanvas();
  document.getElementById('promptInput').addEventListener('input', e => {
    document.getElementById('charCnt').textContent = e.target.value.length;
  });
  document.getElementById('promptInput').addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) runArena();
  });
  checkStatus();
});

/* ── Status ── */
async function checkStatus() {
  const dot = document.getElementById('ksDot');
  const txt = document.getElementById('ksTxt');
  const el  = document.getElementById('keyStatus');
  try {
    const res = await fetch(API() + '/api/status', { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();

    // Show which keys are missing so user knows exactly what to fix
    if (d.missing_keys && d.missing_keys.length > 0) {
      dot.className = 'ks-dot off';
      txt.textContent = 'Missing: ' + d.missing_keys.join(', ') + ' — open ⚙ Settings';
      el.className = 'key-status err';
      return;
    }

    const ok    = d.nvidia || d.groq;
    const parts = [];
    if (d.nvidia)       parts.push('NVIDIA');
    if (d.nvidia_judge) parts.push('JUDGE');
    if (d.groq)         parts.push('GROQ');
    dot.className = 'ks-dot' + (ok ? ' on' : ' off');
    txt.textContent = ok ? parts.join(' · ') + ' ✓' : 'No API keys set — open ⚙ Settings';
    el.className = 'key-status' + (ok ? ' ok' : ' err');
  } catch (err) {
    dot.className = 'ks-dot off';
    const isOffline = err.name === 'TypeError' || err.name === 'AbortError';
    txt.textContent = isOffline
      ? 'Server waking up… try again in 30s'
      : 'Server offline — check Render dashboard';
    el.className = 'key-status err';
  }
}

/* ── Nav ── */
function goView(id, btn) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + id).classList.add('active');
  document.querySelectorAll('.nb').forEach(n => n.classList.remove('active'));
  if (btn) btn.classList.add('active');
  if (id === 'history') renderHistory();
}
function clearPrompt() {
  document.getElementById('promptInput').value = '';
  document.getElementById('charCnt').textContent = '0';
}

/* ── Phase ── */
function setPhase(n, state, sub) {
  const item = document.getElementById('pi' + n);
  const num  = document.getElementById('pb' + n);
  const s    = document.getElementById('ps' + n);
  item.className = 'ps-item' + (state ? ' ' + state : '');
  if (state === 'run')       num.innerHTML = '<span class="sp">⟳</span>';
  else if (state === 'done') num.textContent = '✓';
  else                       num.textContent = n < 10 ? '0' + n : n;
  if (s && sub) s.textContent = sub;
}

/* ── Run ── */
async function runArena() {
  const prompt = document.getElementById('promptInput').value.trim();
  if (!prompt) { alert('Enter a prompt to start the arena!'); return; }

  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="sp">⟳</span> <span class="run-label">Running...</span>';

  document.getElementById('results').style.display = 'none';
  document.getElementById('errBox').style.display  = 'none';

  const bar = document.getElementById('phaseBar');
  bar.style.display = 'flex';
  setPhase(1, 'run', '4 models generating...'); setPhase(2, '', 'Waiting'); setPhase(3, '', 'Waiting');

  try {
    const t2 = setTimeout(() => setPhase(2, 'run', 'Gemma 7B judging...'), 10000);
    const t3 = setTimeout(() => setPhase(3, 'run', 'Synthesizing...'), 22000);

    const res = await fetch(API() + '/api/arena', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ prompt }),
    });
    clearTimeout(t2); clearTimeout(t3);

    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: 'Server error ' + res.status }));
      throw new Error(e.detail || 'Server error ' + res.status);
    }
    const data = await res.json();

    lastResult = { prompt, data, time: new Date() };
    runHistory.unshift(lastResult);
    setPhase(1, 'done', 'Complete'); setPhase(2, 'done', 'Complete'); setPhase(3, 'done', 'Complete');

    updateSidebarWins(data.models);
    renderResults(data);
    document.getElementById('results').style.display = 'block';
    setTimeout(() => document.getElementById('results').scrollIntoView({ behavior: 'smooth' }), 80);
  } catch (e) {
    setPhase(1, '', '—');
    const box = document.getElementById('errBox');
    box.style.display = 'block';

    // Give actionable error messages
    let msg = e.message || 'Unknown error';
    if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('fetch')) {
      msg = 'Cannot reach server. It may be waking up (Render free tier sleeps). Wait 30s and try again, or check your Render dashboard.';
    } else if (msg.includes('API_KEY') || msg.includes('not configured')) {
      msg = msg + ' — Go to Render Dashboard → Environment and add the missing key, then redeploy.';
    }
    box.innerHTML = '⚠ ' + escHtml(msg);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="run-icon">⚡</span><span class="run-label">Run Arena</span>';
    checkStatus(); // Refresh status after each run
  }
}

function updateSidebarWins(models) {
  const winner = models.find(m => m.rank === 1);
  if (!winner) return;
  const el = document.getElementById('w-' + winner.id);
  if (el) {
    const cur = parseInt(el.dataset.wins || '0') + 1;
    el.dataset.wins = cur;
    el.textContent  = cur + 'W';
    el.style.color  = 'var(--acc)';
  }
}

/* ── Render ── */
const MEDALS = ['🥇','🥈','🥉','4️⃣'];
const RB     = ['rb1','rb2','rb3','rb4'];

function renderResults(data) {
  renderCards(data.models);
  renderLeaderboard(data.models);
  renderChampion(data);
}

function renderCards(models) {
  document.getElementById('respGrid').innerHTML = models.map((m, i) => `
    <div class="rcard">
      <div class="rc-top">
        <div class="rc-name-row">
          <span class="rc-dot" style="background:${m.color}"></span>
          <span class="rc-name">${escHtml(m.name)}</span>
        </div>
        <span class="rbadge ${RB[i]}">${MEDALS[i]} #${m.rank}</span>
      </div>
      <div class="rc-track"><div class="rc-fill" style="background:${m.color};width:${(m.scores.total/10)*100}%"></div></div>
      <div class="rc-body">${escHtml(m.response)}</div>
      ${m.error ? `<div class="rc-err">⚠ ${escHtml(m.error)}</div>` : ''}
      <div class="rc-scores">
        <span class="schip">Acc <span class="sv">${m.scores.accuracy}</span></span>
        <span class="schip">Clar <span class="sv">${m.scores.clarity}</span></span>
        <span class="schip">Depth <span class="sv">${m.scores.depth}</span></span>
        <span class="schip">Creat <span class="sv">${m.scores.creativity}</span></span>
        <span class="ttl-chip">${m.scores.total}/10</span>
      </div>
    </div>`).join('');
}

function renderLeaderboard(models) {
  const rows = models.map((m, i) => `
    <div class="lb-row${i === 0 ? ' winner' : ''}">
      <div class="lb-rank">${MEDALS[i]}</div>
      <div class="lb-model"><span class="rc-dot" style="background:${m.color}"></span>${escHtml(m.name)}</div>
      <div class="lb-sc">${m.scores.accuracy}</div>
      <div class="lb-sc">${m.scores.clarity}</div>
      <div class="lb-sc">${m.scores.depth}</div>
      <div class="lb-sc">${m.scores.creativity}</div>
      <div class="lb-sc tot">${m.scores.total}</div>
    </div>`).join('');
  document.getElementById('rankTbl').innerHTML = `
    <div class="lb-row lb-hd">
      <div>#</div><div>Model</div>
      <div style="text-align:center">Acc</div>
      <div style="text-align:center">Clar</div>
      <div style="text-align:center">Depth</div>
      <div style="text-align:center">Creat</div>
      <div style="text-align:center">Total</div>
    </div>${rows}`;
}

function renderChampion(data) {
  const w = data.models.find(m => m.id === data.winner);
  document.getElementById('champWinner').innerHTML = w ? `
    <span class="rc-dot" style="background:${w.color}"></span>
    <span style="color:var(--acc);font-family:'DM Mono',monospace;font-size:.78rem;font-weight:500">${escHtml(w.name)}</span>
    <span style="color:var(--muted);font-family:'DM Mono',monospace;font-size:.68rem">scored ${w.scores.total}/10 · won this round</span>` : '';
  document.getElementById('champBody').textContent = data.synthesis;
  document.getElementById('champMeta').innerHTML = `
    <span>🏆 ${w ? escHtml(w.name) : data.winner} — ${w ? w.scores.total : '?'}/10</span>
    <span>⚖️ Judged by Gemma 7B</span>
    <span>✨ Synthesized from ${data.models.length} responses</span>
    <span>🚀 NVIDIA NIM + Groq</span>`;
}

function copyAnswer() {
  if (!lastResult) return;
  navigator.clipboard.writeText(lastResult.data.synthesis).then(() => {
    const b = document.getElementById('copyBtn');
    b.textContent = '✅ Copied!';
    setTimeout(() => b.innerHTML = '⧉ Copy', 2000);
  });
}

/* ── History ── */
function renderHistory() {
  const el = document.getElementById('histList');
  if (!runHistory.length) {
    el.innerHTML = '<div class="empty-st">No battles yet — enter the arena ⚡</div>';
    return;
  }
  el.innerHTML = runHistory.map((h, i) => `
    <div class="hist-item" onclick="loadHistory(${i})">
      <div class="hist-q">${escHtml(h.prompt)}</div>
      <div class="hist-m">${h.time.toLocaleTimeString()} • 🏆 ${escHtml(h.data.models[0]?.name || h.data.winner)} • ${h.data.models[0]?.scores.total || '?'}/10</div>
    </div>`).join('');
}

function loadHistory(i) {
  lastResult = runHistory[i];
  document.getElementById('promptInput').value = lastResult.prompt;
  document.getElementById('charCnt').textContent = lastResult.prompt.length;
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-arena').classList.add('active');
  document.querySelectorAll('.nb').forEach((n, j) => n.classList.toggle('active', j === 0));
  document.getElementById('phaseBar').style.display = 'flex';
  setPhase(1, 'done', 'Complete'); setPhase(2, 'done', 'Complete'); setPhase(3, 'done', 'Complete');
  renderResults(lastResult.data);
  document.getElementById('results').style.display = 'block';
}

/* ── Settings ── */
function openSettings()  { document.getElementById('settingsModal').classList.add('open'); checkStatus(); }
function closeSettings() { document.getElementById('settingsModal').classList.remove('open'); }
function toggleVis(id, btn) {
  const inp = document.getElementById(id);
  inp.type  = inp.type === 'password' ? 'text' : 'password';
  btn.textContent = inp.type === 'password' ? '👁' : '🙈';
}
async function saveKeys() {
  const msg = document.getElementById('save-msg');
  msg.style.display = 'none';
  const payload = {
    admin_password:   document.getElementById('inp-adminpw').value,
    nvidia_api_key:   document.getElementById('inp-nvidiakey').value  || null,
    nvidia_api_key_2: document.getElementById('inp-nvidiakey2').value || null,
    groq_api_key:     document.getElementById('inp-groqkey').value    || null,
  };
  if (!payload.admin_password) { showMsg(msg, 'err', '✗ Admin password required'); return; }
  try {
    const res = await fetch(API() + '/api/admin/keys', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || 'Failed');
    showMsg(msg, 'ok', '✓ Saved: ' + (d.updated || []).join(' · '));
    setTimeout(checkStatus, 400);
  } catch (e) { showMsg(msg, 'err', '✗ ' + e.message); }
}
function showMsg(el, cls, txt) {
  el.style.display = 'block';
  el.className     = 'save-msg ' + cls;
  el.textContent   = txt;
}
function escHtml(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}