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
SECRET_SALT = "secure_28_web_2024" 

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

# ================= 前端 HTML (赛博朋克) =================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SKYNET 28 智能预测终端</title>
    <style>
        :root {
            --bg-color: #050505;
            --panel-bg: rgba(15, 20, 30, 0.75);
            --border-color: rgba(0, 243, 255, 0.2);
            --cyan: #00f3ff;
            --red: #ff003c;
            --green: #00ff88;
            --text-main: #e2e8f0;
            --text-muted: #64748b;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg-color); color: var(--text-main); min-height: 100vh; background-image: 
            linear-gradient(rgba(0, 243, 255, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 243, 255, 0.03) 1px, transparent 1px);
            background-size: 30px 30px; padding: 15px; }
        
        body::after { content: ""; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06)); background-size: 100% 2px, 3px 100%; pointer-events: none; z-index: 9999; opacity: 0.5;}
        
        .container { max-width: 800px; margin: 0 auto; position: relative; z-index: 10; }
        .header { text-align: center; padding: 20px 0; position: relative; margin-bottom: 20px; }
        .header h1 { font-size: 28px; letter-spacing: 5px; color: var(--cyan); text-shadow: 0 0 10px var(--cyan), 0 0 20px rgba(0, 243, 255, 0.5); font-weight: 900; }
        .header p { font-size: 12px; letter-spacing: 2px; color: var(--text-muted); margin-top: 5px; text-transform: uppercase; }
        
        .sync-status { position: absolute; top: 25px; right: 10px; font-size: 12px; display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.5); padding: 5px 12px; border-radius: 4px; border: 1px solid var(--border-color); font-family: monospace; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
        .dot.success { background: var(--green); box-shadow: 0 0 10px var(--green); }
        .dot.error { background: var(--red); box-shadow: 0 0 10px var(--red); }
        .dot.syncing { background: #f59e0b; box-shadow: 0 0 10px #f59e0b; animation: pulse 1s infinite alternate; }
        @keyframes pulse { from { opacity: 0.4; } to { opacity: 1; } }
        
        .mode-switch { display: flex; gap: 10px; margin-bottom: 20px; }
        .mode-btn { flex: 1; padding: 15px; text-align: center; cursor: pointer; color: var(--text-muted); font-weight: bold; font-size: 15px; background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 8px; transition: 0.3s; backdrop-filter: blur(10px); }
        .mode-btn.active { color: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 15px rgba(0, 243, 255, 0.3); background: rgba(0, 243, 255, 0.05); }
        
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab { flex: 1; padding: 12px; text-align: center; cursor: pointer; color: var(--text-muted); font-size: 14px; background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 6px; transition: 0.3s; font-weight: bold; }
        .tab.active { color: #fff; background: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 20px rgba(0, 243, 255, 0.6); }

        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; margin-bottom: 20px; backdrop-filter: blur(10px); box-shadow: inset 0 0 20px rgba(0,0,0,0.5); position: relative; }
        .panel::before { content: ''; position: absolute; top: 0; left: 0; width: 20px; height: 2px; background: var(--cyan); box-shadow: 0 0 10px var(--cyan); }
        .panel::after { content: ''; position: absolute; bottom: 0; right: 0; width: 20px; height: 2px; background: var(--cyan); box-shadow: 0 0 10px var(--cyan); }

        .dashboard { display: flex; gap: 15px; }
        .timer-box { flex: 1; text-align: center; background: rgba(0,0,0,0.3); border-radius: 8px; padding: 15px; border: 1px solid rgba(255,255,255,0.05); }
        .timer-label { font-size: 13px; color: var(--text-muted); margin-bottom: 8px; letter-spacing: 1px; }
        .timer-val { font-family: 'Courier New', Courier, monospace; font-size: 38px; font-weight: 900; color: var(--cyan); text-shadow: 0 0 15px rgba(0, 243, 255, 0.6); }
        .timer-val.waiting { color: var(--red); text-shadow: 0 0 20px var(--red); animation: pulse 0.5s infinite alternate; font-size: 24px; display: flex; align-items: center; justify-content: center; height: 45px;}

        .prediction-area { display: flex; gap: 15px; margin-bottom: 20px; }
        .pred-box { flex: 1; padding: 20px 15px; text-align: center; border-radius: 12px; position: relative; overflow: hidden; display: flex; flex-direction: column; align-items: center; justify-content: center;}
        .kill-box { background: rgba(255, 0, 60, 0.05); border: 1px solid rgba(255, 0, 60, 0.3); box-shadow: inset 0 0 30px rgba(255, 0, 60, 0.1); }
        .push-box { background: rgba(0, 255, 136, 0.05); border: 1px solid rgba(0, 255, 136, 0.3); box-shadow: inset 0 0 30px rgba(0, 255, 136, 0.1); }
        .target-issue { font-size: 12px; color: #fff; background: rgba(0,0,0,0.6); padding: 4px 12px; border-radius: 20px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.1); letter-spacing: 1px;}
        .target-issue span { color: var(--cyan); font-weight: bold; }
        .pred-title { font-size: 14px; margin-bottom: 10px; color: var(--text-muted); letter-spacing: 2px; }
        .pred-value { font-size: 36px; font-weight: 900; letter-spacing: 3px; }
        .kill-value { color: var(--red); text-shadow: 0 0 15px rgba(255, 0, 60, 0.6); }
        .push-value { color: var(--green); text-shadow: 0 0 15px rgba(0, 255, 136, 0.6); font-size: 22px; }

        .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
        .stat-item { text-align: center; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); }
        .stat-label { font-size: 12px; color: var(--text-muted); margin-bottom: 5px; }
        .stat-val { font-size: 20px; font-weight: bold; font-family: monospace; }
        .stat-val.green { color: var(--green); text-shadow: 0 0 10px rgba(0,255,136,0.4); }
        .stat-val.red { color: var(--red); text-shadow: 0 0 10px rgba(255,0,60,0.4); }

        .list-title { font-size: 15px; font-weight: bold; margin-bottom: 12px; color: var(--cyan); border-left: 4px solid var(--cyan); padding-left: 10px; display: flex; align-items: center; gap: 8px; letter-spacing: 1px;}
        .list-container { max-height: 400px; overflow-y: auto; border-radius: 8px; }
        
        .lottery-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 15px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 14px; }
        .lottery-item:last-child { border-bottom: none; }
        .lottery-issue { color: var(--text-muted); font-size: 12px; width: 100px; line-height: 1.4; font-family: monospace; }
        .lottery-raw { flex: 1; font-weight: bold; font-size: 16px; font-family: 'Courier New', Courier, monospace; color: #fff; }
        .lottery-type { width: 60px; text-align: center; border-radius: 4px; padding: 4px 0; font-size: 12px; font-weight: bold; }
        .type-大单, .type-大双 { background: rgba(255, 0, 60, 0.15); color: var(--red); border: 1px solid rgba(255,0,60,0.3); }
        .type-小单, .type-小双 { background: rgba(0, 243, 255, 0.15); color: var(--cyan); border: 1px solid rgba(0,243,255,0.3); }
        
        .record-item { padding: 12px 15px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px; }
        .record-header { display: flex; justify-content: space-between; color: var(--text-muted); font-size: 12px; margin-bottom: 8px; font-family: monospace; }
        .record-body { display: flex; justify-content: space-between; align-items: center; font-weight: bold; }
        
        /* 中奖 红色字体，未中 深黑色字体 */
        .win-tag { color: var(--red); border: 1px solid var(--red); padding: 2px 8px; border-radius: 4px; font-size: 12px; box-shadow: 0 0 10px rgba(255,0,60,0.3); font-weight: bold;}
        .lose-tag { color: #334155; background: #0f172a; border: 1px solid #334155; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .pending-tag { color: #f59e0b; border: 1px solid #f59e0b; padding: 2px 8px; border-radius: 4px; font-size: 12px; animation: pulse 1s infinite alternate;}
        
        .loading { text-align: center; padding: 30px; color: var(--cyan); font-size: 14px; font-family: monospace; letter-spacing: 2px;}
        .error { text-align: center; padding: 30px; color: var(--red); font-size: 14px; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--cyan); border-radius: 2px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>SKYNET 28</h1>
        <p>Smart Predictive Terminal</p>
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

    <div id="predict-view" style="display:block;">
        <div class="panel">
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
        </div>
        
        <div class="prediction-area">
            <div class="pred-box kill-box">
                <div class="target-issue">目标期号: <span id="kill-issue">--</span></div>
                <div class="pred-title">绝杀组合</div>
                <div class="pred-value kill-value" id="kill-type">--</div>
            </div>
            <div class="pred-box push-box">
                <div class="target-issue">目标期号: <span id="push-issue">--</span></div>
                <div class="pred-title">推荐三组</div>
                <div class="pred-value push-value" id="push-types">--</div>
            </div>
        </div>

        <div class="panel">
            <div class="list-title" style="margin-bottom: 15px;">📈 战绩统计 (近20期)</div>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-label">总中奖</div>
                    <div class="stat-val green" id="stat-total-win">0</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">总未中</div>
                    <div class="stat-val red" id="stat-total-lose">0</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">当前连对</div>
                    <div class="stat-val green" id="stat-streak-win">0</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">当前连错</div>
                    <div class="stat-val red" id="stat-streak-lose">0</div>
                </div>
            </div>
        </div>

        <div class="panel">
            <div class="list-title">📜 历史预测记录 (近20期)</div>
            <div class="list-container" id="record-list"><div class="loading">加载中...</div></div>
        </div>

        <div class="panel">
            <div class="list-title">📊 近期开奖结果</div>
            <div class="list-container" id="draws-list"><div class="loading">加载中...</div></div>
        </div>
    </div>

    <div id="lottery-view" style="display:none;">
        <div class="panel">
            <div class="list-title">📊 近 30 期开奖数据</div>
            <div class="list-container" id="lottery-list"><div class="loading">数据加载中...</div></div>
        </div>
    </div>
</div>

<script>
    document.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('keydown', e => {
        if (e.key === 'F12' || (e.ctrlKey && e.shiftKey && ['I', 'i', 'J', 'j', 'C', 'c'].includes(e.key)) || (e.ctrlKey && ['U', 'u'].includes(e.key))) { e.preventDefault(); return false; }
    });

    let currentGame = 'btc28', currentMode = 'predict', syncInterval = null;
    let isFetching = false;
    let globalNextTs = 0, globalTimeOffset = 0, isWaiting = false;
    
    const drawTimerEl = document.getElementById('draw-timer');
    const predictTimerEl = document.getElementById('predict-timer');

    function setSyncStatus(status) {
        const syncDot = document.getElementById('sync-dot');
        const syncText = document.getElementById('sync-text');
        syncDot.className = 'dot ' + status;
        syncText.innerText = status === 'success' ? '同步成功' : (status === 'error' ? '同步失败' : (status === 'syncing' ? '同步中...' : '未连接'));
    }

    setInterval(() => {
        if (currentMode !== 'predict' || globalNextTs === 0) return;
        const now = Math.floor(Date.now() / 1000) + globalTimeOffset;
        const remaining = globalNextTs - now;
        
        if (remaining > 0) {
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
            if (!isWaiting) {
                isWaiting = true;
                drawTimerEl.classList.add('waiting');
                predictTimerEl.classList.add('waiting');
                fetchPredictData(); 
            }
            drawTimerEl.innerText = '等待开奖...';
            predictTimerEl.innerText = '等待开奖...';
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
        globalNextTs = 0; isWaiting = false;
        document.getElementById('record-list').innerHTML = '<div class="loading">计算中...</div>';
        document.getElementById('draws-list').innerHTML = '<div class="loading">加载中...</div>';
        fetchPredictData();
        clearInterval(syncInterval); syncInterval = setInterval(fetchPredictData, 3000);
    }

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
        document.getElementById('kill-type').innerText = data.prediction.kill;
        document.getElementById('push-types').innerText = data.prediction.push.join(' | ');
        document.getElementById('kill-issue').innerText = data.next_issue;
        document.getElementById('push-issue').innerText = data.next_issue;
        
        // 统计逻辑
        let records = data.predict_records || [];
        let totalWin = 0, totalLose = 0, streakWin = 0, streakLose = 0;
        let currentStreakType = null; 
        
        records.forEach(r => {
            if (r.status === 'settled') {
                if (r.is_win) totalWin++;
                else totalLose++;
            }
        });

        // 【核心修复】从数组最后面（最新的一期）开始往前倒推计算连对连错
        for (let i = records.length - 1; i >= 0; i--) {
            let r = records[i];
            if (r.status !== 'settled') continue; 
            
            if (currentStreakType === null) {
                currentStreakType = r.is_win ? 'win' : 'lose';
                if (currentStreakType === 'win') streakWin++;
                else streakLose++;
            } else {
                if (r.is_win && currentStreakType === 'win') streakWin++;
                else if (!r.is_win && currentStreakType === 'lose') streakLose++;
                else break; 
            }
        }

        document.getElementById('stat-total-win').innerText = totalWin;
        document.getElementById('stat-total-lose').innerText = totalLose;
        document.getElementById('stat-streak-win').innerText = streakWin;
        document.getElementById('stat-streak-lose').innerText = streakLose;

        // 渲染列表 (倒序展示，最新的在最上面)
        let recordHtml = '';
        let reversedRecords = [...records].reverse(); // 倒序显示
        if(reversedRecords.length > 0) {
            reversedRecords.forEach(r => {
                let statusTag = r.status === 'pending' ? '<span class="pending-tag">等待开奖</span>' : (r.is_win ? '<span class="win-tag">🀄 中奖</span>' : '<span class="lose-tag">未中</span>');
                let actualText = r.actual ? `开: ${r.actual}` : '开: --';
                let killColor = r.is_win ? 'color:var(--text-muted)' : 'color:var(--red)';
                recordHtml += `<div class="record-item"><div class="record-header"><span>期号: ${r.issue}</span>${statusTag}</div><div class="record-body"><span>杀: <span style="${killColor}">${r.kill}</span></span><span>推: <span style="color:var(--green)">${r.push.join(',')}</span></span><span>${actualText}</span></div></div>`;
            });
        } else { recordHtml = '<div class="loading">暂无记录</div>'; }
        document.getElementById('record-list').innerHTML = recordHtml;

        let drawsHtml = '';
        data.draws.forEach(d => { drawsHtml += `<div class="lottery-item"><div class="lottery-issue">${d.issue}<br>${d.time}</div><div class="lottery-raw">${d.raw}</div><div class="lottery-type type-${d.type}">${d.type}</div></div>`; });
        document.getElementById('draws-list').innerHTML = drawsHtml;

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
            return False
        if query['_s'][0] != base64.b64encode(("secure_28_web_2024").encode()).decode():
            return False
        return True

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
                
                if game_type == 'btc28': prediction = predict_btc28(draws)
                elif game_type == 'fenfen28': prediction = predict_fenfen28(draws)
                else: prediction = predict_JND(draws)
                
                latest_issue = draws[0].get('issue')
                next_issue = get_next_issue(latest_issue)
                
                history = load_history()
                if game_type not in history: history[game_type] = []
                game_history = history[game_type]
                
                # 回填补全
                if len(game_history) < 5:
                    game_history = []
                    for i in range(len(draws)-1, 0, -1):
                        past_draw = draws[i]
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
                
                # 结算上一期
                if game_history:
                    last_record = game_history[-1]
                    if last_record["status"] == "pending":
                        last_record["actual"] = draws[0]['type']
                        last_record["is_win"] = (draws[0]['type'] != last_record["kill"])
                        last_record["status"] = "settled"
                
                # 生成新一期
                if not game_history or game_history[-1]["issue"] != latest_issue:
                    game_history.append({"issue": latest_issue, "kill": prediction["kill"], "push": prediction["push"], "actual": None, "is_win": None, "status": "pending"})
                
                # 只保存最近 20 期
                game_history = game_history[-20:]
                
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
