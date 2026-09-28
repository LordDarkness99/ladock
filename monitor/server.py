#!/usr/bin/env python3
"""
LaDock Monitor - Standalone Web Dashboard for Monolith & Microservices
Monitors containers, ports, resource usage, routes, credentials, and provides instant shortcuts.
"""

import os
import sys
import json
import time
import re
import socket
import subprocess
import urllib.request
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

PORT = 9090
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def get_docker_stats():
    """Mengambil stats CPU & RAM semua container secara cepat (no-stream)."""
    try:
        res = subprocess.run(
            ['docker', 'stats', '--no-stream', '--format', '{{json .}}'],
            capture_output=True, text=True, timeout=5
        )
        stats = {}
        for line in res.stdout.strip().split('\n'):
            if line:
                try:
                    s = json.loads(line)
                    # Key by container name & ID
                    stats[s.get('Name', '')] = s
                    stats[s.get('ID', '')] = s
                except Exception:
                    pass
        return stats
    except Exception:
        return {}


def parse_env_file(path):
    """Membaca file format KEY=VALUE menjadi dict."""
    data = {}
    if not os.path.isfile(path):
        return data
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    data[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return data


def probe_http_port(port, timeout_sec=0.7):
    """Melakukan HTTP probe cepat ke localhost:<port> untuk cek health & response latency."""
    url = f"http://127.0.0.1:{port}/"
    start_time = time.time()
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'LaDock-Monitor-Probe/1.0'}
        )
        # Handle redirects manually or let urlopen handle
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
        with opener.open(req, timeout=timeout_sec) as resp:
            latency = int((time.time() - start_time) * 1000)
            return {
                "online": True,
                "code": resp.getcode(),
                "latency_ms": latency,
                "msg": f"{resp.getcode()} OK"
            }
    except urllib.error.HTTPError as e:
        latency = int((time.time() - start_time) * 1000)
        return {
            "online": True,
            "code": e.code,
            "latency_ms": latency,
            "msg": f"{e.code} ({e.reason})"
        }
    except Exception as e:
        return {
            "online": False,
            "code": None,
            "latency_ms": None,
            "msg": "Unreachable / Down"
        }


