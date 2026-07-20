#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, sys, time, requests
from datetime import datetime, timezone, timedelta

WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK", "")
BJT = timezone(timedelta(hours=8))
TARGET_MID = 20165629
KEYWORDS = ["\u4eba\u6c11\u65e5\u62a5", "\u592e\u89c6\u65b0\u95fb", "\u65b0\u534e\u793e"]
THRESHOLD = 80000
MAX_RETRIES = 3
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}


def get_recent_videos(mid, ps=30):
    for attempt in range(MAX_RETRIES):
        try:
            url = f"https://api.bilibili.com/x/space/arc/search?mid={mid}&ps={ps}&pn=1&order=pubdate"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            data = resp.json()
            if data.get("code") == 0:
                vlist = data["data"]["list"]["vlist"]
                return [{"bvid":v["bvid"],"title":v["title"],"desc":v.get("description",""),"view":v["play"]} for v in vlist]
            print(f"  [WARN] code={data.get('code')}")
        except Exception as e:
            print(f"  [WARN] attempt {attempt+1}: {e}")
        time.sleep(3)
    # Fallback: dynamic feed API
    for attempt in range(MAX_RETRIES):
        try:
            url = f'https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={mid}'
            resp = requests.get(url, headers=HEADERS, timeout=15)
            data = resp.json()
            if data.get('code') == 0:
                items = data.get('data', {}).get('items', [])
                result = []
                for item in items:
                    mod = item.get('modules', {}).get('module_dynamic', {}).get('major', {})
                    if mod.get('type') == 'MAJOR_TYPE_ARCHIVE':
                        arch = mod.get('archive', {})
                        bvid = arch.get('bvid', '')
                        if bvid:
                            # view comes as string like '1.2万'
                            view_str = arch.get('stat', {}).get('play', '0')
                            try:
                                if '万' in str(view_str):
                                    view = int(float(str(view_str).replace('万','')) * 10000)
                                else:
                                    view = int(view_str)
                            except:
                                view = 0
                            result.append({'bvid':bvid,'title':arch.get('title',''),'desc':arch.get('desc',''),'view':view})
                if result:
                    return result
        except Exception as e:
            print(f'  [WARN] dynamic feed attempt {attempt+1}: {e}')
        time.sleep(3)
    # Fallback: RSSHub public instance
    for attempt in range(2):
        try:
            rss_url = f'https://rsshub.app/bilibili/user/video/{mid}'
            resp = requests.get(rss_url, headers=HEADERS, timeout=20)
            if resp.status_code == 200 and '<item>' in resp.text:
                import re as _re
                items = _re.findall(r'<item>(.+?)</item>', resp.text, _re.DOTALL)
                result = []
                for item_xml in items[:30]:
                    title_m = _re.search(r'<title><!\[CDATA\[(.+?)\]\]></title>', item_xml)
                    link_m = _re.search(r'<link>(.+?)</link>', item_xml)
                    if title_m and link_m:
                        title = title_m.group(1)
                        link = link_m.group(1)
                        bvid_m = _re.search(r'(BV[a-zA-Z0-9]+)', link)
                        if bvid_m:
                            result.append({'bvid': bvid_m.group(1), 'title': title, 'desc': '', 'view': 0})
                if result:
                    print(f'  [OK] RSSHub got {len(result)} videos')
                    return result
        except Exception as e:
            print(f'  [WARN] RSSHub attempt {attempt+1}: {e}')
        time.sleep(2)
    return []


def matches_kw(title, desc):
    text = (title + " " + desc).lower()
    for kw in KEYWORDS:
        if kw.lower() in text:
            return kw
    return None


def send_wecom(msg):
    if not WECOM_WEBHOOK: return
    requests.post(WECOM_WEBHOOK, json={"msgtype":"text","text":{"content":msg}}, timeout=10)


def main():
    print("=== Discover ===")
    now = datetime.now(BJT).strftime("%Y-%m-%d %H:%M")
    print(f"Time: {now}, UID: {TARGET_MID}")
    with open("watched.json", "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    existing = set(v["bvid"].upper() for v in data["videos"])
    hp = "discovered.json"
    history = json.load(open(hp, encoding="utf-8-sig")) if os.path.exists(hp) else []
    hist_set = set(h["bvid"].upper() for h in history)
    videos = get_recent_videos(TARGET_MID)
    if not videos:
        print("No videos fetched."); return
    print(f"Fetched {len(videos)} videos")
    found = []
    for v in videos:
        bvid = v["bvid"]
        if bvid.upper() in existing or bvid.upper() in hist_set:
            continue
        if v["view"] >= THRESHOLD:
            continue
        kw = matches_kw(v["title"], v["desc"])
        if kw:
            found.append({"bvid":bvid,"title":v["title"],"view":v["view"],"kw":kw})
    if not found:
        print("No new matches."); return
    for item in found:
        data["videos"].append({"bvid":item["bvid"],"title":item["title"],"added_by":"\u81ea\u52a8\u53d1\u73b0","added_at":datetime.now(BJT).isoformat(),"current_view":item["view"],"last_check":datetime.now(BJT).isoformat()})
        history.append({"bvid":item["bvid"],"title":item["title"],"kw":item["kw"],"at":datetime.now(BJT).isoformat()})
    with open("watched.json","w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(hp,"w",encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    for item in found:
        t=item["title"]; b=item["bvid"]; k=item["kw"]; vw=f"{item['view']:,}"
        msg = f"\U0001f50d \u53d1\u73b0\u5171\u9752\u56e2\u4e2d\u592e\u642c\u8fd0\u7a3f\u4ef6\n\n\u6807\u9898: {t}\nBV\u53f7: {b}\n\u5173\u952e\u8bcd: {k}\n\u5f53\u524d\u64ad\u653e\u91cf: {vw}\n\n\u5df2\u81ea\u52a8\u7eb3\u5165\u76d1\u63a7\uff0c\u8fbe\u52308w\u5373\u64ad\u62a5"
        send_wecom(msg)
        print(f"  [NEW] {b} - {t}")
        time.sleep(1)
    print(f"Done. Found {len(found)} new.")


if __name__ == "__main__":
    main()
