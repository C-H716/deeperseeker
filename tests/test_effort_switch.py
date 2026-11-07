"""提示词增强总开关的回归测试。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import functions
import plugin_helper
from functions import get_effort_enhance, request_effort, set_effort_enhance


@pytest.fixture()
def settings_db(tmp_path, monkeypatch):
    monkeypatch.setattr(functions, "_db", str(tmp_path / "pool.db"))
    monkeypatch.setattr(functions, "_effort_enhance_cache", None)
    functions.init_db()
    yield
    monkeypatch.setattr(functions, "_effort_enhance_cache", None)


def test_default_is_on(settings_db):
    assert get_effort_enhance() is True


def test_toggle_persists_and_refreshes_cache(settings_db):
    assert set_effort_enhance(False) is False
    assert get_effort_enhance() is False
    assert set_effort_enhance(True) is True
    assert get_effort_enhance() is True


def test_disabled_switch_does_not_inject_instruction(settings_db):
    set_effort_enhance(False)
    token = request_effort.set("max")
    try:
        assert plugin_helper._with_effort("prompt") == "prompt"
    finally:
        request_effort.reset(token)


def test_enabled_switch_injects_instruction(settings_db):
    set_effort_enhance(True)
    token = request_effort.set("max")
    try:
        assert plugin_helper._with_effort("prompt") != "prompt"
    finally:
        request_effort.reset(token)
