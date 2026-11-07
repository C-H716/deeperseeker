"""40303 人机验证停放的回归测试。"""

import asyncio
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module
import functions
from functions import (
    add_token,
    get_tokens,
    mark_parked,
    pick_token,
    pool_state_note,
    restore_token,
)


@pytest.fixture()
def pool(tmp_path, monkeypatch):
    monkeypatch.setattr(functions, "_db", str(tmp_path / "pool.db"))
    functions._inflight.clear()
    functions.init_db()
    yield
    functions._inflight.clear()


def test_mark_parked_sets_timer_and_reason(pool):
    tid = add_token("tok")
    mark_parked(tid, "上游要求人机验证（40303）", 1800)
    row = get_tokens()[0]
    assert row["status"] == "PARKED"
    assert "40303" in row["park_reason"]
    assert row["limited_until"] > time.time()
    assert pool_state_note(row)[0] == "captcha"


def test_parked_token_is_excluded_from_rotation(pool):
    tid = add_token("tok")
    mark_parked(tid, "captcha", 1800)
    # 未到期：既不参与轮换，也不作为「全冷却兜底」被选中
    assert pick_token() is None
    assert get_tokens()[0]["status"] == "PARKED"


def test_parked_token_recovers_after_expiry(pool):
    tid = add_token("tok")
    mark_parked(tid, "captcha", 1800)
    conn = functions.get_db()
    conn.execute(
        "UPDATE tokens SET limited_until = ? WHERE id = ?", (time.time() - 1, tid)
    )
    conn.commit()
    conn.close()
    assert pick_token() == tid
    row = get_tokens()[0]
    assert row["status"] == "ACTIVE"
    assert row["park_reason"] is None


def test_restore_clears_park_reason(pool):
    tid = add_token("tok")
    mark_parked(tid, "captcha", 1800)
    restore_token(tid)
    row = get_tokens()[0]
    assert row["status"] == "ACTIVE"
    assert row["park_reason"] is None


def test_40303_failure_parks_token(pool, monkeypatch):
    tid = add_token("tok")

    async def fake_db(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(app_module, "_db", fake_db)
    error = functions.UpstreamBizError(
        429, "response: code=40303 msg=CHALLENGE_REQUIRED"
    )
    asyncio.run(app_module._handle_upstream_failure(error, tid))
    row = get_tokens()[0]
    assert row["status"] == "PARKED"
    assert "40303" in row["park_reason"]
