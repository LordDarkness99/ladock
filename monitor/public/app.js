/**
 * LaDock Control Center & Monitor v3.0 - Frontend Logic
 */

let activeDeployEventSource = null;
let activeLogEventSource = null;
let globalClusterData = null;

// Tab Switching
function switchTab(tabId) {
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

  const tabBtn = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
  const pane = document.getElementById(tabId);
  if (tabBtn) tabBtn.classList.add('active');
  if (pane) pane.classList.add('active');

  // Load specific data on tab switch
  if (tabId === 'tab-apps') loadDeployedApps();
  if (tabId === 'tab-database') loadDbFiles();
  if (tabId === 'tab-config') { loadConfigData(); loadSummariesData(); }
  if (tabId === 'tab-logs') { loadContainerSelect(); loadDeployHistory(); }
}

document.querySelectorAll('.nav-tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.getAttribute('data-tab')));
});

// Toast Helper
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// Global API Fetch with Auth support
async function apiFetch(url, options = {}) {
  const token = localStorage.getItem('ladock_auth_token') || '';
  options.headers = options.headers || {};
  if (token) options.headers['x-auth-token'] = token;

  const res = await fetch(url, options);
  if (res.status === 401) {
    const inputToken = prompt('Akses membutuhkan token autentikasi LaDock (default: admin123):');
    if (inputToken) {
      localStorage.setItem('ladock_auth_token', inputToken);
      options.headers['x-auth-token'] = inputToken;
      return fetch(url, options);
    }
  }
  return res;
}

// 1. Cluster Status & Overview
async function fetchStatus() {
  try {
    const res = await apiFetch('/api/status');
    const data = await res.json();
    globalClusterData = data;

    // Update Central DB Banner
    const cdb = data.central_db || {};
    const cdbBadge = document.getElementById('central-db-badge');
    if (cdb.running) {
      cdbBadge.className = 'badge badge-success';
      cdbBadge.innerText = 'ONLINE / READY';
    } else {
      cdbBadge.className = 'badge badge-danger';
      cdbBadge.innerText = 'STOPPED';
    }
    document.getElementById('cdb-name').innerText = cdb.container_name || 'ladock_mysql';
    document.getElementById('cdb-port').innerText = cdb.port || '3310';
    document.getElementById('deploy-db-port').value = cdb.port || '3310';
    document.getElementById('cdb-vol').innerText = cdb.volume_name || 'ladock_db_central_data';
    document.getElementById('cdb-net').innerText = cdb.network || 'ladock_net';

    // Summary Cards
    const summary = data.summary || {};
    document.getElementById('stat-total-containers').innerText = summary.total || 0;
    document.getElementById('stat-running-count').innerText = `${summary.running || 0} aktif`;
    document.getElementById('stat-stopped-count').innerText = `${summary.stopped || 0} berhenti`;

    // CPU & RAM averages
    let totalCpu = 0;
    let cpuCount = 0;
    let memList = [];
    (data.containers || []).forEach(c => {
      const cpuVal = parseFloat(c.stats?.cpu?.replace('%', '') || 0);
      if (!isNaN(cpuVal)) { totalCpu += cpuVal; cpuCount++; }
      if (c.stats?.memory && c.stats.memory !== '0B / 0B') memList.push(c.stats.memory.split('/')[0].trim());
    });
    const avgCpu = cpuCount > 0 ? (totalCpu / cpuCount).toFixed(1) : '0.0';
    document.getElementById('stat-avg-cpu').innerText = `${avgCpu}%`;
    document.getElementById('stat-cpu-bar').style.width = `${Math.min(totalCpu, 100)}%`;
    document.getElementById('stat-total-mem').innerText = `${memList.length} containers`;
    document.getElementById('stat-mem-detail').innerText = memList.slice(0, 3).join(', ') || 'Idle';

    // Update Global Indicator Pill
    const pill = document.getElementById('global-status-pill');
    const pillText = document.getElementById('global-status-text');
    if (summary.running > 0) {
      pillText.innerText = `${summary.running} Container Berjalan`;
      pill.querySelector('.status-dot').className = 'status-dot online';
    } else {
      pillText.innerText = 'Semua Container Berhenti';
      pill.querySelector('.status-dot').className = 'status-dot offline';
    }

    // Quick links
    const quickLinksContainer = document.getElementById('quick-links-container');
    quickLinksContainer.innerHTML = '';
    (data.containers || []).filter(c => c.web_url).forEach(c => {
      const btn = document.createElement('a');
      btn.href = c.web_url;
      btn.target = '_blank';
      btn.className = 'shortcut-pill';
      btn.innerHTML = `<strong>${c.name}</strong> <span>${c.web_url}</span> ↗`;
      quickLinksContainer.appendChild(btn);
    });

    // Render Container Table
    renderContainersTable(data.containers || []);
  } catch (err) {
    console.error('Fetch status error:', err);
  }
}

