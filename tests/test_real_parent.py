"""真实回复编号推进会话映射的回归测试（移植自 rh v85）。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import functions
from functions import (
    _extract_response_message_id,
    find_session,
    remember_real_parent,
    save_session,
    saved_parent,
)


@pytest.fixture()
def pool(tmp_path, monkeypatch):
    monkeypatch.setattr(functions, "_db", str(tmp_path / "pool.db"))
    monkeypatch.setattr(functions, "_LAST_REAL_PARENT", functions.OrderedDict())
    monkeypatch.setattr(functions, "_REAL_PARENT_ENABLED", True)
    functions.init_db()
    yield
    functions._LAST_REAL_PARENT.clear()


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"response_message_id": 42}, 42),
        ({"data": {"response_message_id": 43}}, 43),
        ({"v": {"response_message_id": 44}}, 44),
        ({"response_message_id": "42"}, None),
        ({"response_message_id": 0}, None),
        ({"p": "response/status", "v": "FINISHED"}, None),
        ("not-a-dict", None),
    ],
)
def test_extract_response_message_id(payload, expected):
    assert _extract_response_message_id(payload) == expected


def test_saved_parent_returns_none_without_broadcast(pool):
    assert saved_parent("chat-x", 5) is None


def test_remember_then_read(pool):
    remember_real_parent("chat-x", 101)
    assert saved_parent("chat-x", 0) == 101


def test_save_session_keeps_mapping_when_no_broadcast(pool):
    save_session("sig-1", 1, "chat-x", 5)
    assert find_session("sig-1")["parent_message_id"] == 5
    # 无广播（None）不得覆盖已有映射
    save_session("sig-1", 1, "chat-x", None)
    assert find_session("sig-1")["parent_message_id"] == 5


def test_save_session_advances_with_real_id(pool):
    save_session("sig-1", 1, "chat-x", 5)
    remember_real_parent("chat-x", 9)
    save_session("sig-1", 1, "chat-x", saved_parent("chat-x", 5))
    assert find_session("sig-1")["parent_message_id"] == 9


def test_legacy_mode_falls_back_to_plus_two(pool, monkeypatch):
    monkeypatch.setattr(functions, "_REAL_PARENT_ENABLED", False)
    assert saved_parent("chat-x", 5) == 7


def test_real_parent_cache_is_bounded(pool, monkeypatch):
    monkeypatch.setattr(functions, "_MAX_REAL_PARENT", 3)
    for index in range(5):
        remember_real_parent(f"chat-{index}", index)
    assert len(functions._LAST_REAL_PARENT) == 3
    assert saved_parent("chat-0", 0) is None
    assert saved_parent("chat-4", 0) == 4
