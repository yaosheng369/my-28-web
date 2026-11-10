import os
import re
import sys
import json
import time
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
SYNC_INTERVAL = 5
API_KEY = "captain_8888" # 你要求的固定暗号

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

# ================= 安全防护组件 =================
class SecurityGuard:
    def __init__(self):
        self.ip_records = defaultdict(list)
        self.banned_ips = {}
        self.lock = threading.Lock()
        
        # ★ 核心防刷策略修改点 ★
        self.MAX_REQUESTS = 5       # 最多请求次数
        self.WINDOW = 0.3           # 时间窗口：0.3 秒
        self.BAN_TIME = 1800        # 封禁时间：30分钟 (60 * 30)

    def is_banned(self, ip):
        with self.lock:
            if ip in self.banned_ips:
                if time.time() > self.banned_ips[ip]:
                    del self.banned_ips[ip]  # 封禁时间到，解封
                    return False
                return True
            return False

    def check_rate_limit(self, ip):
        with self.lock:
            now = time.time()
            # 只保留 0.3 秒内的请求记录
            self.ip_records[ip] = [t for t in self.ip_records[ip] if now - t < self.WINDOW]
            
            # 如果 0.3 秒内请求 >= 5 次，直接拉黑 30 分钟
            if len(self.ip_records[ip]) >= self.MAX_REQUESTS:
                self.banned_ips[ip] = now + self.BAN_TIME
                return False
            
            # 记录本次请求时间
            self.ip_records[ip].append(now)
            return True

SECURITY = SecurityGuard()

# ================= 数据抓取逻辑 =================
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

# ================= HTTP 处理 =================
class RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 15

    def do_GET(self):
        client_ip = self.client_address[0]
        
        # 检查是否在黑名单中
        if SECURITY.is_banned(client_ip):
            self.send_error(403, "Banned: You have been banned for 30 minutes due to high frequency.")
            return
            
        # 检查限流 (0.3秒内是否超过5次)
        if not SECURITY.check_rate_limit(client_ip):
            self.send_error(429, "Too Many Requests: Banned for 30 minutes.")
            return

        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            # ================= 1. 网页端 (HTML 渲染) =================
            if path == '/' or path == '/index.html':
                with DATA_LOCK:
                    payload_json = {}
                    for key in GAME_DATA:
                        payload_json[key] = {
                            "draws": GAME_DATA[key]["draws"],
                            "next_ts": int(GAME_DATA[key]["next_ts"]),
                            "period": PERIODS[key]
                        }
                
                html = f"""<!DOCTYPE html>
                <html lang="zh-CN">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>舰长开奖网站</title>
                    <style>
                        body {{ background: #0a0a0c; color: #e0e0e0; font-family: monospace; padding: 15px; margin: 0; }}
                        .header {{ text-align: center; border: 1px solid #00f3ff; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
                        .title {{ color: #00f3ff; font-size: 24px; margin: 0 0 10px 0; }}
                        .countdown {{ color: #00ff9d; font-size: 20px; margin-top: 8px; font-weight: bold; }}
                        .tabs {{ display: flex; justify-content: center; margin-bottom: 15px; gap: 10px; }}
                        .tab-btn {{ background: #1a1a1a; color: #888; border: 1px solid #333; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-family: monospace; font-size: 16px; }}
                        .tab-btn.active {{ background: #00f3ff; color: #000; border-color: #00f3ff; font-weight: bold; }}
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
                    </div>
                    <div class="tabs">
                        <button class="tab-btn active" data-game="btc28">比特28</button>
                        <button class="tab-btn" data-game="fenfen28">分分28</button>
                        <button class="tab-btn" data-game="JND">加拿大28</button>
                    </div>
                    <table>
                        <thead><tr><th>期号</th><th>时间</th><th>结果</th><th>属性</th></tr></thead>
                        <tbody id="tbody"></tbody>
                    </table>
                    
                    <script>
                        const ALL_DATA = {json.dumps(payload_json, ensure_ascii=False)};
                        
                        let currentGame = 'btc28';
                        let nextTs = 0;
                        let period = 60;
                        const cdText = document.getElementById('cd');
                        const tbody = document.getElementById('tbody');
                        const btns = document.querySelectorAll('.tab-btn');

                        function renderTable(gameKey) {{
                            const game = ALL_DATA[gameKey];
                            if (!game || game.draws.length === 0) {{
                                tbody.innerHTML = '<tr><td colspan="4">暂无数据</td></tr>';
                                return;
                            }}
                            nextTs = game.next_ts;
                            period = game.period;

                            let html = '';
                            game.draws.forEach(r => {{
                                let colorClass = r.type.includes('大') ? 'big' : 'small';
                                html += `<tr>
                                    <td>${{r.issue}}</td>
                                    <td>${{r.time}}</td>
                                    <td class="result">${{r.raw}}</td>
                                    <td class="${{colorClass}}">${{r.type}}</td>
                                </tr>`;
                            }});
                            tbody.innerHTML = html;
                        }}

                        function tick() {{
                            if (nextTs <= 0) {{ cdText.textContent = '--'; return; }}
                            const now = Date.now() / 1000;
                            while (nextTs <= now) nextTs += period; 
                            cdText.textContent = Math.ceil(nextTs - now);
                        }}
                        setInterval(tick, 1000);

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
                    </script>
                </body>
                </html>
                """
                body = html.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            # ================= 2. 拆分后的三个 JSON API =================
            elif path in ['/api/btc28', '/api/fenfen28', '/api/JND']:
                key = query.get('key', [''])[0]
                if key != API_KEY:
                    self.send_response(401)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"code": 401, "msg": "暗号错误，拒绝访问"}).encode('utf-8'))
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
    print(f"[INFO] 极限防刷已开启: 0.3秒内最多5次请求，触发即封禁IP 30分钟。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