function renderContainersTable(containers) {
  const tbody = document.getElementById('containers-tbody');
  const filter = (document.getElementById('filter-container-input')?.value || '').toLowerCase();
  tbody.innerHTML = '';

  const filtered = containers.filter(c => c.name.toLowerCase().includes(filter) || (c.image || '').toLowerCase().includes(filter));
  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center">Tidak ada container ditemukan.</td></tr>';
    return;
  }

  filtered.forEach(c => {
    const tr = document.createElement('tr');
    const portStr = (c.ports || []).map(p => `:${p.host_port}->${p.container_port}`).join(', ') || '-';
    tr.innerHTML = `
      <td><strong>${c.name}</strong></td>
      <td><span class="badge badge-subtle">${c.image || '-'}</span></td>
      <td><span class="status-pill ${c.is_running ? 'online' : 'offline'}">${c.state}</span></td>
      <td><code>${portStr}</code></td>
      <td><small>CPU: ${c.stats?.cpu || '-'} | RAM: ${c.stats?.memory || '-'}</small></td>
      <td>
        <button class="btn-sm btn-outline" onclick="containerAction('${c.name}', '${c.is_running ? 'restart' : 'start'}')">${c.is_running ? 'Restart' : 'Start'}</button>
        ${c.is_running ? `<button class="btn-sm btn-outline text-danger" onclick="containerAction('${c.name}', 'stop')">Stop</button>` : ''}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

document.getElementById('filter-container-input')?.addEventListener('input', () => {
  if (globalClusterData) renderContainersTable(globalClusterData.containers || []);
});

async function containerAction(name, action) {
  try {
    const res = await apiFetch('/api/container/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, action })
    });
    const d = await res.json();
    if (d.success) {
      showToast(d.message, 'success');
      fetchStatus();
    } else {
      showToast(d.error || 'Gagal menjalankan aksi', 'error');
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// 2. Deploy Hub
async function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const statusText = document.getElementById('upload-status-text');
  statusText.innerText = `Mengupload ${file.name}...`;

  const formData = new FormData();
  formData.append('archive', file);

  try {
    const res = await apiFetch('/api/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      document.getElementById('deploy-archive-path').value = data.file.path;
      statusText.innerText = `✓ Terupload: ${data.file.filename} (${(data.file.size / 1024 / 1024).toFixed(2)} MB)`;
      showToast('Arsip berhasil diupload ke server!', 'success');
    } else {
      statusText.innerText = `❌ Upload gagal: ${data.error}`;
      showToast(data.error, 'error');
    }
  } catch (err) {
    statusText.innerText = `❌ Error: ${err.message}`;
    showToast(err.message, 'error');
  }
}

async function checkDeployPort() {
  const input = document.getElementById('deploy-http-port');
  const status = document.getElementById('deploy-port-status');
  const button = document.getElementById('btn-check-port');
  const requestedPort = input.value.trim();
  const query = requestedPort ? `?start=${encodeURIComponent(requestedPort)}` : '';
  button.disabled = true;
  status.innerText = 'Memeriksa port yang tersedia...';

  try {
    const res = await apiFetch(`/api/ports/available${query}`);
    const data = await res.json();
    if (!res.ok || !data.ports?.length) throw new Error(data.error || 'Port kosong tidak ditemukan.');

    const selectedPort = data.ports[0];
    input.value = selectedPort;
    status.innerText = data.skipped?.length
      ? `Port ${data.skipped.join(', ')} terpakai/dikecualikan; port kosong berikutnya: ${selectedPort}.`
      : `Port ${selectedPort} tersedia.`;
    showToast(`Port ${selectedPort} tersedia.`, 'success');
  } catch (err) {
    status.innerText = `Pengecekan port gagal: ${err.message}`;
    showToast(err.message, 'error');
  } finally {
    button.disabled = false;
  }
}

async function handleDeploySubmit(event) {
  event.preventDefault();
  const archivePath = document.getElementById('deploy-archive-path').value.trim();
  const projectPath = document.getElementById('deploy-project-path').value.trim();
  const httpPort = document.getElementById('deploy-http-port').value.trim();
  const dbPort = document.getElementById('deploy-db-port').value.trim();
  const phpVer = document.getElementById('deploy-php-ver').value.trim();
  const mode = document.getElementById('deploy-mode').value;
  const memoryLimit = document.getElementById('deploy-memory-limit').value.trim();
  const forceImport = document.getElementById('deploy-force-import').checked;
  const skipImport = document.getElementById('deploy-skip-import').checked;

  if (!archivePath && !projectPath) {
    showToast('Harap masukkan path folder atau upload arsip!', 'error');
    return;
  }

  const payload = {
    archive: archivePath || undefined,
    path: projectPath || undefined,
    http_port: httpPort || 'auto',
    db_port: dbPort,
    php_version: phpVer || undefined,
    mode: mode || undefined,
    memory_limit: memoryLimit || undefined,
    force_import: forceImport,
    skip_import: skipImport
  };

  const term = document.getElementById('deploy-live-terminal');
  term.innerText = `[${new Date().toLocaleTimeString()}] Memulai deployment...\n`;
  document.getElementById('btn-submit-deploy').disabled = true;

  try {
    const res = await apiFetch('/api/deploy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (data.success && data.deploy_id) {
      showToast('Proses deploy dimulai, streaming log realtime...', 'info');
      startDeployStream(data.deploy_id);
    } else {
      term.innerText += `❌ Gagal memulai deploy: ${data.error}\n`;
      document.getElementById('btn-submit-deploy').disabled = false;
      showToast(data.error, 'error');
    }
  } catch (e) {
    term.innerText += `❌ Error: ${e.message}\n`;
    document.getElementById('btn-submit-deploy').disabled = false;
  }
}

function startDeployStream(deployId) {
  if (activeDeployEventSource) activeDeployEventSource.close();

  const term = document.getElementById('deploy-live-terminal');
  activeDeployEventSource = new EventSource(`/api/deploy/stream?deployId=${deployId}`);

  activeDeployEventSource.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data);
      if (parsed.message) {
        if (parsed.message.includes('[STREAM_END]')) {
          activeDeployEventSource.close();
          document.getElementById('btn-submit-deploy').disabled = false;
          showToast('Deployment selesai!', 'success');
          fetchStatus();
          loadDeployedApps();
        } else {
          term.innerText += parsed.message;
          term.scrollTop = term.scrollHeight;
        }
      }
    } catch (_) {
      term.innerText += event.data + '\n';
    }
  };

  activeDeployEventSource.onerror = () => {
    activeDeployEventSource.close();
    document.getElementById('btn-submit-deploy').disabled = false;
  };
}

function clearDeployLogs() {
  document.getElementById('deploy-live-terminal').innerText = 'Terminal dibersihkan.\n';
}

// 3. Deployed Apps Tab
async function loadDeployedApps() {
  const container = document.getElementById('apps-container');
  try {
    const res = await apiFetch('/api/apps');
    const data = await res.json();
    const apps = data.apps || [];

    document.getElementById('stat-total-projects').innerText = apps.length;
    document.getElementById('stat-project-breakdown').innerText = `${apps.length} project terdaftar`;

    if (apps.length === 0) {
      container.innerHTML = '<div class="text-center" style="grid-column: 1/-1;">Belum ada aplikasi yang di-deploy ke folder target. Gunakan Deploy Hub untuk memulai.</div>';
      return;
    }

    container.innerHTML = '';
    apps.forEach(app => {
      const stack = app.stack || {};
      const card = document.createElement('div');
      card.className = 'app-card';
      card.innerHTML = `
        <div>
          <div class="app-card-title">
            <span>📦 ${app.name}</span>
            <span class="badge badge-success">Live</span>
          </div>
          <div class="app-meta-row">
            <span class="badge-tag badge-lang">${stack.primary_language || 'PHP'} ${stack.runtime_version || ''}</span>
            <span class="badge-tag badge-frame">${stack.framework || 'Laravel'}</span>
            <span class="badge-tag">${stack.database || 'MySQL'}</span>
          </div>
          <p style="font-size: 0.78rem; color: var(--text-muted); word-break: break-all; margin-bottom: 0.5rem;">
            📁 <code>${app.path}</code>
          </p>
          <div style="font-size: 0.75rem; color: var(--text-dim); margin-bottom: 1rem;">
            Struktur: <strong>src/</strong>: ${app.has_src ? '✓' : '✗'} | <strong>docker-compose.yml</strong>: ${app.has_compose ? '✓' : '✗'}
          </div>
        </div>
        <div class="card-actions" style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <button class="btn-sm btn-primary" onclick="redeployApp('${app.path}')">Redeploy</button>
          <button class="btn-sm btn-outline text-danger" onclick="destroyApp('${app.path}')">Hapus / Destroy</button>
          <button class="btn-sm btn-outline" onclick="triggerDbBackup('${app.name}')">Backup DB</button>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = `<div class="text-danger">Gagal memuat aplikasi: ${err.message}</div>`;
  }
}

