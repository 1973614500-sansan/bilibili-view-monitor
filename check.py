#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, sys, time, requests
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK", "")
BJT = timezone(timedelta(hours=8))
THRESHOLD = 80000
MAX_RETRIES = 3


def get_video_stat(bvid):
    """Get video view count from Bilibili API with retries."""
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            data = resp.json()
            if data.get("code") == 0:
                return {"title": data["data"]["title"], "view": data["data"]["stat"]["view"], "bvid": data["data"]["bvid"]}
            else:
                print(f"  [WARN] API error for {bvid}: {data.get('code')}")
        except Exception as e:
            print(f"  [WARN] Request failed for {bvid} (attempt {attempt+1}): {e}")
        if attempt < MAX_RETRIES - 1:
            time.sleep(5)
    return None


def send_wecom_alert(video_info, threshold):
    if not WECOM_WEBHOOK:
        print("  [ERROR] WECOM_WEBHOOK not set")
        return False
    now = datetime.now(BJT).strftime("%Y-%m-%d %H:%M")
    view_str = f"{video_info['view']:,}"
    thr_str = f"{threshold:,}"
    msg = (
        f"\U0001f389 \u7a3f\u4ef6\u64ad\u653e\u91cf\u8fbe\u6807\uff01\n\n"
        f"\U0001f4fa \u6807\u9898\uff1a{video_info['title']}\n"
        f"\U0001f517 BV\u53f7\uff1a{video_info['bvid']}\n"
        f"\U0001f440 \u5f53\u524d\u64ad\u653e\u91cf\uff1a{view_str}\n"
        f"\U0001f3af \u8fbe\u6807\u9608\u503c\uff1a{thr_str}\n"
        f"\U0001f464 \u6dfb\u52a0\u4eba\uff1a{video_info.get('added_by', '\u672a\u77e5')}\n"
        f"\u23f0 \u8fbe\u6807\u65f6\u95f4\uff1a{now}"
    )
    try:
        resp = requests.post(WECOM_WEBHOOK, json={"msgtype": "text", "text": {"content": msg}}, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            print(f"  [OK] Alert sent for {video_info['bvid']}")
            return True
        else:
            print(f"  [ERROR] WeChat send failed: {result}")
            return False
    except Exception as e:
        print(f"  [ERROR] WeChat send exception: {e}")
        return False


def main():
    print("=== Bilibili View Monitor Check ===")
    print(f"Time: {datetime.now(BJT).strftime('%Y-%m-%d %H:%M:%S')} BJT")
    print()
    if not os.path.exists("watched.json"):
        print("No watched.json found.")
        return
    with open("watched.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    videos = data.get("videos", [])
    threshold = data.get("threshold", THRESHOLD)
    if not videos:
        print("No videos being monitored.")
        return
    print(f"Monitoring {len(videos)} video(s), threshold: {threshold:,}")
    print()
    reached = []
    updated_videos = []
    for v in videos:
        bvid = v["bvid"]
        print(f"Checking: {v.get('title', bvid)} ({bvid})")
        stat = get_video_stat(bvid)
        if stat is None:
            print("  [SKIP] Could not fetch stats")
            updated_videos.append(v)
            continue
        print(f"  View count: {stat['view']:,}")
        if stat["view"] >= threshold:
            print("  [REACHED] Threshold reached!")
            stat["added_by"] = v.get("added_by", "\u672a\u77e5")
            reached.append(stat)
        else:
            v["current_view"] = stat["view"]
            v["last_check"] = datetime.now(BJT).isoformat()
            updated_videos.append(v)
    for r in reached:
        send_wecom_alert(r, threshold)
        time.sleep(1)
    data["videos"] = updated_videos
    with open("watched.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print()
    print(f"Done. Reached: {len(reached)}, Still monitoring: {len(updated_videos)}")


if __name__ == "__main__":
    main()
