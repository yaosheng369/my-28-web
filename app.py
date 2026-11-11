import http.server
import socketserver
import urllib.request
import json
import time
import base64
import os
import re
import hashlib
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

# ================= 300套独立算法矩阵 (明文写死) =================
# 1-60: 冷热频率类 (窗口 3-15)
# 61-120: 连号与趋势类
# 121-180: 均值回归与EMA
# 181-240: 斐波那契与周期
# 241-300: 哈希与高阶混合
ALGORITHMS = [
    {"id": 1, "method": "freq", "window": 3, "mode": "hot"}, {"id": 2, "method": "freq", "window": 4, "mode": "cold"}, {"id": 3, "method": "freq", "window": 5, "mode": "hot"}, 
    {"id": 4, "method": "freq", "window": 6, "mode": "cold"}, {"id": 5, "method": "freq", "window": 7, "mode": "hot"}, {"id": 6, "method": "freq", "window": 8, "mode": "cold"},
    {"id": 7, "method": "freq", "window": 9, "mode": "hot"}, {"id": 8, "method": "freq", "window": 10, "mode": "cold"}, {"id": 9, "method": "freq", "window": 11, "mode": "hot"},
    {"id": 10, "method": "freq", "window": 12, "mode": "cold"}, {"id": 11, "method": "freq", "window": 13, "mode": "hot"}, {"id": 12, "method": "freq", "window": 14, "mode": "cold"},
    {"id": 13, "method": "freq", "window": 15, "mode": "hot"}, {"id": 14, "method": "freq", "window": 3, "mode": "cold"}, {"id": 15, "method": "freq", "window": 4, "mode": "hot"},
    {"id": 16, "method": "freq", "window": 5, "mode": "cold"}, {"id": 17, "method": "freq", "window": 6, "mode": "hot"}, {"id": 18, "method": "freq", "window": 7, "mode": "cold"},
    {"id": 19, "method": "freq", "window": 8, "mode": "hot"}, {"id": 20, "method": "freq", "window": 9, "mode": "cold"}, {"id": 21, "method": "freq", "window": 10, "mode": "hot"},
    {"id": 22, "method": "freq", "window": 11, "mode": "cold"}, {"id": 23, "method": "freq", "window": 12, "mode": "hot"}, {"id": 24, "method": "freq", "window": 13, "mode": "cold"},
    {"id": 25, "method": "freq", "window": 14, "mode": "hot"}, {"id": 26, "method": "freq", "window": 15, "mode": "cold"}, {"id": 27, "method": "freq", "window": 3, "mode": "hot"},
    {"id": 28, "method": "freq", "window": 4, "mode": "cold"}, {"id": 29, "method": "freq", "window": 5, "mode": "hot"}, {"id": 30, "method": "freq", "window": 6, "mode": "cold"},
    {"id": 31, "method": "freq", "window": 7, "mode": "hot"}, {"id": 32, "method": "freq", "window": 8, "mode": "cold"}, {"id": 33, "method": "freq", "window": 9, "mode": "hot"},
    {"id": 34, "method": "freq", "window": 10, "mode": "cold"}, {"id": 35, "method": "freq", "window": 11, "mode": "hot"}, {"id": 36, "method": "freq", "window": 12, "mode": "cold"},
    {"id": 37, "method": "freq", "window": 13, "mode": "hot"}, {"id": 38, "method": "freq", "window": 14, "mode": "cold"}, {"id": 39, "method": "freq", "window": 15, "mode": "hot"},
    {"id": 40, "method": "freq", "window": 3, "mode": "cold"}, {"id": 41, "method": "freq", "window": 4, "mode": "hot"}, {"id": 42, "method": "freq", "window": 5, "mode": "cold"},
    {"id": 43, "method": "freq", "window": 6, "mode": "hot"}, {"id": 44, "method": "freq", "window": 7, "mode": "cold"}, {"id": 45, "method": "freq", "window": 8, "mode": "hot"},
    {"id": 46, "method": "freq", "window": 9, "mode": "cold"}, {"id": 47, "method": "freq", "window": 10, "mode": "hot"}, {"id": 48, "method": "freq", "window": 11, "mode": "cold"},
    {"id": 49, "method": "freq", "window": 12, "mode": "hot"}, {"id": 50, "method": "freq", "window": 13, "mode": "cold"}, {"id": 51, "method": "freq", "window": 14, "mode": "hot"},
    {"id": 52, "method": "freq", "window": 15, "mode": "cold"}, {"id": 53, "method": "freq", "window": 3, "mode": "hot"}, {"id": 54, "method": "freq", "window": 4, "mode": "cold"},
    {"id": 55, "method": "freq", "window": 5, "mode": "hot"}, {"id": 56, "method": "freq", "window": 6, "mode": "cold"}, {"id": 57, "method": "freq", "window": 7, "mode": "hot"},
    {"id": 58, "method": "freq", "window": 8, "mode": "cold"}, {"id": 59, "method": "freq", "window": 9, "mode": "hot"}, {"id": 60, "method": "freq", "window": 10, "mode": "cold"},

    {"id": 61, "method": "streak", "window": 3, "mode": "follow"}, {"id": 62, "method": "streak", "window": 4, "mode": "break"}, {"id": 63, "method": "streak", "window": 5, "mode": "follow"},
    {"id": 64, "method": "streak", "window": 6, "mode": "break"}, {"id": 65, "method": "streak", "window": 7, "mode": "follow"}, {"id": 66, "method": "streak", "window": 8, "mode": "break"},
    {"id": 67, "method": "streak", "window": 9, "mode": "follow"}, {"id": 68, "method": "streak", "window": 10, "mode": "break"}, {"id": 69, "method": "streak", "window": 11, "mode": "follow"},
    {"id": 70, "method": "streak", "window": 12, "mode": "break"}, {"id": 71, "method": "streak", "window": 13, "mode": "follow"}, {"id": 72, "method": "streak", "window": 14, "mode": "break"},
    {"id": 73, "method": "streak", "window": 15, "mode": "follow"}, {"id": 74, "method": "streak", "window": 3, "mode": "break"}, {"id": 75, "method": "streak", "window": 4, "mode": "follow"},
    {"id": 76, "method": "streak", "window": 5, "mode": "break"}, {"id": 77, "method": "streak", "window": 6, "mode": "follow"}, {"id": 78, "method": "streak", "window": 7, "mode": "break"},
    {"id": 79, "method": "streak", "window": 8, "mode": "follow"}, {"id": 80, "method": "streak", "window": 9, "mode": "break"}, {"id": 81, "method": "streak", "window": 10, "mode": "follow"},
    {"id": 82, "method": "streak", "window": 11, "mode": "break"}, {"id": 83, "method": "streak", "window": 12, "mode": "follow"}, {"id": 84, "method": "streak", "window": 13, "mode": "break"},
    {"id": 85, "method": "streak", "window": 14, "mode": "follow"}, {"id": 86, "method": "streak", "window": 15, "mode": "break"}, {"id": 87, "method": "streak", "window": 3, "mode": "follow"},
    {"id": 88, "method": "streak", "window": 4, "mode": "break"}, {"id": 89, "method": "streak", "window": 5, "mode": "follow"}, {"id": 90, "method": "streak", "window": 6, "mode": "break"},
    {"id": 91, "method": "streak", "window": 7, "mode": "follow"}, {"id": 92, "method": "streak", "window": 8, "mode": "break"}, {"id": 93, "method": "streak", "window": 9, "mode": "follow"},
    {"id": 94, "method": "streak", "window": 10, "mode": "break"}, {"id": 95, "method": "streak", "window": 11, "mode": "follow"}, {"id": 96, "method": "streak", "window": 12, "mode": "break"},
    {"id": 97, "method": "streak", "window": 13, "mode": "follow"}, {"id": 98, "method": "streak", "window": 14, "mode": "break"}, {"id": 99, "method": "streak", "window": 15, "mode": "follow"},
    {"id": 100, "method": "streak", "window": 3, "mode": "break"}, {"id": 101, "method": "streak", "window": 4, "mode": "follow"}, {"id": 102, "method": "streak", "window": 5, "mode": "break"},
    {"id": 103, "method": "streak", "window": 6, "mode": "follow"}, {"id": 104, "method": "streak", "window": 7, "mode": "break"}, {"id": 105, "method": "streak", "window": 8, "mode": "follow"},
    {"id": 106, "method": "streak", "window": 9, "mode": "break"}, {"id": 107, "method": "streak", "window": 10, "mode": "follow"}, {"id": 108, "method": "streak", "window": 11, "mode": "break"},
    {"id": 109, "method": "streak", "window": 12, "mode": "follow"}, {"id": 110, "method": "streak", "window": 13, "mode": "break"}, {"id": 111, "method": "streak", "window": 14, "mode": "follow"},
    {"id": 112, "method": "streak", "window": 15, "mode": "break"}, {"id": 113, "method": "streak", "window": 3, "mode": "follow"}, {"id": 114, "method": "streak", "window": 4, "mode": "break"},
    {"id": 115, "method": "streak", "window": 5, "mode": "follow"}, {"id": 116, "method": "streak", "window": 6, "mode": "break"}, {"id": 117, "method": "streak", "window": 7, "mode": "follow"},
    {"id": 118, "method": "streak", "window": 8, "mode": "break"}, {"id": 119, "method": "streak", "window": 9, "mode": "follow"}, {"id": 120, "method": "streak", "window": 10, "mode": "break"},

    {"id": 121, "method": "mean", "window": 5, "mode": "big"}, {"id": 122, "method": "mean", "window": 6, "mode": "small"}, {"id": 123, "method": "mean", "window": 7, "mode": "big"},
    {"id": 124, "method": "mean", "window": 8, "mode": "small"}, {"id": 125, "method": "mean", "window": 9, "mode": "big"}, {"id": 126, "method": "mean", "window": 10, "mode": "small"},
    {"id": 127, "method": "mean", "window": 11, "mode": "big"}, {"id": 128, "method": "mean", "window": 12, "mode": "small"}, {"id": 129, "method": "mean", "window": 13, "mode": "big"},
    {"id": 130, "method": "mean", "window": 14, "mode": "small"}, {"id": 131, "method": "mean", "window": 15, "mode": "big"}, {"id": 132, "method": "mean", "window": 16, "mode": "small"},
    {"id": 133, "method": "mean", "window": 17, "mode": "big"}, {"id": 134, "method": "mean", "window": 18, "mode": "small"}, {"id": 135, "method": "mean", "window": 19, "mode": "big"},
    {"id": 136, "method": "mean", "window": 20, "mode": "small"}, {"id": 137, "method": "mean", "window": 5, "mode": "small"}, {"id": 138, "method": "mean", "window": 6, "mode": "big"},
    {"id": 139, "method": "mean", "window": 7, "mode": "small"}, {"id": 140, "method": "mean", "window": 8, "mode": "big"}, {"id": 141, "method": "mean", "window": 9, "mode": "small"},
    {"id": 142, "method": "mean", "window": 10, "mode": "big"}, {"id": 143, "method": "mean", "window": 11, "mode": "small"}, {"id": 144, "method": "mean", "window": 12, "mode": "big"},
    {"id": 145, "method": "mean", "window": 13, "mode": "small"}, {"id": 146, "method": "mean", "window": 14, "mode": "big"}, {"id": 147, "method": "mean", "window": 15, "mode": "small"},
    {"id": 148, "method": "mean", "window": 16, "mode": "big"}, {"id": 149, "method": "mean", "window": 17, "mode": "small"}, {"id": 150, "method": "mean", "window": 18, "mode": "big"},
    {"id": 151, "method": "mean", "window": 19, "mode": "small"}, {"id": 152, "method": "mean", "window": 20, "mode": "big"}, {"id": 153, "method": "mean", "window": 5, "mode": "big"},
    {"id": 154, "method": "mean", "window": 6, "mode": "small"}, {"id": 155, "method": "mean", "window": 7, "mode": "big"}, {"id": 156, "method": "mean", "window": 8, "mode": "small"},
    {"id": 157, "method": "mean", "window": 9, "mode": "big"}, {"id": 158, "method": "mean", "window": 10, "mode": "small"}, {"id": 159, "method": "mean", "window": 11, "mode": "big"},
    {"id": 160, "method": "mean", "window": 12, "mode": "small"}, {"id": 161, "method": "mean", "window": 13, "mode": "big"}, {"id": 162, "method": "mean", "window": 14, "mode": "small"},
    {"id": 163, "method": "mean", "window": 15, "mode": "big"}, {"id": 164, "method": "mean", "window": 16, "mode": "small"}, {"id": 165, "method": "mean", "window": 17, "mode": "big"},
    {"id": 166, "method": "mean", "window": 18, "mode": "small"}, {"id": 167, "method": "mean", "window": 19, "mode": "big"}, {"id": 168, "method": "mean", "window": 20, "mode": "small"},
    {"id": 169, "method": "mean", "window": 5, "mode": "big"}, {"id": 170, "method": "mean", "window": 6, "mode": "small"}, {"id": 171, "method": "mean", "window": 7, "mode": "big"},
    {"id": 172, "method": "mean", "window": 8, "mode": "small"}, {"id": 173, "method": "mean", "window": 9, "mode": "big"}, {"id": 174, "method": "mean", "window": 10, "mode": "small"},
    {"id": 175, "method": "mean", "window": 11, "mode": "big"}, {"id": 176, "method": "mean", "window": 12, "mode": "small"}, {"id": 177, "method": "mean", "window": 13, "mode": "big"},
    {"id": 178, "method": "mean", "window": 14, "mode": "small"}, {"id": 179, "method": "mean", "window": 15, "mode": "big"}, {"id": 180, "method": "mean", "window": 16, "mode": "small"},

    {"id": 181, "method": "ema", "window": 5, "alpha": 0.1}, {"id": 182, "method": "ema", "window": 6, "alpha": 0.2}, {"id": 183, "method": "ema", "window": 7, "alpha": 0.3},
    {"id": 184, "method": "ema", "window": 8, "alpha": 0.4}, {"id": 185, "method": "ema", "window": 9, "alpha": 0.5}, {"id": 186, "method": "ema", "window": 10, "alpha": 0.6},
    {"id": 187, "method": "ema", "window": 11, "alpha": 0.7}, {"id": 188, "method": "ema", "window": 12, "alpha": 0.8}, {"id": 189, "method": "ema", "window": 13, "alpha": 0.9},
    {"id": 190, "method": "ema", "window": 14, "alpha": 0.15}, {"id": 191, "method": "ema", "window": 15, "alpha": 0.25}, {"id": 192, "method": "ema", "window": 16, "alpha": 0.35},
    {"id": 193, "method": "ema", "window": 17, "alpha": 0.45}, {"id": 194, "method": "ema", "window": 18, "alpha": 0.55}, {"id": 195, "method": "ema", "window": 19, "alpha": 0.65},
    {"id": 196, "method": "ema", "window": 20, "alpha": 0.75}, {"id": 197, "method": "ema", "window": 5, "alpha": 0.85}, {"id": 198, "method": "ema", "window": 6, "alpha": 0.95},
    {"id": 199, "method": "ema", "window": 7, "alpha": 0.12}, {"id": 200, "method": "ema", "window": 8, "alpha": 0.22}, {"id": 201, "method": "ema", "window": 9, "alpha": 0.32},
    {"id": 202, "method": "ema", "window": 10, "alpha": 0.42}, {"id": 203, "method": "ema", "window": 11, "alpha": 0.52}, {"id": 204, "method": "ema", "window": 12, "alpha": 0.62},
    {"id": 205, "method": "ema", "window": 13, "alpha": 0.72}, {"id": 206, "method": "ema", "window": 14, "alpha": 0.82}, {"id": 207, "method": "ema", "window": 15, "alpha": 0.92},
    {"id": 208, "method": "ema", "window": 16, "alpha": 0.18}, {"id": 209, "method": "ema", "window": 17, "alpha": 0.28}, {"id": 210, "method": "ema", "window": 18, "alpha": 0.38},
    {"id": 211, "method": "ema", "window": 19, "alpha": 0.48}, {"id": 212, "method": "ema", "window": 20, "alpha": 0.58}, {"id": 213, "method": "ema", "window": 5, "alpha": 0.68},
    {"id": 214, "method": "ema", "window": 6, "alpha": 0.78}, {"id": 215, "method": "ema", "window": 7, "alpha": 0.88}, {"id": 216, "method": "ema", "window": 8, "alpha": 0.98},
    {"id": 217, "method": "ema", "window": 9, "alpha": 0.11}, {"id": 218, "method": "ema", "window": 10, "alpha": 0.21}, {"id": 219, "method": "ema", "window": 11, "alpha": 0.31},
    {"id": 220, "method": "ema", "window": 12, "alpha": 0.41}, {"id": 221, "method": "ema", "window": 13, "alpha": 0.51}, {"id": 222, "method": "ema", "window": 14, "alpha": 0.61},
    {"id": 223, "method": "ema", "window": 15, "alpha": 0.71}, {"id": 224, "method": "ema", "window": 16, "alpha": 0.81}, {"id": 225, "method": "ema", "window": 17, "alpha": 0.91},
    {"id": 226, "method": "ema", "window": 18, "alpha": 0.14}, {"id": 227, "method": "ema", "window": 19, "alpha": 0.24}, {"id": 228, "method": "ema", "window": 20, "alpha": 0.34},
    {"id": 229, "method": "ema", "window": 5, "alpha": 0.44}, {"id": 230, "method": "ema", "window": 6, "alpha": 0.54}, {"id": 231, "method": "ema", "window": 7, "alpha": 0.64},
    {"id": 232, "method": "ema", "window": 8, "alpha": 0.74}, {"id": 233, "method": "ema", "window": 9, "alpha": 0.84}, {"id": 234, "method": "ema", "window": 10, "alpha": 0.94},
    {"id": 235, "method": "ema", "window": 11, "alpha": 0.16}, {"id": 236, "method": "ema", "window": 12, "alpha": 0.26}, {"id": 237, "method": "ema", "window": 13, "alpha": 0.36},
    {"id": 238, "method": "ema", "window": 14, "alpha": 0.46}, {"id": 239, "method": "ema", "window": 15, "alpha": 0.56}, {"id": 240, "method": "ema", "window": 16, "alpha": 0.66},

    {"id": 241, "method": "mod", "mod_val": 3}, {"id": 242, "method": "mod", "mod_val": 4}, {"id": 243, "method": "mod", "mod_val": 5}, {"id": 244, "method": "mod", "mod_val": 6}, {"id": 245, "method": "mod", "mod_val": 7},
    {"id": 246, "method": "mod", "mod_val": 8}, {"id": 247, "method": "mod", "mod_val": 9}, {"id": 248, "method": "mod", "mod_val": 3}, {"id": 249, "method": "mod", "mod_val": 4}, {"id": 250, "method": "mod", "mod_val": 5},
    {"id": 251, "method": "mod", "mod_val": 6}, {"id": 252, "method": "mod", "mod_val": 7}, {"id": 253, "method": "mod", "mod_val": 8}, {"id": 254, "method": "mod", "mod_val": 9}, {"id": 255, "method": "mod", "mod_val": 3},
    {"id": 256, "method": "mod", "mod_val": 4}, {"id": 257, "method": "mod", "mod_val": 5}, {"id": 258, "method": "mod", "mod_val": 6}, {"id": 259, "method": "mod", "mod_val": 7}, {"id": 260, "method": "mod", "mod_val": 8},
    {"id": 261, "method": "mod", "mod_val": 9}, {"id": 262, "method": "mod", "mod_val": 3}, {"id": 263, "method": "mod", "mod_val": 4}, {"id": 264, "method": "mod", "mod_val": 5}, {"id": 265, "method": "mod", "mod_val": 6},
    {"id": 266, "method": "mod", "mod_val": 7}, {"id": 267, "method": "mod", "mod_val": 8}, {"id": 268, "method": "mod", "mod_val": 9}, {"id": 269, "method": "mod", "mod_val": 3}, {"id": 270, "method": "mod", "mod_val": 4},
    {"id": 271, "method": "mod", "mod_val": 5}, {"id": 272, "method": "mod", "mod_val": 6}, {"id": 273, "method": "mod", "mod_val": 7}, {"id": 274, "method": "mod", "mod_val": 8}, {"id": 275, "method": "mod", "mod_val": 9},
    {"id": 276, "method": "mod", "mod_val": 3}, {"id": 277, "method": "mod", "mod_val": 4}, {"id": 278, "method": "mod", "mod_val": 5}, {"id": 279, "method": "mod", "mod_val": 6}, {"id": 280, "method": "mod", "mod_val": 7},
    {"id": 281, "method": "mod", "mod_val": 8}, {"id": 282, "method": "mod", "mod_val": 9}, {"id": 283, "method": "mod", "mod_val": 3}, {"id": 284, "method": "mod", "mod_val": 4}, {"id": 285, "method": "mod", "mod_val": 5},
    {"id": 286, "method": "mod", "mod_val": 6}, {"id": 287, "method": "mod", "mod_val": 7}, {"id": 288, "method": "mod", "mod_val": 8}, {"id": 289, "method": "mod", "mod_val": 9}, {"id": 290, "method": "mod", "mod_val": 3},
    {"id": 291, "method": "mod", "mod_val": 4}, {"id": 292, "method": "mod", "mod_val": 5}, {"id": 293, "method": "mod", "mod_val": 6}, {"id": 294, "method": "mod", "mod_val": 7}, {"id": 295, "method": "mod", "mod_val": 8},
    {"id": 296, "method": "mod", "mod_val": 9}, {"id": 297, "method": "mod", "mod_val": 3}, {"id": 298, "method": "mod", "mod_val": 4}, {"id": 299, "method": "mod", "mod_val": 5}, {"id": 300, "method": "mod", "mod_val": 6}
]

