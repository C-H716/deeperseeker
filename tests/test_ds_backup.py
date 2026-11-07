"""号池加密备份与灾备恢复的回归测试。"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ds_backup
import functions


@pytest.fixture()
def pool(tmp_path, monkeypatch):
    """在临时库里放一个令牌。"""
    db = str(tmp_path / "pool.db")
    monkeypatch.setattr(functions, "_db", db)
    functions.init_db()
    functions.add_token("tok-a", "alias-a")
    return db


def test_encrypt_decrypt_roundtrip():
    plaintext = '{"hello":"世界"}'.encode()
    payload = ds_backup.encrypt(plaintext, "secret-1")
    assert ds_backup.decrypt(payload, "secret-1") == plaintext
    assert ds_backup.decrypt(payload, "wrong-secret") != plaintext


def test_snapshot_covers_local_token_columns(pool):
    snapshot = ds_backup.export_snapshot(pool)
    assert snapshot["v"] == 2
    columns = snapshot["tables"]["tokens"]["columns"]
    for name in ("cookies", "shumei_id", "device_id", "park_reason"):
        assert name in columns
    # 当前基线没有 accounts 表，快照应自动跳过而不是报错
    assert "accounts" not in snapshot["tables"]


def test_restore_preserves_token_rows(pool):
    snapshot = json.loads(
        json.dumps(ds_backup.export_snapshot(pool), ensure_ascii=False)
    )
    conn = functions.get_db()
    conn.execute("DELETE FROM tokens")
    conn.commit()
    conn.close()

    assert ds_backup.restore_snapshot(snapshot, pool) == 1
    tokens = functions.get_tokens()
    assert len(tokens) == 1
    assert tokens[0]["token"] == "tok-a"


def test_restore_skips_when_pool_is_not_empty(pool, monkeypatch):
    monkeypatch.setattr(ds_backup, "_SECRET", "secret")
    monkeypatch.setattr(ds_backup, "_TARGET", "file")
    called = []

    def forbidden_download():
        called.append(True)
        return ""

    monkeypatch.setattr(ds_backup, "_download", forbidden_download)
    assert "skip restore" in ds_backup.restore_if_needed(pool)
    assert called == []


def test_module_is_inert_without_secret(pool, monkeypatch):
    monkeypatch.setattr(ds_backup, "_SECRET", "")
    monkeypatch.setattr(ds_backup, "_TARGET", "file")
    assert ds_backup.backup_now(pool) == "backup disabled"
    assert ds_backup.restore_if_needed(pool) == "backup disabled"


def test_file_backend_roundtrip(pool, tmp_path, monkeypatch):
    target = str(tmp_path / "snapshot.enc")
    monkeypatch.setattr(ds_backup, "_SECRET", "secret-2")
    monkeypatch.setattr(ds_backup, "_TARGET", "file")
    monkeypatch.setattr(ds_backup, "_FILE_PATH", target)

    assert "backup ok" in ds_backup.backup_now(pool)
    conn = functions.get_db()
    conn.execute("DELETE FROM tokens")
    conn.commit()
    conn.close()

    assert "restored" in ds_backup.restore_if_needed(pool)
    assert len(functions.get_tokens()) == 1
