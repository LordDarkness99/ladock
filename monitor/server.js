#!/usr/bin/env node
/**
 * LaDock Control Center & Monitoring Server (Node.js)
 * Menyediakan REST API, Server-Sent Events (SSE) untuk streaming logs & deploy,
 * kontrol container, upload arsip, manajemen DB sentral, dan konfigurasi.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');
const url = require('url');

const ROOT_DIR = path.resolve(__dirname, '..');
const PUBLIC_DIR = path.join(__dirname, 'public');
const CONFIG_FILE = path.join(ROOT_DIR, 'config.json');
const ENV_FILE = path.join(ROOT_DIR, '.ladock_db.env');
const SUMMARIES_FILE = path.join(ROOT_DIR, '.documentapps', 'summaries.json');
const UPLOADS_DIR = path.join(ROOT_DIR, 'uploads');
const LOGS_DIR = path.join(ROOT_DIR, 'logs');

// Pastikan direktori uploads dan logs ada
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR, { recursive: true });
if (!fs.existsSync(LOGS_DIR)) fs.mkdirSync(LOGS_DIR, { recursive: true });

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
    }
  } catch (e) {
    console.error('Error loading config.json:', e);
  }
  return {
    deploy_root: './docker/apps',
    central_db: {
      container_name: 'ladock_mysql',
      port: 3308,
      volume_name: 'ladock_db_central_data'
    },
    dashboard: { port: 9090, auth_enabled: false, auth_token: 'admin123' }
  };
}

let config = loadConfig();
const PORT = process.env.PORT || (config.dashboard && config.dashboard.port) || 9090;

// Riwayat Deployment In-Memory + Persisted
const deployHistory = [];
const activeStreams = new Map();

// Helper Response JSON
function sendJSON(res, data, statusCode = 200) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, x-auth-token',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Cache-Control': 'no-cache'
  });
  res.end(JSON.stringify(data));
}

function sendError(res, message, statusCode = 400) {
  sendJSON(res, { success: false, error: message }, statusCode);
}

// Helper Autentikasi Minimal
function checkAuth(req) {
  config = loadConfig();
  if (!config.dashboard || !config.dashboard.auth_enabled) return true;
  const token = req.headers['x-auth-token'] || req.headers['authorization']?.replace('Bearer ', '');
  return token === config.dashboard.auth_token;
}

// Ambil Stats Docker CPU & RAM
function getDockerStats() {
  try {
    const raw = execSync('docker stats --no-stream --format "{{json .}}"', { timeout: 4000 }).toString();
    const stats = {};
    raw.trim().split('\n').forEach(line => {
      if (line) {
        try {
          const s = JSON.parse(line);
          stats[s.Name] = s;
          stats[s.ID] = s;
        } catch (_) {}
      }
    });
    return stats;
  } catch (_) {
    return {};
  }
}

// Kumpulkan Data Status Cluster & Central DB
function getClusterStatus() {
  const cfg = loadConfig();
  const dbContainerName = (cfg.central_db && cfg.central_db.container_name) || 'ladock_mysql';
  const statsMap = getDockerStats();

  let containers = [];
  try {
    const names = execSync('docker ps -a --format "{{.Names}}"', { timeout: 4000 }).toString().trim().split('\n').filter(Boolean);
    if (names.length > 0) {
      const inspectRaw = execSync(`docker inspect ${names.join(' ')}`, { timeout: 6000 }).toString();
      const rawContainers = JSON.parse(inspectRaw);

      containers = rawContainers.map(c => {
        const cName = c.Name.replace(/^\//, '');
        const state = c.State?.Status || 'unknown';
        const isRunning = state === 'running';
        const ports = [];
        const portBindings = c.NetworkSettings?.Ports || {};
        let webUrl = null;
        let dbPort = null;

        for (const [cp, bindings] of Object.entries(portBindings)) {
          if (bindings && bindings.length > 0) {
            bindings.forEach(b => {
              const hPort = b.HostPort;
              ports.push({ container_port: cp, host_port: hPort });
              if (cp.startsWith('80') && !webUrl && hPort) webUrl = `http://localhost:${hPort}`;
              if (cp.startsWith('3306')) dbPort = hPort;
            });
          }
        }

        const stat = statsMap[cName] || {};
        return {
          id: c.Id.substring(0, 12),
          name: cName,
          state,
          is_running: isRunning,
          image: c.Config?.Image,
          ports,
          web_url: webUrl,
          db_port: dbPort,
          stats: {
            cpu: stat.CPUPerc || '0.00%',
            memory: stat.MemUsage || '0B / 0B',
            mem_perc: stat.MemPerc || '0.00%'
          }
        };
      });
    }
  } catch (err) {
    console.error('Error inspecting docker containers:', err.message);
  }

  // Cek Central DB
  const centralDbContainer = containers.find(c => c.name === dbContainerName);
  const centralDbStatus = {
    container_name: dbContainerName,
    running: centralDbContainer ? centralDbContainer.is_running : false,
    port: (cfg.central_db && cfg.central_db.port) || 3308,
    volume_name: (cfg.central_db && cfg.central_db.volume_name) || 'ladock_db_central_data',
    network: (cfg.central_db && cfg.central_db.network) || 'ladock_net'
  };

  return {
    central_db: centralDbStatus,
    summary: {
      total: containers.length,
      running: containers.filter(c => c.is_running).length,
      stopped: containers.filter(c => !c.is_running).length
    },
    containers
  };
}

// Scan Aplikasi yang Ter-deploy
function getDeployedApps() {
  const cfg = loadConfig();
  const deployRoot = path.resolve(ROOT_DIR, cfg.deploy_root || './docker');
  const apps = [];

  const checkDir = (dirPath) => {
    if (!fs.existsSync(dirPath)) return;
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    for (const ent of entries) {
      if (ent.isDirectory()) {
        const appDir = path.join(dirPath, ent.name);
        const stackJsonPath = path.join(appDir, 'stack.json');
        const composePath = path.join(appDir, 'docker-compose.yml');
        const legacyComposePath = path.join(appDir, '.docker-compose-app.yml');

        if (fs.existsSync(stackJsonPath) || fs.existsSync(composePath) || fs.existsSync(legacyComposePath)) {
          let stackData = {};
          if (fs.existsSync(stackJsonPath)) {
            try { stackData = JSON.parse(fs.readFileSync(stackJsonPath, 'utf8')); } catch (_) {}
          }

          let creds = {};
          const credsFile = path.join(appDir, '.credentials.env');
          if (fs.existsSync(credsFile)) {
            fs.readFileSync(credsFile, 'utf8').split('\n').forEach(line => {
              if (line && line.includes('=')) {
                const [k, v] = line.split('=');
                creds[k.trim()] = v.trim();
              }
            });
          }

          apps.push({
            name: ent.name,
            path: appDir,
            has_src: fs.existsSync(path.join(appDir, 'src')),
            has_compose: fs.existsSync(composePath),
            stack: stackData,
            credentials: creds,
            db_folder: path.join(ROOT_DIR, 'mysql', 'db', ent.name)
          });
        }
      }
    }
  };

  checkDir(deployRoot);
  return apps;
}

// Multipart Form Parser Sederhana untuk Upload File
function parseMultipart(req, uploadDir) {
  return new Promise((resolve, reject) => {
    const boundary = req.headers['content-type']?.split('boundary=')[1];
    if (!boundary) return reject(new Error('No boundary in multipart form'));

    const chunks = [];
    req.on('data', chunk => chunks.push(chunk));
    req.on('end', () => {
      const buffer = Buffer.concat(chunks);
      const boundaryBuf = Buffer.from('--' + boundary);
      let startIdx = buffer.indexOf(boundaryBuf);

      while (startIdx !== -1) {
        const nextIdx = buffer.indexOf(boundaryBuf, startIdx + boundaryBuf.length);
        if (nextIdx === -1) break;

        const part = buffer.subarray(startIdx + boundaryBuf.length, nextIdx);
        const headerEnd = part.indexOf(Buffer.from('\r\n\r\n'));
        if (headerEnd !== -1) {
          const headersStr = part.subarray(0, headerEnd).toString('utf8');
          const fileBody = part.subarray(headerEnd + 4, part.length - 2);

          const fnMatch = headersStr.match(/filename="([^"]+)"/);
          if (fnMatch) {
            const rawFilename = fnMatch[1];
            const safeFilename = path.basename(rawFilename).replace(/[^a-zA-Z0-9_\.-]/g, '_');
            const destPath = path.join(uploadDir, safeFilename);
            fs.writeFileSync(destPath, fileBody);
            return resolve({ filename: safeFilename, path: destPath, size: fileBody.length });
          }
        }
        startIdx = nextIdx;
      }
      reject(new Error('File tidak ditemukan dalam form data.'));
    });
    req.on('error', reject);
  });
}

// HTTP Server
const server = http.createServer(async (req, res) => {
  const parsedUrl = url.parse(req.url, true);
  const pathname = parsedUrl.pathname;
  const method = req.method;

  // CORS preflight
  if (method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, x-auth-token',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
    });
    res.end();
    return;
  }

  // 1. API: Login
  if (pathname === '/api/auth/login' && method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { token } = JSON.parse(body || '{}');
        const cfg = loadConfig();
        const expected = (cfg.dashboard && cfg.dashboard.auth_token) || 'admin123';
        if (token === expected) {
          sendJSON(res, { success: true, token });
        } else {
          sendError(res, 'Token salah', 401);
        }
      } catch (e) {
        sendError(res, e.message);
      }
    });
    return;
  }

  // Auth gate untuk API
  if (pathname.startsWith('/api/') && pathname !== '/api/auth/login') {
    if (!checkAuth(req)) {
      sendError(res, 'Unauthorized - Masukkan token yang valid', 401);
      return;
    }
  }

  // 2. API: Status Cluster & DB Sentral
  if (pathname === '/api/status' && method === 'GET') {
    const data = getClusterStatus();
    sendJSON(res, data);
    return;
  }

  // 3. API: Daftar Aplikasi Ter-deploy
  if (pathname === '/api/apps' && method === 'GET') {
    const apps = getDeployedApps();
    sendJSON(res, { apps });
    return;
  }

  // 4. API: Upload Arsip (.zip, .tar.gz, dll.)
  if (pathname === '/api/upload' && method === 'POST') {
    try {
      const fileInfo = await parseMultipart(req, UPLOADS_DIR);
      sendJSON(res, { success: true, file: fileInfo });
    } catch (err) {
      sendError(res, err.message, 400);
    }
    return;
  }

  // 5. API: Jalankan Deploy (deploy.sh)
  if (pathname === '/api/deploy' && method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const params = JSON.parse(body || '{}');
        const deployId = 'deploy_' + Date.now();
        const logPath = path.join(LOGS_DIR, `${deployId}.log`);

        const cmdArgs = [];
        if (params.archive) cmdArgs.push(`--archive=${params.archive}`);
        else if (params.path) cmdArgs.push(params.path);

        if (params.http_port) cmdArgs.push(String(params.http_port));
        if (params.db_port) cmdArgs.push(String(params.db_port));
        if (params.php_version) cmdArgs.push(String(params.php_version));

        if (params.force_import) cmdArgs.push('--force-import');
        if (params.skip_import) cmdArgs.push('--skip-import');
        if (params.mode) cmdArgs.push(`--mode=${params.mode}`);

        const deployScript = path.join(ROOT_DIR, 'deploy.sh');
        const proc = spawn('bash', [deployScript, ...cmdArgs], { cwd: ROOT_DIR });

        const historyItem = {
          id: deployId,
          args: cmdArgs.join(' '),
          status: 'running',
          started_at: new Date().toISOString(),
          log_file: logPath
        };
        deployHistory.unshift(historyItem);

        const logStream = fs.createWriteStream(logPath, { flags: 'a' });
        activeStreams.set(deployId, { proc, listeners: [] });

        proc.stdout.on('data', data => {
          logStream.write(data);
          const listeners = activeStreams.get(deployId)?.listeners || [];
          listeners.forEach(fn => fn(data.toString()));
        });

        proc.stderr.on('data', data => {
          logStream.write(data);
          const listeners = activeStreams.get(deployId)?.listeners || [];
          listeners.forEach(fn => fn(data.toString()));
        });

        proc.on('close', code => {
          logStream.end();
          historyItem.status = code === 0 ? 'success' : 'failed';
          historyItem.finished_at = new Date().toISOString();
          const listeners = activeStreams.get(deployId)?.listeners || [];
          listeners.forEach(fn => fn(`\n[SELESAI] Exit code: ${code}\n[STREAM_END]`));
          activeStreams.delete(deployId);
        });

        sendJSON(res, { success: true, deploy_id: deployId, history: historyItem });
      } catch (err) {
        sendError(res, err.message);
      }
    });
    return;
  }

  // 6. API: SSE Streaming untuk Deploy Logs
  if (pathname === '/api/deploy/stream' && method === 'GET') {
    const deployId = parsedUrl.query.deployId;
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*'
    });

    const sendEvent = (msg) => {
      res.write(`data: ${JSON.stringify({ message: msg })}\n\n`);
    };

    const active = activeStreams.get(deployId);
    if (active) {
      active.listeners.push(sendEvent);
      req.on('close', () => {
        const idx = active.listeners.indexOf(sendEvent);
        if (idx !== -1) active.listeners.splice(idx, 1);
      });
    } else {
      // Baca file log statis jika proses sudah selesai
      const logPath = path.join(LOGS_DIR, `${deployId}.log`);
      if (fs.existsSync(logPath)) {
        const content = fs.readFileSync(logPath, 'utf8');
        sendEvent(content);
        sendEvent('[STREAM_END]');
      } else {
        sendEvent('Tidak ada log untuk deploy ID ini.');
        sendEvent('[STREAM_END]');
      }
      res.end();
    }
    return;
  }

  // 7. API: Deploy History
  if (pathname === '/api/deploy/history' && method === 'GET') {
    sendJSON(res, { history: deployHistory });
    return;
  }

  // 8. API: Container Action (start/stop/restart)
  if (pathname === '/api/container/action' && method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { name, action } = JSON.parse(body || '{}');
        if (!name || !['start', 'stop', 'restart'].includes(action)) {
          return sendError(res, 'Parameter name atau action tidak valid.');
        }
        execSync(`docker ${action} ${name}`, { timeout: 15000 });
        sendJSON(res, { success: true, message: `Container ${name} berhasil di-${action}.` });
      } catch (err) {
        sendError(res, err.message);
      }
    });
    return;
  }

  // 9. API: App Action (destroy / redeploy)
  if (pathname === '/api/app/action' && method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { app_path, action } = JSON.parse(body || '{}');
        if (!app_path || !fs.existsSync(app_path)) {
          return sendError(res, 'Folder aplikasi tidak ditemukan: ' + app_path);
        }
        if (action === 'destroy') {
          const destroyScript = path.join(ROOT_DIR, 'destroy.sh');
          execSync(`bash "${destroyScript}" "${app_path}"`, { timeout: 30000, cwd: ROOT_DIR });
          return sendJSON(res, { success: true, message: `Aplikasi berhasil dihentikan/destroy.` });
        } else if (action === 'redeploy') {
          const deployScript = path.join(ROOT_DIR, 'deploy.sh');
          execSync(`bash "${deployScript}" "${app_path}"`, { timeout: 60000, cwd: ROOT_DIR });
          return sendJSON(res, { success: true, message: `Aplikasi berhasil di-redeploy.` });
        }
        sendError(res, 'Aksi tidak didukung');
      } catch (err) {
        sendError(res, err.message);
      }
    });
    return;
  }

  // 10. API: Database Backup / Dump
  if (pathname === '/api/db/dump' && method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { app_name, db_name } = JSON.parse(body || '{}');
        if (!app_name) return sendError(res, 'Nama aplikasi diperlukan.');
        const dumpScript = path.join(ROOT_DIR, 'scripts', 'db_dump.sh');
        const out = execSync(`bash "${dumpScript}" "${app_name}" ${db_name ? `"${db_name}"` : ''}`, { timeout: 30000, cwd: ROOT_DIR }).toString();
        sendJSON(res, { success: true, message: out });
      } catch (err) {
        sendError(res, err.message);
      }
    });
    return;
  }

  // 11. API: Database Restore
  if (pathname === '/api/db/restore' && method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { app_name, sql_file, db_name } = JSON.parse(body || '{}');
        if (!app_name) return sendError(res, 'Nama aplikasi diperlukan.');
        const restoreScript = path.join(ROOT_DIR, 'scripts', 'db_restore.sh');
        const out = execSync(`bash "${restoreScript}" "${app_name}" ${sql_file ? `"${sql_file}"` : ''} ${db_name ? `"${db_name}"` : ''}`, { timeout: 30000, cwd: ROOT_DIR }).toString();
        sendJSON(res, { success: true, message: out });
      } catch (err) {
        sendError(res, err.message);
      }
    });
    return;
  }

  // 12. API: List Database & Dump Files
  if (pathname === '/api/db/list' && method === 'GET') {
    const dbDir = path.join(ROOT_DIR, 'mysql', 'db');
    const dbFolders = [];
    if (fs.existsSync(dbDir)) {
      fs.readdirSync(dbDir, { withFileTypes: true }).forEach(ent => {
        if (ent.isDirectory()) {
          const appDbPath = path.join(dbDir, ent.name);
          const files = fs.readdirSync(appDbPath).map(f => {
            const stat = fs.statSync(path.join(appDbPath, f));
            return { name: f, size: stat.size, mtime: stat.mtime };
          });
          dbFolders.push({ app_name: ent.name, files });
        }
      });
    }
    sendJSON(res, { folders: dbFolders });
    return;
  }

  // 13. API: Live Logs SSE Streaming Container
  if (pathname === '/api/logs/stream' && method === 'GET') {
    const cName = parsedUrl.query.container;
    const tail = parsedUrl.query.tail || '100';
    if (!cName) return sendError(res, 'Missing container name parameter');

    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*'
    });

    const proc = spawn('docker', ['logs', '-f', '--tail', String(tail), '--timestamps', cName]);
    proc.stdout.on('data', d => res.write(`data: ${JSON.stringify({ log: d.toString() })}\n\n`));
    proc.stderr.on('data', d => res.write(`data: ${JSON.stringify({ log: d.toString() })}\n\n`));

    req.on('close', () => proc.kill());
    return;
  }

  // 14. API: Download Container Logs
  if (pathname === '/api/logs/download' && method === 'GET') {
    const cName = parsedUrl.query.container;
    if (!cName) return sendError(res, 'Missing container name');
    try {
      const logs = execSync(`docker logs --timestamps ${cName}`, { timeout: 10000 }).toString();
      res.writeHead(200, {
        'Content-Type': 'text/plain; charset=utf-8',
        'Content-Disposition': `attachment; filename="${cName}_logs.txt"`
      });
      res.end(logs);
    } catch (err) {
      sendError(res, err.message);
    }
    return;
  }

  // 15. API: Get & Update Config
  if (pathname === '/api/config') {
    if (method === 'GET') {
      const configJson = fs.existsSync(CONFIG_FILE) ? fs.readFileSync(CONFIG_FILE, 'utf8') : '{}';
      const ladockEnv = fs.existsSync(ENV_FILE) ? fs.readFileSync(ENV_FILE, 'utf8') : '';
      sendJSON(res, { config: configJson, env: ladockEnv });
    } else if (method === 'POST') {
      let body = '';
      req.on('data', c => body += c);
      req.on('end', () => {
        try {
          const { config: newConfig, env: newEnv } = JSON.parse(body || '{}');
          if (newConfig !== undefined) {
            JSON.parse(newConfig); // Validasi format json
            fs.writeFileSync(CONFIG_FILE, newConfig, 'utf8');
          }
          if (newEnv !== undefined) {
            fs.writeFileSync(ENV_FILE, newEnv, 'utf8');
          }
          sendJSON(res, { success: true, message: 'Konfigurasi berhasil disimpan.' });
        } catch (err) {
          sendError(res, 'Format JSON config tidak valid: ' + err.message);
        }
      });
    }
    return;
  }

  // 16. API: Summaries.json
  if (pathname === '/api/summaries' && method === 'GET') {
    if (fs.existsSync(SUMMARIES_FILE)) {
      try {
        const data = JSON.parse(fs.readFileSync(SUMMARIES_FILE, 'utf8'));
        sendJSON(res, data);
        return;
      } catch (_) {}
    }
    sendJSON(res, {});
    return;
  }

  // 17. Serve Static Files (HTML/CSS/JS di monitor/public)
  let filePath = path.join(PUBLIC_DIR, pathname === '/' ? 'index.html' : pathname);
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(PUBLIC_DIR, 'index.html');
  }

  const ext = path.extname(filePath).toLowerCase();
  const mimeTypes = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml'
  };

  const contentType = mimeTypes[ext] || 'application/octet-stream';
  fs.readFile(filePath, (err, content) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('404 Not Found');
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content);
    }
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log('======================================================');
  console.log(`  LaDock Control Center & Monitoring aktif!`);
  console.log(`  Akses Web : http://localhost:${PORT}`);
  console.log('======================================================');
});
