import asyncio
from datetime import datetime
import json
import os
import random
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
from playwright.async_api import async_playwright

# ---------------------------------------------------------
# Environment Parsers & Configuration
# ---------------------------------------------------------
def parse_range(var_name: str, default_min: float, default_max: float):
    raw_val = os.getenv(var_name, "").strip()
    if not raw_val:
        return default_min, default_max
    try:
        parts = [p.strip() for p in raw_val.split(",") if p.strip()]
        if len(parts) >= 2:
            return float(parts[0]), float(parts[1])
        elif len(parts) == 1:
            val = float(parts[0])
            return val, val
    except ValueError:
        print(f"[WARN] Invalid range in '{var_name}' ('{raw_val}'). Using defaults ({default_min}, {default_max}).", flush=True)
    return default_min, default_max


def parse_list(var_name: str, defaults: list):
    raw_val = os.getenv(var_name, "").strip()
    if not raw_val:
        return defaults
    items = [item.strip() for item in raw_val.split(",") if item.strip()]
    return items if items else defaults


WORKER_MIN, WORKER_MAX = parse_range("WORKER_COUNT_RANGE", 2, 6)
GAP_MIN, GAP_MAX = parse_range("WORKER_GAP_RANGE", 6.0, 12.0)
CYCLE_MIN, CYCLE_MAX = parse_range("CYCLE_INTERVAL_RANGE", 50.0, 70.0)

EXCLUDE_DESKTOP = os.getenv("EXCLUDE_DESKTOP", "").strip() == "1"
EXCLUDE_MOBILE = os.getenv("EXCLUDE_MOBILE", "").strip() == "1"

RAW_DEVICE_TYPE = os.getenv("DEVICE_TYPE", "both").strip().lower()
if RAW_DEVICE_TYPE == "desktop" or EXCLUDE_MOBILE:
    DEVICE_MODE = "desktop"
elif RAW_DEVICE_TYPE == "mobile" or EXCLUDE_DESKTOP:
    DEVICE_MODE = "mobile"
else:
    DEVICE_MODE = "both"

BROWSER_FILTER = os.getenv("BROWSER_FILTER", "all").strip().lower()

RAW_INCLUDE_COUNTRIES = [c.upper() for c in parse_list("INCLUDE_COUNTRIES", [])]
RAW_EXCLUDE_COUNTRIES = [c.upper() for c in parse_list("EXCLUDE_COUNTRIES", [])]
FINAL_EXCLUDE_COUNTRIES = set(RAW_EXCLUDE_COUNTRIES)
FINAL_INCLUDE_COUNTRIES = [c for c in RAW_INCLUDE_COUNTRIES if c not in FINAL_EXCLUDE_COUNTRIES]

DEFAULT_REFERRERS = [
    "none",
    "https://t.co/",
    "none",
    "https://l.facebook.com/",
    "https://l.instagram.com/",
    "https://www.youtube.com/",
    "none",
    "https://www.reddit.com/"
]
REFERRERS = parse_list("REFERRERS", DEFAULT_REFERRERS)
LANDING_PAGES = parse_list("LANDING_PAGES", [])

TOR_SOCKS_PORT = 9050
TOR_CONTROL_PORT = 9051


# ---------------------------------------------------------
# Screen Resolutions & Display Metadata
# ---------------------------------------------------------
SCREEN_RESOLUTIONS = {
    "desktop": [
        {"res": "1920x1080", "width": 1920, "height": 1080},
        {"res": "1536x864",  "width": 1536, "height": 864},
        {"res": "1440x900",  "width": 1440, "height": 900},
        {"res": "1366x768",  "width": 1366, "height": 768},
        {"res": "2560x1440", "width": 2560, "height": 1440},
        {"res": "1680x1050", "width": 1680, "height": 1050}
    ],
    "android": [
        {"res": "412x915", "width": 412, "height": 915},
        {"res": "384x854", "width": 384, "height": 854},
        {"res": "393x873", "width": 393, "height": 873},
        {"res": "412x892", "width": 412, "height": 892},
        {"res": "360x800", "width": 360, "height": 800},
        {"res": "412x919", "width": 412, "height": 919},
        {"res": "360x780", "width": 360, "height": 780}
    ],
    "ios": [
        {"res": "393x852",  "width": 393, "height": 852},
        {"res": "430x932",  "width": 430, "height": 932},
        {"res": "390x844",  "width": 390, "height": 844},
        {"res": "375x812",  "width": 375, "height": 812},
        {"res": "834x1194", "width": 834, "height": 1194},
        {"res": "1024x1366","width": 1024, "height": 1366}
    ]
}


