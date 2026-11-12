"""PR #107 review（2026-11-12）里几条问题的回归测试。

1. 错误正文里的 "202" 子串不能被当成 WAF 202，否则会清空 cookie 并重启浏览器
2. 真正的 status=202 仍要失效 cookie
3. 启动预热放后台后，/health 必须能报告它的状态
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402
import functions  # noqa: E402


def _capture_db(monkeypatch):
    called = []

    async def fake_db(fn, *args, **kwargs):
        called.append(getattr(fn, "__name__", str(fn)))
        return None

    monkeypatch.setattr(app_module, "_db", fake_db)
    return called


def test_error_text_with_202_does_not_invalidate_cookies(monkeypatch):
    """日期 / 消息 ID 里恰好含 202 不能触发 cookie 失效。"""
    called = _capture_db(monkeypatch)
    err = functions.UpstreamError(500, "request id 12023 failed at 2025-11-12")
    asyncio.run(app_module._record_upstream_limit(1, err, 500))
    assert "invalidate_token_cookies" not in called


def test_real_status_202_still_invalidates_cookies(monkeypatch):
    called = _capture_db(monkeypatch)
    err = functions.UpstreamError(202, "AWS WAF challenge page")
    asyncio.run(app_module._record_upstream_limit(1, err, 429))
    assert "invalidate_token_cookies" in called


def test_upstream_http_code_ignores_stray_202():
    err = functions.UpstreamError(500, "request id 12023 failed at 2025-11-12")
    assert app_module._upstream_http_code(err) == 500
    assert app_module._upstream_http_code(functions.UpstreamError(202, "waf")) == 429


def test_health_reports_warmup_state(monkeypatch):
    """直接调用路由函数，避免 TestClient 起停 lifespan 带来的事件循环噪音。"""
    import json

    class Req:
        query_params = {}

    async def fake_db(fn, *args, **kwargs):
        return []

    monkeypatch.setattr(app_module, "_db", fake_db)
    monkeypatch.setattr(app_module, "check_key", lambda r: False)
    resp = asyncio.run(app_module.health(Req()))
    assert resp.status_code in (200, 503)
    body = json.loads(resp.body)
    assert body["warmup"] in ("idle", "running", "done", "failed")