def parse_gateway_routes(gateway_conf_path):
    """Mem-parse aturan ProxyPass dari file apache-gateway.conf."""
    routes = []
    if not os.path.isfile(gateway_conf_path):
        return routes
    try:
        with open(gateway_conf_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                # Cocokkan ProxyPass "/path" "http://service:80/..."
                m = re.match(r'^ProxyPass\s+([^\s]+)\s+([^\s]+)', line)
                if m:
                    prefix = m.group(1)
                    target = m.group(2)
                    # Lewati rule dashboard internal atau assets internal jika ada
                    if prefix not in ['/dashboard-assets']:
                        routes.append({
                            "prefix": prefix,
                            "target": target
                        })
    except Exception:
        pass
    return routes


def collect_cluster_data():
    """Mengumpulkan status seluruh container, dikelompokkan per project."""
    # 1. Ambil list container
    try:
        ps_res = subprocess.run(
            ['docker', 'ps', '-a', '--format', '{{.Names}}'],
            capture_output=True, text=True, timeout=5
        )
        names = [n.strip() for n in ps_res.stdout.strip().split('\n') if n.strip()]
    except Exception as e:
        return {"error": f"Gagal mengecek docker: {str(e)}", "projects": [], "summary": {}}

    if not names:
        return {
            "summary": {
                "total_projects": 0,
                "total_containers": 0,
                "running": 0,
                "stopped": 0,
                "microservices": 0,
                "monolith": 0
            },
            "projects": [],
            "unassigned": []
        }

    # 2. Inspect all
    try:
        inspect_res = subprocess.run(
            ['docker', 'inspect'] + names,
            capture_output=True, text=True, timeout=10
        )
        raw_containers = json.loads(inspect_res.stdout) if inspect_res.stdout else []
    except Exception as e:
        return {"error": f"Gagal inspect container: {str(e)}", "projects": []}

    # 3. Docker stats
    stats_map = get_docker_stats()

    projects_map = {}
    unassigned = []

    total_running = 0
    total_stopped = 0

    for c in raw_containers:
        c_id = c.get('Id', '')[:12]
        c_name = c.get('Name', '').lstrip('/')
        state_obj = c.get('State', {})
        state = state_obj.get('Status', 'unknown')
        is_running = state == 'running'
        if is_running:
            total_running += 1
        else:
            total_stopped += 1

        labels = c.get('Config', {}).get('Labels') or {}
        project_name = labels.get('com.docker.compose.project')
        work_dir = labels.get('com.docker.compose.project.working_dir')
        compose_service = labels.get('com.docker.compose.service', '')

        # Port parsing
        ports_obj = c.get('NetworkSettings', {}).get('Ports') or {}
        mapped_ports = []
        primary_web_url = None
        db_host_port = None

        for container_p, bindings in ports_obj.items():
            c_proto = container_p.split('/')[1] if '/' in container_p else 'tcp'
            c_port = container_p.split('/')[0] if '/' in container_p else container_p
            if bindings:
                for b in bindings:
                    h_ip = b.get('HostIp', '0.0.0.0')
                    h_port = b.get('HostPort')
                    mapped_ports.append({
                        "container_port": c_port,
                        "proto": c_proto,
                        "host_ip": h_ip,
                        "host_port": h_port
                    })
                    # Tentukan jika ini web URL
                    if c_port in ['80', '8080'] and not primary_web_url and h_port:
                        primary_web_url = f"http://localhost:{h_port}"
                    if c_port in ['3306']:
                        db_host_port = h_port

        # Stats info
        c_stat = stats_map.get(c_name) or stats_map.get(c_id) or {}
        cpu_perc = c_stat.get('CPUPerc', '0.00%')
        mem_usage = c_stat.get('MemUsage', '0B / 0B')
        mem_perc = c_stat.get('MemPerc', '0.00%')
        net_io = c_stat.get('NetIO', '-')
        pids = c_stat.get('PIDs', '-')

        # Role
        role = "service"
        img = c.get('Config', {}).get('Image', '')
        if 'mysql' in img or 'db' in c_name.lower():
            role = "database"
        elif 'gateway' in c_name.lower() or 'gateway' in compose_service.lower():
            role = "gateway"
        elif 'app' in c_name.lower():
            role = "web_app"

        # HTTP Probe jika container sedang running dan punya port web
        http_probe = None
        if is_running and primary_web_url:
            p_match = re.search(r':(\d+)$', primary_web_url)
            if p_match:
                http_probe = probe_http_port(p_match.group(1))

        # Health status
        health_status = state_obj.get('Health', {}).get('Status')  # healthy, unhealthy, starting, None

        container_item = {
            "id": c_id,
            "name": c_name,
            "service": compose_service,
            "role": role,
            "image": img,
            "state": state,
            "is_running": is_running,
            "health": health_status,
            "ports": mapped_ports,
            "primary_url": primary_web_url,
            "http_probe": http_probe,
            "db_port": db_host_port,
            "stats": {
                "cpu": cpu_perc,
                "mem_usage": mem_usage,
                "mem_perc": mem_perc,
                "net_io": net_io,
                "pids": pids
            },
            "created": c.get('Created', '')
        }

        if project_name:
            if project_name not in projects_map:
                projects_map[project_name] = {
                    "name": project_name,
                    "work_dir": work_dir or "",
                    "mode": "monolith",  # default, will check gateway
                    "containers": [],
                    "gateway": None,
                    "routes": [],
                    "credentials": None,
                    "services_credentials": {}
                }
            projects_map[project_name]["containers"].append(container_item)
        else:
            unassigned.append(container_item)

    # 4. Enrich project metadata (Microservice / Monolith / Credentials / Routes)
    microservices_count = 0
    monolith_count = 0

    projects_list = []
    for p_name, p_data in projects_map.items():
        w_dir = p_data["work_dir"]
        docker_dir = os.path.join(w_dir, ".docker") if w_dir else ""
        
        # Check if gateway exists
        gateway_conf = os.path.join(docker_dir, "apache-gateway.conf") if docker_dir else ""
        has_gateway = os.path.isfile(gateway_conf)

        # Temukan container gateway jika ada
        gateway_container = next((c for c in p_data["containers"] if c["role"] == "gateway"), None)
        
        if has_gateway or gateway_container:
            p_data["mode"] = "microservices"
            microservices_count += 1
            if has_gateway:
                p_data["routes"] = parse_gateway_routes(gateway_conf)
            if gateway_container and gateway_container.get("primary_url"):
                p_data["gateway"] = {
                    "name": gateway_container["name"],
                    "url": gateway_container["primary_url"],
                    "probe": gateway_container.get("http_probe")
                }
            
            # Cek credentials per service
            creds_dir = os.path.join(docker_dir, "credentials")
            if os.path.isdir(creds_dir):
                for fname in os.listdir(creds_dir):
                    if fname.endswith(".env"):
                        svc_name = fname[:-4]
                        p_data["services_credentials"][svc_name] = parse_env_file(os.path.join(creds_dir, fname))
        else:
            p_data["mode"] = "monolith"
            monolith_count += 1

        # Cek credentials monolith
        creds_file = os.path.join(docker_dir, "credentials.env") if docker_dir else ""
        if os.path.isfile(creds_file):
            p_data["credentials"] = parse_env_file(creds_file)

        # Cari port DB jika ada
        db_container = next((c for c in p_data["containers"] if c["role"] == "database"), None)
        if db_container and db_container.get("db_port") and p_data["credentials"]:
            p_data["credentials"]["DB_PORT"] = db_container["db_port"]
            p_data["credentials"]["DB_HOST"] = "127.0.0.1"

        projects_list.append(p_data)

    # Sort projects alphabetically
    projects_list.sort(key=lambda x: x["name"])

    return {
        "summary": {
            "total_projects": len(projects_list),
            "total_containers": len(raw_containers),
            "running": total_running,
            "stopped": total_stopped,
            "microservices": microservices_count,
            "monolith": monolith_count
        },
        "projects": projects_list,
        "unassigned": unassigned
    }


class MonitorRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return
        super().do_HEAD()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            data = collect_cluster_data()
            self.wfile.write(json.dumps(data).encode('utf-8'))
            return

        elif path == "/api/container/logs":
            container_name = query.get("name", [""])[0]
            tail_lines = query.get("tail", ["150"])[0]
            if not container_name:
                self.send_error(400, "Missing container name")
                return

            try:
                res = subprocess.run(
                    ['docker', 'logs', '--tail', str(tail_lines), '--timestamps', container_name],
                    capture_output=True, text=True, timeout=5
                )
                output = res.stdout + res.stderr
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "name": container_name,
                    "logs": output
                }).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        # Fallback to serving public static files
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/container/action":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                payload = json.loads(body)
                name = payload.get("name")
                action = payload.get("action")  # restart, stop, start

                if action not in ["restart", "stop", "start"] or not name:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Invalid action or container name"}).encode('utf-8'))
                    return

                res = subprocess.run(
                    ['docker', action, name],
                    capture_output=True, text=True, timeout=20
                )
                if res.returncode == 0:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": True,
                        "message": f"Container {name} berhasil di-{action}."
                    }).encode('utf-8'))
                else:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": False,
                        "error": res.stderr.strip()
                    }).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        self.send_error(404, "Endpoint not found")

    def log_message(self, format, *args):
        # Mute normal HTTP 200 log spam
        pass


def main():
    port = PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    server_address = ('0.0.0.0', port)
    httpd = ThreadedHTTPServer(server_address, MonitorRequestHandler)
    print(f"==================================================")
    print(f"  LaDock Monitoring Dashboard aktif!")
    print(f"  Akses Web : http://localhost:{port}")
    print(f"  Tekan Ctrl+C untuk menghentikan.")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[LaDock Monitor] Menghentikan server...")
        httpd.server_close()


if __name__ == "__main__":
    main()
