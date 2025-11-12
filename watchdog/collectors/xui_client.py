"""HTTP client that talks to the 3x-ui panel API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable

import httpx

from watchdog.config import XuiCredentials

LOGIN_ENDPOINT = "/login"
INBOUNDS_LIST_ENDPOINT = "/panel/api/inbounds/list"
CLIENT_TRAFFIC_ENDPOINT = "/panel/api/inbounds/getClientTraffics/{email}"
CLIENT_IP_ENDPOINT = "/panel/api/inbounds/clientIps/{email}"


class XuiError(RuntimeError):
    """Generic 3x-ui communication error."""


class XuiAuthenticationError(XuiError):
    """Raised when the credentials are rejected by the API."""


@dataclass(slots=True)
class ClientSnapshot:
    """Snapshot of a single client returned by ``/panel/api/inbounds/list``."""

    email: str
    inbound_id: int
    client_id: int
    uuid: str
    enable: bool
    total_up: int
    total_down: int
    total: int
    last_online: int
    metadata: Dict[str, Any]


class XuiClient:
    """Thin wrapper around the documented REST endpoints.

    The implementation mirrors the requests described in the public Postman
    collection published at
    https://documenter.getpostman.com/view/5146551/2sB3QCTuB6.  Only the
    endpoints required for the current milestone are implemented: login,
    inbound listing, client traffic snapshots and client IP history queries.
    """

    def __init__(self, credentials: XuiCredentials) -> None:
        self._credentials = credentials
        base_url = credentials.base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=base_url,
            timeout=credentials.request_timeout,
            follow_redirects=True,
        )
        self._authenticated = False

    # ------------------------------------------------------------------
    # Public API
    def list_clients(self) -> Iterable[ClientSnapshot]:
        """Yield :class:`ClientSnapshot` objects for every configured client."""

        payload = self._request_json("GET", INBOUNDS_LIST_ENDPOINT)
        for inbound in payload.get("obj", []) or []:
            inbound_id = inbound.get("id")
            for client in inbound.get("clientStats", []) or []:
                metadata = dict(client)
                yield ClientSnapshot(
                    email=str(client.get("email", "")),
                    inbound_id=int(client.get("inboundId", inbound_id or 0)),
                    client_id=int(client.get("id", 0)),
                    uuid=str(client.get("uuid", "")),
                    enable=bool(client.get("enable", True)),
                    total_up=int(client.get("up", 0)),
                    total_down=int(client.get("down", 0)),
                    total=int(client.get("total", 0)),
                    last_online=int(client.get("lastOnline", 0)),
                    metadata=metadata,
                )

    def pull_usage_stats(self, email: str) -> Dict[str, Any]:
        """Return the payload from ``getClientTraffics/{email}``.

        The documented response body has the shape ``{"success": bool,
        "msg": str, "obj": {...}}``.  ``obj`` contains the most recent traffic
        counters for the requested client when the lookup succeeds, or ``null``
        otherwise.
        """

        endpoint = CLIENT_TRAFFIC_ENDPOINT.format(email=email)
        return self._request_json("GET", endpoint)

    def fetch_client_ips(self, email: str) -> Dict[str, Any]:
        """Return IP history information for ``email``.

        According to the upstream documentation this is a ``POST`` request that
        returns either the string ``"No IP Record"`` or a JSON encoded list of
        connection records.
        """

        endpoint = CLIENT_IP_ENDPOINT.format(email=email)
        return self._request_json("POST", endpoint)

    def close(self) -> None:
        """Close the underlying :class:`httpx.Client`."""

        self._client.close()
        self._authenticated = False

    def __enter__(self) -> "XuiClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    def _ensure_login(self) -> None:
        if self._authenticated:
            return

        data = {
            "username": self._credentials.username,
            "password": self._credentials.password,
            "twoFactorCode": "",
        }
        response = self._client.post(LOGIN_ENDPOINT, data=data)
        self._validate_response(response)
        payload = response.json()
        if not payload.get("success"):
            raise XuiAuthenticationError(payload.get("msg") or "login failed")
        self._authenticated = True

    def _request_json(self, method: str, url: str) -> Dict[str, Any]:
        self._ensure_login()
        response = self._client.request(method, url)
        self._validate_response(response)
        payload = response.json()
        if not isinstance(payload, dict):
            raise XuiError("unexpected payload type from 3x-ui")
        return payload

    @staticmethod
    def _validate_response(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - defensive
            raise XuiError(str(exc)) from exc

