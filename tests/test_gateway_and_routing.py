import pytest
import requests

from config import load_config
from main import format_service_card, format_service_preview
from routing import is_legacy_confirm_command, is_legacy_discount_command
from services.backend_gateway import BackendApiError, BackendGateway
from state import USER_STATE, get_user_state, reset_user_state
from vk_attachments import extract_attachment_url


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text='x'):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_config_validation_backend_mode_missing_backend(monkeypatch):
    monkeypatch.setenv("VK_BOT_USE_BACKEND", "true")
    monkeypatch.setenv("VK_GROUP_TOKEN", "vk")
    monkeypatch.setenv("VK_GROUP_ID", "1")
    monkeypatch.setenv("ADMIN_ID", "1")
    monkeypatch.delenv("BACKEND_BASE_URL", raising=False)
    monkeypatch.delenv("BOT_API_TOKEN", raising=False)
    with pytest.raises(ValueError):
        load_config()


def test_config_validation_legacy_mode_backend_optional(monkeypatch):
    monkeypatch.setenv("VK_BOT_USE_BACKEND", "false")
    monkeypatch.setenv("VK_GROUP_TOKEN", "vk")
    monkeypatch.setenv("VK_GROUP_ID", "1")
    monkeypatch.setenv("ADMIN_ID", "1")
    monkeypatch.delenv("BACKEND_BASE_URL", raising=False)
    monkeypatch.delenv("BOT_API_TOKEN", raising=False)
    cfg = load_config()
    assert cfg.vk_bot_use_backend is False


def test_gateway_url_join_and_structured_error(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["url"] = url
        return DummyResponse(400, {"detail": {"code": "monthly_limit", "message": "Лимит"}})

    monkeypatch.setattr("services.backend_gateway.requests.request", fake_request)
    gw = BackendGateway("https://example.com/", "t")
    with pytest.raises(BackendApiError) as e:
        gw._request("GET", "api/v1/vk/catalog/categories")
    assert captured["url"] == "https://example.com/api/v1/vk/catalog/categories"
    assert e.value.code == "monthly_limit"


def test_gateway_network_error_to_backend_unavailable(monkeypatch):
    def fake_request(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr("services.backend_gateway.requests.request", fake_request)
    gw = BackendGateway("https://example.com", "t")
    with pytest.raises(BackendApiError) as e:
        gw.get_categories()
    assert e.value.code == "backend_unavailable"


def test_routing_legacy_aliases():
    assert is_legacy_discount_command("скидка 1")
    assert is_legacy_confirm_command("ДА 1")


def test_state_reset_and_no_partner_hint():
    user_id = 42
    state = get_user_state(user_id)
    state["last_partner_id"] = 123
    reset_user_state(user_id)
    assert user_id not in USER_STATE


def test_receipt_extractors():
    msg = {"attachments": [{"type": "photo", "photo": {"sizes": [{"width": 50, "height": 50, "url": "small"}, {"width": 100, "height": 100, "url": "big"}]}}]}
    assert extract_attachment_url(msg) == "big"
    doc = {"attachments": [{"type": "doc", "doc": {"url": "doc-url"}}]}
    assert extract_attachment_url(doc) == "doc-url"
    unknown = {"attachments": [{"type": "audio"}]}
    assert extract_attachment_url(unknown) is None


@pytest.mark.parametrize(
    ("method_name", "kwargs", "payload_key", "expected_method"),
    [
        ("auth_vk_user", {"vk_user_id": 123}, "json", "POST"),
        ("get_subscription", {"vk_user_id": 123}, "params", "GET"),
        ("request_discount_code", {"vk_user_id": 123, "partner_id": 1, "partner_service_id": 2}, "json", "POST"),
        ("create_payment_request", {"vk_user_id": 123}, "json", "POST"),
        ("get_latest_payment_request", {"vk_user_id": 123}, "params", "GET"),
    ],
)
def test_gateway_serializes_vk_user_id_as_string(monkeypatch, method_name, kwargs, payload_key, expected_method):
    captured = {}

    def fake_request(method, url, **request_kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = request_kwargs.get(payload_key) or {}
        return DummyResponse(200, {"ok": True})

    monkeypatch.setattr("services.backend_gateway.requests.request", fake_request)
    gw = BackendGateway("https://example.com", "t")

    method = getattr(gw, method_name)
    result = method(**kwargs)

    assert captured["method"] == expected_method
    assert captured["payload"]["vk_user_id"] == "123"
    assert isinstance(captured["payload"]["vk_user_id"], str)
    if method_name == "get_latest_payment_request":
        assert result is None
    else:
        assert result == {"ok": True}


def test_get_partners_unwraps_items(monkeypatch):
    monkeypatch.setattr(
        "services.backend_gateway.requests.request",
        lambda *a, **k: DummyResponse(200, {"items": [{"id": 1, "name": "P1"}], "total": 1}),
    )
    gw = BackendGateway("https://example.com", "t")
    assert gw.get_partners() == [{"id": 1, "name": "P1"}]


def test_get_partner_services_unwraps_items(monkeypatch):
    monkeypatch.setattr(
        "services.backend_gateway.requests.request",
        lambda *a, **k: DummyResponse(200, {"items": [{"id": 10, "title": "Svc"}], "partner_id": 1}),
    )
    gw = BackendGateway("https://example.com", "t")
    assert gw.get_partner_services(1) == [{"id": 10, "title": "Svc"}]


def test_get_latest_payment_request_unwraps_or_none(monkeypatch):
    responses = iter(
        [
            DummyResponse(200, {"payment_request": {"id": 5, "status": "pending"}}),
            DummyResponse(200, {"payment_request": None}),
        ]
    )
    monkeypatch.setattr("services.backend_gateway.requests.request", lambda *a, **k: next(responses))
    gw = BackendGateway("https://example.com", "t")
    assert gw.get_latest_payment_request(1) == {"id": 5, "status": "pending"}
    assert gw.get_latest_payment_request(1) is None


def test_service_formatting_uses_backend_fields():
    service = {"id": 7, "title": "Стрижка", "description": "Классика", "discount_text": "Скидка 10%", "base_price": 1500}
    assert format_service_preview(service) == "7. Стрижка — Скидка 10%"
    card = format_service_card(service)
    assert "Стрижка" in card
    assert "Скидка 10%" in card
    assert "Базовая цена: 1500" in card
