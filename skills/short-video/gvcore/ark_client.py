"""火山方舟 API 封装：大模型、Seedream 文生图、Seedance 视频任务。"""
import base64
import io
import json
import re
import time
from pathlib import Path

import requests

from . import config


class ArkError(RuntimeError):
    pass


class Ark:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or config.ARK_API_KEY
        self.base = (base_url or config.ARK_BASE_URL).rstrip("/")
        if not self.api_key:
            raise ArkError("未设置 ARK_API_KEY：请在 .env 中填写，或使用 --mock 离线测试")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.api_key}",
                               "Content-Type": "application/json"})

    # ---------- 通用请求（带重试） ----------
    def _req(self, method, path, payload=None, retries=4, timeout=180):
        url = f"{self.base}/{path.lstrip('/')}"
        for i in range(retries + 1):
            try:
                r = self.s.request(method, url, json=payload, timeout=timeout)
            except requests.RequestException as e:
                if i == retries:
                    raise ArkError(f"网络错误 {url}: {e}")
                time.sleep(2 ** i * 3)
                continue
            if r.status_code in (429, 500, 502, 503, 504) and i < retries:
                time.sleep(2 ** i * 5)
                continue
            if r.status_code >= 400:
                raise ArkError(f"{r.status_code} {url}: {r.text[:800]}")
            return r.json()

    # ---------- 大模型：返回 JSON ----------
    def chat_json(self, system, user, model=None, temperature=0.6):
        payload = {
            "model": model or config.LLM_MODEL,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
        }
        data = self._req("POST", "chat/completions", payload, timeout=600)
        text = data["choices"][0]["message"]["content"]
        return parse_json_loose(text)

    # ---------- Seedream 文生图 ----------
    def image(self, prompt, size="2K", ref_images=None, model=None):
        payload = {"model": model or config.IMAGE_MODEL, "prompt": prompt, "size": size,
                   "response_format": "url", "watermark": False}
        if ref_images:
            payload["image"] = ref_images if len(ref_images) > 1 else ref_images[0]
        data = self._req("POST", "images/generations", payload, timeout=300)
        return data["data"][0]["url"]

    # ---------- Seedance 视频任务 ----------
    def video_create(self, content, duration, ratio=None, resolution=None,
                     generate_audio=True, seed=None, model=None):
        payload = {
            "model": model or config.VIDEO_MODEL,
            "content": content,
            "duration": int(duration),
            "ratio": ratio or config.VIDEO_RATIO,
            "resolution": resolution or config.VIDEO_RESOLUTION,
            "generate_audio": generate_audio,
            "watermark": False,
        }
        if seed is not None:
            payload["seed"] = seed
        data = self._req("POST", "contents/generations/tasks", payload)
        return data["id"]

    def video_get(self, task_id):
        return self._req("GET", f"contents/generations/tasks/{task_id}")

    def video_wait(self, task_id, poll=10, timeout=1800, log=print):
        t0 = time.time()
        while True:
            d = self.video_get(task_id)
            st = d.get("status")
            if st in ("succeeded", "completed"):
                url = (d.get("content") or {}).get("video_url") or d.get("result_url")
                if not url:
                    raise ArkError(f"任务成功但未找到视频地址: {json.dumps(d, ensure_ascii=False)[:500]}")
                return url
            if st in ("failed", "expired", "cancelled"):
                raise ArkError(f"视频任务 {task_id} {st}: {json.dumps(d.get('error', d), ensure_ascii=False)[:500]}")
            if time.time() - t0 > timeout:
                raise ArkError(f"视频任务 {task_id} 超时")
            time.sleep(poll)


# ---------- 工具函数 ----------
def parse_json_loose(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])


def download(url, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        tmp = path.with_suffix(path.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.replace(path)
    return path


def image_data_uri(path: Path, max_side=2048, quality=90):
    """本地图片 -> base64 data URI（压成 JPEG，控制在接口大小限制内）。"""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
