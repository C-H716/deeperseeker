"""号池加密备份与灾备恢复。

移植自 1515asd/rh-deeperseeker 的 ds_backup.py，并按本仓库的表结构做了
两处适配：

1. rh 的快照只含 tokens 表六列，且恢复时用精简 CREATE TABLE 建表；本仓库
   的 tokens 表另有 account_id / quarantine_reason / mute_until 等列，accounts
   表还保存自动重登所需的加密密码与按账号设备指纹。故改为按 PRAGMA 动态
   读取两表的真实列名导出，恢复时只写当前库中确实存在的列。
2. 后台备份协程用 asyncio.to_thread 执行同步网络与 SQLite 操作，避免阻塞
   事件循环。

仅在显式配置 DEEPSEEKER_BACKUP_SECRET 与目标后启用；未配置时模块完全
静默，不产生任何网络请求，也不改动本地数据。恢复只在 tokens 表为空时
触发，本地数据优先。零第三方依赖，仅使用标准库。
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request

logger = logging.getLogger("deeperseeker.backup")

_SECRET = os.getenv("DEEPSEEKER_BACKUP_SECRET", "").strip()
_TARGET = os.getenv("DEEPSEEKER_BACKUP_TARGET", "none").strip().lower()
try:
    _INTERVAL = max(300, int(os.getenv("DEEPSEEKER_BACKUP_INTERVAL", "21600")))
except ValueError:
    _INTERVAL = 21600
_TG_TOKEN = os.getenv("DEEPSEEKER_BACKUP_TG_BOT_TOKEN", "").strip()
_TG_CHAT = os.getenv("DEEPSEEKER_BACKUP_TG_CHAT_ID", "").strip()
_GIST_TOKEN = os.getenv("DEEPSEEKER_BACKUP_GIST_TOKEN", "").strip()
_GIST_ID = os.getenv("DEEPSEEKER_BACKUP_GIST_ID", "").strip()
_FILE_PATH = os.getenv("DEEPSEEKER_BACKUP_FILE_PATH", "").strip()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SNAPSHOT_NAME = "deeperseeker-tokens-snapshot"
_TG_API = "https://api.telegram.org"
_GIST_API = "https://api.github.com/gists"
_TABLES = ("tokens", "accounts")


def default_db_path():
    """返回数据库路径，与 functions 模块的解析规则保持一致。"""
    return os.getenv("DB_PATH") or os.path.join(_BASE_DIR, "deeperseeker.db")


def _db_connect(db_path=None):
    return sqlite3.connect(db_path or default_db_path(), timeout=10)


# ── 加密：PBKDF2-SHA256 keystream XOR ───────────────────────────────────


def _keystream(secret, salt, length):
    out = b""
    counter = 0
    while len(out) < length:
        out += hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode("utf-8"),
            salt + counter.to_bytes(4, "big"),
            100_000,
            dklen=32,
        )
        counter += 1
    return out[:length]


def encrypt(plaintext, secret=None):
    """加密为 base64(salt + ciphertext)。"""
    secret = secret or _SECRET
    salt = os.urandom(16)
    ks = _keystream(secret, salt, len(plaintext))
    return base64.b64encode(
        salt + bytes(a ^ b for a, b in zip(plaintext, ks, strict=False))
    ).decode("ascii")


def decrypt(payload, secret=None):
    """解密 encrypt() 的输出；密码错误时由调用方的 JSON 校验兜底。"""
    secret = secret or _SECRET
    raw = base64.b64decode(payload)
    salt, ct = raw[:16], raw[16:]
    ks = _keystream(secret, salt, len(ct))
    return bytes(a ^ b for a, b in zip(ct, ks, strict=False))


# ── 快照导出 / 恢复 ────────────────────────────────────────────────────


def _columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def token_count(db_path=None):
    try:
        conn = _db_connect(db_path)
        n = conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
        conn.close()
        return n
    except sqlite3.Error:
        return -1


def export_snapshot(db_path=None):
    """导出 tokens 与 accounts 两表的全部真实列。"""
    conn = _db_connect(db_path)
    tables = {}
    for table in _TABLES:
        columns = _columns(conn, table)
        if not columns:
            continue
        rows = conn.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
        tables[table] = {
            "columns": columns,
            "rows": [dict(zip(columns, row, strict=False)) for row in rows],
        }
    conn.close()
    return {
        "v": 2,
        "created_at": int(time.time()),
        "source": "deeperseeker",
        "tables": tables,
    }


def restore_snapshot(snapshot, db_path=None):
    """把快照写回现有表（表须已由 init_db 建立）。返回恢复的 tokens 行数。

    只写当前库中确实存在的列，因此旧版快照遇到新增列是安全的，新版快照
    遇到旧库也不会因缺列而失败。
    """
    conn = _db_connect(db_path)
    restored = 0
    try:
        for table in _TABLES:
            section = snapshot.get("tables", {}).get(table)
            if not section:
                continue
            current = set(_columns(conn, table))
            columns = [c for c in section.get("columns", []) if c in current]
            if not columns:
                continue
            placeholders = ", ".join("?" for _ in columns)
            sql = (
                f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) "
                f"VALUES ({placeholders})"
            )
            for row in section.get("rows", []):
                conn.execute(sql, [row.get(c) for c in columns])
                if table == "tokens":
                    restored += 1
        conn.commit()
    finally:
        conn.close()
    return restored


# ── 传输后端 ───────────────────────────────────────────────────────────


def _post_json(url, body, headers=None, method="POST", timeout=30):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _upload_tg(payload):
    boundary = "----dsb" + hashlib.md5(str(time.time()).encode()).hexdigest()
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{_TG_CHAT}\r\n'.encode(),
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="document"; '
            f'filename="{_SNAPSHOT_NAME}.enc"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode(),
        payload.encode("utf-8"),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(
        f"{_TG_API}/bot{_TG_TOKEN}/sendDocument",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"telegram send failed: {data}")
    return f"telegram message_id={data['result']['message_id']}"


def _download_tg():
    updates = _get_json(f"{_TG_API}/bot{_TG_TOKEN}/getUpdates?limit=100")
    best = None
    for upd in updates.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        doc = msg.get("document") or {}
        if doc.get("file_id") and _SNAPSHOT_NAME in (doc.get("file_name") or ""):
            date = msg.get("date", 0)
            if best is None or date > best[0]:
                best = (date, doc["file_id"])
    if not best:
        raise RuntimeError("no snapshot document found in telegram chat")
    info = _get_json(f"{_TG_API}/bot{_TG_TOKEN}/getFile?file_id={best[1]}")
    with urllib.request.urlopen(
        f"{_TG_API}/file/bot{_TG_TOKEN}/{info['result']['file_path']}", timeout=60
    ) as resp:
        return resp.read().decode("utf-8")


def _upload_gist(payload):
    body = {"files": {f"{_SNAPSHOT_NAME}.enc": {"content": payload}}}
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {_GIST_TOKEN}",
        "Content-Type": "application/json",
    }
    if _GIST_ID:
        req = urllib.request.Request(
            f"{_GIST_API}/{_GIST_ID}",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="PATCH",
        )
    else:
        req = urllib.request.Request(
            _GIST_API,
            data=json.dumps({**body, "public": False}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return f"gist id={data.get('id', '')}"


def _download_gist():
    gist = _get_json(
        f"{_GIST_API}/{_GIST_ID}",
        headers={"Authorization": f"Bearer {_GIST_TOKEN}"},
    )
    item = gist.get("files", {}).get(f"{_SNAPSHOT_NAME}.enc")
    if not item:
        raise RuntimeError("snapshot file not found in gist")
    if item.get("truncated"):
        with urllib.request.urlopen(item["raw_url"], timeout=60) as resp:
            return resp.read().decode("utf-8")
    return item.get("content", "")


def _upload_file(payload):
    with open(_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(payload)
    return f"file {_FILE_PATH}"


def _download_file():
    with open(_FILE_PATH, encoding="utf-8") as f:
        return f.read()


_BACKENDS = {
    "telegram": (_upload_tg, _download_tg),
    "gist": (_upload_gist, _download_gist),
    "file": (_upload_file, _download_file),
}


def _upload(payload):
    return _BACKENDS[_TARGET][0](payload)


def _download():
    return _BACKENDS[_TARGET][1]()


# ── 对外主流程 ─────────────────────────────────────────────────────────


def restore_if_needed(db_path=None):
    """tokens 表为空时从备份恢复；返回动作描述供启动日志使用。"""
    if not _SECRET or _TARGET not in _BACKENDS:
        return "backup disabled"
    count = token_count(db_path)
    if count != 0:
        return f"local tokens={count}, skip restore"
    try:
        snapshot = json.loads(decrypt(_download()).decode("utf-8"))
        if snapshot.get("source") != "deeperseeker":
            return "snapshot source mismatch, abort"
        restored = restore_snapshot(snapshot, db_path)
        age = int(time.time()) - snapshot.get("created_at", 0)
        return f"restored {restored} tokens from {_TARGET} snapshot (age {age}s)"
    except Exception as exc:
        return f"restore failed: {exc}"


def backup_now(db_path=None):
    """立即执行一次备份；返回成功、禁用或失败原因。"""
    if not _SECRET or _TARGET not in _BACKENDS:
        return "backup disabled"
    count = token_count(db_path)
    if count <= 0:
        return "no tokens to back up"
    payload = encrypt(
        json.dumps(export_snapshot(db_path), ensure_ascii=False).encode("utf-8")
    )
    try:
        return f"backup ok: {count} tokens -> {_upload(payload)}"
    except Exception as exc:
        return f"backup failed: {exc}"


async def background_loop():
    """常规定时备份协程，由 lifespan 用 create_task 启动。

    未配置密钥或目标时立即返回，不留下轮询任务，保持模块完全静默。
    """
    if not _SECRET or _TARGET not in _BACKENDS:
        return
    while True:
        await asyncio.sleep(_INTERVAL)
        try:
            message = await asyncio.to_thread(backup_now)
        except Exception as exc:
            message = f"backup loop error: {exc}"
        logger.info("[ds_backup] %s", message)


if __name__ == "__main__":
    print(restore_if_needed())
    print(backup_now())
