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

# ================= 预测算法区 =================
def predict_btc28(draws):
    if len(draws) < 10: return {"kill": "小单", "push": ["大单", "大双", "小双"]}
    counts = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
    for d in draws[:10]: counts[d['type']] += 1
    kill = max(counts, key=counts.get)
    return {"kill": kill, "push": [k for k in counts.keys() if k != kill]}

def predict_fenfen28(draws):
    if len(draws) < 5: return {"kill": "小双", "push": ["大单", "大双", "小单"]}
    last_type = draws[0]['type']
    consecutive = 0
    for d in draws:
        if d['type'] == last_type: consecutive += 1
        else: break
    if consecutive >= 3: kill = last_type
    else:
        counts = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
        for d in draws[:5]: counts[d['type']] += 1
        kill = min(counts, key=counts.get) 
    return {"kill": kill, "push": [k for k in ["大单", "大双", "小单", "小双"] if k != kill]}

def predict_JND(draws):
    if len(draws) < 15: return {"kill": "大单", "push": ["大双", "小单", "小双"]}
    da, xi, dan, sh = 0, 0, 0, 0
    for d in draws[:15]:
        if '大' in d['type']: da += 1
        else: xi += 1
        if '单' in d['type']: dan += 1
        else: sh += 1
    kill_size = '大' if da > xi + 4 else ('小' if xi > da + 4 else ('大' if da > xi else '小'))
    kill_parity = '单' if dan > sh + 4 else ('双' if sh > dan + 4 else ('单' if dan > sh else '双'))
    kill = kill_size + kill_parity
    return {"kill": kill, "push": [k for k in ["大单", "大双", "小单", "小双"] if k != kill]}

