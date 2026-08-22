import logging

from mindweaver.logging_conf import (
    JsonFormatter,
    clear_secrets,
    redact,
    register_secret,
    setup_logging,
)


def _record(message: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord("test", level, __name__, 0, message, None, None)


def test_redact_replaces_registered_secrets():
    clear_secrets()
    register_secret("abc123")
    assert redact("token=abc123 here") == "token=*** here"


def test_redact_leaves_other_text_untouched():
    clear_secrets()
    register_secret("abc123")
    assert redact("nothing sensitive") == "nothing sensitive"


def test_json_formatter_does_not_leak_secret():
    clear_secrets()
    register_secret("super-secret-value")
    formatted = JsonFormatter().format(_record("connecting with super-secret-value"))
    assert "super-secret-value" not in formatted
    assert "***" in formatted


def test_json_formatter_outputs_valid_json():
    clear_secrets()
    formatted = JsonFormatter().format(_record("hello world"))
    assert '"level": "INFO"' in formatted
    assert '"message": "hello world"' in formatted


def test_setup_logging_registers_secret():
    clear_secrets()
    setup_logging(secret="my-secret-key")
    assert "***" in redact("prefix my-secret-key suffix")
    clear_secrets()
