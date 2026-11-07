import json

from functions import StreamToolParser, _biz_data, normalize_tool_call


def test_corrupted_marker_split_across_stream_chunks():
    parser = StreamToolParser()
    value = "前<｜触｜DSML｜｜ calls>后"
    events = []
    for index in range(0, len(value), 3):
        events.extend(parser.feed(value[index : index + 3]))
    events.extend(parser.flush())
    assert "".join(event.get("text", "") for event in events) == "前后"


def test_clean_nested_tool_arguments_preserves_ascii_pipes():
    call = normalize_tool_call("test", {"values": ["path</｜｜DSML｜｜ >", "a|b"]})
    assert json.loads(call["function"]["arguments"]) == {"values": ["path", "a|b"]}


def test_biz_data_success():
    assert _biz_data({"data": {"biz_data": {"id": "123"}}}) == {"id": "123"}
