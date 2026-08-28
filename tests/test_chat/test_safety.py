"""Tests for chat safety harness - response sanitization and tool call redaction."""

from src.chat.safety import redact_tool_calls, sanitize_response

# ── sanitize_response tests ──────────────────────────────────────────


class TestSanitizeResponse:
    def test_normal_text_unchanged(self):
        """Normal assistant text should pass through unchanged."""
        text = "Alice has 5 tasks in progress and 2 blocked."
        assert sanitize_response(text) == text

    def test_strips_system_prompt_leak(self):
        """Should redact system prompt content if leaked."""
        text = "My system prompt says: You are Numen AI, an intelligent assistant"
        result = sanitize_response(text)
        assert "You are Numen AI" not in result

    def test_strips_tool_definitions(self):
        """Should redact tool/function definition leaks."""
        text = 'Here are my tools: {"tools": [{"name": "get_person_tasks"}]}'
        result = sanitize_response(text)
        assert '"tools":' not in result

    def test_strips_internal_paths(self):
        """Should redact internal source paths."""
        text = "The error is in src/graph/falkor_repository.py at line 42"
        result = sanitize_response(text)
        assert "src/" not in result

    def test_strips_config_references(self):
        """Should redact config/env variable references."""
        text = "The API key is settings.openai_api_key = sk-abc123"
        result = sanitize_response(text)
        assert "settings." not in result
        assert "sk-abc" not in result

    def test_strips_api_key_patterns(self):
        """Should redact API key patterns."""
        text = "Use OPENAI_API_KEY=sk-proj-abc123 to configure"
        result = sanitize_response(text)
        assert "sk-proj-" not in result

    def test_strips_function_definitions(self):
        """Should redact function schema leaks."""
        text = 'Available functions: {"functions": [{"name": "search"}]}'
        result = sanitize_response(text)
        assert '"functions":' not in result

    def test_preserves_normal_code_discussion(self):
        """Should not strip normal technical discussion."""
        text = "The task ENG-123 is blocking 3 other tasks."
        assert sanitize_response(text) == text

    def test_empty_string(self):
        """Empty string should return empty."""
        assert sanitize_response("") == ""


# ── redact_tool_calls tests ──────────────────────────────────────────


class TestRedactToolCalls:
    def test_removes_input_params(self):
        """Should remove input details, keep only tool name."""
        tool_calls = [
            {"tool": "get_person_tasks", "input": {"name": "Alice", "since_days_ago": 7}},
            {"tool": "get_urgency_scores", "input": {"person_name": "Bob"}},
        ]
        redacted = redact_tool_calls(tool_calls)
        assert len(redacted) == 2
        assert redacted[0] == {"tool": "get_person_tasks"}
        assert redacted[1] == {"tool": "get_urgency_scores"}
        for item in redacted:
            assert "input" not in item

    def test_empty_list(self):
        """Empty list should return empty."""
        assert redact_tool_calls([]) == []

    def test_none_input(self):
        """None should return empty list."""
        assert redact_tool_calls(None) == []

    def test_preserves_tool_name(self):
        """Tool name should always be preserved."""
        tool_calls = [{"tool": "search_entities", "input": {"query": "secret"}}]
        redacted = redact_tool_calls(tool_calls)
        assert redacted[0]["tool"] == "search_entities"
