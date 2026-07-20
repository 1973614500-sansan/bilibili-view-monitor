#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, sys, requests, time
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK", "")
BVID = os.getenv("BVID", "").strip()
ADDED_BY = os.getenv("ADDED_BY", "").strip() or "\u672a\u77e5"
BJT = timezone(timedelta(hours=8))


def get_video_info(bvid):
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    headers = {"User-Agent": "Mozilla/5.0 Chrome/120.0"}
    for i in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            data = resp.json()
            if data.get("code") == 0:
                d = data["data"]
                return {"title": d["title"], "view": d["stat"]["view"], "bvid": d["bvid"]}
        except Exception as e:
            print(f"Retry {i+1}: {e}")
            time.sleep(3)
    return None


def send_wecom(msg):
    if not WECOM_WEBHOOK:
        return
    requests.post(WECOM_WEBHOOK, json={"msgtype": "text", "text": {"content": msg}}, timeout=10)


def main():
    if not BVID:
        print("No BVID"); sys.exit(1)
    print(f"Adding: {BVID} (by {ADDED_BY})")
    info = get_video_info(BVID)
    if not info:
        send_wecom(f"\u274c \u65e0\u6cd5\u83b7\u53d6\u89c6\u9891: {BVID}"); sys.exit(1)
    if info["view"] >= 80000:
        title = info["title"]
        view = info["view"]
        send_wecom(f"\u8be5\u89c6\u9891\u64ad\u653e\u91cf\u5df2\u8fbe {view:,}\uff0c\u5df2\u8d85\u8fc78w\n\u6807\u9898: {title}"); return
    with open("watched.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    if any(v["bvid"].upper() == BVID.upper() for v in data["videos"]):
        title = info["title"]
        send_wecom(f"\u8be5\u89c6\u9891\u5df2\u5728\u76d1\u63a7\u5217\u8868: {title}"); return
    data["videos"].append({
        "bvid": info["bvid"],
        "title": info["title"],
        "added_by": ADDED_BY,
        "added_at": datetime.now(BJT).isoformat(),
        "current_view": info["view"],
        "last_check": datetime.now(BJT).isoformat()
    })
    with open("watched.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    title = info["title"]
    bvid = info["bvid"]
    view = info["view"]
    send_wecom(f"\u2705 \u5df2\u6dfb\u52a0\u76d1\u63a7\n\u6807\u9898: {title}\nBV\u53f7: {bvid}\n\u5f53\u524d\u64ad\u653e\u91cf: {view:,}\n\u6dfb\u52a0\u4eba: {ADDED_BY}\n\u9608\u503c: 80,000")
    print("Done")


if __name__ == "__main__":
    main()
