import http.server
import socketserver
import urllib.request
import json
import time
import base64
import os
import re
from urllib.parse import urlparse, parse_qs

# ================= 配置区 =================
API_CONFIG = {
    "btc28": {"url": "https://my-28-web.onrender.com/api/btc28?admin_key=captain_8888_super_secret_key_2024", "name": "比特28"},
    "fenfen28": {"url": "https://my-28-web.onrender.com/api/fenfen28?admin_key=captain_8888_super_secret_key_2024", "name": "分分28"},
    "JND": {"url": "https://my-28-web.onrender.com/api/JND?admin_key=captain_8888_super_secret_key_2024", "name": "加拿大28"}
}

HISTORY_FILE = "predict_history.json"
CACHE_EXPIRE_SECONDS = 3
API_CACHE = {} 

# ================= 300套独立算法矩阵 (明文) =================
# 我们生成了300个不同的参数组合，保证每一期的算法都不同，绝不固定死杀。
ALGORITHMS = []
for i in range(1, 301):
    ALGORITHMS.append({
        "id": i,
        "type": i % 5,  # 0:冷热 1:连号 2:均值 3:期号模 4:混合
        "window": (i % 15) + 5, # 窗口 5-19
        "mod_val": (i % 4) + 2   # 模数 2-5
    })

def dynamic_predict(draws, issue_str):
    """核心：根据期号动态调用 300 套算法中的一套"""
    # 提取期号尾数作为算法索引 (保证每一期算法不同)
    match = re.search(r'(\d+)$', str(issue_str))
    if match:
        algo_index = int(match.group(1)) % 300
    else:
        algo_index = int(time.time()) % 300
        
    algo = ALGORITHMS[algo_index]
    combos = ["大单", "大双", "小单", "小双"]
    recent = draws[:algo["window"]]
    counts = {c: 0 for c in combos}
    for d in recent: counts[d['type']] += 1
    
    # 执行具体算法
    if algo["type"] == 0: # 冷热
        kill = max(counts, key=counts.get) if algo["id"] % 2 == 0 else min(counts, key=counts.get)
    elif algo["type"] == 1: # 连号
        last = recent[0]['type']
        streak = sum(1 for d in recent if d['type'] == last)
        kill = last if streak >= 2 else next(c for c in combos if c != last)
    elif algo["type"] == 2: # 均值回归
        da = sum(1 for d in recent if '大' in d['type'])
        dan = sum(1 for d in recent if '单' in d['type'])
        kill = ('大' if da > len(recent)/2 else '小') + ('单' if dan > len(recent)/2 else '双')
    elif algo["type"] == 3: # 期号模
        kill = combos[int(match.group(1)) % algo["mod_val"]] if match else "大单"
    else: # 混合随机(基于时间和期号)
        seed = (int(time.time()) + int(match.group(1)) if match else 0)
        kill = combos[seed % 4]
        
    if kill not in combos: kill = combos[0]
    return {"kill": kill, "push": [c for c in combos if c != kill]}

