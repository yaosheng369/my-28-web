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
IP_REQUEST_LOG = {} # 用于简单的IP限流
SECRET_SALT = "secure_28_web_2024" # 签名密钥

# ================= 预测算法区 =================
def predict_btc28(draws):
    counts = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
    for d in draws[:10]: counts[d['type']] += 1
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
        counts = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
        for d in draws[:5]: counts[d['type']] += 1
        kill = min(counts, key=counts.get) 
    return {"kill": kill, "push": [k for k in ["大单", "大双", "小单", "小双"] if k != kill]}

def predict_JND(draws):
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
        
        /* 倒计时仪表盘 */
        .dashboard { background: #0f172a; border-radius: 12px; padding: 25px 20px; text-align: center; margin-bottom: 20px; border: 1px solid #1e293b; box-shadow: inset 0 0 20px rgba(0,0,0,0.8); position: relative; overflow: hidden; }
        .dashboard::before { content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 60%); pointer-events: none; }
        
        .target-issue-box { font-size: 15px; color: #94a3b8; margin-bottom: 15px; z-index: 1; position: relative; }
        .target-issue-box span { color: #f43f5e; font-weight: bold; font-size: 20px; letter-spacing: 2px; text-shadow: 0 0 10px rgba(244,63,94,0.6); }
        
        .countdown-time { font-family: 'Courier New', Courier, monospace; font-size: 56px; font-weight: 900; color: #06b6d4; text-shadow: 0 0 20px rgba(6,182,212,0.5); transition: 0.3s; z-index: 1; position: relative; }
        .countdown-time.waiting { color: #ef4444; text-shadow: 0 0 20px rgba(239,68,68,0.8); animation: pulse 0.8s infinite alternate; font-size: 42px; }
        
        /* 预测结果 */
        .prediction-area { display: flex; gap: 15px; margin-bottom: 25px; }
        .pred-box { flex: 1; padding: 20px 15px; border-radius: 12px; text-align: center; position: relative; backdrop-filter: blur(10px); }
        .kill-box { background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.3); box-shadow: 0 0 15px rgba(239, 68, 68, 0.1); }
        .push-box { background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.3); box-shadow: 0 0 15px rgba(16, 185, 129, 0.1); }
        .pred-title { font-size: 14px; margin-bottom: 12px; color: #cbd5e1; font-weight: bold; }
        .pred-value { font-size: 32px; font-weight: 900; letter-spacing: 2px; }
        .kill-value { color: #ef4444; text-shadow: 0 0 12px rgba(239,68,68,0.5); }
        .push-value { color: #10b981; text-shadow: 0 0 12px rgba(16,185,129,0.5); font-size: 22px; }
        
        /* 列表通用 */
        .list-title { font-size: 15px; font-weight: bold; margin-bottom: 12px; color: #60a5fa; border-left: 4px solid #3b82f6; padding-left: 10px; margin-top: 20px; display: flex; align-items: center; gap: 8px;}
        .list-title::after { content: ''; flex: 1; height: 1px; background: linear-gradient(90deg, #334155, transparent); }
        .record-list { max-height: 400px; overflow-y: auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; }
        
        /* 开奖记录 */
        .lottery-item { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #1e293b; font-size: 14px; color: #e2e8f0; }
        .lottery-item:last-child { border-bottom: none; }
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
        <div id="predict-view" style="display:block;">
            <div class="dashboard">
                <div class="target-issue-box">目标期号：<span id="next-issue">--</span></div>
                <div class="countdown-time" id="countdown">--:--</div>
            </div>
            <div class="prediction-area">
                <div class="pred-box kill-box">
                    <div class="pred-title">🚫 本期绝杀</div>
                    <div class="pred-value kill-value" id="kill-type">--</div>
                </div>
                <div class="pred-box push-box">
                    <div class="pred-title">🀄 推荐三组</div>
                    <div class="pred-value push-value" id="push-types">--</div>
                </div>
            </div>
            <div class="list-title">📜 历史预测记录</div>
            <div class="record-list" id="record-list"><div class="loading">加载中...</div></div>
            <div class="list-title">📊 近期开奖结果</div>
            <div class="record-list" id="draws-list"><div class="loading">加载中...</div></div>
        </div>

        <div id="lottery-view" style="display:none;">
            <div class="list-title">📊 近 30 期开奖数据</div>
            <div class="record-list" id="lottery-list"><div class="loading">数据加载中...</div></div>
        </div>
    </div>
</div>

<script>
    // 第3层防护：前端防调试
    document.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('keydown', e => {
        if (e.key === 'F12' || (e.ctrlKey && e.shiftKey && ['I', 'i', 'J', 'j', 'C', 'c'].includes(e.key)) || (e.ctrlKey && ['U', 'u'].includes(e.key))) { e.preventDefault(); return false; }
    });

    let currentGame = 'btc28', currentMode = 'predict', timerInterval = null, syncInterval = null;
    let timeOffset = 0; let isFetching = false;
    
    // 第4层防护：动态签名生成 (与后端校验)
    function genSign(t) { return btoa(t + "_secure_28_web_2024"); }
    function getSecureParams() { let t = Date.now(); return `_t=${t}&_s=${encodeURIComponent(genSign(t))}`; }

    const countdownEl = document.getElementById('countdown');
    const syncDot = document.getElementById('sync-dot');
    const syncText = document.getElementById('sync-text');

    function setSyncStatus(status) {
        syncDot.className = 'dot ' + status;
        if(status === 'success') syncText.innerText = '同步成功';
        else if(status === 'error') syncText.innerText = '同步失败';
        else if(status === 'syncing') syncText.innerText = '同步中...';
        else syncText.innerText = '未连接';
    }

    function switchMode(mode) {
        currentMode = mode;
        document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
        document.getElementById('lottery-view').style.display = mode === 'lottery' ? 'block' : 'none';
        document.getElementById('predict-view').style.display = mode === 'predict' ? 'block' : 'none';
        clearInterval(timerInterval); clearInterval(syncInterval);
        if (mode === 'lottery') fetchLottery(); else startPredictMode();
    }

    function switchGame(game) {
        currentGame = game;
        document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab.dataset.game === game));
        clearInterval(timerInterval); clearInterval(syncInterval);
        if (currentMode === 'lottery') fetchLottery(); else startPredictMode();
    }

    function fetchLottery() {
        const el = document.getElementById('lottery-list');
        el.innerHTML = '<div class="loading">加载中...</div>'; setSyncStatus('syncing');
        fetch(`/api/lottery/${currentGame}?${getSecureParams()}`).then(res => res.json()).then(res => {
            if (res.error) { el.innerHTML = `<div class="error">请求失败</div>`; setSyncStatus('error'); return; }
            const data = JSON.parse(atob(res.payload)); let html = '';
            data.draws.forEach(d => { html += `<div class="lottery-item"><div class="lottery-issue">${d.issue}<br>${d.time}</div><div class="lottery-raw">${d.raw}</div><div class="lottery-type type-${d.type}">${d.type}</div></div>`; });
            el.innerHTML = html; setSyncStatus('success');
        }).catch(err => { el.innerHTML = '<div class="error">网络错误</div>'; setSyncStatus('error'); });
    }

    function startPredictMode() {
        document.getElementById('record-list').innerHTML = '<div class="loading">计算中...</div>';
        document.getElementById('draws-list').innerHTML = '<div class="loading">加载中...</div>';
        document.getElementById('kill-type').innerText = '--'; document.getElementById('push-types').innerText = '--'; 
        countdownEl.classList.remove('waiting'); countdownEl.innerText = '--:--';
        fetchPredictData();
        clearInterval(syncInterval); syncInterval = setInterval(fetchPredictData, 3000); // 每3秒同步
    }

    function fetchPredictData() {
        if (isFetching) return; isFetching = true; setSyncStatus('syncing');
        fetch(`/api/proxy/${currentGame}?${getSecureParams()}`).then(res => { return res.json(); }).then(res => {
            isFetching = false;
            if (res.error) { setSyncStatus('error'); return; }
            renderPredictData(JSON.parse(atob(res.payload))); setSyncStatus('success');
        }).catch(err => { isFetching = false; setSyncStatus('error'); });
    }

    function renderPredictData(data) {
        document.getElementById('kill-type').innerText = data.prediction.kill;
        document.getElementById('push-types').innerText = data.prediction.push.join(' | ');
        document.getElementById('next-issue').innerText = data.next_issue;
        
        let recordHtml = '';
        if(data.predict_records && data.predict_records.length > 0) {
            data.predict_records.slice().reverse().forEach(r => {
                let statusTag = r.status === 'pending' ? '<span class="pending-tag">等待开奖</span>' : (r.is_win ? '<span class="win-tag">🀄 中奖</span>' : '<span class="lose-tag">未中</span>');
                let actualText = r.actual ? `开: ${r.actual}` : '开: --';
                recordHtml += `<div class="record-item"><div class="record-header"><span>期号: ${r.issue}</span>${statusTag}</div><div class="record-body"><span>杀: <span style="color:#ef4444">${r.kill}</span></span><span>推: <span style="color:#10b981">${r.push.join(',')}</span></span><span>${actualText}</span></div></div>`;
            });
        } else { recordHtml = '<div class="loading">暂无预测记录</div>'; }
        document.getElementById('record-list').innerHTML = recordHtml;

        let drawsHtml = '';
        data.draws.forEach(d => { drawsHtml += `<div class="lottery-item"><div class="lottery-issue">${d.issue}<br>${d.time}</div><div class="lottery-raw">${d.raw}</div><div class="lottery-type type-${d.type}">${d.type}</div></div>`; });
        document.getElementById('draws-list').innerHTML = drawsHtml;

        if (countdownEl.dataset.nextTs != data.next_ts) {
            countdownEl.dataset.nextTs = data.next_ts;
            timeOffset = data.server_time - Math.floor(Date.now() / 1000);
            startCountdown(data.next_ts);
        }
    }

    function startCountdown(nextTs) {
        clearInterval(timerInterval);
        function updateTimer() {
            const remaining = nextTs - (Math.floor(Date.now() / 1000) + timeOffset);
            if (remaining <= 0) { 
                countdownEl.innerText = '等待开奖...'; countdownEl.classList.add('waiting'); return; 
            }
            countdownEl.classList.remove('waiting');
            countdownEl.innerText = `${Math.floor(remaining / 60).toString().padStart(2, '0')}:${(remaining % 60).toString().padStart(2, '0')}`;
        }
        updateTimer(); timerInterval = setInterval(updateTimer, 1000);
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
        # 第2层防护：强制安全响应头 (防嵌套/XSS/CSP)
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def verify_security(self):
        # 第4层防护：验证动态签名与时间戳
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)
        
        if '_t' not in query or '_s' not in query:
            return False, "Forbidden: Missing Signature"
        
        t_str = query['_t'][0]
        s_str = query['_s'][0]
        
        try:
            t = int(t_str)
            # 校验时间差 (防重放攻击，3秒有效)
            if abs(time.time() * 1000 - t) > 3000:
                return False, "Forbidden: Token Expired"
        except:
            return False, "Forbidden: Invalid Token"

        # 校验签名
        expected_s = base64.b64encode((t_str + SECRET_SALT).encode()).decode()
        if s_str != expected_s:
            return False, "Forbidden: Invalid Signature"
            
        return True, ""

    def get_api_data(self, game_type):
        # 第6层防护：简单的IP限流 (1秒内最多5次请求)
        client_ip = self.client_address[0]
        now = time.time()
        if client_ip in IP_REQUEST_LOG:
            IP_REQUEST_LOG[client_ip] = [t for t in IP_REQUEST_LOG[client_ip] if now - t < 1]
            if len(IP_REQUEST_LOG[client_ip]) >= 5:
                raise Exception("请求过于频繁，请稍后再试")
            IP_REQUEST_LOG[client_ip].append(now)
        else:
            IP_REQUEST_LOG[client_ip] = [now]

        # 缓存机制
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
        # 首页直接放行
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            return

        # 验证安全签名
        is_valid, err_msg = self.verify_security()
        if not is_valid:
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": err_msg}).encode('utf-8'))
            return

        # 接口路由
        parsed_path = urlparse(self.path).path
        if parsed_path.startswith('/api/lottery/'):
            game_type = parsed_path.split('/')[-1]
            if game_type not in API_CONFIG: return self.send_error(400)
            try:
                data = self.get_api_data(game_type)
                result = {"name": data.get('name'), "draws": data.get('draws', [])[:30]}
                # 第5层防护：数据Base64加密
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
                
                if game_history:
                    last_record = game_history[-1]
                    if last_record["status"] == "pending":
                        last_record["actual"] = draws[0]['type']
                        last_record["is_win"] = (draws[0]['type'] != last_record["kill"])
                        last_record["status"] = "settled"
                
                if not game_history or game_history[-1]["issue"] != latest_issue:
                    game_history.append({"issue": latest_issue, "kill": prediction["kill"], "push": prediction["push"], "actual": None, "is_win": None, "status": "pending"})
                    if len(game_history) > 50: game_history.pop(0)
                save_history(history)
                
                result = {
                    "name": data.get('name'), "period": data.get('period'), 
                    "next_ts": data.get('next_ts'), "server_time": data.get('server_time'), 
                    "draws": draws[:30], "prediction": prediction, 
                    "predict_records": game_history, "next_issue": next_issue
                }
                
                # 第5层防护：数据Base64加密
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
        else:
            self.send_error(404, "Not Found")

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 5000))
    server = ThreadedHTTPServer(("0.0.0.0", PORT), MyHandler)
    print(f"✅ 战舰启动完毕！监听端口: {PORT}")
    server.serve_forever()