async function redeployApp(appPath) {
  if (!confirm(`Redeploy aplikasi di: ${appPath}?`)) return;
  try {
    const res = await apiFetch('/api/app/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_path: appPath, action: 'redeploy' })
    });
    const d = await res.json();
    if (d.success) { showToast(d.message, 'success'); fetchStatus(); }
    else showToast(d.error, 'error');
  } catch (e) { showToast(e.message, 'error'); }
}

async function destroyApp(appPath) {
  if (!confirm(`Hentikan dan bersihkan container untuk aplikasi di ${appPath}?`)) return;
  try {
    const res = await apiFetch('/api/app/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_path: appPath, action: 'destroy' })
    });
    const d = await res.json();
    if (d.success) { showToast(d.message, 'success'); fetchStatus(); loadDeployedApps(); }
    else showToast(d.error, 'error');
  } catch (e) { showToast(e.message, 'error'); }
}

// 4. Database Sentral Tab
async function loadDbFiles() {
  const container = document.getElementById('db-folders-list');
  try {
    const res = await apiFetch('/api/db/list');
    const data = await res.json();
    const folders = data.folders || [];

    if (folders.length === 0) {
      container.innerHTML = '<div class="text-center">Belum ada dump database di folder <code>mysql/db/</code>.</div>';
      return;
    }

    container.innerHTML = '';
    folders.forEach(f => {
      const wrap = document.createElement('div');
      wrap.style.marginBottom = '1rem';
      wrap.innerHTML = `
        <div style="font-weight: 700; font-size: 0.9rem; margin-bottom: 0.3rem;">
          📁 mysql/db/<strong>${f.app_name}</strong>/
        </div>
        <ul style="list-style: none; padding-left: 1rem; font-size: 0.8rem; font-family: var(--font-mono);">
          ${f.files.map(file => `<li>📄 ${file.name} <small>(${(file.size / 1024).toFixed(1)} KB)</small></li>`).join('')}
        </ul>
      `;
      container.appendChild(wrap);
    });
  } catch (err) {
    container.innerHTML = `<div class="text-danger">Gagal memuat daftar DB: ${err.message}</div>`;
  }
}