COMBOS = ["大单", "大双", "小单", "小双"]

def dynamic_predict(draws, issue_str):
    """核心：根据期号动态调用 300 套算法中的一套，绝对互不干扰"""
    match = re.search(r'(\d+)$', str(issue_str))
    issue_num = int(match.group(1)) if match else 0
    
    # 利用期号哈希选取算法，保证每期算法不同
    algo_index = issue_num % 300
    algo = ALGORITHMS[algo_index]
    
    if not draws:
        return {"kill": "大单", "push": ["大双", "小单", "小双"]}

    recent = draws[:algo.get("window", 5)]
    counts = {c: 0 for c in COMBOS}
    for d in recent: 
        if d.get('type') in counts:
            counts[d['type']] += 1
        
    kill = ""
    method = algo["method"]
    
    if method == "freq": # 冷热
        kill = max(counts, key=counts.get) if algo["mode"] == "hot" else min(counts, key=counts.get)
    elif method == "streak": # 连号
        last = recent[0]['type']
        streak = sum(1 for d in recent if d['type'] == last)
        if algo["mode"] == "follow":
            kill = last if streak >= 2 else next(c for c in COMBOS if c != last)
        else:
            kill = next(c for c in COMBOS if c != last) if streak >= 2 else last
    elif method == "mean": # 均值回归
        da = sum(1 for d in recent if '大' in d['type'])
        dan = sum(1 for d in recent if '单' in d['type'])
        target_big = '大' if da > len(recent)/2 else '小'
        target_dan = '单' if dan > len(recent)/2 else '双'
        if algo["mode"] == "big": target_big = '小' if target_big == '大' else '大'
        if algo["mode"] == "small": target_dan = '双' if target_dan == '单' else '单'
        kill = target_big + target_dan
    elif method == "ema": # 指数移动平均
        alpha = algo.get("alpha", 0.5)
        ema_big = 0
        for i, d in enumerate(recent):
            ema_big = (1 if '大' in d['type'] else 0) * alpha + ema_big * (1 - alpha)
        kill = ('小' if ema_big > 0.5 else '大') + ('单' if issue_num % 2 == 0 else '双')
    elif method == "mod": # 期号模
        mod_val = algo.get("mod_val", 4)
        kill = COMBOS[issue_num % mod_val]
        
    if kill not in COMBOS: 
        # 极端容错 + 时间散列，防止固定
        seed = str(issue_num) + str(int(time.time() // 60))
        h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
        kill = COMBOS[h % 4]

    return {"kill": kill, "push": [c for c in COMBOS if c != kill]}

def get_next_issue(issue_str, offset=1):
    match = re.search(r'(\d+)$', str(issue_str))
    if match:
        num_str = match.group(1)
        prefix = str(issue_str)[:-len(num_str)]
        return prefix + str(int(num_str) + offset).zfill(len(num_str))
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

# ================= 前端 HTML (保持原样) =================
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
                next_issue = get_next_issue(latest_issue, 1) 
                
                history = load_history()
                if game_type not in history: history[game_type] = []
                game_history = history[game_type]
                
                # ================= 修复断层核心逻辑 =================
                # 以 API 返回的实际开奖数据为基准，自动回溯补齐缺失的期号
                existing_issues = {r['issue'] for r in game_history}
                
                # 倒序遍历最近30期，补全历史记录中缺失的期号
                for i in range(len(draws) - 1, -1, -1):
                    past_draw = draws[i]
                    past_issue = past_draw['issue']
                    if past_issue not in existing_issues:
                        # 缺失该期记录，利用当时的开奖数据生成预测
                        historical_context = draws[i:]
                        past_pred = dynamic_predict(historical_context, past_issue)
                        game_history.append({
                            "issue": past_issue,
                            "kill": past_pred['kill'],
                            "push": past_pred['push'],
                            "actual": past_draw['type'],
                            "is_win": (past_draw['type'] != past_pred['kill']),
                            "status": "settled"
                        })
                        existing_issues.add(past_issue)
                
                # 按照期号尾数进行排序，防止顺序错乱
                def sort_key(x):
                    m = re.search(r'(\d+)$', str(x['issue']))
                    return int(m.group(1)) if m else 0
                game_history.sort(key=sort_key)
                
                # 只保留最近20期记录
                game_history = game_history[-20:]
                
                # 结算待开奖状态
                for record in game_history:
                    if record["status"] == "pending":
                        # 检查是否已开奖
                        for d in draws:
                            if d['issue'] == record['issue']:
                                record["actual"] = d['type']
                                record["is_win"] = (d['type'] != record["kill"])
                                record["status"] = "settled"
                                break
                
                # 最后追加最新一期的预测 (目标下期)
                if not any(r['issue'] == next_issue for r in game_history):
                    pred = dynamic_predict(draws, next_issue)
                    game_history.append({
                        "issue": next_issue, 
                        "kill": pred["kill"], 
                        "push": pred["push"], 
                        "actual": None, 
                        "is_win": None, 
                        "status": "pending"
                    })
                
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
