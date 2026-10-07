from datetime import datetime
import json
import os
import random
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.parse

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
        print(f"[WARN] Invalid range in '{var_name}' ('{raw_val}'). Using defaults ({default_min}, {default_max}).")
    return default_min, default_max


def parse_list(var_name: str, defaults: list):
    raw_val = os.getenv(var_name, "").strip()
    if not raw_val:
        return defaults
    items = [item.strip() for item in raw_val.split(",") if item.strip()]
    return items if items else defaults


WORKER_MIN, WORKER_MAX = parse_range("WORKER_COUNT_RANGE", 3, 5)
GAP_MIN, GAP_MAX = parse_range("WORKER_GAP_RANGE", 6.0, 12.0)
CYCLE_MIN, CYCLE_MAX = parse_range("CYCLE_INTERVAL_RANGE", 45.0, 60.0)

# Device Configuration & Exclusions (Writing "1" excludes that device type)
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

# Country Filter Logic (Case-insensitive & conflict resolution)
RAW_INCLUDE_COUNTRIES = [c.upper() for c in parse_list("INCLUDE_COUNTRIES", [])]
RAW_EXCLUDE_COUNTRIES = [c.upper() for c in parse_list("EXCLUDE_COUNTRIES", [])]
FINAL_EXCLUDE_COUNTRIES = set(RAW_EXCLUDE_COUNTRIES)
FINAL_INCLUDE_COUNTRIES = [c for c in RAW_INCLUDE_COUNTRIES if c not in FINAL_EXCLUDE_COUNTRIES]

DEFAULT_REFERRERS = [
    "none",
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    "https://search.yahoo.com/",
    "https://www.facebook.com/",
    "https://l.facebook.com/",
    "https://www.instagram.com/",
    "https://t.co/",
    "https://x.com/",
    "https://twitter.com/",
    "https://www.reddit.com/",
    "https://web.telegram.org/",
    "https://discord.com/",
    "https://www.youtube.com/"
]
REFERRERS = parse_list("REFERRERS", DEFAULT_REFERRERS)

TOR_SOCKS_PORT = 9050
TOR_CONTROL_PORT = 9051


