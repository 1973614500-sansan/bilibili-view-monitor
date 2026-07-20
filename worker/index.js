/**
 * Bilibili View Monitor - Cloudflare Worker
 * Receives WeChat Work bot callback, parses bvid commands, updates GitHub repo
 */

// ============ Crypto Helpers ============

function decodeBase64(str) {
  const binary = atob(str);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function sha1(str) {
  const encoder = new TextEncoder();
  const data = encoder.encode(str);
  const hash = await crypto.subtle.digest("SHA-1", data);
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, "0")).join("");
}

async function getAESKey(encodingAESKey) {
  const keyBytes = decodeBase64(encodingAESKey + "=");
  return await crypto.subtle.importKey("raw", keyBytes, { name: "AES-CBC" }, false, ["decrypt", "encrypt"]);
}

async function decrypt(encrypted, encodingAESKey) {
  const key = await getAESKey(encodingAESKey);
  const encBytes = decodeBase64(encrypted);
  const aesKeyBytes = decodeBase64(encodingAESKey + "=");
  const iv = aesKeyBytes.slice(0, 16);

  const decrypted = await crypto.subtle.decrypt({ name: "AES-CBC", iv }, key, encBytes);
  const decBytes = new Uint8Array(decrypted);

  const padLen = decBytes[decBytes.length - 1];
  const content = decBytes.slice(0, decBytes.length - padLen);

  const msgLen = (content[16] << 24) | (content[17] << 16) | (content[18] << 8) | content[19];
  const msg = new TextDecoder().decode(content.slice(20, 20 + msgLen));
  return msg;
}

async function verifySignature(token, timestamp, nonce, echostr) {
  const arr = [token, timestamp, nonce, echostr].sort();
  return await sha1(arr.join(""));
}

// ============ GitHub API ============

async function getWatchedJson(env) {
  const url = "https://api.github.com/repos/" + env.GITHUB_REPO + "/contents/watched.json";
  const resp = await fetch(url, {
    headers: {
      "Authorization": "Bearer " + env.GITHUB_TOKEN,
      "Accept": "application/vnd.github+json",
      "User-Agent": "bilibili-view-monitor-worker"
    }
  });
  if (!resp.ok) return { content: { videos: [], threshold: 80000, notified: [] }, sha: null };
  const data = await resp.json();
  const decoded = atob(data.content.replace(/\n/g, ""));
  const content = JSON.parse(decodeURIComponent(escape(decoded)));
  return { content, sha: data.sha };
}

async function updateWatchedJson(env, content, sha) {
  const jsonStr = JSON.stringify(content, null, 2);
  const encoded = btoa(unescape(encodeURIComponent(jsonStr)));
  const body = {
    message: "update: " + new Date().toISOString(),
    content: encoded,
    sha: sha
  };
  const url = "https://api.github.com/repos/" + env.GITHUB_REPO + "/contents/watched.json";
  const resp = await fetch(url, {
    method: "PUT",
    headers: {
      "Authorization": "Bearer " + env.GITHUB_TOKEN,
      "Accept": "application/vnd.github+json",
      "User-Agent": "bilibili-view-monitor-worker",
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });
  return resp.ok;
}

// ============ Bilibili API ============

async function getVideoInfo(bvid) {
  const url = "https://api.bilibili.com/x/web-interface/view?bvid=" + bvid;
  const resp = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0" }
  });
  if (!resp.ok) return null;
  const data = await resp.json();
  if (data.code !== 0) return null;
  return {
    title: data.data.title,
    view: data.data.stat.view,
    bvid: data.data.bvid
  };
}

// ============ WeChat Work Webhook ============

async function sendWecomMessage(webhookUrl, text) {
  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ msgtype: "text", text: { content: text } })
  });
}

// ============ Command Handler ============

