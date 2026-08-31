from noteagent.bootstrap.settings import Settings
from noteagent.chat.context_budget import budget_from_settings


def test_budget_from_explicit_settings():
    b = budget_from_settings(Settings(
        chat_context_window=32768,
        context_trigger_ratio=0.8,
        context_target_ratio=0.6,
        context_stub_preview_tokens=1000,
        context_args_preview_chars=500,
        context_output_reserve=1024,
        context_safety_buffer=512,
    ))
    assert b.window == 32768
    assert b.stub_preview_tokens == 1000
    assert b.args_preview_chars == 500
    assert b.output_reserve == 1024
    assert b.safety_buffer == 512
    assert b.trigger_tokens() == int(32768 * 0.8)
    assert b.target_tokens() == int(32768 * 0.6)
    assert b.max_tool_hops == 8
