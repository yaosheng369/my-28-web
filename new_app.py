import http.server
import socketserver
import urllib.request
import json
import time
import base64
import os

# ================= 配置区 =================
API_CONFIG = {
    "btc28": {
        "url": "https://my-28-web.onrender.com/api/btc28?admin_key=captain_8888_super_secret_key_2024",
        "name": "比特28"
    },
    "fenfen28": {
        "url": "https://my-28-web.onrender.com/api/fenfen28?admin_key=captain_8888_super_secret_key_2024",
        "name": "分分28"
    },
    "JND": {
        "url": "https://my-28-web.onrender.com/api/JND?admin_key=captain_8888_super_secret_key_2024",
        "name": "加拿大28"
    }
}

HISTORY_FILE = "predict_history.json"
CACHE_EXPIRE_SECONDS = 10 
API_CACHE = {} 

# ================= 预测算法区 =================
def predict_btc28(draws):
    recent_10 = draws[:10]
    counts = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
    for d in recent_10: counts[d['type']] += 1
    kill = max(counts, key=counts.get)
    return {"kill": kill, "push": [k for k in counts.keys() if k != kill]}

def predict_fenfen28(draws):
    last_type = draws[0]['type']
    consecutive = 0
    for d in draws:
        if d['type'] == last_type: consecutive += 1
        else: break
    if consecutive >= 3: kill = last_type
    else:
        recent_5 = draws[:5]
        counts = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
        for d in recent_5: counts[d['type']] += 1
        kill = min(counts, key=counts.get) 
    return {"kill": kill, "push": [k for k in ["大单", "大双", "小单", "小双"] if k != kill]}

def predict_JND(draws):
    recent_15 = draws[:15]
    da_cnt, xiao_cnt, dan_cnt, shuang_cnt = 0, 0, 0, 0
    for d in recent_15:
        if '大' in d['type']: da_cnt += 1
        else: xiao_cnt += 1
        if '单' in d['type']: dan_cnt += 1
        else: shuang_cnt += 1
    if da_cnt > xiao_cnt + 4: kill_size = '大'
    elif xiao_cnt > da_cnt + 4: kill_size = '小'
    else: kill_size = '大' if da_cnt > xiao_cnt else '小'
    if dan_cnt > shuang_cnt + 4: kill_parity = '单'
    elif shuang_cnt > dan_cnt + 4: kill_parity = '双'
    else: kill_parity = '单' if dan_cnt > shuang_cnt else '双'
    kill = kill_size + kill_parity
    return {"kill": kill, "push": [k for k in ["大单", "大双", "小单", "小双"] if k != kill]}

