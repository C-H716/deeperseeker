"""上下文滚动抑制窗口的回归测试。

背景：客户端每轮都重发完整历史，而 rollover 只迁移上游 chat，不会让客户端
历史变短。因此一旦历史越线，``needs_rollover()`` 在之后每个用户轮都为真，
每轮都多跑一次摘要请求（实测 +20~30s）。``_should_rollover()`` 在
``needs_rollover()`` 之上加了抑制窗口，``_note_rollover()`` 记录滚动发生时的
历史规模。

覆盖点：

  1. 未记录过滚动时照常放行；
  2. 刚滚过 + 历史几乎没变 → 抑制；
  3. 抑制键锚定会话根，跨用户轮（历史增长）仍然命中；
  4. 新增内容超过续滚阈值 → 放行；
  5. 超过抑制时长 → 放行；
  6. 未越线时无论如何都不滚动。
"""

import os
import sys
import unittest.mock as mock
from contextlib import ExitStack

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as proxy_app  # noqa: E402
import plugin_helper  # noqa: E402
from plugin_helper import (  # noqa: E402
    context_window_tokens,
    estimate_conversation_tokens,
)


def big_text(words, tag="w"):
    return " ".join(f"{tag}{i}" for i in range(words))


def history(pairs=4, words=60):
    """一段累计历史：首条 user 之后交替 assistant/user。"""
    msgs = [{"role": "user", "content": big_text(words, "root")}]
    for i in range(pairs):
        msgs.append({"role": "assistant", "content": big_text(words, f"a{i}")})
        msgs.append({"role": "user", "content": big_text(words, f"u{i}")})
    return msgs


def low_limit():
    """把上下文上限压到 ~90 token，让构造的小历史也能越线。"""
    stack = ExitStack()
    stack.enter_context(
        mock.patch.object(plugin_helper, "OBSERVED_MEMORY_LIMIT_TOKENS", 100)
    )
    stack.enter_context(mock.patch.object(plugin_helper, "ROLLOVER_SAFETY_TOKENS", 10))
    return stack


def reset_state():
    proxy_app._ROLLOVER_LAST.clear()


def resume_threshold():
    """与 _should_rollover 内的续滚阈值保持一致。"""
    return max(1, int(context_window_tokens() * proxy_app.ROLLOVER_RESUME_FRACTION))


def test_no_record_rolls_over():
    reset_state()
    msgs = history()
    with low_limit():
        assert proxy_app._should_rollover(msgs, "v4.1flash", "sk-test")


def test_recent_rollover_is_suppressed():
    reset_state()
    msgs = history()
    with low_limit():
        assert proxy_app._should_rollover(msgs, "v4.1flash", "sk-test")
        proxy_app._note_rollover(msgs, "v4.1flash", "sk-test")
        assert not proxy_app._should_rollover(msgs, "v4.1flash", "sk-test")


def test_suppression_survives_new_turns():
    """抑制键是会话根，后续轮次历史变长也必须命中。"""
    reset_state()
    msgs = history()
    with low_limit():
        proxy_app._note_rollover(msgs, "v4.1flash", "sk-test")
        grown = msgs + [
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "next question"},
        ]
        assert estimate_conversation_tokens(grown) < (
            estimate_conversation_tokens(msgs) + resume_threshold()
        ), "sanity: 这一轮的增量必须小于续滚阈值"
        assert not proxy_app._should_rollover(grown, "v4.1flash", "sk-test")


def test_enough_growth_resumes_rollover():
    reset_state()
    msgs = history()
    with low_limit():
        proxy_app._note_rollover(msgs, "v4.1flash", "sk-test")
        baseline = estimate_conversation_tokens(msgs)
        target = baseline + resume_threshold()
        grown = list(msgs)
        i = 0
        while estimate_conversation_tokens(grown) < target:
            grown.append({"role": "user", "content": big_text(40, f"g{i}")})
            grown.append({"role": "assistant", "content": big_text(40, f"h{i}")})
            i += 1
        assert proxy_app._should_rollover(grown, "v4.1flash", "sk-test")


def test_expired_window_resumes_rollover():
    reset_state()
    msgs = history()
    with low_limit():
        proxy_app._note_rollover(msgs, "v4.1flash", "sk-test")
        key = proxy_app._conversation_root(msgs, "v4.1flash", "sk-test")
        ts, tokens = proxy_app._ROLLOVER_LAST[key]
        proxy_app._ROLLOVER_LAST[key] = (
            ts - proxy_app.ROLLOVER_SUPPRESS_SECONDS - 1,
            tokens,
        )
        assert proxy_app._should_rollover(msgs, "v4.1flash", "sk-test")


def test_below_limit_never_rolls_over():
    reset_state()
    msgs = history(pairs=1, words=3)
    proxy_app._note_rollover(msgs, "v4.1flash", "sk-test")
    assert not proxy_app._should_rollover(msgs, "v4.1flash", "sk-test")


def test_different_conversations_do_not_share_suppression():
    reset_state()
    first = history()
    second = [{"role": "user", "content": "a completely different root"}] + first[1:]
    with low_limit():
        proxy_app._note_rollover(first, "v4.1flash", "sk-test")
        assert proxy_app._should_rollover(second, "v4.1flash", "sk-test")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for t in tests:
        try:
            t()
            print("PASS " + t.__name__)
        except AssertionError as e:
            bad += 1
            print("FAIL " + t.__name__ + ": " + str(e))
    if bad:
        sys.exit(1)
    print(str(len(tests)) + " passed")


if __name__ == "__main__":
    main()
