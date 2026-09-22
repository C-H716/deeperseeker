"""Token 池分配策略测试：在途最少优先、限流冷却与租约计数。

覆盖两项改动：
1. pick_token() 由无状态随机改为「在途最少优先」，并列时随机均摊；
2. mark_limited() 记录 limited_until 冷却窗口，冷却期内该账号不进入候选集，
   到期后重新参与，避免只能依赖间隔更长的定时健康检查恢复。

同时固定 TokenLease 的计数语义：release() 幂等、rebind() 转移占用且不重复
登记——计数只增不减会让某账号永久显得最忙，破坏负载均衡。
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import functions
from functions import (
    TokenLease,
    add_token,
    inflight_snapshot,
    mark_active,
    mark_limited,
    pick_token,
    token_acquire,
    token_release,
)


@pytest.fixture()
def pool(tmp_path, monkeypatch):
    """将模块级数据库指向临时文件，并清空在途计数。"""
    monkeypatch.setattr(functions, "_db", str(tmp_path / "pool.db"))
    functions._inflight.clear()
    functions.init_db()
    yield functions
    functions._inflight.clear()


def _expire_cooldown(token_id):
    """把冷却截止时间改到过去，模拟冷却窗口已过。"""
    conn = functions.get_db()
    conn.execute("UPDATE tokens SET limited_until = ? WHERE id = ?", (time.time() - 1, token_id))
    conn.commit()
    conn.close()


def test_pick_token_prefers_least_inflight(pool):
    a = add_token("token-a", alias="a")
    b = add_token("token-b", alias="b")
    token_acquire(a)
    token_acquire(a)
    token_acquire(b)

    assert pick_token() == b


def test_pick_token_spreads_across_equal_inflight(pool):
    a = add_token("token-a", alias="a")
    b = add_token("token-b", alias="b")
    c = add_token("token-c", alias="c")

    seen = {pick_token() for _ in range(60)}

    assert seen <= {a, b, c}
    assert len(seen) > 1, "在途数并列时必须继续均摊，而不是固定选同一个"


def test_limited_token_skipped_during_cooldown(pool):
    a = add_token("token-a", alias="a")
    b = add_token("token-b", alias="b")
    mark_limited(a)

    assert pick_token() == b


def test_limited_token_returns_after_cooldown(pool):
    a = add_token("token-a", alias="a")
    b = add_token("token-b", alias="b")
    mark_limited(a)
    assert pick_token() == b

    _expire_cooldown(a)
    seen = {pick_token() for _ in range(60)}

    assert a in seen, "冷却到期后限流账号必须重新进入候选集"


def test_sole_limited_token_is_still_fallback(pool):
    """候选集为空时保持原有兜底语义：不限状态取 id 最小者。"""
    a = add_token("token-a", alias="a")
    mark_limited(a)

    assert pick_token() == a


def test_mark_active_clears_cooldown(pool):
    a = add_token("token-a", alias="a")
    b = add_token("token-b", alias="b")
    mark_limited(a)

    mark_active(a)

    conn = functions.get_db()
    row = conn.execute("SELECT status, limited_until FROM tokens WHERE id = ?", (a,)).fetchone()
    conn.close()
    assert row[0] == "ACTIVE"
    assert row[1] is None
    assert a in {pick_token() for _ in range(60)}


def test_mark_limited_records_future_cooldown(pool):
    a = add_token("token-a", alias="a")
    before = time.time()

    mark_limited(a)

    conn = functions.get_db()
    row = conn.execute("SELECT status, limited_until FROM tokens WHERE id = ?", (a,)).fetchone()
    conn.close()
    assert row[0] == "RATE_LIMITED"
    assert row[1] >= before + functions.RATE_LIMIT_COOLDOWN_SEC - 1


def test_lease_release_is_idempotent(pool):
    a = add_token("token-a", alias="a")
    lease = TokenLease(a)
    assert inflight_snapshot() == {a: 1}

    lease.release()
    lease.release()

    assert inflight_snapshot() == {}


def test_lease_rebind_moves_occupancy(pool):
    a = add_token("token-a", alias="a")
    b = add_token("token-b", alias="b")
    lease = TokenLease(a)

    lease.rebind(b)
    assert inflight_snapshot() == {b: 1}

    lease.rebind(b)
    assert inflight_snapshot() == {b: 1}, "重复绑定同一账号不得重复登记"

    lease.release()
    assert inflight_snapshot() == {}


def test_token_release_drops_zero_key(pool):
    token_acquire(7)
    token_release(7)
    assert 7 not in inflight_snapshot()

    token_release(7)
    assert 7 not in inflight_snapshot(), "归零后重复释放不得产生负数计数"