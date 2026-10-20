"""标签方言漂移回归测试：``tool call`` / ``tool calls`` / ``</tool>``。

模型（DeepSeek V4）偶尔把 ``tool_call`` 写成 ``tool call``，外层包裹写成
``tool calls``，闭标签退化为 ``</tool>``。这些形态原先全部识别不了，
整段 XML+JSON 被当作正文透传给客户端，工具根本不执行（见截图）。

覆盖点：

  1. parse_tools 能解析带空格的标签名族，且外层包裹标签不再把同一段
     JSON 解析两遍（consumed_upto 去重）；
  2. 流式解析在任意分片大小下都只产出一次工具调用，正文无残留；
  3. 裸 ``</tool>`` 能闭合已打开的工具块，不泄漏参数值；
  4. 正常 ``tool_call`` 形态不受影响（不重复、不漏）。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions import StreamToolParser, parse_tools  # noqa: E402

OPEN = chr(60) + "tool_call" + chr(62)
CLOSE = chr(60) + "/tool_call" + chr(62)
DRIFT = (
    "[LT]tool calls[GT] [LT]tool call[GT]"
    '{"name": "Read", "arguments": {"file_path": "a.mjs", "offset": 680}}'
    "[LT]/tool[GT] [LT]tool call[GT]"
    '{"name": "grep", "arguments": {"pattern": "DELETE"}}'
    "[LT]/tool[GT] [LT]/tool calls[GT]"
).replace("[LT]", chr(60)).replace("[GT]", chr(62))

NORMAL = (
    (OPEN + '{"name": "Read", "arguments": {"file_path": "a.mjs"}}' + CLOSE) * 1
    + OPEN
    + '{"name": "grep", "arguments": {"pattern": "DELETE"}}'
    + CLOSE
)


def _names(tools):
    return [t["function"]["name"] for t in tools]


def _stream(text, chunk):
    parser = StreamToolParser()
    out = []
    for i in range(0, len(text), chunk):
        out.extend(parser.feed(text[i : i + chunk]))
    out.extend(parser.flush())
    tools = [r["tool"] for r in out if "tool" in r]
    prose = "".join(r["text"] for r in out if "text" in r)
    return tools, prose


def test_parse_spaced_tags():
    tools, _ = parse_tools(DRIFT)
    assert _names(tools) == ["Read", "grep"], _names(tools)
    assert json.loads(tools[0]["function"]["arguments"])["offset"] == 680


def test_parse_spaced_tags_no_duplicate():
    tools, _ = parse_tools(DRIFT)
    assert len(tools) == 2, _names(tools)


def test_parse_spaced_tags_clean_text():
    _, clean = parse_tools(DRIFT)
    assert "tool call" not in clean
    assert "a.mjs" not in clean


def test_stream_spaced_tags_any_chunk():
    for chunk in (1, 3, 7, 50, 1000):
        tools, prose = _stream(DRIFT, chunk)
        assert _names(tools) == ["Read", "grep"], (chunk, _names(tools))
        assert "arguments" not in prose, (chunk, prose)


def test_bare_tool_closer_does_not_leak():
    text = (
        "[LT]tool call[GT]"
        '{"name": "Read", "arguments": {"file_path": "secret.txt"}}'
        "[LT]/tool[GT]"
    ).replace("[LT]", chr(60)).replace("[GT]", chr(62))
    tools, prose = _stream(text, 5)
    assert _names(tools) == ["Read"], _names(tools)
    assert "secret.txt" not in prose


def test_normal_tags_unaffected():
    tools, _ = parse_tools(NORMAL)
    assert _names(tools) == ["Read", "grep"], _names(tools)
    stream_tools, prose = _stream(NORMAL, 4)
    assert _names(stream_tools) == ["Read", "grep"], _names(stream_tools)
    assert "arguments" not in prose


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
