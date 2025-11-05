#!/usr/bin/env python3
# MIT License
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Optional: if present, we can do GUI login to get a cookie.
try:
    from fabric_cm.credmgr.session_helper import SessionHelper  # type: ignore
    _HAS_SESSION_HELPER = True
except Exception:
    _HAS_SESSION_HELPER = False


# =========================
# DTOs
# =========================

@dataclass(slots=True)
class TokenDTO:
    token_hash: str
    created_at: str
    expires_at: str
    state: str
    created_from: Optional[str] = None
    comment: Optional[str] = None
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TokenDTO":
        return TokenDTO(
            token_hash=d.get("token_hash"),
            created_at=d.get("created_at"),
            expires_at=d.get("expires_at"),
            state=d.get("state"),
            created_from=d.get("created_from"),
            comment=d.get("comment"),
            id_token=d.get("id_token"),
            refresh_token=d.get("refresh_token"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_hash": self.token_hash,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "state": self.state,
            "created_from": self.created_from,
            "comment": self.comment,
            "id_token": self.id_token,
            "refresh_token": self.refresh_token,
        }


@dataclass(slots=True)
class DecodedTokenDTO:
    token: Dict[str, Any]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DecodedTokenDTO":
        # API returns { ..., "token": {...} }
        token = d.get("token") or {}
        return DecodedTokenDTO(token=token)

    def to_dict(self) -> Dict[str, Any]:
        return {"token": self.token}


# =========================
# Errors
# =========================

class CredMgrError(Exception):
    pass


class CredMgrValidationError(CredMgrError):
    pass


class CredMgrHTTPError(CredMgrError):
    def __init__(self, status_code: int, message: str, body_preview: str = ""):
        super().__init__(f"{status_code}: {message}\n{body_preview}")
        self.status_code = status_code
        self.body_preview = body_preview


# =========================
# Core client (merged)
# =========================

class CredmgrClient:
    """
    Single-class client that merges the HTTP layer and the higher-level token helpers.

    Features:
    - requests + retries
    - structured logging
    - optional GUI login cookie via SessionHelper (if importable)
    - DTO/dataclass conversions
    - return_fmt = "dict" | "dto" for MCP friendliness
    - on-disk token.json helpers
    """

    TIME_FORMAT = "%Y-%m-%d %H:%M:%S %z"

    def __init__(
        self,
        credmgr_host: str,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        backoff_factor: float = 0.3,
        logger: Optional[logging.Logger] = None,
        http_debug: bool = False,
        cookie_provider: Optional[Callable[[], str]] = None,  # alternative to SessionHelper
        cookie_name: str = "fabric-service",
    ):
        if not credmgr_host:
            raise CredMgrError("credmgr_host must be provided")

        if not credmgr_host.startswith("http"):
            base = f"https://{credmgr_host}"
        else:
            base = credmgr_host
        if not base.endswith("/"):
            base += "/"

        # OpenAPI shows base like .../credmgr/
        if not base.endswith("credmgr/"):
            base += "credmgr/"

        self.base_url = base
        self.timeout = timeout
        self.session = self._build_session(retries, backoff_factor)
        self.log = logger or logging.getLogger("fabric.credmgr")
        self.http_debug = http_debug
        self.cookie_provider = cookie_provider
        self.cookie_name = cookie_name
        self._cookie: Optional[str] = None  # cache between calls

    # -------------
    # Session + HTTP
    # -------------

    @staticmethod
    def _build_session(retries: int, backoff: float) -> requests.Session:
        s = requests.Session()
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=backoff,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        return s

    def _req(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Union[Dict[str, Any], List[Tuple[str, Any]]]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes]] = None,
        cookie: Optional[str] = None,
    ) -> requests.Response:
        url = self.base_url + path.lstrip("/")
        hdrs = {"Accept": "application/json"}
        if headers:
            hdrs.update(headers)

        cookies = {}
        if cookie:
            cookies[self.cookie_name] = cookie

        t0 = time.perf_counter()
        resp = self.session.request(
            method=method,
            url=url,
            headers=hdrs,
            params=params,
            json=json_body,
            data=data,
            cookies=cookies if cookies else None,
            timeout=self.timeout,
        )
        dt = (time.perf_counter() - t0) * 1000.0
        self.log.info(
            "credmgr_http_call",
            extra={
                "event": "http_call",
                "http_method": method,
                "url_path": path,
                "status_code": resp.status_code,
                "elapsed_ms": round(dt, 2),
                "resp_len": len(resp.content or b""),
            },
        )

        if not (200 <= resp.status_code < 300):
            if self.http_debug:
                self.log.debug(
                    "credmgr_http_failure_dump",
                    extra={
                        "event": "http_failure",
                        "http_method": method,
                        "url": url,
                        "status_code": resp.status_code,
                        "request_headers": hdrs,
                        "request_params": params,
                        "request_json": json_body,
                        "response_text": resp.text[:2000],
                    },
                )
            raise CredMgrHTTPError(resp.status_code, "HTTP request failed", resp.text[:2000])
        return resp

    @staticmethod
    def _json(resp: requests.Response) -> Dict[str, Any]:
        try:
            return resp.json() if resp.content else {}
        except Exception as e:
            raise CredMgrError(f"Failed to parse JSON: {e}; status={resp.status_code}, text={resp.text[:500]}")

    # -------------
    # Cookie helpers
    # -------------

    def _resolve_cookie(
        self,
        *,
        cookie: Optional[str],
        use_gui_login: bool,
        browser_name: str,
        base_ui_url: Optional[str] = None,
        wait_timeout: int = 500,
        wait_interval: int = 5,
    ) -> Optional[str]:
        """
        Resolve a cookie in priority:
        1) explicit cookie argument
        2) cached self._cookie
        3) cookie_provider() if set
        4) GUI login via SessionHelper (if available and use_gui_login=True)

        base_ui_url defaults to "<scheme>://<host>/" inferred from self.base_url when not provided.
        """
        if cookie:
            self._cookie = cookie
            return cookie
        if self._cookie:
            return self._cookie
        if self.cookie_provider:
            try:
                ck = self.cookie_provider()
                if ck:
                    self._cookie = ck
                    return ck
            except Exception as e:
                self.log.warning("cookie_provider_failed", extra={"error": str(e)})

        if use_gui_login:
            if not _HAS_SESSION_HELPER:
                raise CredMgrError("SessionHelper is not available; cannot perform GUI login.")
            # infer https://<host>/
            if not base_ui_url:
                # self.base_url like https://host/credmgr/ -> want https://host/
                parts = self.base_url.split("/credmgr/")[0]
                if not parts.endswith("/"):
                    parts += "/"
                base_ui_url = parts
            session = SessionHelper(
                url=base_ui_url,
                cookie_name=self.cookie_name,
                wait_timeout=wait_timeout,
                wait_interval=wait_interval,
            )
            ck = session.login(browser_name=browser_name)
            self._cookie = ck
            return ck

        return None

    # =========================
    # CredMgr API
    # =========================

    def version(self) -> Dict[str, Any]:
        resp = self._req("GET", "/version")
        return self._json(resp)

    def certs(self) -> Dict[str, Any]:
        resp = self._req("GET", "/certs")
        return self._json(resp)

    def create(
        self,
        *,
        scope: str = "all",
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        lifetime_hours: int = 4,
        comment: str = "Create Token via GUI",
        # cookie acquisition options:
        cookie: Optional[str] = None,
        use_gui_login: bool = False,
        browser_name: str = "chrome",
        base_ui_url: Optional[str] = None,
        wait_timeout: int = 500,
        wait_interval: int = 5,
        # output options:
        file_path: Optional[Union[str, Path]] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[TokenDTO] | List[Dict[str, Any]]:
        """
        Create token(s) using a GUI-authenticated cookie.
        Provide either `cookie` or set `use_gui_login=True` (requires SessionHelper).
        """
        if not project_id and not project_name:
            raise CredMgrValidationError("project_id or project_name must be specified")

        ck = self._resolve_cookie(
            cookie=cookie,
            use_gui_login=use_gui_login,
            browser_name=browser_name,
            base_ui_url=base_ui_url,
            wait_timeout=wait_timeout,
            wait_interval=wait_interval,
        )
        if not ck:
            raise CredMgrValidationError("No cookie available to call /tokens/create")

        params: Dict[str, Any] = {
            "scope": scope,
            "lifetime": lifetime_hours,
            "comment": comment,
        }
        if project_id:
            params["project_id"] = project_id
        if project_name:
            params["project_name"] = project_name

        resp = self._req("POST", "/tokens/create", params=params, cookie=ck)
        payload = self._json(resp)
        data = payload.get("data") or []

        if file_path:
            # save the first token (most useful) to disk preserving the familiar layout
            first = data[0] if data else {}
            self.save_file(file_path, first)

        tokens = [TokenDTO.from_dict(x) for x in data]
        return [t.to_dict() for t in tokens] if return_fmt == "dict" else tokens

    def refresh(
        self,
        *,
        refresh_token: str,
        scope: str = "all",
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        file_path: Optional[Union[str, Path]] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[TokenDTO] | List[Dict[str, Any]]:
        if not refresh_token:
            raise CredMgrValidationError("refresh_token must be provided")
        if not project_id and not project_name:
            raise CredMgrValidationError("project_id or project_name must be specified")

        params: Dict[str, Any] = {"scope": scope}
        if project_id:
            params["project_id"] = project_id
        if project_name:
            params["project_name"] = project_name

        body = {"refresh_token": refresh_token}
        resp = self._req("POST", "/tokens/refresh", params=params, json_body=body)
        payload = self._json(resp)
        data = payload.get("data") or []

        if file_path and data:
            self.save_file(file_path, data[0])

        tokens = [TokenDTO.from_dict(x) for x in data]
        return [t.to_dict() for t in tokens] if return_fmt == "dict" else tokens

    def revoke(
        self,
        *,
        id_token: str,
        token_type: Literal["refresh", "identity"],
        refresh_token: Optional[str] = None,
        token_hash: Optional[str] = None,
    ) -> None:
        """
        Revoke a refresh token or an identity token (by hash).
        """
        if token_type == "refresh" and not refresh_token:
            raise CredMgrValidationError("refresh_token is required when token_type='refresh'")
        if token_type == "identity" and not token_hash:
            raise CredMgrValidationError("token_hash is required when token_type='identity'")

        headers = {"Authorization": f"Bearer {id_token}", "Content-Type": "application/json"}
        post_body = {"type": token_type, "token": refresh_token if token_type == "refresh" else token_hash}
        resp = self._req("POST", "/tokens/revokes", headers=headers, json_body=post_body)
        _ = self._json(resp)  # no-content schema in spec

    def delete(self, *, id_token: str, token_hash: str) -> None:
        headers = {"Authorization": f"Bearer {id_token}"}
        self._req("DELETE", f"/tokens/delete/{token_hash}", headers=headers)

    def delete_all(self, *, id_token: str) -> None:
        headers = {"Authorization": f"Bearer {id_token}"}
        self._req("DELETE", "/tokens/delete", headers=headers)

    def tokens(
        self,
        *,
        id_token: str,
        project_id: Optional[str] = None,
        token_hash: Optional[str] = None,
        expires: Optional[str] = None,  # TIME_FORMAT on server side
        states: Optional[List[str]] = None,
        limit: int = 200,
        offset: int = 0,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[TokenDTO] | List[Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {id_token}"}
        params: List[Tuple[str, Any]] = [("limit", limit), ("offset", offset)]
        if token_hash:
            params.append(("token_hash", token_hash))
        if project_id:
            params.append(("project_id", project_id))
        if expires:
            params.append(("expires", expires))
        if states:
            for s in states:
                params.append(("states", s))

        resp = self._req("GET", "/tokens", headers=headers, params=params)
        payload = self._json(resp)
        data = payload.get("data") or []
        tokens = [TokenDTO.from_dict(x) for x in data]
        return [t.to_dict() for t in tokens] if return_fmt == "dict" else tokens

    def revoke_list(self, *, id_token: str, project_id: Optional[str] = None) -> List[str]:
        headers = {"Authorization": f"Bearer {id_token}"}
        params: Dict[str, Any] = {}
        if project_id:
            params["project_id"] = project_id
        resp = self._req("GET", "/tokens/revoke_list", headers=headers, params=params)
        payload = self._json(resp)
        return payload.get("data") or []

    def validate(
        self,
        *,
        id_token: str,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> DecodedTokenDTO | Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        body = {"type": "identity", "token": id_token}
        resp = self._req("POST", "/tokens/validate", headers=headers, json_body=body)
        payload = self._json(resp)
        dto = DecodedTokenDTO.from_dict(payload)
        return dto.to_dict() if return_fmt == "dict" else dto

