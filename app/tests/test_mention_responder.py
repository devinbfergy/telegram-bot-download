from app.features.mention_responder import _SYSTEM_PROMPT


def test_gork_personality_is_kind():
    prompt = _SYSTEM_PROMPT.lower()
    assert "never be mean" in prompt
    assert "warm" in prompt
    assert "dunk on people" in prompt


def test_gork_system_prompt_includes_capabilities():
    prompt = _SYSTEM_PROMPT.lower()
    assert "@gork is this real" in prompt
    assert "open issue" in prompt
    assert "bad bot" in prompt
    assert "good bot" in prompt
    assert "media downloader" in prompt
    assert "user memory" in prompt
