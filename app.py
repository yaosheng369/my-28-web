import requests
from bs4 import BeautifulSoup
import re
import time
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import urllib3
from concurrent.futures import ThreadPoolExecutor
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PORT = int(os.environ.get("PORT", 8080))
SYNC_INTERVAL = 5
# 🌟 防盗暗号
API_SECRET_KEY = "captain_8888"

URLS = {
    "btc28": "https://kjsix28.com/portal/btc28",
    "fenfen28": "http://www.qilin28.com/index?type=3",
    "JND": "http://www.qilin28.com/"
}
CN_NAME_MAP = {"btc28": "比特28", "fenfen28": "分分28", "JND": "加拿大28"}
PERIODS = {"btc28": 60, "fenfen28": 60, "JND": 210}

GAME_DATA = {
    "btc28": {"draws": [], "next_ts": 0, "last_sync": 0},
    "fenfen28": {"draws": [], "next_ts": 0, "last_sync": 0},
    "JND": {"draws": [], "next_ts": 0, "last_sync": 0}
}
LAST_ISSUE = {"btc28": "", "fenfen28": "", "JND": ""}
DATA_LOCK = threading.Lock() 

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "close"
}

def fetch_data(game_key):
    url = URLS[game_key]
    try:
        with requests.Session() as s:
            s.headers.update(HEADERS)
            response = s.get(url, timeout=10, verify=False)
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
                current_issue = records[0]["issue"]
                is_new = (LAST_ISSUE[game_key] != current_issue)
                
                with DATA_LOCK:
                    GAME_DATA[game_key]["draws"] = records
                    latest_time = datetime.strptime(records[0]["time"], "%H:%M:%S")
                    now = datetime.now()
                    latest_dt = now.replace(hour=latest_time.hour, minute=latest_time.minute, second=latest_time.second)
                    if latest_dt > now + timedelta(minutes=10): latest_dt -= timedelta(days=1)
                        
                    GAME_DATA[game_key]["next_ts"] = (latest_dt + timedelta(seconds=PERIODS[game_key])).timestamp()
                    GAME_DATA[game_key]["last_sync"] = time.time()
                
                if is_new:
                    LAST_ISSUE[game_key] = current_issue
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

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == '/' or self.path == '/index.html':
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(HTML_PAGE.encode('utf-8'))
                
            elif self.path.startswith('/api/'):
                # 防盗拦截
                if f"key={API_SECRET_KEY}" not in self.path:
                    self.send_error(401, "Unauthorized: 请输入正确的暗号")
                    return
                
                game_key = self.path.replace('/api/', '').split('?')[0]
                
                if game_key in GAME_DATA:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    with DATA_LOCK:
                        gd = GAME_DATA[game_key]
                        response_data = {"status": "success", "next_draw_ts": gd["next_ts"], "last_sync_ts": gd["last_sync"], "sync_interval": SYNC_INTERVAL, "data": gd["draws"]}
                    self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
                else:
                    self.send_error(404, "API Not Found")
            else:
                self.send_error(404, "Not Found")
        except (BrokenPipeError, ConnectionResetError): pass

    def log_message(self, format, *args): pass

HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>舰长开奖网站</title>
    <style>
        :root {
            --neon-cyan: #00f3ff; --neon-green: #39ff14; --neon-red: #ff003c; --neon-blue: #007bff;
            --bg-color: #0a0a0c; --panel-bg: rgba(20, 25, 30, 0.85); --text-main: #e0e0e0; --text-dim: #888;
        }
        body {
            background-color: var(--bg-color);
            background-image: linear-gradient(rgba(0, 243, 255, 0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 243, 255, 0.05) 1px, transparent 1px);
            background-size: 20px 20px; color: var(--text-main);
            font-family: 'Courier New', Courier, monospace; margin: 0; padding: 15px;
        }
        .header {
            text-align: center; margin-bottom: 20px; padding: 15px;
            background: var(--panel-bg); border: 1px solid var(--neon-cyan);
            box-shadow: 0 0 10px rgba(0, 243, 255, 0.2); border-radius: 8px;
        }
        .main-title {
            font-size: 24px; color: var(--neon-cyan); text-shadow: 0 0 15px rgba(0, 243, 255, 0.6);
            margin: 0 0 20px 0; letter-spacing: 3px;
        }
        .tabs { display: flex; justify-content: center; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
        .tab-btn {
            background: transparent; color: var(--text-dim); border: 1px solid rgba(0, 243, 255, 0.2);
            padding: 8px 15px; border-radius: 20px; font-family: inherit; font-size: 14px; cursor: pointer; transition: all 0.3s;
        }
        .tab-btn.active {
            color: var(--neon-cyan); border-color: var(--neon-cyan);
            box-shadow: 0 0 10px rgba(0, 243, 255, 0.3); background: rgba(0, 243, 255, 0.1); text-shadow: 0 0 5px rgba(0, 243, 255, 0.5);
        }
        .status-bar {
            display: flex; justify-content: space-around; font-size: 15px;
            color: var(--text-dim); background: rgba(0,0,0,0.3); padding: 10px; border-radius: 6px;
        }
        .status-item span { font-weight: bold; font-size: 16px; color: var(--neon-green); transition: all 0.3s; }
        .status-item span.waiting { color: var(--neon-red) !important; text-shadow: 0 0 10px rgba(255, 0, 60, 0.8); animation: pulse-red 1s infinite; }
        @keyframes pulse-red { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        
        .table-container {
            background: var(--panel-bg); border: 1px solid rgba(0, 243, 255, 0.3);
            border-radius: 8px; overflow: hidden; max-height: 65vh; overflow-y: auto;
        }
        table { width: 100%; border-collapse: collapse; text-align: center; }
        th { background: rgba(0, 243, 255, 0.1); color: var(--neon-cyan); padding: 12px 5px; font-size: 13px; position: sticky; top: 0; backdrop-filter: blur(5px); z-index: 10; }
        td { padding: 12px 5px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); font-size: 14px; }
        tr:hover { background: rgba(255, 255, 255, 0.05); }
        .issue { color: var(--text-dim); }
        .time { color: var(--text-dim); font-size: 12px; }
        .result { color: var(--neon-cyan); font-weight: bold; letter-spacing: 1px; }
        .big { color: var(--neon-red); text-shadow: 0 0 5px rgba(255,0,60,0.5); }
        .small { color: var(--neon-blue); text-shadow: 0 0 5px rgba(0,123,255,0.5); }
        @keyframes flash { 0% { background-color: rgba(0, 243, 255, 0.3); } 100% { background-color: transparent; } }
        .new-row { animation: flash 2s ease-out; }
        .loading-text { color: #ffcc00; text-align: center; padding: 20px; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 0.5; } 50% { opacity: 1; } 100% { opacity: 0.5; } }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-thumb { background: var(--neon-cyan); border-radius: 5px; }
    </style>
</head>
<body>
    <div class="header">
        <h1 class="main-title">⚡ 舰长开奖网站 ⚡</h1>
        <div class="tabs">
            <button id="btn-btc28" class="tab-btn active" onclick="switchGame('btc28')">舰长比特28</button>
            <button id="btn-fenfen28" class="tab-btn" onclick="switchGame('fenfen28')">舰长分分28</button>
            <button id="btn-JND" class="tab-btn" onclick="switchGame('JND')">舰长加拿大28</button>
        </div>
        <div class="status-bar">
            <div class="status-item">网络同步: <span id="sync-count">-</span>s</div>
            <div class="status-item">开奖倒计时: <span id="draw-count">--:--</span></div>
        </div>
    </div>
    
    <div class="table-container">
        <table>
            <thead><tr><th>期号</th><th>时间</th><th>结果</th><th>属性</th></tr></thead>
            <tbody id="table-body"><tr><td colspan="4" class="loading-text">正在建立数据链路...</td></tr></tbody>
        </table>
    </div>

    <script>
        let currentGame = 'btc28';
        const state = { btc28: { lastIssue: "", nextTs: 0, lastSync: 0 }, fenfen28: { lastIssue: "", nextTs: 0, lastSync: 0 }, JND: { lastIssue: "", nextTs: 0, lastSync: 0 } };
        const syncInterval = 5;
        let pollTimer = null, fastRetryTimer = null;

        function switchGame(game) {
            if (currentGame === game) return;
            currentGame = game;
            ['btc28', 'fenfen28', 'JND'].forEach(g => document.getElementById(`btn-${g}`).classList.remove('active'));
            document.getElementById(`btn-${game}`).classList.add('active');
            
            const elDraw = document.getElementById('draw-count');
            elDraw.innerText = "--:--"; elDraw.classList.remove('waiting');
            document.getElementById('sync-count').innerText = "-";
            document.getElementById('table-body').innerHTML = '<tr><td colspan="4" class="loading-text">正在切换数据源...</td></tr>';
            
            if (pollTimer) clearTimeout(pollTimer);
            if (fastRetryTimer) clearTimeout(fastRetryTimer);
            fetchData(true); 
        }

        function formatCountdown(seconds) {
            if (seconds < 0) return "00:00";
            if (seconds >= 60) {
                let m = Math.floor(seconds / 60), s = seconds % 60;
                return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
            }
            return seconds.toString().padStart(2, '0');
        }

        async function fetchData(isSwitch = false) {
            if (pollTimer) clearTimeout(pollTimer);
            if (fastRetryTimer) clearTimeout(fastRetryTimer);
            try {
                // 网页端自带密码访问
                const response = await fetch(`/api/${currentGame}?key=captain_8888`);
                const res = await response.json();
                if (res.status === "success") {
                    if (res.next_draw_ts > 0) {
                        state[currentGame].nextTs = res.next_draw_ts;
                        state[currentGame].lastSync = res.last_sync_ts;
                    }
                    if (res.data && res.data.length > 0) {
                        renderTable(res.data);
                        if (state[currentGame].nextTs - (Date.now()/1000) <= 0) {
                            fastRetryTimer = setTimeout(fetchData, 1000);
                        } else {
                            pollTimer = setTimeout(fetchData, syncInterval * 1000);
                        }
                    } else {
                        document.getElementById('table-body').innerHTML = '<tr><td colspan="4" class="loading-text">网络拥挤，极速重试中...</td></tr>';
                        fastRetryTimer = setTimeout(fetchData, 1000);
                    }
                }
            } catch (e) { fastRetryTimer = setTimeout(fetchData, 2000); }
        }

        function renderTable(data) {
            const tbody = document.getElementById('table-body');
            const s = state[currentGame];
            const currentLatest = data[0].issue;
            const isNew = s.lastIssue !== "" && s.lastIssue !== currentLatest;
            const container = tbody.parentElement.parentElement;
            const scrollPos = container.scrollTop;
            
            tbody.innerHTML = "";
            data.forEach((item, index) => {
                const tr = document.createElement('tr');
                if (isNew && index === 0) tr.className = 'new-row';
                let typeClass = item.type.includes('大') ? 'big' : 'small';
                tr.innerHTML = `<td class="issue">${item.issue}</td><td class="time">${item.time}</td><td class="result">${item.raw}</td><td class="${typeClass}">${item.type}</td>`;
                tbody.appendChild(tr);
            });
            s.lastIssue = currentLatest;
            if (!isNew) container.scrollTop = scrollPos;
        }

        setInterval(() => {
            const now = Date.now() / 1000, s = state[currentGame], elDraw = document.getElementById('draw-count');
            if (s.nextTs > 0) {
                let drawLeft = Math.floor(s.nextTs - now);
                if (drawLeft <= 0) { elDraw.innerText = "等待开奖"; elDraw.classList.add('waiting'); }
                else { elDraw.innerText = formatCountdown(drawLeft); elDraw.classList.remove('waiting'); }
            }
            if (s.lastSync > 0) {
                let syncLeft = Math.floor(syncInterval - (now - s.lastSync));
                document.getElementById('sync-count').innerText = syncLeft <= 0 ? syncInterval : syncLeft;
            }
        }, 1000);

        fetchData();
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    threading.Thread(target=sync_all_worker, daemon=True).start()
    print(f"✅ 服务端已启动，端口: {PORT}")
    
    server = ThreadingHTTPServer(('0.0.0.0', PORT), RequestHandler)
    server.serve_forever()
