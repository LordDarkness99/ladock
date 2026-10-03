/**
 * LaDock Monitor - Frontend Application Logic
 * Reactive UI with live polling, shortcuts generator, and modal controllers
 */

(function () {
  'use strict';

  // --- State ---
  let state = {
    data: null,
    filterText: '',
    filterMode: 'all', // 'all', 'microservices', 'monolith'
    pollIntervalMs: 5000,
    pollTimer: null,
    isRefreshing: false,
    
    // Active Log Modal
    activeLogContainer: null,
    logPollTimer: null,
    logSearchText: '',

    // Active Shortcuts Modal
    activeShortcutContainer: null
  };

  // --- DOM Elements ---
  const el = {
    filterInput: document.getElementById('filter-input'),
    segButtons: document.querySelectorAll('.seg-btn'),
    refreshSelect: document.getElementById('refresh-interval-select'),
    btnManualRefresh: document.getElementById('btn-manual-refresh'),
    refreshIcon: document.getElementById('refresh-icon'),
    globalStatusPill: document.getElementById('global-status-pill'),
    globalStatusText: document.getElementById('global-status-text'),
    
    // Summary
    statTotalProjects: document.getElementById('stat-total-projects'),
    statMicroCount: document.getElementById('stat-micro-count'),
    statMonoCount: document.getElementById('stat-mono-count'),
    statTotalContainers: document.getElementById('stat-total-containers'),
    statBadgeRunning: document.getElementById('stat-badge-running'),
    statRunningCount: document.getElementById('stat-running-count'),
    statStoppedCount: document.getElementById('stat-stopped-count'),
    statAvgCpu: document.getElementById('stat-avg-cpu'),
    statCpuBar: document.getElementById('stat-cpu-bar'),
    statTotalMem: document.getElementById('stat-total-mem'),
    statMemDetail: document.getElementById('stat-mem-detail'),

    // Quick links
    quickLinksContainer: document.getElementById('quick-links-container'),

    // Projects list
    projectsContainer: document.getElementById('projects-container'),
    lastUpdatedText: document.getElementById('last-updated-text'),

    // Modals
    logModal: document.getElementById('log-modal'),
    logModalTitle: document.getElementById('log-modal-title'),
    logContentPre: document.getElementById('log-content-pre'),
    logSearchInput: document.getElementById('log-search-input'),
    logAutoScroll: document.getElementById('log-auto-scroll'),
    logTailSelect: document.getElementById('log-tail-select'),
    btnCloseLogModal: document.getElementById('btn-close-log-modal'),
    btnCopyLogs: document.getElementById('btn-copy-logs'),

    shortcutsModal: document.getElementById('shortcuts-modal'),
    shortcutsModalTitle: document.getElementById('shortcuts-modal-title'),
    shortcutsModalDesc: document.getElementById('shortcuts-modal-desc'),
    shortcutsCommandList: document.getElementById('shortcuts-command-list'),
    btnCloseShortcutsModal: document.getElementById('btn-close-shortcuts-modal'),

    toastContainer: document.getElementById('toast-container')
  };

  // --- Toast Function ---
  function showToast(message, type = 'normal') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    if (type === 'success') {
      icon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    } else if (type === 'error') {
      icon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
    }
    
    toast.innerHTML = `${icon}<span>${message}</span>`;
    el.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.2s ease';
      setTimeout(() => toast.remove(), 200);
    }, 2800);
  }

  // --- Copy to Clipboard Utility ---
  function copyText(text, label = 'Teks') {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        showToast(`${label} disalin ke clipboard!`, 'success');
      }).catch(() => fallbackCopy(text, label));
    } else {
      fallbackCopy(text, label);
    }
  }

  function fallbackCopy(text, label) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
      showToast(`${label} disalin!`, 'success');
    } catch (e) {
      showToast(`Gagal menyalin ${label}`, 'error');
    }
    document.body.removeChild(textarea);
  }

  // --- Fetch Cluster Status ---
  async function fetchClusterStatus() {
    if (state.isRefreshing) return;
    state.isRefreshing = true;
    el.refreshIcon.classList.add('rotating');

    try {
      const resp = await fetch('/api/status');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.data = data;
      renderUI();
      
      el.globalStatusText.textContent = `${data.summary.running} Layanan Online`;
      el.globalStatusPill.style.display = 'inline-flex';
    } catch (err) {
      console.error("Gagal refresh data cluster:", err);
      el.globalStatusText.textContent = "Koneksi terputus / Docker down";
      el.globalStatusPill.classList.remove('status-indicator-pill');
      el.globalStatusPill.style.background = '#fef2f2';
      el.globalStatusPill.style.color = '#dc2626';
      el.globalStatusPill.style.borderColor = 'rgba(220, 38, 38, 0.3)';
    } finally {
      state.isRefreshing = false;
      el.refreshIcon.classList.remove('rotating');
      el.lastUpdatedText.textContent = `Diperbarui: ${new Date().toLocaleTimeString()}`;
    }
  }

  // --- Render Top Summary Cards ---
  function renderSummary(summary, projects) {
    if (!summary) return;

    el.statTotalProjects.textContent = summary.total_projects;
    el.statMicroCount.textContent = `${summary.microservices} Microservice`;
    el.statMonoCount.textContent = `${summary.monolith} Monolith`;

    el.statTotalContainers.textContent = summary.total_containers;
    el.statBadgeRunning.textContent = `${summary.running} Running`;
    el.statRunningCount.textContent = `${summary.running} aktif`;
    el.statStoppedCount.textContent = `${summary.stopped} berhenti`;

    // Kalkulasi total CPU & RAM dari semua container
    let totalCpu = 0;
    let totalMemUsageBytes = 0;
    let totalMemLimitBytes = 0;

    projects.forEach(p => {
      p.containers.forEach(c => {
        if (c.is_running && c.stats) {
          const cpuVal = parseFloat(c.stats.cpu.replace('%', '')) || 0;
          totalCpu += cpuVal;

          // Parse memory string e.g. "13.15MiB / 11.43GiB"
          if (c.stats.mem_usage && c.stats.mem_usage.includes('/')) {
            const parts = c.stats.mem_usage.split('/');
            totalMemUsageBytes += parseBytes(parts[0].trim());
            if (totalMemLimitBytes === 0) {
              totalMemLimitBytes = parseBytes(parts[1].trim());
            }
          }
        }
      });
    });

    el.statAvgCpu.textContent = `${totalCpu.toFixed(1)}%`;
    el.statCpuBar.style.width = `${Math.min(totalCpu, 100)}%`;

    if (totalMemUsageBytes > 0) {
      el.statTotalMem.textContent = formatBytes(totalMemUsageBytes);
      const memPerc = totalMemLimitBytes > 0 ? ((totalMemUsageBytes / totalMemLimitBytes) * 100).toFixed(1) : 0;
      el.statMemDetail.textContent = `dari ${formatBytes(totalMemLimitBytes)} (${memPerc}%)`;
    } else {
      el.statTotalMem.textContent = "-";
      el.statMemDetail.textContent = "Tidak ada beban memori aktif";
    }
  }

  function parseBytes(str) {
    const units = { 'b': 1, 'kib': 1024, 'kb': 1000, 'mib': 1024**2, 'mb': 1000**2, 'gib': 1024**3, 'gb': 1000**3 };
    const match = str.toLowerCase().match(/^([\d.]+)\s*([a-z]+)?$/);
    if (!match) return 0;
    const val = parseFloat(match[1]);
    const unit = match[2] || 'b';
    return val * (units[unit] || 1);
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  // --- Render Quick Links Strip ---
  function renderQuickLinks(projects) {
    el.quickLinksContainer.innerHTML = '';
    const links = [];

    projects.forEach(p => {
      // Gateway link if microservice
      if (p.gateway && p.gateway.url) {
        links.push({
          label: `${p.name} [Gateway]`,
          url: p.gateway.url,
          isGateway: true
        });
      }
      // Container web links
      p.containers.forEach(c => {
        if (c.primary_url && c.role !== 'gateway') {
          links.push({
            label: `${p.name} (${c.role === 'web_app' ? 'App' : c.service || c.name})`,
            url: c.primary_url,
            isGateway: false
          });
        }
      });
    });

    if (links.length === 0) {
      el.quickLinksContainer.innerHTML = `<span style="font-size: 0.78rem; color: var(--text-dim);">Belum ada port web aktif.</span>`;
      return;
    }

    links.forEach(item => {
      const chip = document.createElement('a');
      chip.className = 'quick-link-chip';
      chip.href = item.url;
      chip.target = '_blank';
      chip.rel = 'noopener noreferrer';
      chip.title = `Buka ${item.url} di tab baru`;

      const port = item.url.split(':').pop();
      chip.innerHTML = `
        <span class="chip-dot"></span>
        <span>${item.label}</span>
        <span class="chip-port">:${port}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
          <polyline points="15 3 21 3 21 9"></polyline>
          <line x1="10" y1="14" x2="21" y2="3"></line>
        </svg>
      `;
      el.quickLinksContainer.appendChild(chip);
    });
  }

  // --- Render Projects ---
  function renderProjects(projects) {
    el.projectsContainer.innerHTML = '';

    // Filter projects
    const filtered = projects.filter(p => {
      // Mode filter
      if (state.filterMode !== 'all' && p.mode !== state.filterMode) {
        return false;
      }
      // Text search
      if (state.filterText) {
        const q = state.filterText.toLowerCase();
        const matchProject = p.name.toLowerCase().includes(q) || p.work_dir.toLowerCase().includes(q);
        const matchContainers = p.containers.some(c => 
          c.name.toLowerCase().includes(q) || 
          c.image.toLowerCase().includes(q) ||
          c.ports.some(pt => String(pt.host_port).includes(q))
        );
        return matchProject || matchContainers;
      }
      return true;
    });

    if (filtered.length === 0) {
      el.projectsContainer.innerHTML = `
        <div style="text-align: center; padding: 3rem; background: var(--bg-surface); border-radius: var(--radius-lg); border: 1px solid var(--border-subtle);">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" stroke-width="1.5" style="margin-bottom: 0.5rem;">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <h3 style="font-size: 1.1rem; color: var(--text-main);">Tidak ada project yang cocok</h3>
          <p style="font-size: 0.8rem; color: var(--text-dim); margin-top: 0.25rem;">Coba ubah kata kunci pencarian atau filter mode.</p>
        </div>
      `;
      return;
    }

    filtered.forEach(project => {
      const card = document.createElement('div');
      card.className = 'project-card';
      card.dataset.projectName = project.name;

      // Header
      const isMicro = project.mode === 'microservices';
      const modeLabel = isMicro ? 'Microservices Cluster' : 'Monolith App';
      const modeClass = isMicro ? 'microservices' : 'monolith';

      // Total running in project
      const runningCount = project.containers.filter(c => c.is_running).length;

      // HTML building
      let html = `
        <div class="project-card-header">
          <div class="project-title-group">
            <h3 class="project-name">${escapeHtml(project.name)}</h3>
            <span class="badge-mode ${modeClass}">${modeLabel}</span>
            <span class="project-path" title="Klik untuk copy path" onclick="window.ladock.copy('${escapeJs(project.work_dir)}', 'Project Path')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
              </svg>
              <span>${escapeHtml(project.work_dir || '-')}</span>
            </span>
          </div>
          <div class="project-meta-pills">
            <span class="meta-pill"><strong>${runningCount}/${project.containers.length}</strong> Container Aktif</span>
          </div>
        </div>
      `;

      // Gateway Banner if Microservices
      if (isMicro && (project.gateway || project.routes.length > 0)) {
        html += `
          <div class="gateway-banner">
            <div class="gateway-banner-header">
              <div class="gateway-title-wrap">
                <svg class="gateway-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                  <polyline points="2 17 12 22 22 17"></polyline>
                  <polyline points="2 12 12 17 22 12"></polyline>
                </svg>
                <span class="gateway-title">Apache Reverse Proxy Gateway</span>
              </div>
              <div style="display: flex; gap: 0.5rem; align-items: center;">
                ${project.gateway && project.gateway.url ? `
                  <a href="${project.gateway.url}" target="_blank" class="btn-service primary" style="padding: 0.35rem 0.75rem;">
                    <span>Buka Gateway Dashboard</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                      <polyline points="15 3 21 3 21 9"></polyline>
                      <line x1="10" y1="14" x2="21" y2="3"></line>
                    </svg>
                  </a>
                ` : ''}
              </div>
            </div>
            ${project.routes && project.routes.length > 0 ? `
              <table class="gateway-routes-table">
                <thead>
                  <tr>
                    <th>Prefix Routing</th>
                    <th>Target Internal Container</th>
                    <th>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  ${project.routes.map(r => `
                    <tr>
                      <td><span class="route-badge">${escapeHtml(r.prefix)}</span></td>
                      <td><span class="target-badge">${escapeHtml(r.target)}</span></td>
                      <td>
                        ${project.gateway && project.gateway.url ? `
                          <a href="${project.gateway.url}${r.prefix.replace(/^\//, '')}" target="_blank" class="btn-service" style="padding: 0.2rem 0.5rem; font-size: 0.7rem;">
                            Test Endpoint ↗
                          </a>
                        ` : '-'}
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            ` : ''}
          </div>
        `;
      }

      // Services Grid
      html += `<div class="services-grid">`;
      project.containers.forEach(container => {
        html += renderServiceCard(container, project);
      });
      html += `</div>`;

      // Database Drawer (if credentials exist)
      if (project.credentials && project.credentials.DB_NAME) {
        html += renderDatabaseAccordion(project.credentials, project.name);
      }

      card.innerHTML = html;
      el.projectsContainer.appendChild(card);
    });
  }

  // --- Render Individual Service Card ---
  function renderServiceCard(c, project) {
    const isRunning = c.is_running;
    const statusText = isRunning ? 'Running' : (c.state || 'Stopped');
    const statusClass = isRunning ? 'running' : 'stopped';

    // Role Icon
    let roleClass = 'service';
    let roleIconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="2"></rect><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>`;
    
    if (c.role === 'web_app') {
      roleClass = 'web_app';
      roleIconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`;
    } else if (c.role === 'database') {
      roleClass = 'database';
      roleIconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>`;
    } else if (c.role === 'gateway') {
      roleClass = 'gateway';
      roleIconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>`;
    }

    // Ports list
    let portTagsHtml = '';
    if (c.ports && c.ports.length > 0) {
      // Unikkan host ports
      const seen = new Set();
      c.ports.forEach(p => {
        const key = `${p.host_port}:${p.container_port}`;
        if (!seen.has(key) && p.host_port) {
          seen.add(key);
          portTagsHtml += `<span class="port-tag">:${p.host_port} &rarr; ${p.container_port}</span>`;
        }
      });
    } else {
      portTagsHtml = `<span style="color: var(--text-dim); font-size: 0.72rem;">Internal Only</span>`;
    }

    // HTTP Probe
    let probeHtml = '';
    if (c.http_probe) {
      if (c.http_probe.online) {
        probeHtml = `<span class="probe-badge online" title="Status code & latency HTTP probe">● ${c.http_probe.code} OK • ${c.http_probe.latency_ms}ms</span>`;
      } else {
        probeHtml = `<span class="probe-badge offline" title="${c.http_probe.msg}">● Down</span>`;
      }
    } else if (c.health) {
      probeHtml = `<span class="probe-badge ${c.health === 'healthy' ? 'online' : 'offline'}">● ${c.health}</span>`;
    }

    // CPU & Memory percentages
    const cpuPerc = parseFloat((c.stats.cpu || '0%').replace('%', '')) || 0;
    const memPerc = parseFloat((c.stats.mem_perc || '0%').replace('%', '')) || 0;

    return `
      <div class="service-card" data-container-name="${escapeHtml(c.name)}">
        <div class="service-card-top">
          <div class="service-info">
            <div class="service-role-icon ${roleClass}">${roleIconSvg}</div>
            <div class="service-heading">
              <div class="service-name">${escapeHtml(c.name)}</div>
              <div class="service-sub">${escapeHtml(c.service || c.image)}</div>
            </div>
          </div>
          <span class="service-status-pill ${statusClass}">
            <span class="status-dot ${isRunning ? 'pulsing' : ''}" style="background-color: ${isRunning ? 'var(--status-success)' : 'var(--status-danger)'}"></span>
            ${statusText}
          </span>
        </div>

        <!-- Port & Health Probe -->
        <div class="service-port-strip">
          <div class="ports-list">${portTagsHtml}</div>
          <div>${probeHtml}</div>
        </div>

        <!-- Metrics Bars -->
        <div class="service-metrics">
          <div class="metric-item">
            <div class="metric-label-row">
              <span>CPU</span>
              <span class="metric-val">${c.stats.cpu || '0.00%'}</span>
            </div>
            <div class="metric-bar">
              <div class="metric-bar-fill" style="width: ${Math.min(cpuPerc, 100)}%;"></div>
            </div>
          </div>
          <div class="metric-item">
            <div class="metric-label-row">
              <span>RAM</span>
              <span class="metric-val">${c.stats.mem_perc || '0.00%'}</span>
            </div>
            <div class="metric-bar">
              <div class="metric-bar-fill" style="width: ${Math.min(memPerc, 100)}%; background: var(--accent-purple);"></div>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="service-actions">
          ${c.primary_url ? `
            <a href="${c.primary_url}" target="_blank" rel="noopener" class="btn-service primary" title="Buka website">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                <polyline points="15 3 21 3 21 9"></polyline>
                <line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
              <span>Buka Web</span>
            </a>
          ` : ''}

          <button class="btn-service" onclick="window.ladock.openLogs('${escapeJs(c.name)}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="4 17 10 11 4 5"></polyline>
              <line x1="12" y1="19" x2="20" y2="19"></line>
            </svg>
            <span>Logs</span>
          </button>

          <button class="btn-service" onclick="window.ladock.openShortcuts('${escapeJs(c.name)}', '${escapeJs(project.name)}', '${escapeJs(project.work_dir)}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
            </svg>
            <span>Shortcuts</span>
          </button>

          <button class="btn-service" onclick="window.ladock.triggerAction('${escapeJs(c.name)}', 'restart')" title="Restart Container">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
            </svg>
            <span>Restart</span>
          </button>

          ${isRunning ? `
            <button class="btn-service warning" onclick="window.ladock.triggerAction('${escapeJs(c.name)}', 'stop')" title="Stop Container">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="6" y="6" width="12" height="12"></rect>
              </svg>
              <span>Stop</span>
            </button>
          ` : `
            <button class="btn-service primary" onclick="window.ladock.triggerAction('${escapeJs(c.name)}', 'start')" title="Start Container">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
              <span>Start</span>
            </button>
          `}
        </div>
      </div>
    `;
  }

  // --- Render Database Credentials Accordion ---
  function renderDatabaseAccordion(creds, projectName) {
    const host = creds.DB_HOST || '127.0.0.1';
    const port = creds.DB_PORT || '3306';
    const name = creds.DB_NAME || '';
    const user = creds.DB_USER || '';
    const pass = creds.DB_PASS || '';

    const mysqlCliCmd = `mysql -h ${host} -P ${port} -u ${user} -p'${pass}' ${name}`;
    const envBlock = `DB_CONNECTION=mysql\nDB_HOST=${host}\nDB_PORT=${port}\nDB_DATABASE=${name}\nDB_USERNAME=${user}\nDB_PASSWORD=${pass}`;

    return `
      <div class="db-accordion">
        <div class="db-accordion-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'flex' : 'none'">
          <div class="db-accordion-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
              <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
              <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
            </svg>
            <span>Kredensial Database MySQL (${escapeHtml(name)})</span>
          </div>
          <span style="font-size: 0.75rem; color: var(--text-dim);">Klik untuk buka/tutup &darr;</span>
        </div>
        <div class="db-accordion-content" style="display: flex;">
          <div class="db-creds-grid">
            <div class="db-cred-item">
              <span class="cred-label">Host & Port</span>
              <div class="cred-val-wrap">
                <span class="cred-val">${host}:${port}</span>
                <button class="btn-cred-copy" onclick="window.ladock.copy('${host}:${port}', 'Host:Port')">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                </button>
              </div>
            </div>

            <div class="db-cred-item">
              <span class="cred-label">Database Name</span>
              <div class="cred-val-wrap">
                <span class="cred-val">${escapeHtml(name)}</span>
                <button class="btn-cred-copy" onclick="window.ladock.copy('${escapeJs(name)}', 'Database Name')">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                </button>
              </div>
            </div>

            <div class="db-cred-item">
              <span class="cred-label">User</span>
              <div class="cred-val-wrap">
                <span class="cred-val">${escapeHtml(user)}</span>
                <button class="btn-cred-copy" onclick="window.ladock.copy('${escapeJs(user)}', 'User')">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                </button>
              </div>
            </div>

            <div class="db-cred-item">
              <span class="cred-label">Password</span>
              <div class="cred-val-wrap">
                <span class="cred-val" id="pass-${escapeHtml(projectName)}">••••••••••••</span>
                <button class="btn-cred-copy" title="Tampilkan/Sembunyikan" onclick="
                  const el = document.getElementById('pass-${escapeJs(projectName)}');
                  el.textContent = el.textContent === '••••••••••••' ? '${escapeJs(pass)}' : '••••••••••••';
                ">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                </button>
                <button class="btn-cred-copy" onclick="window.ladock.copy('${escapeJs(pass)}', 'Password')">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                </button>
              </div>
            </div>
          </div>

          <div class="db-copy-actions">
            <button class="btn-service" onclick="window.ladock.copy('${escapeJs(mysqlCliCmd)}', 'MySQL Command')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              <span>1-Click Copy MySQL CLI Command</span>
            </button>
            <button class="btn-service" onclick="window.ladock.copy('${escapeJs(envBlock)}', '.env Block')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              <span>Copy .env Format</span>
            </button>
          </div>
        </div>
      </div>
    `;
  }

  // --- Render Master UI ---
  function renderUI() {
    if (!state.data) return;
    renderSummary(state.data.summary, state.data.projects);
    renderQuickLinks(state.data.projects);
    renderProjects(state.data.projects);
  }

  // --- Realtime Log Viewer Logic ---
  async function loadLogs() {
    if (!state.activeLogContainer) return;
    const tail = el.logTailSelect.value || '150';

    try {
      const resp = await fetch(`/api/container/logs?name=${encodeURIComponent(state.activeLogContainer)}&tail=${tail}`);
      if (!resp.ok) throw new Error("Gagal mengambil log");
      const res = await resp.json();
      
      let logs = res.logs || 'Belum ada log dari container ini.';
      if (state.logSearchText) {
        const lines = logs.split('\n');
        const filteredLines = lines.filter(l => l.toLowerCase().includes(state.logSearchText.toLowerCase()));
        logs = filteredLines.join('\n') || `(Tidak ada log yang cocok dengan filter: "${state.logSearchText}")`;
      }

      el.logContentPre.textContent = logs;

      if (el.logAutoScroll.checked) {
        el.logContentPre.scrollTop = el.logContentPre.scrollHeight;
      }
    } catch (e) {
      el.logContentPre.textContent = `Error: ${e.message}`;
    }
  }

  function openLogs(containerName) {
    state.activeLogContainer = containerName;
    el.logModalTitle.textContent = `Logs: ${containerName}`;
    el.logContentPre.textContent = 'Memuat log realtime...';
    el.logModal.style.display = 'flex';
    loadLogs();

    // Auto poll log
    if (state.logPollTimer) clearInterval(state.logPollTimer);
    state.logPollTimer = setInterval(loadLogs, 1500);
  }

  function closeLogs() {
    state.activeLogContainer = null;
    if (state.logPollTimer) clearInterval(state.logPollTimer);
    el.logModal.style.display = 'none';
  }

  // --- CLI Shortcuts Modal Logic ---
  function openShortcuts(containerName, projectName, workDir) {
    el.shortcutsModalTitle.textContent = `⚡ Shortcuts: ${containerName}`;
    el.shortcutsModalDesc.textContent = `Perintah siap pakai untuk container '${containerName}' (Project: ${projectName})`;
    
    // Find container info
    let container = null;
    if (state.data && state.data.projects) {
      for (const p of state.data.projects) {
        const found = p.containers.find(c => c.name === containerName);
        if (found) {
          container = found;
          break;
        }
      }
    }

    const commands = [
      {
        title: 'Buka Bash Terminal di Container',
        cmd: `docker exec -it ${containerName} bash`
      },
      {
        title: 'Lihat Live Log (Follow)',
        cmd: `docker logs -f --tail 100 ${containerName}`
      }
    ];

    // Jika ini Laravel app
    if (container && (container.role === 'web_app' || container.role === 'service')) {
      commands.push(
        { title: 'Artisan: Route List', cmd: `docker exec -it ${containerName} php artisan route:list` },
        { title: 'Artisan: Migrate Status', cmd: `docker exec -it ${containerName} php artisan migrate:status` },
        { title: 'Artisan: Clear All Cache', cmd: `docker exec -it ${containerName} php artisan optimize:clear` },
        { title: 'Artisan: Interactive Tinker CLI', cmd: `docker exec -it ${containerName} php artisan tinker` },
        { title: 'Composer: Dump Autoload', cmd: `docker exec -it ${containerName} composer dump-autoload` }
      );
    }

    // Docker Compose Shortcuts
    if (workDir) {
      commands.push(
        { title: 'Docker Compose: Status Services', cmd: `docker compose -f "${workDir}/.docker-compose.yml" ps` },
        { title: 'Docker Compose: Restart Container Ini', cmd: `docker compose -f "${workDir}/.docker-compose.yml" restart ${container ? container.service : containerName}` }
      );
    }

    // Render list
    el.shortcutsCommandList.innerHTML = commands.map(c => `
      <div class="shortcut-row">
        <span class="shortcut-title">${escapeHtml(c.title)}</span>
        <div class="shortcut-code-box">
          <code class="shortcut-code">${escapeHtml(c.cmd)}</code>
          <button class="btn-copy-code" onclick="window.ladock.copy('${escapeJs(c.cmd)}', 'Perintah')">
            Copy
          </button>
        </div>
      </div>
    `).join('');

    el.shortcutsModal.style.display = 'flex';
  }

  function closeShortcuts() {
    el.shortcutsModal.style.display = 'none';
  }

  // --- Container Actions (Restart, Stop, Start) ---
  async function triggerAction(containerName, action) {
    const actionLabel = action === 'restart' ? 'Restarting' : (action === 'stop' ? 'Menghentikan' : 'Menjalankan');
    showToast(`${actionLabel} container ${containerName}...`);

    try {
      const resp = await fetch('/api/container/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: containerName, action: action })
      });
      const res = await resp.json();
      if (res.success) {
        showToast(res.message, 'success');
        // Immediate fetch
        fetchClusterStatus();
      } else {
        showToast(`Gagal: ${res.error || 'Terjadi kesalahan'}`, 'error');
      }
    } catch (e) {
      showToast(`Error: ${e.message}`, 'error');
    }
  }

  // --- Polling Timer Control ---
  function setupPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    if (state.pollIntervalMs > 0) {
      state.pollTimer = setInterval(fetchClusterStatus, state.pollIntervalMs);
    }
  }

  // --- Helper Escapes ---
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function escapeJs(str) {
    if (!str) return '';
    return String(str)
      .replace(/\\/g, '\\\\')
      .replace(/'/g, "\\'")
      .replace(/"/g, '\\"')
      .replace(/\n/g, '\\n')
      .replace(/\r/g, '\\r');
  }

  // --- Event Listeners ---
  function initEventListeners() {
    // Search input
    el.filterInput.addEventListener('input', (e) => {
      state.filterText = e.target.value.trim();
      renderProjects(state.data ? state.data.projects : []);
    });

    // Segmented Mode filter buttons
    el.segButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        el.segButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.filterMode = btn.dataset.filter;
        renderProjects(state.data ? state.data.projects : []);
      });
    });

    // Refresh interval select
    el.refreshSelect.addEventListener('change', (e) => {
      state.pollIntervalMs = parseInt(e.target.value, 10);
      setupPolling();
      showToast(`Interval refresh diubah ke ${state.pollIntervalMs === 0 ? 'Jeda' : (state.pollIntervalMs / 1000) + ' detik'}`);
    });

    // Manual refresh button
    el.btnManualRefresh.addEventListener('click', () => {
      fetchClusterStatus();
    });

    // Log modal controls
    el.btnCloseLogModal.addEventListener('click', closeLogs);
    el.logModal.addEventListener('click', (e) => {
      if (e.target === el.logModal) closeLogs();
    });

    el.logTailSelect.addEventListener('change', loadLogs);
    el.logSearchInput.addEventListener('input', (e) => {
      state.logSearchText = e.target.value.trim();
      loadLogs();
    });

    el.btnCopyLogs.addEventListener('click', () => {
      copyText(el.logContentPre.textContent, 'Log Container');
    });

    // Shortcuts modal controls
    el.btnCloseShortcutsModal.addEventListener('click', closeShortcuts);
    el.shortcutsModal.addEventListener('click', (e) => {
      if (e.target === el.shortcutsModal) closeShortcuts();
    });

    // Keyboard ESC to close modals
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeLogs();
        closeShortcuts();
      }
    });
  }

  // --- Expose API to window for inline onclick ---
  window.ladock = {
    copy: copyText,
    openLogs: openLogs,
    openShortcuts: openShortcuts,
    triggerAction: triggerAction
  };

  // --- Initial Start ---
  initEventListeners();
  fetchClusterStatus();
  setupPolling();

})();
