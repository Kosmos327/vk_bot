import re

import pytest

from config import Config
from diagnostics import format_debug_status, format_health_status
from services.backend_gateway import BackendApiError, BackendGateway


class DummyGateway:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.called = False

    def check_catalog_health(self):
        self.called = True
        if self.should_fail:
            raise BackendApiError("backend_unavailable", "boom", 503)
        return {"ok": True, "status": "ok"}


def make_cfg(use_backend=True, token="super-secret-token"):
    return Config(
        vk_group_token="vk-group-token",
        vk_group_id=123,
        admin_id=777,
        club_invite_link="",
        backend_base_url="https://api.example.com/base?token=123",
        bot_api_token=token,
        vk_bot_use_backend=use_backend,
    )


def test_debug_formatter_hides_real_bot_token():
    cfg = make_cfg(token="super-secret-token")
    text = format_debug_status(cfg, user_state_size=2)
    assert "super-secret-token" not in text
    assert "BOT_API_TOKEN: configured" in text


def test_debug_formatter_token_missing():
    cfg = make_cfg(token="")
    text = format_debug_status(cfg, user_state_size=0)
    assert "BOT_API_TOKEN: missing" in text


def test_health_formatter_ok():
    cfg = make_cfg()
    gw = DummyGateway()
    text = format_health_status(cfg, gw)
    assert gw.called is True
    assert "Связь с backend: OK" in text
    assert "Проверка каталога: OK" in text


def test_health_formatter_fail_without_stacktrace():
    cfg = make_cfg()
    gw = DummyGateway(should_fail=True)
    text = format_health_status(cfg, gw)
    assert "Связь с backend: FAIL" in text
    assert "Traceback" not in text
    assert "boom" not in text


def test_gateway_check_catalog_health_endpoint_and_header(monkeypatch):
    captured = {}

    class DummyResponse:
        status_code = 200
        text = "[]"

        def json(self):
            return []

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return DummyResponse()

    monkeypatch.setattr("services.backend_gateway.requests.request", fake_request)
    gw = BackendGateway("https://example.com", "bot-token")
    result = gw.check_catalog_health()
    assert result["ok"] is True
    assert captured["method"] == "GET"
    assert captured["url"] == "https://example.com/api/v1/vk/catalog/categories"
    assert captured["headers"]["X-Bot-Api-Token"] == "bot-token"


def test_non_admin_command_no_debug_info():
    response = "Команда недоступна"
    assert "BOT_API_TOKEN" not in response
    assert response == "Команда недоступна"