async function handleCommand(text, userName, env) {
  const trimmed = text.trim();
  const bvidMatch = trimmed.match(/[Bb][Vv][a-zA-Z0-9]+/);
  const avMatch = trimmed.match(/[Aa][Vv](\d+)/);

  if (/^(\u6dfb\u52a0|add|\u76d1\u63a7)\s/i.test(trimmed)) {
    let bvid = null;
    if (bvidMatch) {
      bvid = bvidMatch[0];
    } else if (avMatch) {
      return "\u8bf7\u4f7f\u7528BV\u53f7\u6dfb\u52a0\uff0c\u4f8b\u5982\uff1a\u6dfb\u52a0 BV1xxxxxxxxx";
    }
    if (!bvid) return "\u672a\u8bc6\u522b\u5230\u6709\u6548\u7684BV\u53f7\uff0c\u8bf7\u53d1\u9001\uff1a\u6dfb\u52a0 BV1xxxxxxxxx";

    const info = await getVideoInfo(bvid);
    if (!info) return "\u65e0\u6cd5\u83b7\u53d6\u89c6\u9891\u4fe1\u606f\uff0c\u8bf7\u68c0\u67e5BV\u53f7\u662f\u5426\u6b63\u786e\uff1a" + bvid;

    if (info.view >= 80000) {
      return "\u8be5\u89c6\u9891\u64ad\u653e\u91cf\u5df2\u8fbe " + info.view.toLocaleString() + "\uff0c\u5df2\u8d85\u8fc78w\u9608\u503c\uff0c\u65e0\u9700\u76d1\u63a7\n\u6807\u9898\uff1a" + info.title;
    }

    const { content, sha } = await getWatchedJson(env);
    if (content.videos.some(v => v.bvid.toUpperCase() === bvid.toUpperCase())) {
      return "\u8be5\u89c6\u9891\u5df2\u5728\u76d1\u63a7\u5217\u8868\u4e2d\uff1a" + info.title;
    }

    content.videos.push({
      bvid: info.bvid,
      title: info.title,
      added_by: userName || "\u672a\u77e5",
      added_at: new Date().toISOString(),
      current_view: info.view,
      last_check: new Date().toISOString()
    });

    const ok = await updateWatchedJson(env, content, sha);
    if (!ok) return "\u6dfb\u52a0\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5";

    return "\u2705 \u5df2\u6dfb\u52a0\u76d1\u63a7\n\u6807\u9898\uff1a" + info.title + "\nBV\u53f7\uff1a" + info.bvid + "\n\u5f53\u524d\u64ad\u653e\u91cf\uff1a" + info.view.toLocaleString() + "\n\u9608\u503c\uff1a80,000";

  } else if (/^(\u5217\u8868|list|\u67e5\u770b)$/i.test(trimmed)) {
    const { content } = await getWatchedJson(env);
    if (content.videos.length === 0) return "\u5f53\u524d\u65e0\u76d1\u63a7\u7a3f\u4ef6";

    let msg = "\ud83d\udccb \u5f53\u524d\u76d1\u63a7 " + content.videos.length + " \u4e2a\u7a3f\u4ef6\uff1a\n";
    content.videos.forEach((v, i) => {
      msg += "\n" + (i + 1) + ". " + v.title + "\n   BV\u53f7\uff1a" + v.bvid + "\n   \u64ad\u653e\u91cf\uff1a" + (v.current_view || 0).toLocaleString() + "\n   \u6dfb\u52a0\u4eba\uff1a" + v.added_by;
    });
    return msg;

  } else if (/^(\u79fb\u9664|remove|\u5220\u9664)\s/i.test(trimmed)) {
    const bvid = bvidMatch ? bvidMatch[0] : null;
    if (!bvid) return "\u8bf7\u6307\u5b9a\u8981\u79fb\u9664\u7684BV\u53f7\uff0c\u4f8b\u5982\uff1a\u79fb\u9664 BV1xxxxxxxxx";

    const { content, sha } = await getWatchedJson(env);
    const idx = content.videos.findIndex(v => v.bvid.toUpperCase() === bvid.toUpperCase());
    if (idx === -1) return "\u8be5\u89c6\u9891\u4e0d\u5728\u76d1\u63a7\u5217\u8868\u4e2d";

    const removed = content.videos.splice(idx, 1)[0];
    const ok = await updateWatchedJson(env, content, sha);
    if (!ok) return "\u79fb\u9664\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5";

    return "\u2705 \u5df2\u79fb\u9664\u76d1\u63a7\uff1a" + removed.title;

  } else if (bvidMatch || avMatch) {
    return await handleCommand("\u6dfb\u52a0 " + trimmed, userName, env);

  } else {
    return "\u652f\u6301\u7684\u547d\u4ee4\uff1a\n- \u6dfb\u52a0 BV1xxxxxxxxx\n- \u5217\u8868\n- \u79fb\u9664 BV1xxxxxxxxx\n\n\u4e5f\u53ef\u4ee5\u76f4\u63a5\u53d1BV\u53f7\uff0c\u9ed8\u8ba4\u6dfb\u52a0\u76d1\u63a7";
  }
}

// ============ XML Parser ============

function extractXmlValue(xml, tag) {
  const re1 = new RegExp("<" + tag + "><!" + "\\[CDATA\\[" + "(.+?)" + "\\]\\]" + "></" + tag + ">");
  const match = xml.match(re1);
  if (match) return match[1];
  const re2 = new RegExp("<" + tag + ">(.+?)</" + tag + ">");
  const match2 = xml.match(re2);
  return match2 ? match2[1] : "";
}

// ============ Main Handler ============

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // GET: WeChat Work callback URL verification
    if (request.method === "GET") {
      const msgSignature = url.searchParams.get("msg_signature");
      const timestamp = url.searchParams.get("timestamp");
      const nonce = url.searchParams.get("nonce");
      const echostr = url.searchParams.get("echostr");

      if (!msgSignature || !timestamp || !nonce || !echostr) {
        return new Response("Bilibili View Monitor Worker is running!", { status: 200 });
      }

      const signature = await verifySignature(env.WECOM_TOKEN, timestamp, nonce, echostr);
      if (signature !== msgSignature) {
        return new Response("signature mismatch", { status: 403 });
      }

      const decrypted = await decrypt(echostr, env.WECOM_AES_KEY);
      return new Response(decrypted, { status: 200 });
    }

    // POST: Receive message
    if (request.method === "POST") {
      try {
        const msgSignature = url.searchParams.get("msg_signature");
        const timestamp = url.searchParams.get("timestamp");
        const nonce = url.searchParams.get("nonce");

        const body = await request.text();

        const encryptMatch = body.match(/<Encrypt><!\[CDATA\[(.+?)\]\]><\/Encrypt>/);
        if (!encryptMatch) {
          return new Response("no encrypt field", { status: 400 });
        }
        const encrypted = encryptMatch[1];

        const signature = await verifySignature(env.WECOM_TOKEN, timestamp, nonce, encrypted);
        if (signature !== msgSignature) {
          return new Response("signature mismatch", { status: 403 });
        }

        const xml = await decrypt(encrypted, env.WECOM_AES_KEY);
        const content = extractXmlValue(xml, "Content");
        const fromUser = extractXmlValue(xml, "FromUserName");

        if (!content) {
          return new Response("success", { status: 200 });
        }

        const reply = await handleCommand(content, fromUser, env);
        if (reply) {
          await sendWecomMessage(env.WECOM_WEBHOOK, reply);
        }

        return new Response("success", { status: 200 });
      } catch (e) {
        console.error("Error:", e.message, e.stack);
        return new Response("error", { status: 200 });
      }
    }

    return new Response("Method not allowed", { status: 405 });
  }
};