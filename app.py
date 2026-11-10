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
from collections import defaultdict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PORT = int(os.environ.get("PORT", 8080))
SYNC_INTERVAL = 5
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

# 记录每个 IP 的请求时间，用于防爬虫限流
IP_REQUEST_TIMES = defaultdict(float)

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
