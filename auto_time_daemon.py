#!/usr/bin/env python3
import time
import subprocess
import socket
from datetime import datetime
import fun_GNSS

CHECK_INTERVAL = 300    # 每 5 分钟检查一次
GNSS_WAIT = 30          # 等待 GNSS 时间的最长时间（秒）
LOG_FILE = "gnss_time_sync.log"  # 如果不想要日志，设为 None
# LOG_FILE = None


def log(msg):
    """写入日志文件（可关闭）"""
    if LOG_FILE:
        try:
            with open(LOG_FILE, "a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
        except:
            pass


def check_internet(timeout=2):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except:
        return False


def sync_time_via_internet():
    try:
        subprocess.run(["timedatectl", "set-ntp", "true"], check=False)
        log("Internet time sync OK.")
        return True
    except Exception as e:
        log(f"Internet sync failed: {e}")
        return False


def sync_time_via_gnss(max_wait_sec=GNSS_WAIT):
    start = time.time()

    while time.time() - start < max_wait_sec:
        try:
            gnssInfo = fun_GNSS.get_gnss_location(timeout=1)

            if gnssInfo and gnssInfo.get("GNSS_time"):
                GNSS_raw = gnssInfo["GNSS_time"]
                subprocess.run(["sudo", "date", "-s", GNSS_raw], check=False)
                log(f"System time corrected by GNSS: {GNSS_raw}")
                return True

        except:
            pass

        time.sleep(1)

    log("GNSS sync timeout.")
    return False


def main():
    log("Daemon started.")

    while True:
        if check_internet():
            sync_time_via_internet()
        else:
            sync_time_via_gnss()

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
