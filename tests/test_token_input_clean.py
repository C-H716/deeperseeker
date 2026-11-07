"""粘贴 Token 的清洗规则。

面板里粘贴的 Token 常带首尾引号或空格（浏览器 Console 复制出来是
``'eyJ...'``，localStorage 复制出来是整段 JSON），也可能叠着
``value:`` 前缀。清洗必须一次到位，否则带引号的串会被原样入库，之后每个
请求都拿它去请求上游，表现为「Token 明明有效却一直 401」。

Run:  python -m pytest tests/test_token_input_clean.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import clean_auth_token  # noqa: E402

TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abc-_DEF"


def test_bare_token_is_untouched():
    assert clean_auth_token(TOKEN) == TOKEN


def test_surrounding_spaces_are_stripped():
    assert clean_auth_token("   " + TOKEN + "  \n") == TOKEN


def test_single_quotes_are_stripped():
    """Console 复制出来最常见的就是单引号包裹。"""
    assert clean_auth_token("'" + TOKEN + "'") == TOKEN
    assert clean_auth_token("  ' " + TOKEN + " '  ") == TOKEN


def test_double_quotes_are_stripped():
    assert clean_auth_token('"' + TOKEN + '"') == TOKEN


def test_mismatched_quotes_are_stripped():
    """左右引号不一致（粘贴时被编辑器改过）也要能剥掉。"""
    assert clean_auth_token("'" + TOKEN + '"') == TOKEN
    assert clean_auth_token('"' + TOKEN + "'") == TOKEN


def test_nested_wrapping_is_collapsed():
    assert clean_auth_token('"' + "'" + TOKEN + "'" + '"') == TOKEN


def test_single_sided_quote_is_stripped():
    """只粘到一半的引号（缺闭合）也当残留处理。"""
    assert clean_auth_token("'" + TOKEN) == TOKEN
    assert clean_auth_token(TOKEN + "'") == TOKEN


def test_curly_and_fullwidth_quotes_are_stripped():
    assert clean_auth_token("\u2018" + TOKEN + "\u2019") == TOKEN
    assert clean_auth_token("\u201c" + TOKEN + "\u201d") == TOKEN
    assert clean_auth_token("\uff07" + TOKEN + "\uff07") == TOKEN


def test_value_prefix_is_stripped():
    assert clean_auth_token("value: " + TOKEN) == TOKEN
    assert clean_auth_token("value=" + TOKEN) == TOKEN
    assert clean_auth_token('"value": "' + TOKEN + '"') == TOKEN


def test_json_wrapper_is_unwrapped():
    assert clean_auth_token('{"value":"' + TOKEN + '"}') == TOKEN
    assert clean_auth_token('{"value": "' + TOKEN + '", "other": 1}') == TOKEN


def test_stacked_wrapping_converges():
    """value: 前缀 + 引号 + 空格叠在一起，一次调用就要洗干净。"""
    assert clean_auth_token('  value:  " ' + TOKEN + " '  ") == TOKEN


def test_empty_input_is_empty_string():
    assert clean_auth_token("") == ""
    assert clean_auth_token("   ") == ""
    assert clean_auth_token("''") == ""
