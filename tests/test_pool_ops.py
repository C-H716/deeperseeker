"""号池五态说明与人工恢复的回归测试。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import functions
from functions import (
    add_token,
    get_tokens,
    mark_quarantined,
    pool_state_note,
    restore_token,
)


@pytest.mark.parametrize(
    "status,reason,expected_kind",
    [
        ("ACTIVE", "", "ok"),
        ("RATE_LIMITED", "", "cooling"),
        ("INVALID", "", "expired"),
        ("CHECK_ERROR", "", "other"),
        ("QUARANTINED", "user is muted (until 2026-11-14 12:00)", "muted"),
        ("QUARANTINED", "3 consecutive auth-shaped business errors", "expired"),
        ("QUARANTINED", "3 consecutive upstream 403s", "restricted"),
        ("QUARANTINED", "account banned (bridge login)", "other"),
        ("MUTED", "", "muted"),
    ],
)
def test_pool_state_note_classification(status, reason, expected_kind):
    kind, note = pool_state_note({"status": status, "quarantine_reason": reason})
    assert kind == expected_kind
    assert note


def test_manual_restore_clears_quarantine(tmp_path, monkeypatch):
    monkeypatch.setattr(functions, "_db", str(tmp_path / "pool.db"))
    functions.init_db()
    tid = add_token("tok")
    mark_quarantined(tid, "user is muted (until x)", 1762502400)

    row = get_tokens()[0]
    assert row["status"] == "QUARANTINED"
    assert pool_state_note(row)[0] == "muted"

    restore_token(tid)
    row = get_tokens()[0]
    assert row["status"] == "ACTIVE"
    assert row["quarantine_reason"] is None
    assert row["mute_until"] is None
    assert pool_state_note(row)[0] == "ok"
