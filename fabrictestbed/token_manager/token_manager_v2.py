#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple, List

import requests

try:
    import jwt  # PyJWT
    from jwt import PyJWKClient
except Exception:  # pragma: no cover
    jwt = None
    PyJWKClient = None


# ---------------------------
# Utilities & Defaults
# ---------------------------

DEFAULT_TIME_FMT = "%Y-%m-%d %H:%M:%S %z"

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def to_unix(dt: datetime) -> int:
    return int(dt.timestamp())

def from_unix(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)

def short(s: str, n: int = 8) -> str:
    return s[:n] if s else ""


# ---------------------------
# Dataclasses
# ---------------------------

@dataclass(frozen=True)
class TokenPair:
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    created_at: Optional[str] = None  # informational string, not used for auth flow

@dataclass(frozen=True)
class TokenClaims:
    sub: Optional[str] = None
    email: Optional[str] = None
    iss: Optional[str] = None
    aud: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None
    nbf: Optional[int] = None
    jti: Optional[str] = None
    # FABRIC custom claims commonly embedded (adjust as needed):
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    preferred_username: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    # Capture any extra claims:
    _raw: Optional[Dict[str, Any]] = None


# ---------------------------
# Token Manager V2
# ---------------------------

class TokenManagerV2:
    """
    Requests-based token helper with:
      * proactive auto-refresh (skew window)
      * claims extraction (optionally verified with CredMgr JWKS)
      * thread-safe updates
    """

    def __init__(
        self,
        credmgr_host: str,
        *,
        scope: str = "all",
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        http_timeout: float = 15.0,
        http_debug: bool = False,
        jwks_ttl: int = 6 * 3600,            # 6 hours
        refresh_skew_sec: int = 300,         # refresh if exp < now + 5min
        logger: Optional[logging.Logger] = None,
    ):
        """
        :param credmgr_host: e.g. 'cm.fabric-testbed.net' (NO trailing path)
        :param scope: scope for refresh calls
        :param project_id: FABRIC project UUID (optional)
        :param project_name: FABRIC project name (optional)
        :param http_timeout: requests timeout
        :param http_debug: log request/response details
        :param jwks_ttl: seconds to cache JWKS
        :param refresh_skew_sec: refresh if token expires within this window
        """
        self.base = f"https://{credmgr_host}/credmgr"
        self.scope = scope
        self.project_id = project_id
        self.project_name = project_name
        self.http_timeout = http_timeout
        self.http_debug = http_debug
        self.refresh_skew = timedelta(seconds=refresh_skew_sec)

        self._log = logger or self._default_logger()
        self._lock = threading.RLock()

        # in-memory token store
        self._pair: TokenPair = TokenPair()

        # JWKS cache
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_expire_at: float = 0.0

        if self.http_debug:
            self._log.setLevel(logging.DEBUG)

    # ------------- Public API -------------

    def set_tokens(
        self,
        *,
        id_token: Optional[str],
        refresh_token: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> None:
        """Inject tokens (e.g., coming from MCP Bearer and optional refresh)."""
        with self._lock:
            self._pair = TokenPair(id_token=id_token, refresh_token=refresh_token, created_at=created_at)
            self._log.debug("Tokens set: id=%s refresh=%s",
                            short(id_token or ""), short(refresh_token or ""))

    def ensure_valid_id_token(
        self,
        *,
        allow_refresh: bool = True,
        verify_jwt: bool = False,
    ) -> str:
        """
        Return a **valid** id_token. If near expiry and a refresh_token is present, will refresh.
        :param allow_refresh: attempt refresh if exp nearly due
        :param verify_jwt: verify signature against JWKS (credmgr /certs)
        """
        with self._lock:
            if not self._pair.id_token:
                raise ValueError("No id_token present")

            exp = self._get_exp(self._pair.id_token, verify=verify_jwt)
            if exp is None:
                # If we can't read exp, try a refresh if allowed; else return as is.
                self._log.debug("Token has no exp; allow_refresh=%s", allow_refresh)
                if allow_refresh and self._pair.refresh_token:
                    self._refresh_locked()
                return self._pair.id_token

            now = utc_now()
            exp_dt = from_unix(exp)
            if exp_dt <= now + self.refresh_skew:
                self._log.info("Token expiring soon (%s); allow_refresh=%s", exp_dt.isoformat(), allow_refresh)
                if allow_refresh and self._pair.refresh_token:
                    self._refresh_locked()
                else:
                    self._log.warning("Token near expiry and no refresh performed (no RT or allow_refresh=False).")
            return self._pair.id_token  # may be updated by refresh

    def get_claims(
        self,
        *,
        verify: bool = False,
        return_fmt: str = "object",
    ) -> TokenClaims | Dict[str, Any]:
        """
        Decode id_token and return structured claims.
        :param verify: verify with JWKS
        :param return_fmt: "object" | "dict"
        """
        with self._lock:
            if not self._pair.id_token:
                raise ValueError("No id_token present")
            claims = self._decode(self._pair.id_token, verify=verify)
            parsed = _claims_to_dc(claims)
            return asdict(parsed) if return_fmt == "dict" else parsed

    def get_user_email(self, verify: bool = False) -> Optional[str]:
        with self._lock:
            if not self._pair.id_token:
                return None
            claims = self._decode(self._pair.id_token, verify=verify)
            return claims.get("email") or claims.get("preferred_username")

    def get_project(self, verify: bool = False) -> Tuple[Optional[str], Optional[str]]:
        """
        Returns (project_id, project_name) from token claims if present.
        """
        with self._lock:
            if not self._pair.id_token:
                return None, None
            c = self._decode(self._pair.id_token, verify=verify)
            return c.get("project_id"), c.get("project_name")

    def maybe_refresh_now(self) -> bool:
        """
        Force a refresh attempt if a refresh_token is present.
        Returns True if refreshed, False if skipped.
        """
        with self._lock:
            if not self._pair.refresh_token:
                return False
            self._refresh_locked()
            return True

    # ------------- Internals -------------

    def _refresh_locked(self) -> None:
        """Perform refresh using CredMgr API (assumes lock held)."""
        assert self._pair.refresh_token, "refresh_token required to refresh"

        url = f"{self.base}/tokens/refresh"
        params = {
            "scope": self.scope,
        }
        if self.project_id:
            params["project_id"] = self.project_id
        if self.project_name:
            params["project_name"] = self.project_name

        body = {"refresh_token": self._pair.refresh_token}

        if self.http_debug:
            self._log.debug("POST %s params=%s body=%s", url, params, self._redact(body))

        resp = requests.post(url, params=params, json=body, timeout=self.http_timeout)
        if self.http_debug:
            self._log.debug("-> %s %s", resp.status_code, resp.text[:256])

        if resp.status_code != 200:
            # Try to carry any refresh token echo back (your API sometimes includes it)
            try:
                err = resp.json()
            except Exception:
                err = {"error": resp.text}
            raise RuntimeError(f"Refresh failed: {err}")

        data = resp.json()
        # Expecting fabric CM's `tokens` wrapper -> get first datum
        tokens = _unwrap_paginated_first(data)
        new_id = tokens.get("id_token")
        new_rt = tokens.get("refresh_token") or self._pair.refresh_token

        self._pair = TokenPair(
            id_token=new_id,
            refresh_token=new_rt,
            created_at=datetime.now(timezone.utc).strftime(DEFAULT_TIME_FMT),
        )
        self._log.info("Refreshed id_token (new=%s..., rt=%s...)", short(new_id or ""), short(new_rt or ""))

    def _get_exp(self, id_token: str, verify: bool) -> Optional[int]:
        """Return exp claim seconds, or None."""
        c = self._decode(id_token, verify=verify)
        exp = c.get("exp")
        try:
            return int(exp) if exp is not None else None
        except Exception:
            return None

    def _decode(self, id_token: str, verify: bool) -> Dict[str, Any]:
        """
        Decode JWT. If verify=True and PyJWT available, validate signature via JWKS (/certs).
        Otherwise do a safe base64 decode without verification.
        """
        if verify and jwt is not None and PyJWKClient is not None:
            jwks = self._jwks()
            try:
                jwk_client = PyJWKClient(jwks["jwks_uri"]) if "jwks_uri" in jwks else None
            except Exception:
                jwk_client = None

            # If /certs returns a JWKS document ({"keys":[...]})
            if jwk_client is None and "keys" in jwks:
                # Build a temporary kid->key mapping for PyJWT
                # PyJWT needs a key per token header's kid; do dynamic selection if possible.
                # For simplicity, try "options={'verify_aud': False}" and iterate keys.
                header = jwt.get_unverified_header(id_token)
                kid = header.get("kid")
                key = None
                for k in jwks.get("keys", []):
                    if k.get("kid") == kid:
                        key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(k))
                        break
                if key is None:
                    # fall back to first key
                    keys = jwks.get("keys", [])
                    if keys:
                        key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(keys[0]))
                if not key:
                    raise RuntimeError("Unable to resolve JWKS key for verification")
                return jwt.decode(id_token, key=key, algorithms=["RS256"], options={"verify_aud": False})

            if jwk_client is not None:
                signing_key = jwk_client.get_signing_key_from_jwt(id_token)
                return jwt.decode(
                    id_token,
                    signing_key.key,
                    algorithms=["RS256"],
                    options={"verify_aud": False},
                )

            # If we got here without keys, fallback to unverified decode
            self._log.warning("JWKS not usable; falling back to unverified decode")
            return _unsafe_decode(id_token)

        # Unverified decode (no external deps)
        return _unsafe_decode(id_token)

    def _jwks(self) -> Dict[str, Any]:
        """Fetch & cache CredMgr JWKS from /certs (or equivalent)."""
        now = time.time()
        if self._jwks_cache and now < self._jwks_expire_at:
            return self._jwks_cache

        url = f"{self.base}/certs"
        if self.http_debug:
            self._log.debug("GET %s", url)
        resp = requests.get(url, timeout=self.http_timeout)
        if self.http_debug:
            self._log.debug("-> %s %s", resp.status_code, resp.text[:256])
        resp.raise_for_status()
        data = resp.json()

        # normalize: if the server also advertises jwks_uri, prefer it for PyJWKClient
        if "jwks_uri" not in data:
            data["jwks_uri"] = url  # local JWKS endpoint is adequate

        self._jwks_cache = data
        self._jwks_expire_at = now + float(getattr(self, "jwks_ttl", 6 * 3600))
        return data

    # ------------- Logging -------------

    @staticmethod
    def _default_logger() -> logging.Logger:
        logger = logging.getLogger("fabric.token.v2")
        if not logger.handlers:
            h = logging.StreamHandler()
            fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
            h.setFormatter(fmt)
            logger.addHandler(h)
            logger.setLevel(logging.INFO)
        return logger

    def _redact(self, obj: Any) -> Any:
        try:
            s = json.dumps(obj)
            s = s.replace(self._pair.refresh_token or "", "***") if self._pair.refresh_token else s
            s = s.replace(self._pair.id_token or "", "***") if self._pair.id_token else s
            return json.loads(s)
        except Exception:
            return obj


