"""Testes do validador seguro do ambiente de preview."""

from __future__ import annotations

import httpx
import pytest

from scripts.validate_preview import PreviewConfig, ValidationError, validate_public

API_URL = "https://api-preview.example"
WEB_URL = "https://web-preview.example"


def _config() -> PreviewConfig:
    return PreviewConfig(
        api_url=API_URL,
        web_url=WEB_URL,
        origin=WEB_URL,
        expected_ttl=28800,
        admin_username="",
    )


def _handler(*, allow_any_origin: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{API_URL}/health":
            return httpx.Response(200, json={"status": "ok"})
        if str(request.url) == WEB_URL:
            return httpx.Response(200, text="<!doctype html>", headers={"Content-Type": "text/html"})
        if str(request.url) == f"{API_URL}/kb/list":
            return httpx.Response(401)
        if request.method == "POST" and str(request.url) == f"{API_URL}/auth/login":
            return httpx.Response(401)
        if request.method == "OPTIONS" and str(request.url) == f"{API_URL}/auth/login":
            origin = request.headers["Origin"]
            headers = {"Access-Control-Allow-Origin": origin} if allow_any_origin or origin == WEB_URL else {}
            return httpx.Response(200, headers=headers)
        return httpx.Response(404)

    return handler


def test_validate_public_accepts_restricted_cors():
    with httpx.Client(transport=httpx.MockTransport(_handler())) as client:
        results = validate_public(client, _config())

    assert "API saudável" in results
    assert "CORS restrito à origem configurada" in results


def test_validate_public_rejects_wildcard_cors():
    with httpx.Client(transport=httpx.MockTransport(_handler(allow_any_origin=True))) as client:
        with pytest.raises(ValidationError, match="origem externa"):
            validate_public(client, _config())
