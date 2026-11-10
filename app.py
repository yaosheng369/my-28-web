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
from string import Template
from collections import defaultdict
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= 配置区域 =================
PORT = int(os.environ.get("PORT", "8080"))
SYNC_INTERVAL = 5
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "captain_8888_secure_key_2024")

URLS = {
    "btc28": "https://kjsix28.com/portal/btc28",
    "fenfen28": "http://www.qilin28.com/index?type=3",
    "JND": "http://www.qilin28.com/",
}
PERIODS = {"btc28": 60, "fenfen28": 60, "JND": 210}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "close"
}

# ================= 全局数据结构 =================
GAME_DATA = {
    "btc28": {"draws": [], "next_ts": 0, "last_sync": 0},
    "fenfen28": {"draws": [], "next_ts": 0, "last_sync": 0},
    "JND": {"draws": [], "next_ts": 0, "last_sync": 0}
}
DATA_LOCK = threading.Lock()

# ================= 安全防护组件 =================

class SecurityGuard:
    """限流、黑名单、反爬校验"""
    def __init__(self):
        self.ip_records = defaultdict(list)
        self.banned_ips = {}
        self.lock = threading.Lock()
        self.MAX_REQUESTS = 30  # 10秒内最多请求30次
        self.WINDOW = 10
        self.BAN_TIME = 300     # 封禁5分钟

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
            # 清理旧记录
            self.ip_records[ip] = [t for t in self.ip_records[ip] if now - t < self.WINDOW]
            
            if len(self.ip_records[ip]) >= self.MAX_REQUESTS:
                self.banned_ips[ip] = now + self.BAN_TIME
                return False
            
            self.ip_records[ip].append(now)
            return True

SECURITY = SecurityGuard()

def x_xor(data: str, key: str) -> str:
    """简单的异或加密，用于前端混淆。防君子不防小人，但能挡住90%的F12查看"""
    key_bytes = key.encode('utf-8')
    return base64.b64encode(bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data.encode('utf-8'))])).decode('utf-8')

def fetch_data(game_key):
    url = URLS[game_key]
    try:
        with requests.Session() as s:
            s.headers.update(HEADERS)
            response = s.get(url, timeout=8, verify=False)
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
                                "total": total
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
                    # 确保倒计时永远是正数
                    while next_ts <= time.time(): next_ts += period
                    
                    GAME_DATA[game_key]["next_ts"] = next_ts
                    GAME_DATA[game_key]["last_sync"] = now.timestamp()
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
        sleep_time = max(0.1, SYNC_INTERVAL - (time.time() - start_time))
        time.sleep(sleep_time)

