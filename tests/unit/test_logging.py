import io
import json
import logging

import structlog

from app.core.config import Settings
from app.core.logging import REDACTED, configure_logging, redact_sensitive_data


def test_redacts_sensitive_keys_recursively() -> None:
    event = redact_sensitive_data(
        None,
        "info",
        {
            "event": "user.login",
            "password": "hunter2",
            "nested": {"refresh_token": "abc", "safe": "value"},
            "headers": [{"authorization": "Bearer xyz"}],
            "email_count": 1,
        },
    )
    assert event["password"] == REDACTED
    assert event["nested"] == {"refresh_token": REDACTED, "safe": "value"}
    assert event["headers"] == [{"authorization": REDACTED}]
    assert event["email_count"] == 1


def test_scrubs_tokens_and_url_credentials_in_free_text() -> None:
    jwt_like = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    event = redact_sensitive_data(
        None,
        "info",
        {
            "event": "debug",
            "message": f"header Bearer abc.def and {jwt_like}",
            "target": "postgresql+psycopg://user:pa55@db:5432/app",
        },
    )
    assert "abc.def" not in event["message"]
    assert jwt_like not in event["message"]
    assert "pa55" not in event["target"]
    assert event["target"].endswith("db:5432/app")


def test_json_log_output_is_redacted() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",
        jwt_secret_key="x" * 40,
        log_json=True,
        environment="testing",
    )
    configure_logging(settings)
    root = logging.getLogger()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(root.handlers[0].formatter)
    root.addHandler(handler)
    try:
        structlog.stdlib.get_logger("test").info("auth.attempt", password="s3cret", user_id="u-1")
        logging.getLogger("thirdparty").warning("token=%s", "eyJa.eyJb.sig")
    finally:
        root.removeHandler(handler)

    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line]
    app_record = next(line for line in lines if line["event"] == "auth.attempt")
    assert app_record["password"] == REDACTED
    assert app_record["user_id"] == "u-1"
    assert app_record["logger"] == "test"
    assert app_record["level"] == "info"
    assert "s3cret" not in stream.getvalue()
    assert "eyJa.eyJb.sig" not in stream.getvalue()
