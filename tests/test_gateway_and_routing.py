from services.backend_gateway import BackendApiError, BackendGateway
from routing import parse_code_command, parse_partner_command, parse_service_command


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text='x'):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_structured_backend_error(monkeypatch):
    def fake_request(*args, **kwargs):
        return DummyResponse(400, {"detail": {"code": "monthly_limit", "message": "Лимит"}})

    monkeypatch.setattr("services.backend_gateway.requests.request", fake_request)
    gw = BackendGateway("https://example.com", "token")
    try:
        gw.get_categories()
    except BackendApiError as e:
        assert e.code == "monthly_limit"
        assert e.message == "Лимит"


def test_gateway_adds_token_header(monkeypatch):
    holder = {}

    def fake_request(method, url, **kwargs):
        holder.update(kwargs)
        return DummyResponse(200, [], text='[]')

    monkeypatch.setattr("services.backend_gateway.requests.request", fake_request)
    gw = BackendGateway("https://example.com", "abc")
    gw.get_categories()
    assert holder["headers"]["X-Bot-Api-Token"] == "abc"


def test_routing_helpers():
    assert parse_partner_command("Партнёр 123") == 123
    assert parse_service_command("Услуга 456") == 456
    assert parse_code_command("Код 456") == 456


def test_codes_formatting_empty():
    codes = []
    formatted = "\n".join([str(c) for c in codes])
    assert formatted == ""