def get_prev_issue(issue_str, offset=1):
    match = re.search(r'(\d+)$', str(issue_str))
    if match:
        num_str = match.group(1)
        prefix = str(issue_str)[:-len(num_str)]
        return prefix + str(int(num_str) - offset).zfill(len(num_str))
    return "未知"

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
    <title>SKYNET 28 预测终端</title>
    <style>
        :root { --bg: #050505; --panel: rgba(15, 20, 30, 0.75); --border: rgba(0, 243, 255, 0.2); --cyan: #00f3ff; --red: #ff003c; --green: #00ff88; --text: #e2e8f0; --muted: #64748b; }
        * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
        body { font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); padding: 15px; background-image: linear-gradient(rgba(0,243,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,243,255,0.03) 1px, transparent 1px); background-size: 30px 30px; }
        .container { max-width: 800px; margin: 0 auto; position: relative; }
        .header { text-align: center; padding: 20px 0; position: relative; margin-bottom: 20px; }
        .header h1 { font-size: 28px; letter-spacing: 5px; color: var(--cyan); text-shadow: 0 0 10px var(--cyan); }
        .sync-status { position: absolute; top: 25px; right: 0; font-size: 12px; display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.5); padding: 5px 12px; border-radius: 4px; border: 1px solid var(--border); }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
        .dot.success { background: var(--green); box-shadow: 0 0 10px var(--green); }
        .dot.error { background: var(--red); box-shadow: 0 0 10px var(--red); }
        .mode-switch { display: flex; gap: 10px; margin-bottom: 20px; }
        .mode-btn { flex: 1; padding: 15px; text-align: center; cursor: pointer; color: var(--muted); font-weight: bold; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; }
        .mode-btn.active { color: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 15px rgba(0,243,255,0.3); }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab { flex: 1; padding: 12px; text-align: center; cursor: pointer; color: var(--muted); background: var(--panel); border: 1px solid var(--border); border-radius: 6px; font-weight: bold; }
        .tab.active { color: #fff; background: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 20px rgba(0,243,255,0.6); }
        .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; backdrop-filter: blur(10px); }
        .dashboard { display: flex; gap: 15px; }
        .timer-box { flex: 1; text-align: center; background: rgba(0,0,0,0.3); border-radius: 8px; padding: 15px; border: 1px solid rgba(255,255,255,0.05); }
        .timer-label { font-size: 13px; color: var(--muted); margin-bottom: 8px; }
        .timer-val { font-family: 'Courier New', monospace; font-size: 38px; font-weight: 900; color: var(--cyan); text-shadow: 0 0 15px rgba(0,243,255,0.6); }
        .timer-val.waiting { color: var(--red); text-shadow: 0 0 20px var(--red); font-size: 24px; height: 45px; display: flex; align-items: center; justify-content: center; animation: pulse 0.8s infinite alternate; }
        @keyframes pulse { from { opacity: 0.5; } to { opacity: 1; } }
        .prediction-area { display: flex; gap: 15px; margin-bottom: 20px; }
        .pred-box { flex: 1; padding: 20px 15px; text-align: center; border-radius: 12px; display: flex; flex-direction: column; align-items: center; }
        .kill-box { background: rgba(255,0,60,0.05); border: 1px solid rgba(255,0,60,0.3); }
        .push-box { background: rgba(0,255,136,0.05); border: 1px solid rgba(0,255,136,0.3); }
        .target-issue { font-size: 12px; color: #fff; background: rgba(0,0,0,0.6); padding: 4px 12px; border-radius: 20px; margin-bottom: 15px; }
        .target-issue span { color: var(--cyan); font-weight: bold; }
        .pred-title { font-size: 14px; color: var(--muted); margin-bottom: 10px; }
        .pred-value { font-size: 36px; font-weight: 900; }
        .kill-value { color: var(--red); text-shadow: 0 0 15px rgba(255,0,60,0.6); }
        .push-value { color: var(--green); text-shadow: 0 0 15px rgba(0,255,136,0.6); font-size: 22px; }
        .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
        .stat-item { text-align: center; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px; }
        .stat-label { font-size: 12px; color: var(--muted); margin-bottom: 5px; }
        .stat-val { font-size: 20px; font-weight: bold; }
        .stat-val.green { color: var(--green); }
        .stat-val.red { color: var(--red); }
        .list-title { font-size: 15px; font-weight: bold; margin-bottom: 12px; color: var(--cyan); border-left: 4px solid var(--cyan); padding-left: 10px; }
        .list-container { max-height: 400px; overflow-y: auto; }
        .lottery-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 15px; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .lottery-issue { color: var(--muted); font-size: 12px; width: 100px; }
        .lottery-raw { flex: 1; font-weight: bold; font-size: 16px; font-family: monospace; }
        .lottery-type { width: 60px; text-align: center; border-radius: 4px; padding: 4px 0; font-size: 12px; font-weight: bold; }
        .type-大单, .type-大双 { background: rgba(255,0,60,0.15); color: var(--red); border: 1px solid rgba(255,0,60,0.3); }
        .type-小单, .type-小双 { background: rgba(0,243,255,0.15); color: var(--cyan); border: 1px solid rgba(0,243,255,0.3); }
        .record-item { padding: 12px 15px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px; }
        .record-header { display: flex; justify-content: space-between; color: var(--muted); font-size: 12px; margin-bottom: 8px; }
        .record-body { display: flex; justify-content: space-between; align-items: center; font-weight: bold; }
        .win-tag { color: var(--red); border: 1px solid var(--red); padding: 2px 8px; border-radius: 4px; font-size: 12px; box-shadow: 0 0 10px rgba(255,0,60,0.3); }
        .lose-tag { color: #334155; background: #0f172a; border: 1px solid #334155; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .pending-tag { color: #f59e0b; border: 1px solid #f59e0b; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .loading { text-align: center; padding: 30px; color: var(--cyan); }
        .error { text-align: center; padding: 30px; color: var(--red); }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>SKYNET 28</h1>
        <div class="sync-status"><div class="dot" id="sync-dot"></div><span id="sync-text">未连接</span></div>
    </div>
    <div class="mode-switch">
        <div class="mode-btn active" data-mode="predict" onclick="switchMode('predict')">🎯 智能预测</div>
        <div class="mode-btn" data-mode="lottery" onclick="switchMode('lottery')">📊 开奖大厅</div>
    </div>
    <div class="tabs">
        <div class="tab active" data-game="btc28" onclick="switchGame('btc28')">比特28</div>
        <div class="tab" data-game="fenfen28" onclick="switchGame('fenfen28')">分分28</div>
        <div class="tab" data-game="JND" onclick="switchGame('JND')">加拿大28</div>
    </div>

    <div id="predict-view" style="display:block;">
        <div class="panel"><div class="dashboard">
            <div class="timer-box"><div class="timer-label">本期开奖倒计时</div><div class="timer-val" id="draw-timer">--:--</div></div>
            <div class="timer-box"><div class="timer-label">下期预测锁定状态</div><div class="timer-val" id="predict-timer">--:--</div></div>
        </div></div>
        <div class="prediction-area">
            <div class="pred-box kill-box"><div class="target-issue">目标期号: <span id="kill-issue">--</span></div><div class="pred-title">绝杀组合</div><div class="pred-value kill-value" id="kill-type">--</div></div>
            <div class="pred-box push-box"><div class="target-issue">目标期号: <span id="push-issue">--</span></div><div class="pred-title">推荐三组</div><div class="pred-value push-value" id="push-types">--</div></div>
        </div>
        <div class="panel">
            <div class="list-title" style="margin-bottom: 15px;">📈 战绩统计 (近20期)</div>
            <div class="stats-grid">
                <div class="stat-item"><div class="stat-label">总中奖</div><div class="stat-val green" id="stat-total-win">0</div></div>
                <div class="stat-item"><div class="stat-label">总未中</div><div class="stat-val red" id="stat-total-lose">0</div></div>
                <div class="stat-item"><div class="stat-label">当前连对</div><div class="stat-val green" id="stat-streak-win">0</div></div>
                <div class="stat-item"><div class="stat-label">当前连错</div><div class="stat-val red" id="stat-streak-lose">0</div></div>
            </div>
        </div>
        <div class="panel"><div class="list-title">📜 历史预测记录 (近20期)</div><div class="list-container" id="record-list"><div class="loading">加载中...</div></div></div>
        <div class="panel"><div class="list-title">📊 近期开奖结果</div><div class="list-container" id="draws-list"><div class="loading">加载中...</div></div></div>
    </div>
    <div id="lottery-view" style="display:none;">
        <div class="panel"><div class="list-title">📊 近 30 期开奖数据</div><div class="list-container" id="lottery-list"><div class="loading">加载中...</div></div></div>
    </div>
</div>

<script>
    document.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('keydown', e => { if (e.key === 'F12' || (e.ctrlKey && e.shiftKey && ['I', 'i', 'J', 'j', 'C', 'c'].includes(e.key))) { e.preventDefault(); return false; } });

    let currentGame = 'btc28', currentMode = 'predict', syncInterval = null, isFetching = false;
    let globalNextTs = 0, globalTimeOffset = 0, isWaiting = false;
    const drawTimerEl = document.getElementById('draw-timer'), predictTimerEl = document.getElementById('predict-timer');

    function setSyncStatus(status) {
        document.getElementById('sync-dot').className = 'dot ' + status;
        document.getElementById('sync-text').innerText = status === 'success' ? '同步成功' : (status === 'error' ? '同步失败' : '同步中...');
    }

    setInterval(() => {
        if (currentMode !== 'predict' || globalNextTs === 0) return;
        const remaining = globalNextTs - (Math.floor(Date.now() / 1000) + globalTimeOffset);
        if (remaining > 0) {
            if (isWaiting) { isWaiting = false; drawTimerEl.classList.remove('waiting'); predictTimerEl.classList.remove('waiting'); }
            const m = Math.floor(remaining / 60).toString().padStart(2, '0');
            const s = (remaining % 60).toString().padStart(2, '0');
            drawTimerEl.innerText = `${m}:${s}`; predictTimerEl.innerText = `${m}:${s}`;
        } else {
            if (!isWaiting) { isWaiting = true; drawTimerEl.classList.add('waiting'); predictTimerEl.classList.add('waiting'); fetchPredictData(); }
            drawTimerEl.innerText = '等待开奖...'; predictTimerEl.innerText = '等待开奖...';
        }
    }, 1000);

    function switchMode(mode) {
        currentMode = mode;
        document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
        document.getElementById('lottery-view').style.display = mode === 'lottery' ? 'block' : 'none';
        document.getElementById('predict-view').style.display = mode === 'predict' ? 'block' : 'none';
        clearInterval(syncInterval); 
        if (mode === 'lottery') fetchLottery(); else startPredictMode();
    }
    function switchGame(game) {
        currentGame = game;
        document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab.dataset.game === game));
        clearInterval(syncInterval); 
        if (currentMode === 'lottery') fetchLottery(); else startPredictMode();
    }

    function fetchLottery() {
        const el = document.getElementById('lottery-list'); el.innerHTML = '<div class="loading">加载中...</div>'; setSyncStatus('syncing');
        fetch(`/api/lottery/${currentGame}?_s=${btoa("secure_28_web_2024")}`).then(res => res.json()).then(res => {
            if (res.error) { el.innerHTML = `<div class="error">${res.error}</div>`; setSyncStatus('error'); return; }
            const data = JSON.parse(atob(res.payload)); let html = '';
            data.draws.forEach(d => { html += `<div class="lottery-item"><div class="lottery-issue">${d.issue}<br>${d.time}</div><div class="lottery-raw">${d.raw}</div><div class="lottery-type type-${d.type}">${d.type}</div></div>`; });
            el.innerHTML = html; setSyncStatus('success');
        }).catch(err => { el.innerHTML = '<div class="error">网络错误</div>'; setSyncStatus('error'); });
    }

    function startPredictMode() {
        globalNextTs = 0; isWaiting = false;
        document.getElementById('record-list').innerHTML = '<div class="loading">计算中...</div>';
        document.getElementById('draws-list').innerHTML = '<div class="loading">加载中...</div>';
        fetchPredictData();
        clearInterval(syncInterval); syncInterval = setInterval(fetchPredictData, 3000);
    }

    function fetchPredictData() {
        if (isFetching) return; isFetching = true; setSyncStatus('syncing');
        const controller = new AbortController(); const timeoutId = setTimeout(() => controller.abort(), 6000);
        fetch(`/api/proxy/${currentGame}?_s=${btoa("secure_28_web_2024")}`, { signal: controller.signal }).then(res => { clearTimeout(timeoutId); return res.json(); }).then(res => {
            isFetching = false;
            if (res.error) { setSyncStatus('error'); document.getElementById('draws-list').innerHTML = `<div class="error">API源响应超时或休眠中</div>`; return; }
            renderPredictData(JSON.parse(atob(res.payload))); setSyncStatus('success');
        }).catch(err => { isFetching = false; setSyncStatus('error'); });
    }

    function renderPredictData(data) {
        document.getElementById('kill-type').innerText = data.prediction.kill;
        document.getElementById('push-types').innerText = data.prediction.push.join(' | ');
        document.getElementById('kill-issue').innerText = data.next_issue;
        document.getElementById('push-issue').innerText = data.next_issue;
        
        let records = data.predict_records || [];
        let totalWin = 0, totalLose = 0, streakWin = 0, streakLose = 0, currentStreakType = null; 
        records.forEach(r => { if (r.status === 'settled') { if (r.is_win) totalWin++; else totalLose++; } });
        for (let i = records.length - 1; i >= 0; i--) {
            let r = records[i];
            if (r.status !== 'settled') continue; 
            if (currentStreakType === null) { currentStreakType = r.is_win ? 'win' : 'lose'; if (currentStreakType === 'win') streakWin++; else streakLose++; }
            else { if (r.is_win && currentStreakType === 'win') streakWin++; else if (!r.is_win && currentStreakType === 'lose') streakLose++; else break; }
        }
        document.getElementById('stat-total-win').innerText = totalWin;
        document.getElementById('stat-total-lose').innerText = totalLose;
        document.getElementById('stat-streak-win').innerText = streakWin;
        document.getElementById('stat-streak-lose').innerText = streakLose;

        let recordHtml = '';
        let reversedRecords = [...records].reverse(); 
        if(reversedRecords.length > 0) {
            reversedRecords.forEach(r => {
                let statusTag = r.status === 'pending' ? '<span class="pending-tag">等待开奖</span>' : (r.is_win ? '<span class="win-tag">🀄 中奖</span>' : '<span class="lose-tag">未中</span>');
                let actualText = r.actual ? `开: ${r.actual}` : '开: --';
                let killColor = r.is_win ? 'color:var(--muted)' : 'color:var(--red)';
                recordHtml += `<div class="record-item"><div class="record-header"><span>期号: ${r.issue}</span>${statusTag}</div><div class="record-body"><span>杀: <span style="${killColor}">${r.kill}</span></span><span>推: <span style="color:var(--green)">${r.push.join(',')}</span></span><span>${actualText}</span></div></div>`;
            });
        } else { recordHtml = '<div class="loading">暂无记录</div>'; }
        document.getElementById('record-list').innerHTML = recordHtml;

        let drawsHtml = '';
        data.draws.forEach(d => { drawsHtml += `<div class="lottery-item"><div class="lottery-issue">${d.issue}<br>${d.time}</div><div class="lottery-raw">${d.raw}</div><div class="lottery-type type-${d.type}">${d.type}</div></div>`; });
        document.getElementById('draws-list').innerHTML = drawsHtml;

        globalNextTs = data.next_ts; globalTimeOffset = data.server_time - Math.floor(Date.now() / 1000);
    }
    startPredictMode();