async function triggerDbBackup(appNameArg) {
  const appName = appNameArg || document.getElementById('backup-app-name').value.trim();
  if (!appName) return showToast('Masukkan nama aplikasi!', 'error');

  showToast(`Memulai backup database untuk ${appName}...`, 'info');
  try {
    const res = await apiFetch('/api/db/dump', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_name: appName })
    });
    const d = await res.json();
    if (d.success) {
      showToast(`Dump ${appName} berhasil disimpan di mysql/db/${appName}/!`, 'success');
      loadDbFiles();
    } else {
      showToast(d.error || 'Backup gagal', 'error');
    }
  } catch (e) { showToast(e.message, 'error'); }
}

async function triggerDbRestore() {
  const appName = document.getElementById('restore-app-name').value.trim();
  if (!appName) return showToast('Masukkan nama aplikasi!', 'error');
  if (!confirm(`Restore database ${appName} dari mysql/db/${appName}/data.sql?`)) return;

  showToast(`Memulai restore database ${appName}...`, 'info');
  try {
    const res = await apiFetch('/api/db/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_name: appName })
    });
    const d = await res.json();
    if (d.success) {
      showToast(`Restore ${appName} berhasil!`, 'success');
    } else {
      showToast(d.error || 'Restore gagal', 'error');
    }
  } catch (e) { showToast(e.message, 'error'); }
}

