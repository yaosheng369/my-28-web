import os
import re
import sys
import json
import time
import hmac
import base64
import hashlib
import secrets
import threading
import urllib3
from collections import defaultdict
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= 配置区域 =================
PORT = int(os.environ.get("PORT", 8080))
SYNC_INTERVAL = 2  
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "captain_8888_super_secret_key_2024")

URLS = {
    "btc28": "https://kjsix28.com/portal/btc28",
    "fenfen28": "http://www.qilin28.com/index?type=3",
    "JND": "http://www.qilin28.com/"
}
PERIODS = {"btc28": 60, "fenfen28": 60, "JND": 210}
CN_NAMES = {"btc28": "比特28", "fenfen28": "分分28", "JND": "加拿大28"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "close"
}

# ================= 全局数据结构 =================
GAME_DATA = {
    "btc28": {"draws": [], "next_ts": 0},
    "fenfen28": {"draws": [], "next_ts": 0},
    "JND": {"draws": [], "next_ts": 0}
}
DATA_LOCK = threading.Lock()
NONCE_STORE = {}
NONCE_LOCK = threading.Lock()

# ================= 安全防护组件 =================
class SecurityGuard:
    def __init__(self):
        self.ip_records = defaultdict(list)
        self.banned_ips = {}
        self.lock = threading.Lock()
        self.MAX_REQUESTS = 10       
        self.WINDOW = 0.5           
        self.BAN_TIME = 1800        

    def is_banned(self, ip):
        with self.lock:
            if ip in self.banned_ips:
                if time.time() > self.banned_ips[ip]:
                    del self.banned_ips[ip]
                    return False
                return True
            return False

    def check_rate_limit(self, ip):
        with self.lock:
            now = time.time()
            self.ip_records[ip] = [t for t in self.ip_records[ip] if now - t < self.WINDOW]
            if len(self.ip_records[ip]) >= self.MAX_REQUESTS:
                self.banned_ips[ip] = now + self.BAN_TIME
                return False
            self.ip_records[ip].append(now)
            return True

SECURITY = SecurityGuard()

def x_xor(data: str, key: str) -> str:
    key_bytes = key.encode('utf-8')
    return base64.b64encode(bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data.encode('utf-8'))])).decode('utf-8')

# ================= 数据抓取 =================
def fetch_data(game_key):
    url = URLS[game_key]
    try:
        with requests.Session() as s:
            s.headers.update(HEADERS)
            response = s.get(url, timeout=6, verify=False)
            response.encoding = 'utf-8'
            if response.status_code != 200: return False

            soup = BeautifulSoup(response.text, 'html.parser')
            records = []
            
            for tr in soup.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 3:
                    issue = tds[0].get_text(strip=True)
                    time_str = tds[1].get_text(strip=True)
                    result_text = tds[2].get_text(strip=True)
                    
                    if re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", time_str):
                        result_clean = re.sub(r'\s+', '', result_text)
                        match = re.search(r"(\d+)\+(\d+)\+(\d+)=(\d+)", result_clean)
                        if match:
                            total = int(match.group(4))
                            records.append({
                                "issue": issue,
                                "time": time_str[11:],
                                "raw": result_clean,
                                "type": f"{'大' if total >= 14 else '小'}{'单' if total % 2 != 0 else '双'}",
                            })
                            if len(records) >= 50: break
            
            if records:
                with DATA_LOCK:
                    GAME_DATA[game_key]["draws"] = records
                    latest_time = datetime.strptime(records[0]["time"], "%H:%M:%S")
                    now = datetime.now()
                    latest_dt = now.replace(hour=latest_time.hour, minute=latest_time.minute, second=latest_time.second)
                    if latest_dt > now + timedelta(minutes=10): latest_dt -= timedelta(days=1)
                    
                    period = PERIODS[game_key]
                    next_ts = (latest_dt + timedelta(seconds=period)).timestamp()
                    while next_ts <= time.time(): next_ts += period
                    GAME_DATA[game_key]["next_ts"] = next_ts
                return True
            return False
    except Exception:
        return False

executor = ThreadPoolExecutor(max_workers=3)

def sync_all_worker():
    time.sleep(1)
    while True:
        start_time = time.time()
        futures = [executor.submit(fetch_data, key) for key in URLS.keys()]
        for f in futures: f.result()
        time.sleep(max(0.1, SYNC_INTERVAL - (time.time() - start_time)))