def get_next_issue(issue_str):
    match = re.search(r'(\d+)$', str(issue_str))
    if match:
        num_str = match.group(1)
        prefix = str(issue_str)[:-len(num_str)]
        return prefix + str(int(num_str) + 1).zfill(len(num_str))
    return "下一期"

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
    <title>舰长 28 智能预测系统</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
        body { font-family: 'Helvetica Neue', Arial, sans-serif; background: #070b14; color: #e2e8f0; padding: 15px; }
        .container { max-width: 800px; margin: 0 auto; background: #101827; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.8); overflow: hidden; border: 1px solid #1e293b; }
        
        /* 头部与同步状态 */
        .header { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); padding: 25px 20px; text-align: center; border-bottom: 2px solid #3b82f6; position: relative; }
        .header h1 { font-size: 24px; letter-spacing: 2px; text-shadow: 0 0 10px rgba(59,130,246,0.6); color: #60a5fa; }
        .header p { font-size: 13px; margin-top: 5px; color: #94a3b8; letter-spacing: 1px; }
        
        .sync-status { position: absolute; top: 20px; right: 20px; font-size: 12px; display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.4); padding: 5px 10px; border-radius: 20px; border: 1px solid #334155; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: #64748b; }
        .dot.success { background: #10b981; box-shadow: 0 0 8px #10b981; }
        .dot.error { background: #ef4444; box-shadow: 0 0 8px #ef4444; }
        .dot.syncing { background: #f59e0b; box-shadow: 0 0 8px #f59e0b; animation: pulse 1s infinite alternate; }
        @keyframes pulse { from { opacity: 0.4; } to { opacity: 1; } }
        
        /* 切换栏 */
        .mode-switch { display: flex; background: #0f172a; border-bottom: 1px solid #1e293b; }
        .mode-btn { flex: 1; padding: 15px; text-align: center; cursor: pointer; color: #64748b; font-weight: bold; font-size: 15px; transition: 0.3s; border-bottom: 2px solid transparent; }
        .mode-btn.active { color: #60a5fa; border-bottom: 2px solid #3b82f6; background: #101827; }
        
        .tabs { display: flex; background: #0f172a; padding: 10px; gap: 10px; }
        .tab { flex: 1; padding: 12px; text-align: center; cursor: pointer; color: #94a3b8; font-weight: bold; font-size: 14px; border-radius: 8px; transition: 0.3s; background: #1e293b; border: 1px solid #334155; }
        .tab.active { background: #3b82f6; color: #fff; box-shadow: 0 0 15px rgba(59,130,246,0.6); border-color: #3b82f6; }
        
        .content { padding: 20px; }
        
        /* 双倒计时仪表盘 */
        .dashboard { display: flex; gap: 15px; margin-bottom: 20px; }
        .timer-box { flex: 1; background: #0f172a; border-radius: 12px; padding: 20px 15px; text-align: center; border: 1px solid #1e293b; box-shadow: inset 0 0 20px rgba(0,0,0,0.8); position: relative; }
        .timer-label { font-size: 13px; color: #94a3b8; margin-bottom: 8px; }
        .timer-val { font-family: 'Courier New', Courier, monospace; font-size: 36px; font-weight: 900; color: #06b6d4; text-shadow: 0 0 15px rgba(6,182,212,0.5); transition: 0.3s; }
        .timer-val.waiting { color: #ef4444; text-shadow: 0 0 15px rgba(239,68,68,0.8); animation: pulse 0.8s infinite alternate; font-size: 22px; }
        
        /* 预测展示区 */
        .prediction-area { display: flex; gap: 15px; margin-bottom: 25px; }
        .pred-box { flex: 1; padding: 20px 15px; border-radius: 12px; text-align: center; position: relative; backdrop-filter: blur(10px); display: flex; flex-direction: column; align-items: center; }
        .kill-box { background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.3); box-shadow: 0 0 15px rgba(239, 68, 68, 0.1); }
        .push-box { background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.3); box-shadow: 0 0 15px rgba(16, 185, 129, 0.1); }
        
        /* 目标期号放到方框内 */
        .target-issue { font-size: 12px; color: #cbd5e1; background: rgba(0,0,0,0.4); padding: 3px 10px; border-radius: 12px; margin-bottom: 12px; border: 1px solid #334155; }
        .target-issue span { color: #f43f5e; font-weight: bold; margin-left: 5px; }
        
        .pred-title { font-size: 14px; margin-bottom: 10px; color: #cbd5e1; font-weight: bold; }
        .pred-value { font-size: 28px; font-weight: 900; letter-spacing: 2px; }
        .kill-value { color: #ef4444; text-shadow: 0 0 12px rgba(239,68,68,0.5); }
        .push-value { color: #10b981; text-shadow: 0 0 12px rgba(16,185,129,0.5); font-size: 20px; }
        
        /* 列表通用 */
        .list-title { font-size: 15px; font-weight: bold; margin-bottom: 12px; color: #60a5fa; border-left: 4px solid #3b82f6; padding-left: 10px; margin-top: 20px; display: flex; align-items: center; gap: 8px;}
        .record-list { max-height: 400px; overflow-y: auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; }
        .lottery-item { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #1e293b; font-size: 14px; color: #e2e8f0; }
        .lottery-issue { color: #64748b; font-size: 12px; width: 120px; line-height: 1.4; }
        .lottery-raw { flex: 1; font-weight: bold; font-size: 16px; font-family: monospace; color: #cbd5e1; }
        .lottery-type { width: 60px; text-align: center; border-radius: 6px; padding: 6px 0; font-size: 12px; color: #fff; font-weight: bold; }
        .type-大单, .type-大双 { background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #ef4444; text-shadow: 0 0 5px rgba(239,68,68,0.5); }
        .type-小单, .type-小双 { background: rgba(59, 130, 246, 0.2); border: 1px solid #3b82f6; color: #3b82f6; text-shadow: 0 0 5px rgba(59,130,246,0.5); }
        
        /* 预测记录 */
        .record-item { display: flex; flex-direction: column; gap: 8px; padding: 15px; border-bottom: 1px solid #1e293b; color: #e2e8f0; font-size: 13px; }
        .record-item:last-child { border-bottom: none; }
        .record-header { display: flex; justify-content: space-between; color: #64748b; font-size: 12px; }
        .record-body { display: flex; justify-content: space-between; align-items: center; font-weight: bold; }
        .win-tag { color: #fff; background: #ef4444; padding: 3px 10px; border-radius: 4px; font-size: 12px; box-shadow: 0 0 10px rgba(239,68,68,0.5); }
        .lose-tag { color: #fff; background: #475569; padding: 3px 10px; border-radius: 4px; font-size: 12px; }
        .pending-tag { color: #fff; background: #f59e0b; padding: 3px 10px; border-radius: 4px; font-size: 12px; box-shadow: 0 0 10px rgba(245,158,11,0.5); animation: pulse 1s infinite alternate;}
        
        .loading { text-align: center; padding: 30px; color: #64748b; font-size: 14px; }
        .error { text-align: center; padding: 30px; color: #ef4444; font-size: 14px; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>舰长 28 系统</h1>
        <p>智能算法 · 杀一推三 · 极速同步</p>
        <div class="sync-status">
            <div class="dot" id="sync-dot"></div>
            <span id="sync-text">未连接</span>
        </div>
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

    <div class="content">
        <!-- 预测大厅 -->
        <div id="predict-view" style="display:block;">
            
            <!-- 两个倒计时框 -->
            <div class="dashboard">
                <div class="timer-box">
                    <div class="timer-label">本期开奖倒计时</div>
                    <div class="timer-val" id="draw-timer">--:--</div>
                </div>
                <div class="timer-box">
                    <div class="timer-label">下期预测锁定状态</div>
                    <div class="timer-val" id="predict-timer">--:--</div>
                </div>
            </div>
            
            <!-- 预测结果 (期号已移入框内) -->
            <div class="prediction-area">
                <div class="pred-box kill-box">
                    <div class="target-issue">目标期号: <span id="kill-issue">--</span></div>
                    <div class="pred-title">🚫 本期绝杀</div>
                    <div class="pred-value kill-value" id="kill-type">--</div>
                </div>
                <div class="pred-box push-box">
                    <div class="target-issue">目标期号: <span id="push-issue">--</span></div>
                    <div class="pred-title">🀄 推荐三组</div>
                    <div class="pred-value push-value" id="push-types">--</div>
                </div>
            </div>
            
            <div class="list-title">📜 历史预测记录</div>
            <div class="record-list" id="record-list"><div class="loading">加载中...</div></div>
            <div class="list-title">📊 近期开奖结果</div>
            <div class="record-list" id="draws-list"><div class="loading">加载中...</div></div>
        </div>

        <!-- 开奖大厅 -->
        <div id="lottery-view" style="display:none;">
            <div class="list-title">📊 近 30 期开奖数据</div>
            <div class="record-list" id="lottery-list"><div class="loading">数据加载中...</div></div>
        </div>
    </div>
</div>

<script>
    // 防调试与右键
    document.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('keydown', e => {
        if (e.key === 'F12' || (e.ctrlKey && e.shiftKey && ['I', 'i', 'J', 'j', 'C', 'c'].includes(e.key)) || (e.ctrlKey && ['U', 'u'].includes(e.key))) { e.preventDefault(); return false; }
    });

    let currentGame = 'btc28', currentMode = 'predict', syncInterval = null;
    let isFetching = false;
    
    // 独立时钟变量
    let globalNextTs = 0;
    let globalTimeOffset = 0;
    let isWaiting = false;

    const drawTimerEl = document.getElementById('draw-timer');
    const predictTimerEl = document.getElementById('predict-timer');
    const syncDot = document.getElementById('sync-dot');
    const syncText = document.getElementById('sync-text');

    function setSyncStatus(status) {
        syncDot.className = 'dot ' + status;
        if(status === 'success') syncText.innerText = '同步成功';
        else if(status === 'error') syncText.innerText = '同步失败';
        else if(status === 'syncing') syncText.innerText = '同步中...';
        else syncText.innerText = '未连接';
    }

    // ================= 核心：独立本地时钟 (每秒跑) =================
    setInterval(() => {
        if (currentMode !== 'predict') return;
        
        // 如果还没拿到服务器时间，先显示 ---
        if (globalNextTs === 0) {
            drawTimerEl.innerText = '--:--';
            predictTimerEl.innerText = '--:--';
            return;
        }
        
        // 使用本地时间 + 偏移量 = 模拟服务器当前时间
        const now = Math.floor(Date.now() / 1000) + globalTimeOffset;
        const remaining = globalNextTs - now;
        
        if (remaining > 0) {
            // 倒计时进行中
            if (isWaiting) {
                isWaiting = false;
                drawTimerEl.classList.remove('waiting');
                predictTimerEl.classList.remove('waiting');
            }
            const m = Math.floor(remaining / 60).toString().padStart(2, '0');
            const s = (remaining % 60).toString().padStart(2, '0');
            
            drawTimerEl.innerText = `${m}:${s}`;
            predictTimerEl.innerText = `${m}:${s}`;
        } else {
            // 倒计时归零：变红字闪烁，等待开奖
            if (!isWaiting) {
                isWaiting = true;
                drawTimerEl.classList.add('waiting');
                predictTimerEl.classList.add('waiting');
                // 触发一次立即拉取，去拿最新结果
                fetchPredictData(); 
            }
            drawTimerEl.innerText = '等待开奖...';
            predictTimerEl.innerText = '等待开奖...';
        }
    }, 1000); // 每秒刷新

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

    // 获取开奖大厅数据
    function fetchLottery() {
        const el = document.getElementById('lottery-list');
        el.innerHTML = '<div class="loading">加载中...</div>'; setSyncStatus('syncing');
        fetch(`/api/lottery/${currentGame}?_s=${btoa("secure_28_web_2024")}`).then(res => res.json()).then(res => {
            if (res.error) { el.innerHTML = `<div class="error">${res.error}</div>`; setSyncStatus('error'); return; }
            const data = JSON.parse(atob(res.payload)); 
            let html = '';
            data.draws.forEach(d => { html += `<div class="lottery-item"><div class="lottery-issue">${d.issue}<br>${d.time}</div><div class="lottery-raw">${d.raw}</div><div class="lottery-type type-${d.type}">${d.type}</div></div>`; });
            el.innerHTML = html; setSyncStatus('success');
        }).catch(err => { el.innerHTML = '<div class="error">网络错误</div>'; setSyncStatus('error'); });
    }

    function startPredictMode() {
        globalNextTs = 0; // 重置时钟，等待接口返回
        isWaiting = false;
        document.getElementById('record-list').innerHTML = '<div class="loading">计算中...</div>';
        document.getElementById('draws-list').innerHTML = '<div class="loading">加载中...</div>';
        document.getElementById('kill-type').innerText = '--'; document.getElementById('push-types').innerText = '--'; 
        document.getElementById('kill-issue').innerText = '--'; document.getElementById('push-issue').innerText = '--'; 
        
        fetchPredictData();
        clearInterval(syncInterval); syncInterval = setInterval(fetchPredictData, 3000);
    }

    // 获取预测数据 (3秒一次)
    function fetchPredictData() {
        if (isFetching) return; isFetching = true; setSyncStatus('syncing');
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 6000);
        
        fetch(`/api/proxy/${currentGame}?_s=${btoa("secure_28_web_2024")}`, { signal: controller.signal })
            .then(res => { clearTimeout(timeoutId); return res.json(); })
            .then(res => {
                isFetching = false;
                if (res.error) { 
                    setSyncStatus('error'); 
                    document.getElementById('draws-list').innerHTML = `<div class="error">API源响应超时或休眠中</div>`;
                    return; 
                }
                renderPredictData(JSON.parse(atob(res.payload))); 
                setSyncStatus('success');
            })
            .catch(err => { isFetching = false; setSyncStatus('error'); });
    }

    function renderPredictData(data) {
        // 更新预测结果与目标期号
        document.getElementById('kill-type').innerText = data.prediction.kill;
        document.getElementById('push-types').innerText = data.prediction.push.join(' | ');
        document.getElementById('kill-issue').innerText = data.next_issue;
        document.getElementById('push-issue').innerText = data.next_issue;
        
        // 渲染预测记录
        let recordHtml = '';
        if(data.predict_records && data.predict_records.length > 0) {
            data.predict_records.slice().reverse().forEach(r => {
                // 只要实际结果不是杀号，就是中奖
                let statusTag = r.status === 'pending' ? '<span class="pending-tag">等待开奖</span>' : (r.is_win ? '<span class="win-tag">🀄 中奖</span>' : '<span class="lose-tag">未中</span>');
                let actualText = r.actual ? `开: ${r.actual}` : '开: --';
                recordHtml += `<div class="record-item"><div class="record-header"><span>期号: ${r.issue}</span>${statusTag}</div><div class="record-body"><span>杀: <span style="color:#ef4444">${r.kill}</span></span><span>推: <span style="color:#10b981">${r.push.join(',')}</span></span><span>${actualText}</span></div></div>`;
            });
        } else { 
            recordHtml = '<div class="loading">暂无预测记录</div>'; 
        }
        document.getElementById('record-list').innerHTML = recordHtml;

        // 渲染开奖列表
        let drawsHtml = '';
        data.draws.forEach(d => { drawsHtml += `<div class="lottery-item"><div class="lottery-issue">${d.issue}<br>${d.time}</div><div class="lottery-raw">${d.raw}</div><div class="lottery-type type-${d.type}">${d.type}</div></div>`; });
        document.getElementById('draws-list').innerHTML = drawsHtml;

        // 更新全局时间
        globalNextTs = data.next_ts;
        globalTimeOffset = data.server_time - Math.floor(Date.now() / 1000);
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
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def verify_security(self):
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)
        if '_s' not in query:
            return False, "Forbidden"
        if query['_s'][0] != base64.b64encode(("secure_28_web_2024").encode()).decode():
            return False, "Forbidden"
        return True, ""

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

        # 安全验证
        is_valid, _ = self.verify_security()
        if not is_valid:
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
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif parsed_path.startswith('/api/proxy/'):
            game_type = parsed_path.split('/')[-1]
            if game_type not in API_CONFIG: return self.send_error(400)
            try:
                data = self.get_api_data(game_type)
                draws = data.get('draws', [])
                if not draws: raise Exception("API 数据为空")
                
                if game_type == 'btc28': prediction = predict_btc28(draws)
                elif game_type == 'fenfen28': prediction = predict_fenfen28(draws)
                else: prediction = predict_JND(draws)
                
                latest_issue = draws[0].get('issue')
                next_issue = get_next_issue(latest_issue)
                
                history = load_history()
                if game_type not in history: history[game_type] = []
                game_history = history[game_type]
                
                # 【核心修复】如果服务器重启导致历史记录丢失，立刻根据现有的 30 期数据回测补全
                if len(game_history) < 5:
                    game_history = []
                    for i in range(len(draws)-1, 0, -1):
                        past_draw = draws[i]
                        # 用之前的算法倒推预测（这里简单调用算法接口）
                        if game_type == 'btc28': past_pred = predict_btc28(draws[i:])
                        elif game_type == 'fenfen28': past_pred = predict_fenfen28(draws[i:])
                        else: past_pred = predict_JND(draws[i:])
                            
                        game_history.append({
                            "issue": past_draw['issue'],
                            "kill": past_pred['kill'],
                            "push": past_pred['push'],
                            "actual": past_draw['type'],
                            "is_win": (past_draw['type'] != past_pred['kill']),
                            "status": "settled"
                        })
                
                # 结算上一期预测
                if game_history:
                    last_record = game_history[-1]
                    if last_record["status"] == "pending":
                        last_record["actual"] = draws[0]['type']
                        last_record["is_win"] = (draws[0]['type'] != last_record["kill"])
                        last_record["status"] = "settled"
                
                # 生成下一期预测
                if not game_history or game_history[-1]["issue"] != latest_issue:
                    game_history.append({"issue": latest_issue, "kill": prediction["kill"], "push": prediction["push"], "actual": None, "is_win": None, "status": "pending"})
                    if len(game_history) > 50: game_history.pop(0)
                
                save_history({game_type: game_history})
                
                result = {
                    "name": data.get('name'), "period": data.get('period'), 
                    "next_ts": data.get('next_ts'), "server_time": data.get('server_time'), 
                    "draws": draws[:30], "prediction": prediction, 
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
