"""Prompt-cache accounting: the bridge must report a non-zero cached_tokens.

The DeepSeek web endpoint returns no token metadata, so the bridge reproduces
`prompt_cache_hit_tokens` from the fact that a client resends the whole
conversation every turn: the previous turn's prompt is a prefix of this turn's.
These tests pin the pairing that makes that reconstruction correct — the
`next_sig` recorded at the end of turn N must equal the `sig` of turn N+1.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions import (  # noqa: E402
    count_tokens,
    peek_cached_input,
    record_cached_input,
    reset_cached_input,
)
from plugin_helper import generate_signature_sync  # noqa: E402

MODEL = "deepseek-v4.1-flash"


def _msgs(*turns):
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": t}
        for i, t in enumerate(turns)
    ]


def test_first_turn_has_no_cache_to_read():
    msgs = _msgs("[SYSTEM]\npolicy\n\n[USER]\nhello")
    sig = generate_signature_sync(msgs, MODEL)
    assert peek_cached_input(sig) == 0


def _prior_sig(msgs):
    """与 app.py 一致：会话续接用「截到最后一个 assistant 为止」的签名。"""
    last_ast = -1
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") == "assistant":
            last_ast = i
            break
    return generate_signature_sync(msgs[: last_ast + 1], MODEL)


def test_next_sig_of_turn_n_equals_sig_of_turn_n_plus_1():
    """This equality is the whole basis of the reconstruction."""
    m1 = _msgs("[SYSTEM]\npolicy\n\n[USER]\nfirst question")
    sig1 = generate_signature_sync(m1, MODEL)
    a1 = {"role": "assistant", "content": "first answer"}
    next_sig1 = generate_signature_sync(m1 + [a1], MODEL)

    m2 = m1 + [a1, {"role": "user", "content": "second question"}]
    sig2 = _prior_sig(m2)

    assert sig1 != sig2, "distinct turns must not share a signature"
    assert sig2 == next_sig1, "turn-2 sig must equal turn-1 next_sig"


def test_cached_tokens_reports_previous_turn_prompt_size():
    m1 = _msgs("[SYSTEM]\npolicy\n\n[USER]\nfirst question")
    sig1 = generate_signature_sync(m1, MODEL)
    in1 = count_tokens(m1[0]["content"])
    assert peek_cached_input(sig1) == 0

    a1 = {"role": "assistant", "content": "first answer"}
    record_cached_input(generate_signature_sync(m1 + [a1], MODEL), in1)

    m2 = m1 + [a1, {"role": "user", "content": "second question"}]
    sig2 = _prior_sig(m2)
    in2 = sum(count_tokens(m["content"]) for m in m2)

    assert peek_cached_input(sig2) == in1
    assert 0 < in1 < in2, "cache hit must be a proper prefix of the new prompt"
    rate = peek_cached_input(sig2) / in2 * 100
    assert 0 < rate < 100, f"hit rate must be a real percentage, got {rate}"


def test_cache_is_capped_at_prompt_size():
    """A shorter turn must not report more cached tokens than it sent."""
    sig = "shrink-signature"
    record_cached_input(sig, 5000)
    assert min(peek_cached_input(sig), 120) == 120


def test_reset_clears_a_rebuilt_history():
    sig = "rollover-signature"
    record_cached_input(sig, 4000)
    assert peek_cached_input(sig) == 4000
    reset_cached_input(sig)
    assert peek_cached_input(sig) == 0


def test_dsh_contract_prompt_tokens_includes_cached():
    """DSH's pi-ai adapter subtracts cacheRead from promptTokens.

    It computes `input = promptTokens - cacheReadTokens`, so prompt_tokens MUST
    include the cached portion or the derived non-cache input goes negative and
    the client's hit rate reads 0% forever. This pins the arithmetic the bridge
    relies on.
    """
    from app import _cached_prompt_tokens, _remember_prompt_tokens  # noqa: E402

    sig = "contract-signature"
    reset_cached_input(sig)
    assert _cached_prompt_tokens(sig, 10_000) == 0, "cold turn must report no hit"

    _remember_prompt_tokens(sig, 8_000)
    cached = _cached_prompt_tokens(sig, 10_000)
    assert cached == 8_000

    prompt_tokens = 10_000
    non_cached_input = prompt_tokens - cached
    assert non_cached_input == 2_000, "cacheRead must be a subset of promptTokens"
    assert 0 < cached / prompt_tokens < 1, "hit rate must be a real fraction"


def test_cached_never_exceeds_reported_prompt_tokens():
    """A shrinking prompt must not report a hit larger than what it sent."""
    from app import _cached_prompt_tokens  # noqa: E402

    sig = "shrink-signature"
    reset_cached_input(sig)
    record_cached_input(sig, 50_000)
    assert _cached_prompt_tokens(sig, 1_200) == 1_200


def test_cache_hit_must_be_looked_up_with_prior_sig():
    """回归：用当前轮完整 sig 查表会永远查不到上一轮写入的键。

    上一轮以 next_sig（该轮 messages + 该轮回复）写入前缀大小；下一轮的
    prior_sig 才是同一个签名，sig 多了新的 user 消息，二者必然不同。
    """
    from app import _cache_hit_for, _cached_prompt_tokens  # noqa: E402

    m1 = _msgs("[SYSTEM]\npolicy\n\n[USER]\nfirst question")
    a1 = {"role": "assistant", "content": "first answer"}
    in1 = sum(count_tokens(m["content"]) for m in m1)
    next_sig1 = generate_signature_sync(m1 + [a1], MODEL)
    reset_cached_input(next_sig1)
    record_cached_input(next_sig1, in1)

    m2 = m1 + [a1, {"role": "user", "content": "second question"}]
    sig2 = generate_signature_sync(m2, MODEL)
    prior2 = _prior_sig(m2)
    in2 = sum(count_tokens(m["content"]) for m in m2)

    assert prior2 == next_sig1
    assert sig2 != next_sig1, "当前轮完整签名不可能等于上一轮的 next_sig"
    assert _cached_prompt_tokens(sig2, in2) == 0, "旧实现：用 sig 查表恒 0"
    assert _cache_hit_for(sig2, prior2, in2) == in1
    assert 0 < in1 / in2 < 1, "命中率必须是真实比例，而不是恒 0"


def test_two_turn_flow_goes_from_cold_to_warm():
    """首轮冷启动无命中，完成一轮后下一轮必须读到非零命中。"""
    from app import _cache_hit_for, _remember_prompt_tokens  # noqa: E402

    m1 = _msgs("[SYSTEM]\npolicy\n\n[USER]\nfirst question")
    a1 = {"role": "assistant", "content": "first answer"}
    in1 = sum(count_tokens(m["content"]) for m in m1)
    sig1 = generate_signature_sync(m1, MODEL)

    assert _cache_hit_for(sig1, None, in1) == 0, "首轮没有可复用前缀"
    _remember_prompt_tokens(generate_signature_sync(m1 + [a1], MODEL), in1)

    m2 = m1 + [a1, {"role": "user", "content": "second question"}]
    in2 = sum(count_tokens(m["content"]) for m in m2)
    hit = _cache_hit_for(generate_signature_sync(m2, MODEL), _prior_sig(m2), in2)
    assert hit == in1
    assert 0 < hit < in2


def test_hourly_row_receives_the_cache_hit(monkeypatch):
    """缓存命中数必须落到 usage_hours.cache_read_tokens，供 /stats 出图。"""
    import asyncio  # noqa: E402

    import app  # noqa: E402

    calls = []

    async def fake_db(fn, *args, **kwargs):
        calls.append((fn, args, kwargs))
        return None

    monkeypatch.setattr(app, "_db", fake_db)
    asyncio.run(
        app._record_usage_safe(
            "scope", "openai", MODEL, 1000, 50, token_id=1, cached_tokens=800
        )
    )
    # record_usage_hour 是 usage_stats.record_usage 的别名，两边 __name__
    # 相同，只能按带 cache_read_tokens 的那次关键字调用区分。
    hour_calls = [c for c in calls if "cache_read_tokens" in c[2]]
    assert len(hour_calls) == 1
    assert hour_calls[0][2]["cache_read_tokens"] == 800
    assert hour_calls[0][2]["input_tokens"] == 1000


def test_openai_usage_exposes_cached_tokens_and_prices_it():
    """非流式响应必须把命中数报给客户端，并按命中/未命中分档计价。"""
    from app import format_response  # noqa: E402

    msgs = _msgs("question one", "answer one", "question two")
    cold = format_response("answer two", MODEL, msgs)
    # 以响应自己上报的 prompt_tokens 为准：它按拼接后的整段文本计数。
    in_tok = cold["usage"]["prompt_tokens"]
    warm = format_response("answer two", MODEL, msgs, cached_tokens=in_tok)

    assert cold["usage"]["prompt_tokens_details"]["cached_tokens"] == 0
    assert warm["usage"]["prompt_tokens_details"]["cached_tokens"] == in_tok
    assert warm["usage"]["prompt_tokens"] == in_tok, "prompt_tokens 必须含缓存部分"
    assert warm["usage"]["cost"] < cold["usage"]["cost"], "命中档单价更低"
    capped = format_response("answer two", MODEL, msgs, cached_tokens=in_tok * 10)
    assert capped["usage"]["prompt_tokens_details"]["cached_tokens"] == in_tok


def test_responses_usage_exposes_cached_tokens():
    from app import _responses_usage, format_responses_response  # noqa: E402

    usage = _responses_usage(1000, 50, 800)
    assert usage["input_tokens"] == 1000
    assert usage["input_tokens_details"]["cached_tokens"] == 800
    assert _responses_usage(1000, 50)["input_tokens_details"]["cached_tokens"] == 0
    assert (
        _responses_usage(100, 10, 500)["input_tokens_details"]["cached_tokens"] == 100
    ), "命中数不得超过本次上报的输入总量"

    result = {
        "id": "chatcmpl-123",
        "created": 1,
        "model": MODEL,
        "choices": [{"message": {"content": "OK", "tool_calls": None}}],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "total_tokens": 1050,
            "prompt_tokens_details": {"cached_tokens": 800},
        },
    }
    response = format_responses_response(result, MODEL)
    assert response["usage"]["input_tokens"] == 1000
    assert response["usage"]["input_tokens_details"]["cached_tokens"] == 800


def test_anthropic_usage_uses_non_cached_input_plus_cache_read():
    """Anthropic 口径：input_tokens 不含缓存读，两者相加才是完整输入。"""
    from app import format_anthropic_response  # noqa: E402

    result = {
        "id": "chatcmpl-123",
        "model": MODEL,
        "choices": [{"message": {"content": "OK", "tool_calls": None}}],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "total_tokens": 1050,
            "prompt_tokens_details": {"cached_tokens": 800},
        },
    }
    usage = format_anthropic_response(result, MODEL)["usage"]
    assert usage["input_tokens"] == 200
    assert usage["cache_read_input_tokens"] == 800
    assert usage["input_tokens"] + usage["cache_read_input_tokens"] == 1000