# ================= HTML 页面生成 =================
def build_html(client_key, encrypted_payload, nonce):
    # 避免使用 string.Template，直接返回纯正 HTML 防止 JS 解析出错
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>舰长开奖网站</title>
    <style nonce="{nonce}">
        body {{ background: #0a0a0c; color: #e0e0e0; font-family: monospace; padding: 15px; margin: 0; }}
        .header {{ position: relative; text-align: center; border: 1px solid #00f3ff; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .title {{ color: #00f3ff; font-size: 24px; margin: 0 0 10px 0; }}
        .countdown {{ color: #00ff9d; font-size: 20px; margin-top: 8px; font-weight: bold; }}
        
        .sync-badge {{ 
            position: absolute; right: 10px; top: 10px;
            font-size: 12px; color: #00f3ff; 
            background: rgba(0, 243, 255, 0.1); 
            padding: 4px 8px; border-radius: 4px; border: 1px solid #00f3ff;
            opacity: 0; transition: opacity 0.3s; pointer-events: none;
        }}
        .sync-badge.show {{ opacity: 1; }}

        .tabs {{ display: flex; justify-content: center; margin-bottom: 15px; gap: 10px; }}
        .tab-btn {{ background: #1a1a1a; color: #888; border: 1px solid #333; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-family: monospace; font-size: 16px; transition: all 0.3s; }}
        .tab-btn.active {{ background: #00f3ff; color: #000; border-color: #00f3ff; font-weight: bold; box-shadow: 0 0 10px rgba(0,243,255,0.5); }}
        
        table {{ width: 100%; border-collapse: collapse; text-align: center; }}
        th {{ color: #00f3ff; padding: 10px; border-bottom: 1px solid #333; }}
        td {{ padding: 10px; border-bottom: 1px solid #222; }}
        .result {{ color: #00f3ff; font-weight: bold; }}
        .big {{ color: #ff003c; font-weight: bold; }}
        .small {{ color: #007bff; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 class="title">⚡ 舰长开奖网站 ⚡</h1>
        <div class="countdown">下一期开奖倒计时：<span id="cd">--</span> 秒</div>
        <div id="sync-badge" class="sync-badge">🔄 请求上游中...</div>
    </div>
    
    <div class="tabs">
        <button class="tab-btn active" data-game="btc28">比特28</button>
        <button class="tab-btn" data-game="fenfen28">分分28</button>
        <button class="tab-btn" data-game="JND">加拿大28</button>
    </div>
    <table>
        <thead><tr><th>期号</th><th>时间</th><th>结果</th><th>属性</th></tr></thead>
        <tbody id="tbody"><tr><td colspan="4">解密加载中...</td></tr></tbody>
    </table>
    
    <div id="vault" data-payload="{encrypted_payload}" style="display:none"></div>

    <script nonce="{nonce}">
    (function() {{
        'use strict';
        const SECRET_KEY = "{client_key}";
        
        function xorDecrypt(b64Data) {{
            const str = atob(b64Data);
            let result = '';
            for (let i = 0; i < str.length; i++) {{
                result += String.fromCharCode(str.charCodeAt(i) ^ SECRET_KEY.charCodeAt(i % SECRET_KEY.length));
            }}
            try {{ return decodeURIComponent(escape(result)); }} 
            catch(e) {{ return result; }}
        }}

        const vault = document.getElementById('vault');
        let allData = {{}};
        let timeOffset = 0; 
        let currentGame = 'btc28';
        const cdText = document.getElementById('cd');
        const tbody = document.getElementById('tbody');
        const btns = document.querySelectorAll('.tab-btn');
        const badge = document.getElementById('sync-badge');

        try {{
            const dataObj = JSON.parse(xorDecrypt(vault.getAttribute('data-payload')));
            allData = dataObj.games;
            timeOffset = Math.floor(Date.now() / 1000) - dataObj.server_time;
        }} catch(e) {{ console.error("初始解密失败", e); }}

        function renderTable(gameKey) {{
            const game = allData[gameKey];
            if (!game || !game.draws || game.draws.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="4" style="color:#ff003c;">暂无数据</td></tr>';
                return;
            }}
            const frag = document.createDocumentFragment();
            game.draws.forEach(r => {{
                const tr = document.createElement('tr');
                const td1 = document.createElement('td'); td1.textContent = r.issue;
                const td2 = document.createElement('td'); td2.textContent = r.time;
                const td3 = document.createElement('td'); td3.className = 'result'; td3.textContent = r.raw;
                const td4 = document.createElement('td'); 
                td4.className = r.type.includes('大') ? 'big' : 'small';
                td4.textContent = r.type;
                tr.append(td1, td2, td3, td4);
                frag.appendChild(tr);
            }});
            tbody.innerHTML = '';
            tbody.appendChild(frag);
        }}

        function tick() {{
            if (!allData[currentGame]) return;
            const nextTs = allData[currentGame].next_ts;
            const nowServer = Math.floor(Date.now() / 1000) - timeOffset;
            let remain = Math.ceil(nextTs - nowServer);
            if (remain < 0) remain = 0;
            cdText.textContent = remain;
        }}
        setInterval(tick, 1000);

        async function syncData() {{
            badge.classList.add('show');
            try {{
                const res = await fetch('/_sync?_t=' + Date.now(), {{
                    cache: 'no-store',
                    headers: {{ 'Pragma': 'no-cache', 'Cache-Control': 'no-cache' }}
                }});
                if (!res.ok) throw new Error();
                
                const json = await res.json();
                const dataObj = JSON.parse(xorDecrypt(json.payload));
                
                allData = dataObj.games;
                timeOffset = Math.floor(Date.now() / 1000) - dataObj.server_time;
                
                renderTable(currentGame);
                tick(); 
                
                badge.textContent = '✅ 已更新';
                setTimeout(() => badge.classList.remove('show'), 1000);
            }} catch(e) {{ 
                badge.textContent = '❌ 同步失败';
                setTimeout(() => badge.classList.remove('show'), 2000);
            }}
        }}
        
        setInterval(syncData, 5000); 

        btns.forEach(btn => {{
            btn.addEventListener('click', () => {{
                btns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentGame = btn.getAttribute('data-game');
                renderTable(currentGame);
                tick(); 
            }});
        }});

        renderTable(currentGame);
        tick();
    }})();
    </script>
</body>
</html>
"""

# ================= HTTP 处理 =================
class RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 15

    def _verify_api(self, query, path):
        try:
            ts = query.get("ts", [""])[0]
            nonce = query.get("nonce", [""])[0]
            sig = query.get("sig", [""])[0]
            if not ts or not nonce or not sig: return False
            if len(nonce) > 64 or len(sig) != 64: return False
            
            ts_i = int(ts)
            if abs(time.time() - ts_i) > 30: return False
            
            msg = f"{path}|{ts}|{nonce}".encode('utf-8')
            expected_sig = hmac.new(API_SECRET_KEY.encode('utf-8'), msg, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected_sig, sig): return False
            
            now = time.time()
            with NONCE_LOCK:
                for k in [k for k, v in NONCE_STORE.items() if v < now]: del NONCE_STORE[k]
                if nonce in NONCE_STORE: return False
                NONCE_STORE[nonce] = now + 60
            return True
        except Exception:
            return False

    def do_GET(self):
        client_ip = self.client_address[0]
        
        if SECURITY.is_banned(client_ip):
            self.send_error(403, "Banned for 30 mins")
            return
        if not SECURITY.check_rate_limit(client_ip):
            self.send_error(429, "Too Many Requests. Banned for 30 mins")
            return

        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            # ================= 1. 网页初始加载 =================
            if path == '/' or path == '/index.html':
                with DATA_LOCK:
                    payload_data = {
                        "server_time": int(time.time()),
                        "games": {}
                    }
                    for key in GAME_DATA:
                        payload_data["games"][key] = {
                            "draws": GAME_DATA[key]["draws"],
                            "next_ts": int(GAME_DATA[key]["next_ts"]),
                            "period": PERIODS[key]
                        }

                json_str = json.dumps(payload_data, ensure_ascii=False)
                client_key = secrets.token_hex(8) 
                encrypted_payload = x_xor(json_str, client_key)
                nonce = secrets.token_urlsafe(16)

                html = build_html(client_key, encrypted_payload, nonce)
                body = html.encode('utf-8')

                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
                self.end_headers()
                self.wfile.write(body)
                return

            # ================= 2. 网页内嵌 5秒强同步接口 =================
            elif path == '/_sync':
                with DATA_LOCK:
                    payload_data = {
                        "server_time": int(time.time()),
                        "games": {}
                    }
                    for key in GAME_DATA:
                        payload_data["games"][key] = {
                            "draws": GAME_DATA[key]["draws"],
                            "next_ts": int(GAME_DATA[key]["next_ts"]),
                            "period": PERIODS[key]
                        }

                json_str = json.dumps(payload_data, ensure_ascii=False)
                client_key = secrets.token_hex(8) 
                encrypted_payload = x_xor(json_str, client_key)

                resp = {
                    "key": client_key,
                    "payload": encrypted_payload
                }
                
                body = json.dumps(resp).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                self.wfile.write(body)
                return

            # ================= 3. 受保护的 API 接口 =================
            elif path in ['/api/btc28', '/api/fenfen28', '/api/JND']:
                admin_key = query.get('admin_key', [''])[0]
                if admin_key != API_SECRET_KEY and not self._verify_api(query, path):
                    self.send_response(401)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"code": 401, "msg": "签名错误或链接已过期"}).encode('utf-8'))
                    return

                game_key = path.split('/')[-1]
                with DATA_LOCK:
                    game_data = GAME_DATA[game_key]
                    response_data = {
                        "code": 200,
                        "message": "success",
                        "name": CN_NAMES[game_key],
                        "period": PERIODS[game_key],
                        "next_ts": int(game_data["next_ts"]),
                        "draws": game_data["draws"]
                    }

                body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            else:
                self.send_error(404, "Not Found")

        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print(f"Server Error: {e}", file=sys.stderr)
            self.send_error(500, "Internal Error")

    def log_message(self, format, *args):
        pass

class ThreadedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

# ================= 启动 =================
if __name__ == '__main__':
    threading.Thread(target=sync_all_worker, daemon=True).start()
    server = ThreadedHTTPServer(('0.0.0.0', PORT), RequestHandler)
    print(f"[INFO] 服务器已启动，端口: {PORT}")
    print(f"[INFO] 最终修复版，精确5秒强同步校准开启")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