# ================= 页面模板 (数据加密混淆) =================
# 注意：这里不再直接渲染明文，而是把数据转成 JSON 后异或加密，前端解密
PAGE_TEMPLATE = Template(r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>舰长开奖网站</title>
    <style nonce="$nonce">
        body { background: #0a0a0c; color: #e0e0e0; font-family: monospace; padding: 15px; }
        .header { text-align: center; border: 1px solid #00f3ff; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .title { color: #00f3ff; font-size: 24px; margin: 0 0 10px 0; }
        .countdown { color: #00ff9d; font-size: 20px; margin-top: 8px; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; text-align: center; }
        th { color: #00f3ff; padding: 10px; border-bottom: 1px solid #333; }
        td { padding: 10px; border-bottom: 1px solid #222; }
        .result { color: #00f3ff; font-weight: bold; }
        .big { color: #ff003c; font-weight: bold; }
        .small { color: #007bff; font-weight: bold; }
    </style>
</head>
<body>
    <div class="header">
        <h1 class="title">⚡ 舰长开奖网站 ⚡</h1>
        <div class="countdown">下一期开奖倒计时：<span id="cd">--</span> 秒</div>
    </div>
    <table>
        <thead><tr><th>期号</th><th>时间</th><th>结果</th><th>属性</th></tr></thead>
        <tbody id="tbody"></tbody>
    </table>
    
    <!-- 隐藏字段存储加密后的数据和动态Token -->
    <div id="vault" data-payload="$encrypted_payload" data-ts="$next_ts" data-p="$period" style="display:none"></div>

    <script nonce="$nonce">
    (function() {
        'use strict';
        // 前端动态解密逻辑
        const SECRET_KEY = "$client_key";
        
        function xorDecrypt(b64Data) {
            const str = atob(b64Data);
            const key = SECRET_KEY;
            let result = '';
            for (let i = 0; i < str.length; i++) {
                result += String.fromCharCode(str.charCodeAt(i) ^ key.charCodeAt(i % key.length));
            }
            try {
                // 处理UTF-8中文
                return decodeURIComponent(escape(result));
            } catch(e) { return result; }
        }

        const vault = document.getElementById('vault');
        let nextTs = parseFloat(vault.getAttribute('data-ts')) || 0;
        const period = parseInt(vault.getAttribute('data-p'), 10) || 60;
        const cd = document.getElementById('cd');

        // 1. 倒计时逻辑
        function tick() {
            const now = Date.now() / 1000;
            if (nextTs <= 0) nextTs = now + period;
            while (nextTs <= now) nextTs += period; 
            cd.textContent = Math.ceil(nextTs - now);
        }
        setInterval(tick, 1000);
        tick();

        // 2. 解密并渲染数据
        function renderData() {
            try {
                const rawJson = xorDecrypt(vault.getAttribute('data-payload'));
                const data = JSON.parse(rawJson);
                const tbody = document.getElementById('tbody');
                tbody.innerHTML = ''; // 清空

                data.forEach(r => {
                    const tr = document.createElement('tr');
                    // 使用 textContent 杜绝 XSS
                    const td1 = document.createElement('td'); td1.textContent = r.issue;
                    const td2 = document.createElement('td'); td2.textContent = r.time;
                    const td3 = document.createElement('td'); td3.className = 'result'; td3.textContent = r.raw;
                    const td4 = document.createElement('td'); 
                    td4.className = r.type.includes('大') ? 'big' : 'small';
                    td4.textContent = r.type;

                    tr.append(td1, td2, td3, td4);
                    tbody.appendChild(tr);
                });
            } catch(e) { console.error("Decode error", e); }
        }
        renderData();
    })();
    </script>
</body>
</html>
""")

# ================= HTTP 处理 =================
class RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 15

    def do_GET(self):
        client_ip = self.client_address[0]
        
        # 1. IP 黑名单与限流检测
        if SECURITY.is_banned(client_ip):
            self.send_error(403, "Banned: Too many requests")
            return
            
        if not SECURITY.check_rate_limit(client_ip):
            self.send_error(429, "Too Many Requests")
            return

        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == '/' or path == '/index.html':
                # 2. 校验 Referer 和 UA (简单的反爬)
                ua = self.headers.get('User-Agent', '').lower()
                if 'python' in ua or 'curl' in ua or 'postman' in ua:
                    self.send_error(403, "Forbidden Bot")
                    return

                with DATA_LOCK:
                    # 提取数据
                    data_to_send = GAME_DATA["btc28"]["draws"]
                    next_ts = int(GAME_DATA["btc28"]["next_ts"])
                    period = PERIODS["btc28"]

                # 3. 数据加密：把明文JSON转为密文
                json_str = json.dumps(data_to_send, ensure_ascii=False)
                client_key = secrets.token_hex(8) # 每次请求生成动态密钥
                encrypted_payload = x_xor(json_str, client_key)
                nonce = secrets.token_urlsafe(16)

                # 4. 生成 HTML
                html = PAGE_TEMPLATE.substitute(
                    encrypted_payload=encrypted_payload,
                    next_ts=str(next_ts),
                    period=str(period),
                    nonce=nonce,
                    client_key=client_key
                )

                body = html.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store, max-age=0')
                self.send_header('X-Content-Type-Options', 'nosniff')
                # 严格 CSP，防止注入
                self.send_header('Content-Security-Policy', f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self';")
                self.end_headers()
                self.wfile.write(body)

            elif path == '/api/data':
                # 仅供合法签名的 API 调用 (同上一版逻辑，略作精简)
                self.send_error(401, "API Disabled for public")
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
    print(f"[INFO] 重装甲开奖服务器已启动，端口: {PORT}")
    print(f"[INFO] 前端数据已加密混淆，IP限流已开启(10秒30次)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