// 5. Config Tab
async function loadConfigData() {
  try {
    const res = await apiFetch('/api/config');
    const data = await res.json();
    document.getElementById('config-json-editor').value = data.config || '';
    document.getElementById('env-editor').value = data.env || '';
  } catch (e) { console.error(e); }
}

async function saveConfig() {
  const newConfig = document.getElementById('config-json-editor').value;
  try {
    const res = await apiFetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: newConfig })
    });
    const d = await res.json();
    if (d.success) showToast('config.json berhasil disimpan!', 'success');
    else showToast(d.error, 'error');
  } catch (e) { showToast(e.message, 'error'); }
}

async function saveEnv() {
  const newEnv = document.getElementById('env-editor').value;
  try {
    const res = await apiFetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ env: newEnv })
    });
    const d = await res.json();
    if (d.success) showToast('.ladock_db.env berhasil disimpan!', 'success');
    else showToast(d.error, 'error');
  } catch (e) { showToast(e.message, 'error'); }
}

async function loadSummariesData() {
  try {
    const res = await apiFetch('/api/summaries');
    const data = await res.json();
    document.getElementById('summaries-preview').innerText = JSON.stringify(data, null, 2);
  } catch (e) { console.error(e); }
}

// 6. Logs & Riwayat Tab
function loadContainerSelect() {
  const sel = document.getElementById('log-container-select');
  sel.innerHTML = '<option value="">-- Pilih Container --</option>';
  if (globalClusterData && globalClusterData.containers) {
    globalClusterData.containers.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.name;
      opt.innerText = `${c.name} (${c.state})`;
      sel.appendChild(opt);
    });
  }
}

function startContainerLogStream() {
  const cName = document.getElementById('log-container-select').value;
  const pre = document.getElementById('live-container-logs');
  if (!cName) { pre.innerText = 'Pilih container untuk melihat streaming logs...'; return; }

  if (activeLogEventSource) activeLogEventSource.close();
  pre.innerText = `Menghubungkan ke logs container ${cName}...\n`;

  activeLogEventSource = new EventSource(`/api/logs/stream?container=${cName}&tail=100`);
  activeLogEventSource.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data);
      if (parsed.log) {
        pre.innerText += parsed.log;
        pre.scrollTop = pre.scrollHeight;
      }
    } catch (_) {
      pre.innerText += event.data + '\n';
    }
  };
}

function filterLogs() {
  const q = document.getElementById('log-search-input').value.toLowerCase();
  const pre = document.getElementById('live-container-logs');
  const lines = pre.innerText.split('\n');
  if (!q) return;
  // Visual search feedback can be extended
}

function downloadSelectedLog() {
  const cName = document.getElementById('log-container-select').value;
  if (!cName) return showToast('Pilih container terlebih dahulu', 'error');
  window.open(`/api/logs/download?container=${cName}`, '_blank');
}

async function loadDeployHistory() {
  const tbody = document.getElementById('deploy-history-tbody');
  try {
    const res = await fetch('/api/deploy/history');
    const d = await res.json();
    const history = d.history || [];

    if (history.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center">Belum ada riwayat deployment.</td></tr>';
      return;
    }

    tbody.innerHTML = '';
    history.forEach(h => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><small>${new Date(h.started_at).toLocaleTimeString()}</small></td>
        <td><code>${h.args || 'deploy'}</code></td>
        <td><span class="badge ${h.status === 'success' ? 'badge-success' : 'badge-danger'}">${h.status}</span></td>
        <td><button class="btn-sm btn-outline" onclick="viewHistoricalLog('${h.id}')">Lihat Log</button></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) { console.error(e); }
}

function viewHistoricalLog(deployId) {
  switchTab('tab-deploy');
  startDeployStream(deployId);
}

// Inisialisasi & Polling Interval
document.getElementById('btn-manual-refresh')?.addEventListener('click', () => {
  fetchStatus();
  loadDeployedApps();
});

fetchStatus();
loadDeployedApps();
checkDeployPort();
setInterval(fetchStatus, 5000);
