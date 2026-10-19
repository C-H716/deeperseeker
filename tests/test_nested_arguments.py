"""Regression tests for the double-wrapped arguments unwrap.

DeepSeek V4 occasionally emits the entire argument object as the value of a
single ``arguments`` field (vllm-ascend fixed the same shape on 2026-04-26),
so the decoded payload carries one extra level. ``normalize_tool_call`` must
collapse exactly that shape while leaving genuine single-key tools alone.

Run:  python tests/test_nested_arguments.py   (pytest-compatible)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions import _unwrap_nested_arguments, parse_tools  # noqa: E402

B = chr(65372)
M = B * 2 + "DSML" + B * 2
LT = "<"
GT = ">"
Q = '"'


def wrap(body):
    return LT + "tool_call" + GT + body + LT + "/tool_call" + GT


def parsed(payload):
    return parse_tools(payload)


def test_json_arguments_double_wrapped():
    """A doubly wrapped arguments field collapses to the inner object."""
    payload = wrap(
        "{" + Q + "name" + Q + ": " + Q + "Bash" + Q + ", "
        + Q + "arguments" + Q + ": {" + Q + "arguments" + Q + ": {"
        + Q + "command" + Q + ": " + Q + "ls" + Q + "}}}"
    )
    tools, clean = parsed(payload)
    assert [t["function"]["name"] for t in tools] == ["Bash"]
    assert json.loads(tools[0]["function"]["arguments"]) == {"command": "ls"}
    assert clean == ""


def test_xml_arguments_parameter():
    """An arguments parameter carrying the whole object unwraps too."""
    payload = (
        LT + M + "tool_call" + GT
        + LT + M + "invoke name=" + Q + "Bash" + Q + GT
        + LT + M + "parameter name=" + Q + "arguments" + Q
        + " string=" + Q + "true" + Q + GT
        + "{" + Q + "command" + Q + ": " + Q + "ls" + Q + "}"
        + LT + "/" + M + "parameter" + GT
        + LT + "/" + M + "invoke" + GT
        + LT + "/" + M + "tool_call" + GT
    )
    tools, clean = parsed(payload)
    assert [t["function"]["name"] for t in tools] == ["Bash"]
    assert json.loads(tools[0]["function"]["arguments"]) == {"command": "ls"}
    assert clean == ""


def test_typed_arguments_preserved():
    """integer / boolean / array values survive the round trip unchanged."""
    payload = wrap(
        "{" + Q + "name" + Q + ": " + Q + "T" + Q + ", "
        + Q + "arguments" + Q + ": {" + Q + "n" + Q + ": 3, "
        + Q + "b" + Q + ": true, " + Q + "arr" + Q + ": [1,2]}}"
    )
    tools, _ = parsed(payload)
    assert json.loads(tools[0]["function"]["arguments"]) == {
        "n": 3,
        "b": True,
        "arr": [1, 2],
    }


def test_genuine_single_key_untouched():
    """A tool whose only argument is a normal key keeps its shape."""
    payload = wrap(
        "{" + Q + "name" + Q + ": " + Q + "T" + Q + ", "
        + Q + "arguments" + Q + ": {" + Q + "query" + Q + ": " + Q + "x" + Q + "}}"
    )
    tools, _ = parsed(payload)
    assert json.loads(tools[0]["function"]["arguments"]) == {"query": "x"}


def test_wrapper_key_with_scalar_value_untouched():
    """A wrapper key holding a scalar is real data, not an extra layer."""
    payload = wrap(
        "{" + Q + "name" + Q + ": " + Q + "T" + Q + ", "
        + Q + "arguments" + Q + ": {" + Q + "input" + Q + ": "
        + Q + "plain text" + Q + "}}"
    )
    tools, _ = parsed(payload)
    assert json.loads(tools[0]["function"]["arguments"]) == {"input": "plain text"}


def test_unwrap_is_bounded():
    """Three layers collapse at most twice; deeper junk is returned as-is."""
    args = {"arguments": {"arguments": {"arguments": {"command": "ls"}}}}
    assert _unwrap_nested_arguments(args) == {"arguments": {"command": "ls"}}


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