# ================= 记录保存 =================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# ================= 前端 HTML =================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>28智能预测系统</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
        body { font-family: sans-serif; background-color: #f5f7fa; color: #333; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); overflow: hidden; }
        .header { background: #2c3e50; color: #fff; padding: 20px; text-align: center; }
        .mode-switch { display: flex; background: #1a252f; }
        .mode-btn { flex: 1; padding: 15px; text-align: center; cursor: pointer; color: #bdc3c7; font-weight: bold; font-size: 16px; transition: 0.3s; }
        .mode-btn.active { background: #e74c3c; color: #fff; }
        .tabs { display: flex; background: #34495e; }
        .tab { flex: 1; padding: 12px; text-align: center; cursor: pointer; color: #bdc3c7; font-weight: bold; font-size: 14px; }
        .tab.active { background: #fff; color: #2c3e50; border-top: 3px solid #3498db; }
        .content { padding: 20px; }
        #lottery-view { display: none; }
        .lottery-list { background: #fafafa; border: 1px solid #eee; border-radius: 8px; overflow: hidden; }
        .lottery-item { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #eee; font-size: 15px; }
        .lottery-item:nth-child(even) { background: #fff; }
        .lottery-issue { color: #7f8c8d; font-size: 13px; width: 120px; }
        .lottery-raw { flex: 1; font-weight: bold; font-size: 16px; }
        .lottery-type { width: 65px; text-align: center; border-radius: 4px; padding: 5px 0; font-size: 13px; color: #fff; font-weight: bold; }
        .type-大单, .type-大双 { background: #e74c3c; }
        .type-小单, .type-小双 { background: #3498db; }
        #predict-view { display: block; }
        .countdown-area { text-align: center; margin-bottom: 15px; padding: 15px; background: #ecf0f1; border-radius: 8px; }
        .countdown-time { font-size: 32px; font-weight: bold; color: #e74c3c; }
        .countdown-label { font-size: 14px; color: #7f8c8d; margin-top: 5px; }
        .prediction-area { display: flex; gap: 15px; margin-bottom: 20px; }
        .pred-box { flex: 1; padding: 20px; border-radius: 8px; text-align: center; }
        .kill-box { background: #fde8e8; border: 2px solid #f5c6c6; }
        .push-box { background: #e8f8f5; border: 2px solid #a3e4d7; }
        .pred-title { font-size: 15px; margin-bottom: 10px; color: #555; font-weight: bold; }
        .pred-value { font-size: 26px; font-weight: bold; }
        .kill-value { color: #e74c3c; }
        .push-value { color: #27ae60; font-size: 20px; }
        .list-title { font-size: 16px; font-weight: bold; margin-bottom: 10px; border-left: 4px solid #3498db; padding-left: 10px; margin-top: 20px; }
        .record-list { max-height: 350px; overflow-y: auto; background: #fafafa; border: 1px solid #eee; border-radius: 8px; }
        .record-item { display: flex; flex-direction: column; gap: 5px; padding: 12px 15px; border-bottom: 1px solid #eee; background: #fff; font-size: 14px; }
        .record-header { display: flex; justify-content: space-between; color: #7f8c8d; font-size: 12px; }
        .record-body { display: flex; justify-content: space-between; align-items: center; font-weight: bold; }
        .win-tag { color: #fff; background: #e74c3c; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
        .lose-tag { color: #fff; background: #95a5a6; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
        .pending-tag { color: #fff; background: #f39c12; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
        .loading { text-align: center; padding: 30px; color: #95a5a6; font-size: 16px; }
        .error { text-align: center; padding: 30px; color: #e74c3c; font-size: 16px; }
        .btn { padding: 8px 16px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; margin-top: 10px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header"><h1>舰长 28 系统</h1><p style="font-size: 13px; margin-top: 5px; color: #bdc3c7;">开奖大厅 + 智能预测</p></div>
    <div class="mode-switch">
        <div class="mode-btn active" data-mode="lottery" onclick="switchMode('lottery')">📊 开奖大厅</div>
        <div class="mode-btn" data-mode="predict" onclick="switchMode('predict')">🎯 智能预测</div>
    </div>
    <div class="tabs">
        <div class="tab active" data-game="btc28" onclick="switchGame('btc28')">比特28</div>
        <div class="tab" data-game="fenfen28" onclick="switchGame('fenfen28')">分分28</div>
        <div class="tab" data-game="JND" onclick="switchGame('JND')">加拿大28</div>
    </div>
    <div class="content">
        <div id="lottery-view"><div class="lottery-list" id="lottery-list"><div class="loading">加载中...</div></div></div>
        <div id="predict-view">
            <div class="countdown-area">
                <div class="countdown-label">距离下一期开奖还有</div>
                <div class="countdown-time" id="countdown">--:--</div>
                <div class="countdown-label" id="sync-status">正在同步...</div>
            </div>
            <div class="prediction-area">
                <div class="pred-box kill-box"><div class="pred-title">🚫 本期绝杀</div><div class="pred-value kill-value" id="kill-type">--</div></div>
                <div class="pred-box push-box"><div class="pred-title">🀄 推荐三组</div><div class="pred-value push-value" id="push-types">--</div></div>
            </div>
            <div class="list-title">历史预测记录</div>
            <div class="record-list" id="record-list"><div class="loading">加载中...</div></div>
            <div class="list-title">近 30 期开奖结果</div>
            <div class="record-list" id="draws-list"><div class="loading">加载中...</div></div>
        </div>
    </div>
</div>
<script>
    document.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('keydown', e => {
        if (e.key === 'F12' || (e.ctrlKey && e.shiftKey && ['I', 'i', 'J', 'j', 'C', 'c'].includes(e.key)) || (e.ctrlKey && ['U', 'u'].includes(e.key))) { e.preventDefault(); return false; }
    });

    let currentGame = 'btc28', currentMode = 'lottery', timerInterval = null, timeOffset = 0; 
    function switchMode(mode) {
        currentMode = mode;
        document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
        document.getElementById('lottery-view').style.display = mode === 'lottery' ? 'block' : 'none';
        document.getElementById('predict-view').style.display = mode === 'predict' ? 'block' : 'none';
        if (mode === 'lottery') fetchLottery(); else fetchPredict();
    }
    function switchGame(game) {
        currentGame = game;
        document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab.dataset.game === game));
        if (currentMode === 'lottery') fetchLottery(); else fetchPredict();
    }
    function fetchLottery() {
        const el = document.getElementById('lottery-list');
        el.innerHTML = '<div class="loading">极速加载中...</div>';
        fetch(`/api/lottery/${currentGame}`).then(res => res.json()).then(res => {
            if (res.error) { el.innerHTML = `<div class="error">请求失败: ${res.error}<br><br><button class="btn" onclick="fetchLottery()">点击重试</button></div>`; return; }
            const data = JSON.parse(atob(res.payload));
            let html = '';
            data.draws.forEach(d => { html += `<div class="lottery-item"><div class="lottery-issue">${d.issue}<br>${d.time}</div><div class="lottery-raw">${d.raw}</div><div class="lottery-type type-${d.type}">${d.type}</div></div>`; });
            el.innerHTML = html;
        }).catch(err => el.innerHTML = '<div class="error">网络错误<br><br><button class="btn" onclick="fetchLottery()">点击重试</button></div>');
    }
    function fetchPredict() {
        document.getElementById('record-list').innerHTML = '<div class="loading">极速加载中...</div>';
        document.getElementById('draws-list').innerHTML = '<div class="loading">加载中...</div>';
        document.getElementById('kill-type').innerText = '--'; document.getElementById('push-types').innerText = '--'; document.getElementById('sync-status').innerText = '请求中...'; clearInterval(timerInterval);
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 8000);
        fetch(`/api/proxy/${currentGame}`, { signal: controller.signal }).then(res => { clearTimeout(timeoutId); return res.json(); }).then(res => {
            if (res.error) { document.getElementById('draws-list').innerHTML = `<div class="error">请求失败: ${res.error}<br><br><button class="btn" onclick="fetchPredict()">点击重试</button></div>`; document.getElementById('record-list').innerHTML = ''; document.getElementById('sync-status').innerText = '同步失败'; return; }
            const data = JSON.parse(atob(res.payload));
            document.getElementById('kill-type').innerText = data.prediction.kill;
            document.getElementById('push-types').innerText = data.prediction.push.join(' | ');
            let drawsHtml = '';
            data.draws.forEach(d => { drawsHtml += `<div class="lottery-item"><div class="lottery-issue">${d.issue}<br>${d.time}</div><div class="lottery-raw">${d.raw}</div><div class="lottery-type type-${d.type}">${d.type}</div></div>`; });
            document.getElementById('draws-list').innerHTML = drawsHtml;
            let recordHtml = '';
            if(data.predict_records && data.predict_records.length > 0) {
                data.predict_records.slice().reverse().forEach(r => {
                    let statusTag = r.status === 'pending' ? '<span class="pending-tag">等待开奖</span>' : (r.is_win ? '<span class="win-tag">🀄 中奖</span>' : '<span class="lose-tag">未中</span>');
                    let actualText = r.actual ? `开: ${r.actual}` : '开: --';
                    recordHtml += `<div class="record-item"><div class="record-header"><span>${r.issue}</span>${statusTag}</div><div class="record-body"><span>杀: <span style="color:#e74c3c">${r.kill}</span></span><span>推: <span style="color:#27ae60">${r.push.join(',')}</span></span><span>${actualText}</span></div></div>`;
                });
            } else { recordHtml = '<div class="loading">暂无预测记录</div>'; }
            document.getElementById('record-list').innerHTML = recordHtml;
            timeOffset = data.server_time - Math.floor(Date.now() / 1000);
            document.getElementById('sync-status').innerText = `已同步 (周期: ${data.period}秒)`;
            startCountdown(data.next_ts);
        }).catch(err => {
            clearTimeout(timeoutId); let errMsg = err.name === 'AbortError' ? '请求超时，请重试' : '网络错误';
            document.getElementById('draws-list').innerHTML = `<div class="error">${errMsg}<br><br><button class="btn" onclick="fetchPredict()">点击重试</button></div>`; document.getElementById('record-list').innerHTML = ''; document.getElementById('sync-status').innerText = '连接失败';
        });
    }
    function startCountdown(nextTs) {
        clearInterval(timerInterval);
        function updateTimer() {
            const remaining = nextTs - (Math.floor(Date.now() / 1000) + timeOffset);
            if (remaining <= 0) { document.getElementById('countdown').innerText = '00:00'; clearInterval(timerInterval); setTimeout(fetchPredict, 2000); return; }
            document.getElementById('countdown').innerText = `${Math.floor(remaining / 60).toString().padStart(2, '0')}:${(remaining % 60).toString().padStart(2, '0')}`;
        }
        updateTimer(); timerInterval = setInterval(updateTimer, 1000);
    }
    fetchLottery();
</script>
</body>
</html>
"""

# ================= 原生 HTTP 服务器 (适配云环境) =================
class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class MyHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def get_api_data(self, game_type):
        now = time.time()
        if game_type in API_CACHE:
            cache_time, cache_data = API_CACHE[game_type]
            if now - cache_time < CACHE_EXPIRE_SECONDS: return cache_data
        req = urllib.request.Request(API_CONFIG[game_type]["url"], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode('utf-8'))
        API_CACHE[game_type] = (now, data)
        return data

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
        elif self.path.startswith('/api/lottery/'):
            game_type = self.path.split('/')[-1]
            if game_type not in API_CONFIG: return self.send_error(400)
            try:
                data = self.get_api_data(game_type)
                result = {"name": data.get('name'), "draws": data.get('draws', [])[:30]}
                b64_str = base64.b64encode(json.dumps(result).encode('utf-8')).decode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"payload": b64_str}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif self.path.startswith('/api/proxy/'):
            game_type = self.path.split('/')[-1]
            if game_type not in API_CONFIG: return self.send_error(400)
            try:
                data = self.get_api_data(game_type)
                draws = data.get('draws', [])
                if not draws: raise Exception("API 数据为空")
                if game_type == 'btc28': prediction = predict_btc28(draws)
                elif game_type == 'fenfen28': prediction = predict_fenfen28(draws)
                else: prediction = predict_JND(draws)
                history = load_history()
                if game_type not in history: history[game_type] = []
                game_history = history[game_type]
                if game_history:
                    last_record = game_history[-1]
                    if last_record["status"] == "pending":
                        last_record["actual"] = draws[0]['type']
                        last_record["is_win"] = (draws[0]['type'] != last_record["kill"])
                        last_record["status"] = "settled"
                latest_issue = draws[0].get('issue')
                if not game_history or game_history[-1]["issue"] != latest_issue:
                    game_history.append({"issue": latest_issue, "kill": prediction["kill"], "push": prediction["push"], "actual": None, "is_win": None, "status": "pending"})
                    if len(game_history) > 50: game_history.pop(0)
                save_history(history)
                result = {"name": data.get('name'), "period": data.get('period'), "next_ts": data.get('next_ts'), "server_time": data.get('server_time'), "draws": draws[:30], "prediction": prediction, "predict_records": game_history}
                b64_str = base64.b64encode(json.dumps(result).encode('utf-8')).decode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"payload": b64_str}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"服务器响应慢: {str(e)}"}).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 5000))
    server = ThreadedHTTPServer(("0.0.0.0", PORT), MyHandler)
    print(f"✅ 服务已启动！端口: {PORT}")
    server.serve_forever()
