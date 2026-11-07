"""防封禁移植项的回归测试。

对应 1515asd/rh-deeperseeker：
  v89.7          禁言硬证据识别、只读令牌探测、隔离与恢复
  v89.8 / v89.11 x-hif-leim 风控头的默认关闭、缓存与失败退避
  v89.12         桥内登录自动重登的凭据加密、节流与终态禁用
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import functions
from functions import (
    AccountLoginError,
    UpstreamMutedError,
    _format_mute_until,
    _raise_if_muted_envelope,
    _seal_password,
    _unseal_password,
    add_token,
    get_hif_token,
    get_token,
    get_tokens,
    mark_quarantined,
    probe_token_mute,
    relogin_account,
    restore_token,
    save_account_login,
)


@pytest.fixture()
def pool(tmp_path, monkeypatch):
    """把数据库与凭据密钥指向临时目录，隔离真实数据卷。"""
    monkeypatch.setattr(functions, "_db", str(tmp_path / "anti_ban.db"))
    monkeypatch.setattr(
        functions, "_ACCOUNT_KEY_FILE", str(tmp_path / "account_secret.key")
    )
    functions._hif_cache.update({"value": None, "expire_at": 0.0, "retry_at": 0.0})
    functions.init_db()
    yield functions
    functions._relogin_inflight.clear()
    functions._hif_cache.update({"value": None, "expire_at": 0.0, "retry_at": 0.0})


class _FakeResponse:
    def __init__(self, body, headers=None):
        self._body = body
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self, content_type=None):
        return self._body


class _FakeSession:
    def __init__(self, body, headers=None):
        self.body = body
        self.headers = headers or {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeResponse(self.body, self.headers)


def _install_session(monkeypatch, body, headers=None):
    session = _FakeSession(body, headers)

    async def fake_get_session():
        return session

    monkeypatch.setattr(functions, "get_session", fake_get_session)
    return session


# ── 禁言识别与只读探测 ─────────────────────────────────────────────────


def test_format_mute_until_uses_fixed_utc8():
    stamp = datetime(2026, 11, 7, 4, 0, tzinfo=timezone.utc).timestamp()
    assert _format_mute_until(stamp) == "2026-11-07 12:00"
    assert _format_mute_until(None) == "unknown"


def test_muted_error_is_hard_403():
    err = UpstreamMutedError(1762502400)
    assert err.status == 403
    assert err.mute_until == 1762502400
    assert "user is muted" in str(err)


@pytest.mark.parametrize(
    "envelope",
    [
        {"is_muted": 1, "mute_until": 123},
        {"chat": {"is_muted": 1, "mute_until": 456}},
    ],
)
def test_muted_envelope_shapes(envelope):
    with pytest.raises(UpstreamMutedError):
        _raise_if_muted_envelope(envelope)


def test_healthy_envelope_is_ignored():
    _raise_if_muted_envelope({"chat": {"is_muted": 0}})
    _raise_if_muted_envelope(None)


def test_biz_data_detects_muted_account():
    payload = {
        "code": 0,
        "data": {"biz_data": {"chat": {"is_muted": 1, "mute_until": 789}}},
    }
    with pytest.raises(UpstreamMutedError):
        functions._biz_data(payload)


@pytest.mark.parametrize(
    "body,verdict",
    [
        (
            {
                "code": 0,
                "data": {
                    "biz_data": {"chat": {"is_muted": 1, "mute_until": 1762502400}}
                },
            },
            "muted",
        ),
        ({"code": 40003, "msg": "invalid token"}, "invalid"),
        ({"code": 0, "data": {"biz_data": {"id": 1}}}, "ok"),
        ({"code": 7}, "error"),
    ],
)
def test_probe_token_mute_verdicts(monkeypatch, body, verdict):
    session = _install_session(monkeypatch, body)
    result = asyncio.run(probe_token_mute("token-value"))
    assert result["verdict"] == verdict
    assert session.calls[0][0].endswith("/api/v0/users/current")
    assert "token-value" not in str(result)


def test_check_token_status_muted_quarantines(pool, monkeypatch):
    tid = add_token("abc", "alias")

    async def fake_probe(token):
        return {
            "verdict": "muted",
            "detail": "user is muted",
            "mute_until": 1762502400,
        }

    monkeypatch.setattr(functions, "probe_token_mute", fake_probe)
    result = asyncio.run(functions.check_token_status(tid))
    assert result["status"] == "MUTED"
    row = get_tokens()[0]
    assert row["status"] == "QUARANTINED"
    assert "muted" in row["quarantine_reason"]
    assert row["mute_until"] == 1762502400


def test_check_token_status_ok_clears_mute_quarantine(pool, monkeypatch):
    tid = add_token("abc")
    mark_quarantined(tid, "user is muted", 1762502400)

    async def fake_probe(token):
        return {"verdict": "ok", "detail": "", "mute_until": None}

    monkeypatch.setattr(functions, "probe_token_mute", fake_probe)
    assert asyncio.run(functions.check_token_status(tid))["status"] == "ACTIVE"
    row = get_tokens()[0]
    assert row["status"] == "ACTIVE"
    assert row["quarantine_reason"] is None


def test_quarantined_token_never_enters_rotation(pool):
    tid = add_token("abc")
    mark_quarantined(tid, "user is muted", 1762502400)
    assert functions.pick_token() is None
    restore_token(tid)
    assert get_tokens()[0]["status"] == "ACTIVE"
    assert functions.pick_token() == tid


# ── x-hif-leim 风控头 ──────────────────────────────────────────────────


def test_hif_disabled_by_default_has_zero_network(pool, monkeypatch):
    monkeypatch.setattr(functions, "_HIF_ENABLED", False)
    session = _install_session(monkeypatch, {"data": {"biz_data": {"value": "x"}}})
    assert asyncio.run(get_hif_token()) is None
    assert session.calls == []


def test_hif_caches_token_and_refreshes_only_once(pool, monkeypatch):
    monkeypatch.setattr(functions, "_HIF_ENABLED", True)
    session = _install_session(
        monkeypatch,
        {"data": {"biz_data": {"value": "hif-1"}}},
        {"x-hif-ttl": "600"},
    )
    assert asyncio.run(get_hif_token()) == "hif-1"
    assert asyncio.run(get_hif_token()) == "hif-1"
    assert len(session.calls) == 1


def test_hif_failure_degrades_without_retry_storm(pool, monkeypatch):
    monkeypatch.setattr(functions, "_HIF_ENABLED", True)
    session = _install_session(monkeypatch, {"data": {}})
    assert asyncio.run(get_hif_token()) is None
    assert functions._hif_cache["retry_at"] > time.time()
    assert asyncio.run(get_hif_token()) is None
    assert len(session.calls) == 1


# ── 桥内登录自动重登 ──────────────────────────────────────────────────


def test_password_seal_roundtrip(pool):
    secret = _seal_password("p@ssw0rd-中文")
    assert "p@ssw0rd" not in secret
    assert _unseal_password(secret) == "p@ssw0rd-中文"
    assert _unseal_password(None) is None


def test_account_login_error_carries_reason():
    err = AccountLoginError("risk_device", "登录被拒")
    assert err.reason == "risk_device"
    assert str(err) == "登录被拒"


def test_relogin_is_inert_for_manually_pasted_token(pool, monkeypatch):
    tid = add_token("manual-token")
    called = []

    async def fake_login(email, password, device_id=None):
        called.append((email, password))
        return {"ok": True, "token": "new", "muted": False}

    monkeypatch.setattr(functions, "login_deepseek_account", fake_login)
    asyncio.run(relogin_account(tid))
    assert called == []


def test_relogin_honours_throttle(pool, monkeypatch):
    save_account_login("a@b.com", None, "old-token", password="pw")
    tid = get_tokens()[0]["id"]
    called = []

    async def fake_login(email, password, device_id=None):
        called.append(email)
        return {"ok": True, "token": "new", "muted": False}

    monkeypatch.setattr(functions, "login_deepseek_account", fake_login)
    asyncio.run(relogin_account(tid))
    assert called == []


def test_relogin_refreshes_token_after_expiry(pool, monkeypatch):
    save_account_login(
        "a@b.com", None, "old-token", password="pw", device_id="smsdk-fingerprint"
    )
    tid = get_tokens()[0]["id"]
    conn = functions.get_db()
    conn.execute("UPDATE accounts SET relogin_at = 0")
    conn.commit()
    conn.close()

    async def fake_login(email, password, device_id=None):
        assert (email, password) == ("a@b.com", "pw")
        # 重登复用按账号持久化的同一指纹，不会被识别为新设备。
        assert device_id == "smsdk-fingerprint"
        return {
            "ok": True,
            "token": "fresh-token",
            "muted": False,
            "device_id": device_id,
            "account": email,
        }

    monkeypatch.setattr(functions, "login_deepseek_account", fake_login)
    asyncio.run(relogin_account(tid))
    assert get_token(tid)["token"] == "fresh-token"
    assert get_tokens()[0]["status"] == "ACTIVE"


def test_relogin_terminal_rejection_disables_account(pool, monkeypatch):
    save_account_login("a@b.com", None, "old-token", password="pw")
    tid = get_tokens()[0]["id"]
    conn = functions.get_db()
    conn.execute("UPDATE accounts SET relogin_at = 0")
    conn.commit()
    conn.close()

    async def fake_login(email, password, device_id=None):
        raise AccountLoginError("risk_device", "设备指纹被拒")

    monkeypatch.setattr(functions, "login_deepseek_account", fake_login)
    asyncio.run(relogin_account(tid))
    assert functions.get_relogin_credentials(tid) is None
    assert get_token(tid)["token"] == "old-token"


def test_device_id_persists_per_account_and_reaches_dashboard(pool):
    save_account_login(
        "a@b.com", None, "tok-a", password="pw", device_id="fingerprint-a"
    )
    save_account_login(
        "13800138000", None, "tok-b", password="pw", device_id="fingerprint-b"
    )
    accounts = {a["email"]: a for a in functions.get_accounts()}
    assert accounts["a@b.com"]["device_id"] == "fingerprint-a"
    assert accounts["13800138000"]["device_id"] == "fingerprint-b"
    assert functions.get_account_device_id("a@b.com") == "fingerprint-a"
    assert functions.get_account_device_id("missing@example.com") is None


def test_relogin_quarantines_muted_session(pool, monkeypatch):
    save_account_login("a@b.com", None, "old-token", password="pw")
    tid = get_tokens()[0]["id"]
    conn = functions.get_db()
    conn.execute("UPDATE accounts SET relogin_at = 0")
    conn.commit()
    conn.close()

    async def fake_login(email, password, device_id=None):
        return {
            "ok": True,
            "token": "fresh-token",
            "muted": True,
            "mute_until": 1762502400,
            "device_id": None,
            "account": email,
        }

    monkeypatch.setattr(functions, "login_deepseek_account", fake_login)
    asyncio.run(relogin_account(tid))
    row = get_tokens()[0]
    assert row["token"] == "fresh-token"
    assert row["status"] == "QUARANTINED"
    assert row["mute_until"] == 1762502400
