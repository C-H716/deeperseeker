"""深度健康探针的回归测试。"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module


def _patch(monkeypatch, tokens, verdict):
    async def fake_db(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def fake_probe(token):
        return {"verdict": verdict, "detail": "", "mute_until": None}

    monkeypatch.setattr(app_module, "_db", fake_db)
    monkeypatch.setattr(app_module, "get_tokens", lambda: tokens)
    monkeypatch.setattr(app_module, "probe_token_mute", fake_probe)


def test_no_active_token(monkeypatch):
    _patch(monkeypatch, [], "ok")
    result = asyncio.run(app_module._deep_health_probe())
    assert result["upstream_reachable"] is False
    assert "没有可用令牌" in result["reason"]


def test_ok_verdict(monkeypatch):
    _patch(monkeypatch, [{"status": "ACTIVE", "token": "t"}], "ok")
    result = asyncio.run(app_module._deep_health_probe())
    assert result["upstream_reachable"] is True
    assert isinstance(result["latency_ms"], float)


def test_muted_still_counts_as_reachable(monkeypatch):
    _patch(monkeypatch, [{"status": "ACTIVE", "token": "t"}], "muted")
    assert asyncio.run(app_module._deep_health_probe())["upstream_reachable"] is True


def test_invalid_verdict(monkeypatch):
    _patch(monkeypatch, [{"status": "ACTIVE", "token": "t"}], "invalid")
    result = asyncio.run(app_module._deep_health_probe())
    assert result["upstream_reachable"] is False
    assert "invalid" in result["reason"]