</script>
</body>
</html>
"""

# ================= 后端服务 =================
class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class MyHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def verify_security(self):
        query = parse_qs(urlparse(self.path).query)
        return '_s' in query and query['_s'][0] == base64.b64encode(("secure_28_web_2024").encode()).decode()

    def get_api_data(self, game_type):
        now = time.time()
        if game_type in API_CACHE:
            cache_time, cache_data = API_CACHE[game_type]
            if now - cache_time < CACHE_EXPIRE_SECONDS: return cache_data
        req = urllib.request.Request(API_CONFIG[game_type]["url"], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        API_CACHE[game_type] = (now, data)
        return data

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            return

        if not self.verify_security():
            self.send_response(403)
            self.end_headers()
            return

        parsed_path = urlparse(self.path).path
        if parsed_path.startswith('/api/lottery/'):
            game_type = parsed_path.split('/')[-1]
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
                self.end_headers()
                
        elif parsed_path.startswith('/api/proxy/'):
            game_type = parsed_path.split('/')[-1]
            if game_type not in API_CONFIG: return self.send_error(400)
            try:
                data = self.get_api_data(game_type)
                draws = data.get('draws', [])
                if not draws: raise Exception("API 数据为空")
                
                latest_issue = draws[0].get('issue')
                next_issue = get_prev_issue(latest_issue, -1) # 反推下一期
                
                # 核心生成连贯历史记录
                history = load_history()
                if game_type not in history: history[game_type] = []
                game_history = history[game_type]
                
                # 如果记录不够 20 期，基于最新数据，连贯地倒推生成
                if len(game_history) < 20:
                    game_history = []
                    for i in range(len(draws)-1, max(-1, len(draws)-21), -1):
                        past_draw = draws[i]
                        past_issue = past_draw['issue']
                        past_pred = dynamic_predict(draws[i:], past_issue)
                        game_history.append({
                            "issue": past_issue,
                            "kill": past_pred['kill'],
                            "push": past_pred['push'],
                            "actual": past_draw['type'],
                            "is_win": (past_draw['type'] != past_pred['kill']),
                            "status": "settled"
                        })
                else:
                    # 结算上一期
                    last_record = game_history[-1]
                    if last_record["status"] == "pending":
                        last_record["actual"] = draws[0]['type']
                        last_record["is_win"] = (draws[0]['type'] != last_record["kill"])
                        last_record["status"] = "settled"
                    
                    # 生成新一期
                    if game_history[-1]["issue"] != latest_issue:
                        pred = dynamic_predict(draws, next_issue)
                        game_history.append({"issue": next_issue, "kill": pred["kill"], "push": pred["push"], "actual": None, "is_win": None, "status": "pending"})
                
                game_history = game_history[-20:]
                save_history({game_type: game_history})
                
                # 生成当前这期的预测
                current_pred = dynamic_predict(draws, next_issue)
                
                result = {
                    "name": data.get('name'), "period": data.get('period'), 
                    "next_ts": data.get('next_ts'), "server_time": data.get('server_time'), 
                    "draws": draws[:30], "prediction": current_pred, 
                    "predict_records": game_history, "next_issue": next_issue
                }
                
                b64_str = base64.b64encode(json.dumps(result).encode('utf-8')).decode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"payload": b64_str}).encode('utf-8'))
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"API源无响应/超时 ({str(e)})"}).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 5000))
    server = ThreadedHTTPServer(("0.0.0.0", PORT), MyHandler)
    server.serve_forever()
