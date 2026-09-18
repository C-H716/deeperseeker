"""Regression coverage for OpenAI Responses API compatibility."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import _responses_payload, convert_responses_input, stream_openai_responses
from functions import _deepseek_event_finished, _deepseek_event_fragments
from plugin_helper import extract_tools


def test_responses_function_tools_use_top_level_definition():
    tools = [{
        "type": "function",
        "name": "read_file",
        "description": "Read a file",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
    }]
    prompt = asyncio.run(extract_tools(tools))
    assert "Tool: read_file" in prompt
    assert '"path"' in prompt


def test_invalid_and_builtin_tools_do_not_create_blank_entries():
    tools = [
        {"type": "function", "name": "", "parameters": {}},
        {"type": "web_search", "external_web_access": False},
    ]
    assert asyncio.run(extract_tools(tools)) is None


def test_responses_input_converts_instructions_and_tool_outputs():
    body = {
        "instructions": "Answer briefly.",
        "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Run it"}]},
            {"type": "function_call", "call_id": "call_1", "name": "shell", "arguments": "{\"cmd\":\"dir\"}"},
            {"type": "function_call_output", "call_id": "call_1", "output": "file.txt"},
        ],
    }
    messages = convert_responses_input(body)
    assert messages[0] == {"role": "system", "content": "Answer briefly."}
    assert messages[1]["content"][0] == {"type": "text", "text": "Run it"}
    assert messages[2]["tool_calls"][0]["function"]["name"] == "shell"
    assert messages[3] == {"role": "tool", "tool_call_id": "call_1", "content": "file.txt"}


def test_non_stream_response_uses_official_output_types():
    result = {
        "id": "chatcmpl-123",
        "created": 1,
        "model": "v4.1flash",
        "choices": [{"message": {"content": "OK", "tool_calls": None}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
    }
    response = _responses_payload(result, "v4.1flash")
    assert response["id"] == "resp_123"
    assert response["status"] == "completed"
    assert response["output"][0]["content"][0]["type"] == "output_text"
    assert response["usage"]["input_tokens"] == 2


def test_batched_deepseek_fragments_are_not_lost():
    event = {
        "o": "BATCH",
        "v": [
            {"p": "response/fragments", "o": "APPEND", "v": [{"type": "RESPONSE", "content": "hello"}]},
            {"p": "quasi_status", "v": "FINISHED"},
        ],
    }
    assert _deepseek_event_fragments(event) == [("RESPONSE", "hello")]
    assert _deepseek_event_finished(event)


def test_responses_stream_emits_semantic_events():
    async def chat_stream():
        yield 'data: {"choices":[{"delta":{"content":"O"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"K"}}]}\n\n'
        yield 'data: [DONE]\n\n'

    async def collect():
        return "".join([chunk async for chunk in stream_openai_responses(chat_stream(), "v4.1flash")])

    streamed = asyncio.run(collect())
    assert "event: response.created" in streamed
    assert "event: response.output_text.delta" in streamed
    assert '"delta": "O"' in streamed
    assert "event: response.completed" in streamed
    assert "choices" not in streamed


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