# ---------------------------
# Helpers (module-level)
# ---------------------------

def _unwrap_paginated_first(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fabric CM wraps payloads (tokens -> data[]). Return first item or {}.
    """
    if not isinstance(resp_json, dict):
        return {}
    data = resp_json.get("data")
    if isinstance(data, list) and data:
        return data[0]
    return resp_json


def _unsafe_decode(jwt_token: str) -> Dict[str, Any]:
    """
    Decode JWT **without verifying signature** (portable, no deps).
    """
    try:
        parts = jwt_token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1] + "==="  # pad
        payload = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return {}


def _get(claims: Dict[str, Any], *keys: str) -> Optional[Any]:
    for k in keys:
        if k in claims and claims[k] is not None:
            return claims[k]
    return None


def _as_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime(DEFAULT_TIME_FMT) if dt else None


def _to_int(val: Any) -> Optional[int]:
    try:
        return int(val)
    except Exception:
        return None


def _claims_to_dc(claims: Dict[str, Any]) -> TokenClaims:
    return TokenClaims(
        sub=_get(claims, "sub"),
        email=_get(claims, "email", "preferred_username"),
        iss=_get(claims, "iss"),
        aud=_get(claims, "aud"),
        exp=_to_int(_get(claims, "exp")),
        iat=_to_int(_get(claims, "iat")),
        nbf=_to_int(_get(claims, "nbf")),
        jti=_get(claims, "jti"),
        project_id=_get(claims, "project_id"),
        project_name=_get(claims, "project_name"),
        preferred_username=_get(claims, "preferred_username"),
        given_name=_get(claims, "given_name"),
        family_name=_get(claims, "family_name"),
        _raw=claims or {},
    )