# ---------------------------------------------------------
# Comprehensive User-Agent Database
# ---------------------------------------------------------
UA_DATABASE = {
    "desktop": {
        "windows": {
            "chrome": [
                {"browser": "Chrome Standard",        "ver": "140", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"},
                {"browser": "Chrome 151 (Surface)",   "ver": "151", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Surface Pro 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"},
                {"browser": "Chrome 150 (Dell XPS)",   "ver": "150", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Dell XPS 15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"},
                {"browser": "Chrome 148 (ThinkPad)",  "ver": "148", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; ThinkPad X1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"},
                {"browser": "Chrome 146 (HP Envy)",   "ver": "146", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; HP Envy x360) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"},
                {"browser": "Chrome 145 (ROG Strix)", "ver": "145", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; ASUS ROG Strix) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"},
                {"browser": "Chrome 143 (ZenBook)",   "ver": "143", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; ASUS ZenBook) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"},
                {"browser": "Chrome 141 (Legion 5)",  "ver": "141", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Lenovo Legion 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"},
                {"browser": "Chrome 137 (Acer Swift)","ver": "137", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Acer Swift 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"},
                {"browser": "Chrome 133 (Razer Blade)","ver": "133", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Razer Blade 16) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"}
            ],
            "edge": [
                {"browser": "Edge Standard",       "ver": "140", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"},
                {"browser": "Edge 150 (Surface Laptop)","ver": "150", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Surface Laptop 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0"},
                {"browser": "Edge 148 (Dell Latitude)","ver": "148", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Latitude 7440) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"},
                {"browser": "Edge 145 (ThinkBook)",   "ver": "145", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Lenovo ThinkBook) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"},
                {"browser": "Edge 143 (HP Pavilion)", "ver": "143", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; HP Pavilion 15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"},
                {"browser": "Edge 138 (Alienware)",   "ver": "138", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Alienware m16) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"}
            ],
            "firefox": [
                {"browser": "Firefox Default",      "ver": "135", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"},
                {"browser": "Firefox 145 (ThinkPad)","ver": "145", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0"},
                {"browser": "Firefox 143 (Dell XPS)", "ver": "143", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0"},
                {"browser": "Firefox 141 (Surface)",  "ver": "141", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0"},
                {"browser": "Firefox 137 (ZenBook)",  "ver": "137", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0"}
            ],
            "opera": [
                {"browser": "Opera Standard",     "ver": "118", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 OPR/118.0.0.0"},
                {"browser": "Opera 122 (HP Omen)","ver": "122", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 OPR/122.0.0.0"},
                {"browser": "Opera 116 (Predator)","ver": "116", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Acer Predator) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 OPR/116.0.0.0"}
            ]
        },
        "mac": {
            "safari": [
                {"browser": "Safari Generic",          "ver": "18.0", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"},
                {"browser": "Safari 19.4 (MacBook Pro)","ver": "19.4", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_2; MacBookPro18,1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.4 Safari/605.1.15"},
                {"browser": "Safari 19.2 (MacBook Air)","ver": "19.2", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1; MacBookAir10,1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.2 Safari/605.1.15"},
                {"browser": "Safari 19.0 (Mac Studio)", "ver": "19.0", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0; Mac13,2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Safari/605.1.15"},
                {"browser": "Safari 18.4 (iMac 24)",    "ver": "18.4", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_3; iMac21,1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15"},
                {"browser": "Safari 18.3 (Mac mini)",   "ver": "18.3", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2; Macmini9,1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15"},
                {"browser": "Safari 18.2 (MBP M2)",     "ver": "18.2", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7; Mac14,6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15"},
                {"browser": "Safari 18.1 (MBA M2)",     "ver": "18.1", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1; Mac14,2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15"},
                {"browser": "Safari 17.6 (MBP 16)",     "ver": "17.6", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_9; MacBookPro16,1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15"},
                {"browser": "Safari 17.4 (Intel Mac)",  "ver": "17.4", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"}
            ],
            "chrome": [
                {"browser": "Chrome Mac Base",        "ver": "140", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"},
                {"browser": "Chrome 150 (MacBook Pro)","ver": "150", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1; Mac15,3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"},
                {"browser": "Chrome 148 (MacBook Air)","ver": "148", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2; Mac14,15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"},
                {"browser": "Chrome 145 (Mac Studio)", "ver": "145", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; Mac14,14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"},
                {"browser": "Chrome 142 (Mac mini)",   "ver": "142", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1; Mac14,3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"},
                {"browser": "Chrome 136 (iMac M3)",    "ver": "136", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_9; Mac15,5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"}
            ],
            "firefox": [
                {"browser": "Firefox Mac Default",     "ver": "135", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0"},
                {"browser": "Firefox 143 (MacBook Pro)","ver": "143", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15.1; rv:143.0) Gecko/20100101 Firefox/143.0"},
                {"browser": "Firefox 141 (MacBook Air)","ver": "141", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:141.0) Gecko/20100101 Firefox/141.0"},
                {"browser": "Firefox 133 (Mac mini)",   "ver": "133", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.5; rv:133.0) Gecko/20100101 Firefox/133.0"}
            ],
            "edge": [
                {"browser": "Edge Mac 148 (MBP M3)","ver": "148", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1; Mac15,6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"},
                {"browser": "Edge Mac 144 (MBA M2)","ver": "144", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1; Mac14,2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"},
                {"browser": "Edge Mac 138 (iMac)",  "ver": "138", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_9; iMac21,2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"}
            ],
            "opera": [
                {"browser": "Opera Mac 120 (MBP)", "ver": "120", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1; Mac14,7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 OPR/120.0.0.0"},
                {"browser": "Opera Mac 116 (MBA)", "ver": "116", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1; Mac14,2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 OPR/116.0.0.0"}
            ]
        },
        "linux": {
            "chrome": [
                {"browser": "Chrome Linux Base",      "ver": "140", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"},
                {"browser": "Chrome 149 (Ubuntu 24)", "ver": "149", "ua": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"},
                {"browser": "Chrome 145 (Fedora 40)", "ver": "145", "ua": "Mozilla/5.0 (X11; Fedora; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"},
                {"browser": "Chrome 141 (Debian 12)", "ver": "141", "ua": "Mozilla/5.0 (X11; Debian; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"},
                {"browser": "Chrome 137 (Arch Linux)","ver": "137", "ua": "Mozilla/5.0 (X11; Arch Linux; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"}
            ],
            "firefox": [
                {"browser": "Firefox Linux",          "ver": "135", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"},
                {"browser": "Firefox 143 (Ubuntu 24)","ver": "143", "ua": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) Gecko/20100101 Firefox/143.0"},
                {"browser": "Firefox 139 (Fedora 40)","ver": "139", "ua": "Mozilla/5.0 (X11; Fedora; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"},
                {"browser": "Firefox 135 (Debian 12)","ver": "135", "ua": "Mozilla/5.0 (X11; Debian; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"}
            ],
            "edge": [
                {"browser": "Edge Linux 145 (Ubuntu)","ver": "145", "ua": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"},
                {"browser": "Edge Linux 139 (Fedora)","ver": "139", "ua": "Mozilla/5.0 (X11; Fedora; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"}
            ],
            "opera": [
                {"browser": "Opera Linux 118 (Ubuntu)","ver": "118", "ua": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 OPR/118.0.0.0"}
            ]
        }
    },
    "mobile": {
        "ios": {
            "safari": [
                {"browser": "Mobile Safari Generic",       "ver": "18.0", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Safari (iPhone 16 Pro Max)",  "ver": "19.4", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_4 like Mac OS X; iPhone16,2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.4 Mobile/15E148 Safari/604.1"},
                {"browser": "Safari (iPhone 16 Plus)",     "ver": "19.2", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_2 like Mac OS X; iPhone16,4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.2 Mobile/15E148 Safari/604.1"},
                {"browser": "Safari (iPhone 15 Pro)",      "ver": "18.4", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X; iPhone15,2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Mobile/15E148 Safari/604.1"},
                {"browser": "Safari (iPhone 15)",          "ver": "18.2", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X; iPhone15,4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1"},
                {"browser": "Safari (iPhone 14 Pro Max)",  "ver": "18.1", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X; iPhone14,3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"},
                {"browser": "Safari (iPhone 14)",          "ver": "17.6", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X; iPhone14,5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1"},
                {"browser": "Safari (iPhone 13 mini)",     "ver": "17.5", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X; iPhone14,4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"},
                {"browser": "Safari (iPad Pro 13 M4)",     "ver": "18.3", "ua": "Mozilla/5.0 (iPad; CPU OS 18_3 like Mac OS X; iPad16,3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Mobile/15E148 Safari/604.1"},
                {"browser": "Safari (iPad Air 11 M2)",     "ver": "18.2", "ua": "Mozilla/5.0 (iPad; CPU OS 18_2 like Mac OS X; iPad14,8) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1"}
            ],
            "chrome": [
                {"browser": "Chrome iOS Base",             "ver": "140", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0.0.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Chrome iOS (iPhone 16 Pro)",  "ver": "150", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_3 like Mac OS X; iPhone16,1) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/150.0.0.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Chrome iOS (iPhone 15 Pro)",  "ver": "148", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_1 like Mac OS X; iPhone15,2) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/148.0.0.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Chrome iOS (iPhone 14 Plus)", "ver": "145", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3 like Mac OS X; iPhone14,8) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/145.0.0.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Chrome iOS (iPhone 13)",      "ver": "141", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X; iPhone14,5) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/141.0.0.0 Mobile/15E148 Safari/604.1"}
            ],
            "firefox": [
                {"browser": "Firefox iOS Generic",         "ver": "140", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/140.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Firefox iOS (iPhone 16)",     "ver": "144", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_2 like Mac OS X; iPhone16,5) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/144.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Firefox iOS (iPhone 15)",     "ver": "141", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3 like Mac OS X; iPhone15,4) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/141.0 Mobile/15E148 Safari/604.1"}
            ],
            "opera": [
                {"browser": "Opera Touch (iPhone 16 Pro)", "ver": "7",   "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_1 like Mac OS X; iPhone16,1) AppleWebKit/605.1.15 (KHTML, like Gecko) OPT/7.1.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Opera Touch (iPhone 15)",     "ver": "6",   "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X; iPhone15,4) AppleWebKit/605.1.15 (KHTML, like Gecko) OPT/6.2.0 Mobile/15E148 Safari/604.1"}
            ]
        },
        "android": {
            "chrome": [
                {"browser": "Android 10 K (Default Spec)", "ver": "137", "ua": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36"},
                {"browser": "Android Generic (No Model)",   "ver": "142", "ua": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (Galaxy S24 Ultra)",    "ver": "151", "ua": "Mozilla/5.0 (Linux; Android 15; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (Pixel 9 Pro XL)",      "ver": "150", "ua": "Mozilla/5.0 (Linux; Android 15; Pixel 9 Pro XL) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (Xiaomi 14 Ultra)",     "ver": "149", "ua": "Mozilla/5.0 (Linux; Android 14; 24030PN60G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (Galaxy S24+)",         "ver": "148", "ua": "Mozilla/5.0 (Linux; Android 15; SM-S926B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (OnePlus 12)",          "ver": "147", "ua": "Mozilla/5.0 (Linux; Android 14; CPH2581) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (Pixel 8a)",            "ver": "146", "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8a) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (Galaxy A55 5G)",       "ver": "145", "ua": "Mozilla/5.0 (Linux; Android 14; SM-A556B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (Redmi Note 13 Pro+)",  "ver": "143", "ua": "Mozilla/5.0 (Linux; Android 13; 23090RA98G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (POCO F6 Pro)",         "ver": "142", "ua": "Mozilla/5.0 (Linux; Android 14; 23113RKC6G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (Galaxy Z Fold5)",      "ver": "141", "ua": "Mozilla/5.0 (Linux; Android 14; SM-F946B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome (Moto Edge 50 Ultra)",  "ver": "139", "ua": "Mozilla/5.0 (Linux; Android 14; motorola edge 50 ultra) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"}
            ],
            "firefox": [
                {"browser": "Firefox Mobile (Pixel 9 Pro)", "ver": "145", "ua": "Mozilla/5.0 (Android 15; Mobile; Pixel 9 Pro; rv:145.0) Gecko/145.0 Firefox/145.0"},
                {"browser": "Firefox Mobile (Galaxy S24)",  "ver": "142", "ua": "Mozilla/5.0 (Android 15; Mobile; SM-S921B; rv:142.0) Gecko/142.0 Firefox/142.0"},
                {"browser": "Firefox Mobile (Xiaomi 13T)",  "ver": "139", "ua": "Mozilla/5.0 (Android 14; Mobile; 2306EPN60G; rv:139.0) Gecko/139.0 Firefox/139.0"},
                {"browser": "Firefox Mobile (Galaxy A54)",  "ver": "138", "ua": "Mozilla/5.0 (Android 14; Mobile; SM-A546B; rv:138.0) Gecko/138.0 Firefox/138.0"}
            ],
            "opera": [
                {"browser": "Opera Mobile (Galaxy S24 Ultra)","ver": "89", "ua": "Mozilla/5.0 (Linux; Android 15; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36 OPR/89.0.0.0"},
                {"browser": "Opera Mobile (Pixel 8 Pro)",     "ver": "86", "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 OPR/86.0.0.0"},
                {"browser": "Opera Mobile (OnePlus 12)",      "ver": "84", "ua": "Mozilla/5.0 (Linux; Android 14; CPH2581) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36 OPR/84.0.0.0"}
            ]
        }
    }
}


# ---------------------------------------------------------
# Dynamic Hardware & Navigator Sync
# ---------------------------------------------------------
def pick_client_profile():
    if DEVICE_MODE == "desktop":
        device_key = "desktop"
    elif DEVICE_MODE == "mobile":
        device_key = "mobile"
    else:
        device_key = "mobile" if random.random() < 0.60 else "desktop"

    # OS, platform string, and hardware specs
    if device_key == "desktop":
        roll_os = random.random()
        if roll_os < 0.60:
            os_key = "windows"
            platform_header = '"Windows"'
            js_platform = "Win32"
            ram = random.choice([8, 16, 32])
            cores = random.choice([4, 8, 12, 16])
            gl_vendor = "Google Inc. (NVIDIA)"
            gl_renderer = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"
        elif roll_os < 0.93:
            os_key = "mac"
            platform_header = '"macOS"'
            js_platform = "MacIntel"
            ram = random.choice([8, 16, 24])
            cores = random.choice([8, 10, 12])
            gl_vendor = "Apple"
            gl_renderer = "Apple M2"
        else:
            os_key = "linux"
            platform_header = '"Linux"'
            js_platform = "Linux x86_64"
            ram = random.choice([8, 16])
            cores = random.choice([4, 8])
            gl_vendor = "Google Inc. (AMD)"
            gl_renderer = "ANGLE (AMD, AMD Radeon RX 6600, OpenGL 4.6)"
    else:
        if random.random() < 0.60:
            os_key = "android"
            platform_header = '"Android"'
            js_platform = "Linux armv8l"  # Real Android hardware architecture
            ram = random.choice([6, 8, 12])
            cores = 8
            gl_vendor = "Qualcomm"
            gl_renderer = "Adreno (TM) 740"
        else:
            os_key = "ios"
            platform_header = '"iOS"'
            js_platform = "iPhone"
            ram = random.choice([6, 8])
            cores = 6
            gl_vendor = "Apple Inc."
            gl_renderer = "Apple GPU"

    if device_key == "desktop":
        screen_spec = random.choice(SCREEN_RESOLUTIONS["desktop"])
    else:
        screen_spec = random.choice(SCREEN_RESOLUTIONS[os_key])

    # Browser Engine Choice
    if BROWSER_FILTER != "all":
        b_key = BROWSER_FILTER
    else:
        roll_b = random.random()
        if os_key in ("mac", "ios"):
            if roll_b < 0.70:
                b_key = "safari"
            elif roll_b < 0.95:
                b_key = "chrome"
            else:
                others = [k for k in UA_DATABASE[device_key][os_key].keys() if k not in ("safari", "chrome")]
                b_key = random.choice(others) if others else "safari"
        else:
            if roll_b < 0.65:
                b_key = "chrome"
            elif roll_b < 0.80:
                b_key = "firefox"
            elif roll_b < 0.95:
                b_key = "edge" if "edge" in UA_DATABASE[device_key][os_key] else "chrome"
            else:
                b_key = "opera"

    os_dict = UA_DATABASE[device_key][os_key]
    if b_key not in os_dict:
        b_key = "chrome" if "chrome" in os_dict else list(os_dict.keys())[0]

    selected = random.choice(os_dict[b_key])
    is_mobile_flag = "?1" if device_key == "mobile" else "?0"

    is_chromium = (b_key in ("chrome", "edge", "opera")) and (os_key != "ios")
    brand_list = ""
    if is_chromium:
        v = selected["ver"]
        if b_key == "chrome":
            brand_list = f'"Not A(Brand";v="99", "Chromium";v="{v}", "Google Chrome";v="{v}"'
        elif b_key == "edge":
            brand_list = f'"Not A(Brand";v="99", "Chromium";v="{v}", "Microsoft Edge";v="{v}"'
        elif b_key == "opera":
            brand_list = f'"Not A(Brand";v="99", "Chromium";v="{v}", "Opera";v="{v}"'

    return {
        "device": device_key.capitalize(),
        "os": os_key.capitalize(),
        "browser_engine": b_key,
        "is_chromium": is_chromium,
        "brand_list": brand_list,
        "platform_header": platform_header,
        "js_platform": js_platform,
        "ram": ram,
        "cores": cores,
        "gl_vendor": gl_vendor,
        "gl_renderer": gl_renderer,
        "is_mobile": is_mobile_flag,
        "browser_name": selected["browser"],
        "browser_ver": selected["ver"],
        "user_agent": selected["ua"],
        "screen_res": screen_spec["res"],
        "viewport_w": screen_spec["width"],
        "viewport_h": screen_spec["height"]
    }


# ---------------------------------------------------------
# Dynamic Links Resolver & Cycle Deduplication
# ---------------------------------------------------------
def get_resolved_pools():
    short_pool = []
    full_pool = []

    raw_full = parse_list("LINKS", [])
    for item in raw_full:
        if item.startswith("http://") or item.startswith("https://"):
            full_pool.append(item)
        else:
            full_pool.append(f"https://{item}")

    raw_short = parse_list("SHORT_LINKS", [])
    base_url = os.getenv("BASE_URL", "").strip().rstrip("/")

    for item in raw_short:
        if item.startswith("http://") or item.startswith("https://"):
            short_pool.append(item)
        elif base_url:
            if item.startswith("?") or item.startswith("&") or item.startswith("/"):
                short_pool.append(f"{base_url}{item}")
            else:
                short_pool.append(f"{base_url}/{item}")

    return list(dict.fromkeys(full_pool)), list(dict.fromkeys(short_pool))


def pick_cycle_targets(worker_count: int, full_pool: list, short_pool: list):
    targets = []
    available_short = list(short_pool)
    available_full = list(full_pool)

    for _ in range(worker_count):
        pick_short = False
        if available_short and available_full:
            pick_short = (random.random() < 0.88)
        elif available_short:
            pick_short = True
        elif available_full:
            pick_short = False
        else:
            available_short = list(short_pool)
            available_full = list(full_pool)
            pick_short = bool(available_short)

        if pick_short and available_short:
            chosen = random.choice(available_short)
            available_short.remove(chosen)
            targets.append(chosen)
        elif available_full:
            chosen = random.choice(available_full)
            available_full.remove(chosen)
            targets.append(chosen)

    return targets


# ---------------------------------------------------------
# Tor Daemon Management
# ---------------------------------------------------------
def start_tor_service():
    tor_cmd = [
        "tor",
        "--RunAsDaemon", "1",
        "--SocksPort", str(TOR_SOCKS_PORT),
        "--ControlPort", str(TOR_CONTROL_PORT),
        "--CookieAuthentication", "0",
        "--DataDirectory", "/tmp/tor_data"
    ]

    if FINAL_INCLUDE_COUNTRIES:
        nodes_str = ",".join([f"{{{c.lower()}}}" for c in FINAL_INCLUDE_COUNTRIES])
        tor_cmd.extend(["--ExitNodes", nodes_str, "--StrictNodes", "1"])

    if FINAL_EXCLUDE_COUNTRIES:
        exclude_str = ",".join([f"{{{c.lower()}}}" for c in FINAL_EXCLUDE_COUNTRIES])
        tor_cmd.extend(["--ExcludeExitNodes", exclude_str])

    try:
        subprocess.run(tor_cmd, check=True)
        print("[TOR] Service started. Waiting for circuit initialization...", flush=True)
        time.sleep(6)
    except Exception as e:
        print(f"[TOR CRITICAL] Failed to execute Tor binary: {e}", flush=True)
        sys.exit(1)


def renew_tor_exit_node():
    try:
        with socket.create_connection(("127.0.0.1", TOR_CONTROL_PORT), timeout=5) as s:
            s.sendall(b'AUTHENTICATE ""\r\n')
            resp = s.recv(1024)
            if b"250" not in resp:
                return False
            s.sendall(b"SIGNAL NEWNYM\r\n")
            resp = s.recv(1024)
            return b"250" in resp
    except Exception:
        return False


def get_current_exit_info():
    try:
        s = socket.create_connection(("127.0.0.1", TOR_SOCKS_PORT), timeout=10)
        s.sendall(b"\x05\x01\x00")
        s.recv(2)
        target = b"api.ipify.org"
        req = struct.pack("!BBBB", 5, 1, 0, 3) + bytes([len(target)]) + target + struct.pack("!H", 80)
        s.sendall(req)
        s.recv(10)
        s.sendall(b"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
        data = s.recv(2048).decode("utf-8", errors="ignore").split("\r\n\r\n")[-1].strip()
        s.close()
        return data, "Tor"
    except Exception:
        return "Unknown", "??"


def get_shifted_circuit(last_ip: str, max_retries=3):
    renew_tor_exit_node()
    exit_ip, country = get_current_exit_info()
    retries = 0
    while exit_ip == last_ip and retries < max_retries and exit_ip != "Unknown":
        time.sleep(1.5)
        renew_tor_exit_node()
        exit_ip, country = get_current_exit_info()
        retries += 1
    return exit_ip, country


# ---------------------------------------------------------
# Real Browser Automation Engine (Full Real-User JavaScript)
# ---------------------------------------------------------
async def execute_real_browser_bot(bot_id: int, total_bots: int, target_url: str, last_ip: str, playwright_instance):
    exit_ip, country = get_shifted_circuit(last_ip)
    client = pick_client_profile()

    chosen_ref = random.choice(REFERRERS)
    if "google" in chosen_ref.lower() or "bing" in chosen_ref.lower():
        ref_url = random.choice(LANDING_PAGES) if LANDING_PAGES else chosen_ref
    elif chosen_ref.lower() == "none":
        ref_url = ""
    else:
        ref_url = chosen_ref

    masked_target = f"{target_url[:22]}...{target_url[-8:]}" if len(target_url) > 34 else target_url
    ref_display = f"{ref_url[:18]}...{ref_url[-6:]}" if len(ref_url) > 28 else (ref_url or "None (Direct)")

    extra_headers = {
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1"
    }
    if client["is_chromium"]:
        extra_headers["Sec-CH-UA"] = client["brand_list"]
        extra_headers["Sec-CH-UA-Mobile"] = client["is_mobile"]
        extra_headers["Sec-CH-UA-Platform"] = client["platform_header"]

    # Launch genuine Chromium process through Tor socks5
    browser = await playwright_instance.chromium.launch(
        headless=True,
        proxy={"server": f"socks5://127.0.0.1:{TOR_SOCKS_PORT}"},
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars"
        ]
    )

    context = await browser.new_context(
        user_agent=client["user_agent"],
        viewport={"width": client["viewport_w"], "height": client["viewport_h"]},
        is_mobile=(client["is_mobile"] == "?1"),
        has_touch=(client["is_mobile"] == "?1"),
        extra_http_headers=extra_headers
    )

    # Injected Pre-Navigation JavaScript: Overrides platform, RAM, cores, WebGL & hides automation flags
    js_patch = f"""
        // 1. Delete webdriver fingerprint
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});

        // 2. Override platform to genuine hardware spec (e.g. 'Linux armv8l', 'Win32', 'MacIntel')
        Object.defineProperty(navigator, 'platform', {{ get: () => '{client["js_platform"]}' }});

        // 3. Hardware specifications (RAM and CPU cores)
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {client["ram"]} }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {client["cores"]} }});

        // 4. Spoof WebGL Vendor and GPU Renderer
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) return '{client["gl_vendor"]}';
            if (parameter === 37446) return '{client["gl_renderer"]}';
            return getParameter.apply(this, arguments);
        }};
    """
    await context.add_init_script(js_patch)

    page = await context.new_page()

    try:
        response = await page.goto(
            target_url,
            referer=ref_url if ref_url else None,
            timeout=45000,
            wait_until="domcontentloaded"
        )
        status_code = response.status if response else "200 OK"

        # Natural human delay and interaction
        await asyncio.sleep(random.uniform(2.5, 4.5))
        await page.mouse.wheel(0, random.randint(300, 650))
        await asyncio.sleep(random.uniform(1.5, 3.0))

        print(f"[Bot-{bot_id}/{total_bots}] [Exit: {exit_ip}] [{client['device']}-{client['os']} | {client['browser_name']} | JS: {client['js_platform']} | RAM: {client['ram']}GB | {client['screen_res']}] [Target: {masked_target}] [Ref: {ref_display}] -> HTTP {status_code} (JS Active)", flush=True)

    except Exception as ex:
        err_msg = str(ex).split("\n")[0][:80]
        print(f"[Bot-{bot_id}/{total_bots}] [Exit: {exit_ip}] [{client['device']}-{client['os']} | {client['browser_name']}] [Target: {masked_target}] [ERROR]: {err_msg}", flush=True)

    finally:
        await context.close()
        await browser.close()

    gap = random.uniform(GAP_MIN, GAP_MAX)
    await asyncio.sleep(gap)
    return exit_ip


# ---------------------------------------------------------
# Engine Main Loop
# ---------------------------------------------------------
async def main_loop():
    print("==================================================", flush=True)
    print("  TOR ENGINE (REAL PLAYWRIGHT BROWSER & FULL JS)  ", flush=True)
    print("==================================================", flush=True)
    print(f"Device Selection     : {DEVICE_MODE.upper()}", flush=True)
    print(f"Browser Filter       : {BROWSER_FILTER.upper()}", flush=True)
    print(f"Include Countries    : {', '.join(FINAL_INCLUDE_COUNTRIES) if FINAL_INCLUDE_COUNTRIES else 'ALL (Default)'}", flush=True)
    print(f"Exclude Countries    : {', '.join(FINAL_EXCLUDE_COUNTRIES) if FINAL_EXCLUDE_COUNTRIES else 'NONE'}", flush=True)
    print(f"Workers Per Cycle    : {int(WORKER_MIN)} - {int(WORKER_MAX)}", flush=True)
    print(f"Worker Gap Range     : {GAP_MIN:.1f}s - {GAP_MAX:.1f}s", flush=True)
    print(f"Cycle Duration Range : {CYCLE_MIN:.1f}s - {CYCLE_MAX:.1f}s", flush=True)
    print("==================================================\n", flush=True)

    start_tor_service()

    cycle_num = 1
    last_exit_ip = ""

    async with async_playwright() as playwright:
        try:
            while True:
                full_pool, short_pool = get_resolved_pools()

                if not full_pool and not short_pool:
                    print("----------------------------------------------------------------------", flush=True)
                    print(" [IDLE WAITING] Please configure target links in Railway:", flush=True)
                    print(" -> LINKS=https://site1.com,https://site2.com", flush=True)
                    print(" -> (Optional) BASE_URL=https://site.com & SHORT_LINKS=s1,s2", flush=True)
                    print(" Checking again in 20s...", flush=True)
                    print("----------------------------------------------------------------------\n", flush=True)
                    await asyncio.sleep(20)
                    continue

                cycle_start = time.time()
                worker_count = random.randint(int(WORKER_MIN), int(WORKER_MAX))
                target_cycle_time = random.uniform(CYCLE_MIN, CYCLE_MAX)

                cycle_links = pick_cycle_targets(worker_count, full_pool, short_pool)

                print(f"\n--- [Cycle #{cycle_num} Started] Dispatching {len(cycle_links)} real browser bots | Target: {target_cycle_time:.1f}s ---", flush=True)

                for idx, target_url in enumerate(cycle_links, start=1):
                    last_exit_ip = await execute_real_browser_bot(
                        idx, len(cycle_links), target_url, last_exit_ip, playwright
                    )

                elapsed = time.time() - cycle_start
                wait_time = target_cycle_time - elapsed

                if wait_time > 0:
                    print(f"--- [Cycle #{cycle_num} Complete] Duration: {elapsed:.1f}s | Pausing {wait_time:.1f}s before Cycle #{cycle_num + 1} ---", flush=True)
                    await asyncio.sleep(wait_time)
                else:
                    print(f"--- [Cycle #{cycle_num} Complete] Duration: {elapsed:.1f}s | Starting Cycle #{cycle_num + 1} immediately ---", flush=True)

                cycle_num += 1

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nEngine stopped.", flush=True)
            sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main_loop())