# ---------------------------------------------------------
# OS-Specific User-Agent Database
# ---------------------------------------------------------
UA_DATABASE = {
    "desktop": {
        "windows": {
            "chrome": [
                {"browser": "Chrome 149", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"},
                {"browser": "Chrome 148", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"},
                {"browser": "Chrome 143", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"},
                {"browser": "Chrome 137", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"},
                {"browser": "Chrome 133", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"}
            ],
            "edge": [
                {"browser": "Edge 148", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"},
                {"browser": "Edge 143", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"},
                {"browser": "Edge 139", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"},
                {"browser": "Edge 135", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"}
            ],
            "firefox": [
                {"browser": "Firefox 143", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0"},
                {"browser": "Firefox 138", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0"},
                {"browser": "Firefox 134", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0"},
                {"browser": "Firefox 132", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0"}
            ],
            "opera": [
                {"browser": "Opera 120", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 OPR/120.0.0.0"},
                {"browser": "Opera 117", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 OPR/117.0.0.0"},
                {"browser": "Opera 115", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 OPR/115.0.0.0"}
            ]
        },
        "mac": {
            "safari": [
                {"browser": "Safari 19.2", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.2 Safari/605.1.15"},
                {"browser": "Safari 19.0", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Safari/605.1.15"},
                {"browser": "Safari 18.3", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15"},
                {"browser": "Safari 18.2", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15"},
                {"browser": "Safari 18.1", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15"},
                {"browser": "Safari 18.0", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"},
                {"browser": "Safari 17.6", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_9) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15"},
                {"browser": "Safari 17.5", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"},
                {"browser": "Safari 17.4", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"}
            ],
            "chrome": [
                {"browser": "Chrome 148", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"},
                {"browser": "Chrome 145", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"},
                {"browser": "Chrome 139", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"},
                {"browser": "Chrome 135", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"}
            ],
            "firefox": [
                {"browser": "Firefox 141", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:141.0) Gecko/20100101 Firefox/141.0"},
                {"browser": "Firefox 136", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0"},
                {"browser": "Firefox 130", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.5; rv:130.0) Gecko/20100101 Firefox/130.0"}
            ],
            "edge": [
                {"browser": "Edge 146", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"},
                {"browser": "Edge 137", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"}
            ],
            "opera": [
                {"browser": "Opera 118", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 OPR/118.0.0.0"},
                {"browser": "Opera 114", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 OPR/114.0.0.0"}
            ]
        },
        "linux": {
            "chrome": [
                {"browser": "Chrome 141", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"},
                {"browser": "Chrome 137", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"},
                {"browser": "Chrome 133", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"}
            ],
            "firefox": [
                {"browser": "Firefox 139", "ua": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0"},
                {"browser": "Firefox 135", "ua": "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0"}
            ],
            "edge": [
                {"browser": "Edge 141", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"}
            ],
            "opera": [
                {"browser": "Opera 116", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 OPR/116.0.0.0"}
            ]
        }
    },
    "mobile": {
        "ios": {
            "safari": [
                {"browser": "Mobile Safari 19.2", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.2 Mobile/15E148 Safari/604.1"},
                {"browser": "Mobile Safari 19.0", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Mobile Safari 18.3", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Mobile/15E148 Safari/604.1"},
                {"browser": "Mobile Safari 18.2", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1"},
                {"browser": "Mobile Safari 18.1", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"},
                {"browser": "Mobile Safari 18.0", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Mobile Safari 17.6", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1"},
                {"browser": "Mobile Safari 17.5", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"},
                {"browser": "Mobile Safari iPad", "ua": "Mozilla/5.0 (iPad; CPU OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1"}
            ],
            "chrome": [
                {"browser": "Chrome iOS 149", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/149.0.0.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Chrome iOS 145", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/145.0.0.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Chrome iOS 141", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/141.0.0.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Chrome iOS 137", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/137.0.0.0 Mobile/15E148 Safari/604.1"}
            ],
            "firefox": [
                {"browser": "Firefox iOS 142", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/142.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Firefox iOS 139", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/139.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Firefox iOS 136", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/136.0 Mobile/15E148 Safari/604.1"}
            ],
            "opera": [
                {"browser": "Opera Touch iOS 6", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) OPT/6.2.0 Mobile/15E148 Safari/604.1"},
                {"browser": "Opera Touch iOS 5", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) OPT/5.8.0 Mobile/15E148 Safari/604.1"}
            ]
        },
        "android": {
            "chrome": [
                {"browser": "Chrome Mobile 149", "ua": "Mozilla/5.0 (Linux; Android 15; SM-S938B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome Mobile 148", "ua": "Mozilla/5.0 (Linux; Android 15; Pixel 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome Mobile 145", "ua": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome Mobile 143", "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome Mobile 139", "ua": "Mozilla/5.0 (Linux; Android 13; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"},
                {"browser": "Chrome Mobile 135", "ua": "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"}
            ],
            "firefox": [
                {"browser": "Firefox Mobile 143", "ua": "Mozilla/5.0 (Android 15; Mobile; rv:143.0) Gecko/143.0 Firefox/143.0"},
                {"browser": "Firefox Mobile 139", "ua": "Mozilla/5.0 (Android 14; Mobile; rv:139.0) Gecko/139.0 Firefox/139.0"},
                {"browser": "Firefox Mobile 135", "ua": "Mozilla/5.0 (Android 13; Mobile; rv:135.0) Gecko/135.0 Firefox/135.0"}
            ],
            "opera": [
                {"browser": "Opera Mobile 87", "ua": "Mozilla/5.0 (Linux; Android 15; SM-S938B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36 OPR/87.0.0.0"},
                {"browser": "Opera Mobile 85", "ua": "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36 OPR/85.0.0.0"}
            ]
        }
    }
}


# ---------------------------------------------------------
# Dynamic Browser & OS Routing Engine
# ---------------------------------------------------------
def pick_user_agent():
    # 1. Device Selection
    if DEVICE_MODE == "desktop":
        device_key = "desktop"
    elif DEVICE_MODE == "mobile":
        device_key = "mobile"
    else:
        device_key = "mobile" if random.random() < 0.60 else "desktop"

    # 2. OS Selection (Desktop: 60% Windows, 33% Mac, 7% Linux | Mobile: 60% Android, 40% iOS)
    if device_key == "desktop":
        roll_os = random.random()
        if roll_os < 0.60:
            os_key = "windows"
        elif roll_os < 0.93:
            os_key = "mac"
        else:
            os_key = "linux"
    else:
        os_key = "android" if random.random() < 0.60 else "ios"

    # 3. Browser Distribution Rule (Specific to Apple Ecosystem vs Others)
    if BROWSER_FILTER != "all":
        b_key = BROWSER_FILTER
    else:
        roll_b = random.random()
        if os_key in ("mac", "ios"):
            # 70% Native Safari, 25% Chrome, 5% Others (Firefox, Opera, Edge)
            if roll_b < 0.70:
                b_key = "safari"
            elif roll_b < 0.95:
                b_key = "chrome"
            else:
                other_choices = [k for k in UA_DATABASE[device_key][os_key].keys() if k not in ("safari", "chrome")]
                b_key = random.choice(other_choices) if other_choices else "safari"
        else:
            # Non-Apple platforms (Chrome dominant, Firefox, Edge, Opera)
            if roll_b < 0.65:
                b_key = "chrome"
            elif roll_b < 0.80:
                b_key = "firefox"
            elif roll_b < 0.95:
                b_key = "edge" if "edge" in UA_DATABASE[device_key][os_key] else "chrome"
            else:
                b_key = "opera"

    # Fallback to Chrome if selected browser category does not exist for that specific OS
    os_dict = UA_DATABASE[device_key][os_key]
    if b_key not in os_dict:
        b_key = "chrome" if "chrome" in os_dict else list(os_dict.keys())[0]

    selected = random.choice(os_dict[b_key])
    return device_key.capitalize(), os_key.capitalize(), selected["browser"], selected["ua"]


# ---------------------------------------------------------
# Dynamic Links Resolver (88% Short / 12% Full Rule)
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
    if short_pool and full_pool:
        for _ in range(worker_count):
            if random.random() < 0.88:
                targets.append(random.choice(short_pool))
            else:
                targets.append(random.choice(full_pool))
    elif short_pool:
        for _ in range(worker_count):
            targets.append(random.choice(short_pool))
    elif full_pool:
        for _ in range(worker_count):
            targets.append(random.choice(full_pool))

    return targets


# ---------------------------------------------------------
# Tor Daemon Management & Native SOCKS5 Client
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
        print("[TOR] Service started. Waiting for circuit initialization...")
        time.sleep(6)
    except Exception as e:
        print(f"[TOR CRITICAL] Failed to execute Tor binary: {e}")
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


def socks5_connect(dest_host: str, dest_port: int, proxy_host="127.0.0.1", proxy_port=TOR_SOCKS_PORT, timeout=30):
    s = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    s.sendall(b"\x05\x01\x00")
    res = s.recv(2)
    if res != b"\x05\x00":
        s.close()
        raise ConnectionError(f"SOCKS5 auth negotiation failed: {res}")

    domain_bytes = dest_host.encode("idna")
    request = struct.pack("!BBBB", 0x05, 0x01, 0x00, 0x03) + bytes([len(domain_bytes)]) + domain_bytes + struct.pack("!H", dest_port)
    s.sendall(request)

    response = s.recv(4)
    if not response or response[1] != 0x00:
        s.close()
        raise ConnectionError(f"SOCKS5 connection rejected with code {response[1] if response else 'None'}")

    if response[3] == 0x01:    # IPv4
        s.recv(6)
    elif response[3] == 0x03:  # Domain
        length = s.recv(1)[0]
        s.recv(length + 2)
    elif response[3] == 0x04:  # IPv6
        s.recv(18)
    return s


def get_current_exit_info():
    try:
        s = socks5_connect("ipwho.is", 80, timeout=10)
        s.sendall(b"GET / HTTP/1.1\r\nHost: ipwho.is\r\nUser-Agent: curl/7.88.1\r\nConnection: close\r\n\r\n")
        
        raw_data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            raw_data += chunk
        s.close()

        body = raw_data.decode("utf-8", errors="ignore").split("\r\n\r\n", 1)[-1]
        data = json.loads(body)
        return data.get("ip", "Unknown"), data.get("country_code", "??")
    except Exception:
        try:
            s = socks5_connect("api.ipify.org", 80, timeout=8)
            s.sendall(b"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
            body = s.recv(2048).decode("utf-8", errors="ignore").split("\r\n\r\n")[-1].strip()
            s.close()
            return body, "??"
        except Exception:
            return "Unknown", "??"


# ---------------------------------------------------------
# Worker Execution
# ---------------------------------------------------------
def execute_bot(bot_id: int, total_bots: int, target_url: str):
    renew_tor_exit_node()
    exit_ip, exit_country = get_current_exit_info()

    device_name, os_name, browser_name, user_agent = pick_user_agent()

    parsed = urllib.parse.urlsplit(target_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path if parsed.path else "/"
    if parsed.query:
        path += f"?{parsed.query}"

    chosen_ref = random.choice(REFERRERS)
    ref_display = "None (Direct)" if chosen_ref.lower() == "none" else chosen_ref

    headers = {
        "Host": host,
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "close"
    }

    if chosen_ref.lower() != "none":
        headers["Referer"] = chosen_ref

    try:
        s = socks5_connect(host, port, timeout=30)
        if parsed.scheme == "https":
            context = ssl.create_default_context()
            s = context.wrap_socket(s, server_hostname=host)

        req_lines = [f"GET {path} HTTP/1.1"]
        for k, v in headers.items():
            req_lines.append(f"{k}: {v}")
        req_lines.append("\r\n")
        s.sendall("\r\n".join(req_lines).encode("utf-8"))

        raw_resp = s.recv(1024).decode("utf-8", errors="ignore")
        status_line = raw_resp.split("\r\n")[0] if raw_resp else "NO RESPONSE"
        s.close()

        print(f"[Bot-{bot_id}/{total_bots}] [Exit: {exit_ip} ({exit_country})] [{device_name}-{os_name} | {browser_name}] [Target: {target_url}] [Ref: {ref_display}] -> {status_line}")

    except Exception as ex:
        print(f"[Bot-{bot_id}/{total_bots}] [Exit: {exit_ip} ({exit_country})] [{device_name}-{os_name} | {browser_name}] [ERROR]: {str(ex)}")

    gap = random.uniform(GAP_MIN, GAP_MAX)
    time.sleep(gap)


# ---------------------------------------------------------
# Engine Main Loop
# ---------------------------------------------------------
def main():
    print("==================================================")
    print("   TOR ENGINE (APPLE DEFAULT SAFARI 70/25/5 RULE) ")
    print("==================================================")
    print(f"Device Selection     : {DEVICE_MODE.upper()}")
    print(f"Browser Filter       : {BROWSER_FILTER.upper()}")
    print(f"Include Countries    : {', '.join(FINAL_INCLUDE_COUNTRIES) if FINAL_INCLUDE_COUNTRIES else 'ALL (Default)'}")
    print(f"Exclude Countries    : {', '.join(FINAL_EXCLUDE_COUNTRIES) if FINAL_EXCLUDE_COUNTRIES else 'NONE'}")
    print(f"Referrers In Pool    : {len(REFERRERS)} (Includes 'none'/direct traffic)")
    print(f"Workers Per Cycle    : {int(WORKER_MIN)} - {int(WORKER_MAX)}")
    print(f"Worker Gap Range     : {GAP_MIN:.1f}s - {GAP_MAX:.1f}s")
    print(f"Cycle Duration Range : {CYCLE_MIN:.1f}s - {CYCLE_MAX:.1f}s")
    print("==================================================\n")

    start_tor_service()

    cycle_num = 1

    try:
        while True:
            full_pool, short_pool = get_resolved_pools()

            if not full_pool and not short_pool:
                print("----------------------------------------------------------------------")
                print(" [IDLE WAITING] Please configure target links in Railway:")
                print(" -> Standard links: LINKS=https://site1.com,https://site2.com")
                print(" -> (Optional) Short links: BASE_URL=https://site.com & SHORT_LINKS=s1,s2")
                print(" Checking again in 20s...")
                print("----------------------------------------------------------------------\n")
                time.sleep(20)
                continue

            cycle_start = time.time()
            worker_count = random.randint(int(WORKER_MIN), int(WORKER_MAX))
            target_cycle_time = random.uniform(CYCLE_MIN, CYCLE_MAX)

            cycle_links = pick_cycle_targets(worker_count, full_pool, short_pool)

            print(f"\n--- [Cycle #{cycle_num}] Starting {len(cycle_links)} bots (Full: {len(full_pool)}, Short: {len(short_pool)}) | Target: {target_cycle_time:.1f}s ---")

            for idx, target_url in enumerate(cycle_links, start=1):
                execute_bot(idx, len(cycle_links), target_url)

            elapsed = time.time() - cycle_start
            wait_time = target_cycle_time - elapsed

            if wait_time > 0:
                print(f"--- [Cycle #{cycle_num} Complete] Elapsed: {elapsed:.1f}s | Pausing {wait_time:.1f}s before next cycle ---")
                time.sleep(wait_time)
            else:
                print(f"--- [Cycle #{cycle_num} Complete] Elapsed: {elapsed:.1f}s | Starting next cycle immediately ---")

            cycle_num += 1

    except KeyboardInterrupt:
        print("\nEngine stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()