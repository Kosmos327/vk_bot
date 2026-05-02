from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests


class BackendApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass
class BackendGateway:
    base_url: str
    bot_api_token: str
    timeout: int = 10

    def _headers(self) -> dict[str, str]:
        return {"X-Bot-Api-Token": self.bot_api_token}

    def _request(self, method: str, path: str, *, params: Optional[dict[str, Any]] = None, json: Optional[dict[str, Any]] = None) -> Any:
        clean_path = "/" + path.lstrip("/")
        url = f"{self.base_url.rstrip('/')}{clean_path}"
        try:
            response = requests.request(method, url, params=params, json=json, headers=self._headers(), timeout=self.timeout)
        except requests.RequestException:
            raise BackendApiError("backend_unavailable", "Сервис временно недоступен. Попробуйте позже.", 503)

        if response.status_code >= 400:
            code = "backend_error"
            message = "Не удалось обработать запрос. Попробуйте позже."
            try:
                payload = response.json()
                detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
                if isinstance(detail, dict):
                    code = detail.get("code", code)
                    message = detail.get("message", message)
                elif isinstance(detail, str) and detail.strip():
                    message = detail.strip()
            except ValueError:
                pass
            raise BackendApiError(code, message, response.status_code)

        if response.status_code == 204 or not response.text:
            return {}
        return response.json()

    def auth_vk_user(self, vk_user_id: int, first_name: str | None = None, last_name: str | None = None, screen_name: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/v1/vk/auth", json={"vk_user_id": vk_user_id, "first_name": first_name, "last_name": last_name, "screen_name": screen_name})

    def get_subscription(self, vk_user_id: int) -> dict[str, Any]:
        return self._request("GET", "/api/v1/vk/subscription", params={"vk_user_id": vk_user_id})

    def get_categories(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/vk/catalog/categories")

    def get_partners(self, category: str | None = None, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        params = {"limit": limit, "offset": offset}
        if category:
            params["category"] = category
        return self._request("GET", "/api/v1/vk/catalog/partners", params=params)

    def get_partner(self, partner_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/vk/partners/{partner_id}")

    def get_partner_services(self, partner_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/v1/vk/partners/{partner_id}/services")

    def request_discount_code(self, vk_user_id: int, partner_id: int, partner_service_id: int) -> dict[str, Any]:
        return self._request("POST", "/api/v1/vk/discount-codes/request", json={"vk_user_id": vk_user_id, "partner_id": partner_id, "partner_service_id": partner_service_id})

    def get_my_codes(self, vk_user_id: int, limit: int = 20, offset: int = 0, status: str | None = None) -> list[dict[str, Any]]:
        params = {"vk_user_id": vk_user_id, "limit": limit, "offset": offset}
        if status:
            params["status"] = status
        return self._request("GET", "/api/v1/vk/my-codes", params=params)

    def create_payment_request(self, vk_user_id: int) -> dict[str, Any]:
        return self._request("POST", "/api/v1/vk/payment-request", json={"vk_user_id": vk_user_id})

    def mark_payment_paid(self, vk_user_id: int, payment_request_id: int | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/v1/vk/payment-request/mark-paid", json={"vk_user_id": vk_user_id, "payment_request_id": payment_request_id})

    def attach_payment_receipt(self, vk_user_id: int, file_url: str, payment_request_id: int | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/v1/vk/payment-request/receipt", json={"vk_user_id": vk_user_id, "file_url": file_url, "payment_request_id": payment_request_id})


    def check_catalog_health(self) -> dict[str, Any]:
        self._request("GET", "/api/v1/vk/catalog/categories")
        return {"ok": True, "status": "ok"}

    def get_latest_payment_request(self, vk_user_id: int) -> dict[str, Any]:
        return self._request("GET", "/api/v1/vk/payment-request/latest", params={"vk_user_id": vk_user_id})
