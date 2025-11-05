#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2020 FABRIC Testbed
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# Author: Komal Thareja (kthare10@renci.org)

"""
Token management utilities for FABRIC clients.

This module defines :class:`TokenManager`, which manages FABRIC identity and
refresh tokens. It supports both legacy **file-based** token handling and
modern **in-memory** (MCP-friendly) workflows.

Typical usage (MCP/in-memory)::

    tm = TokenManager(
        token_location=None,
        cm_host="cm.fabric-testbed.net",
        id_token=passed_in_id_token,
        refresh_token=maybe_refresh_token,
        no_write=True,
    )
    token = tm.ensure_valid_id_token()

Typical usage (legacy/file-based)::

    tm = TokenManager(
        token_location="/path/to/tokens.json",
        cm_host="cm.fabric-testbed.net",
        scope="all",
    )
    token = tm.ensure_valid_id_token()
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Union, List, Dict, Any

from fabric_cm.credmgr.credmgr_proxy import CredmgrProxy, Status, TokenType

from fabrictestbed.slice_manager import CmStatus
from fabrictestbed.util.constants import Constants
from fabrictestbed.util.utils import Utils

class TokenManagerException(Exception):
    pass

class TokenManager:
    """
    Manage FABRIC identity and refresh tokens (file-based or in-memory).

    The manager supports two modes:

    1. **File-based (legacy)** — provide ``token_location`` path to a JSON file.
       Tokens are read/written on disk.

    2. **In-memory (MCP-friendly)** — provide ``id_token`` and optionally
       ``refresh_token``; all file I/O is skipped.

    :param token_location: Path to tokens JSON file (legacy mode). Use ``None`` for MCP mode.
    :type token_location: str or None
    :param cm_host: Credential Manager hostname (e.g., ``cm.fabric-testbed.net``)
    :type cm_host: str
    :param scope: Token scope (e.g., ``"all"`` or ``"project"``)
    :type scope: str
    :param project_id: Optional project UUID
    :type project_id: str or None
    :param project_name: Optional project name
    :type project_name: str or None
    :param user_id: Optional user UUID
    :type user_id: str or None
    :param user_email: Optional user email
    :type user_email: str or None
    :param id_token: Optional in-memory ID token (JWT)
    :type id_token: str or None
    :param refresh_token: Optional in-memory refresh token
    :type refresh_token: str or None
    :param no_write: If True, suppress file writes (for MCP usage)
    :type no_write: bool
    :param auto_refresh: (Optional) A flag indicating whether the token should be automatically refreshed
                              when it expires. Defaults to True.
    :type no_write: bool

    :raises TokenManagerException: on refresh or token handling failures
    """

    def __init__(
        self,
        *,
        token_location: Optional[str],
        cm_host: str,
        scope: str = "all",
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        id_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        no_write: bool = False,
        auto_refresh: bool = True,
    ):
        self.cm_host = cm_host
        self.scope = scope
        self.project_id = project_id
        self.project_name = project_name
        self.user_id = user_id
        self.user_email = user_email
        self.token_location = token_location
        self.no_write = no_write
        self.auto_refresh = auto_refresh
        self.cm_proxy = CredmgrProxy(credmgr_host=cm_host)
        self.tokens: Dict[str, Any] = {}

        if id_token:
            self.tokens[CredmgrProxy.ID_TOKEN] = id_token
        if refresh_token:
            self.tokens[CredmgrProxy.REFRESH_TOKEN] = refresh_token

        if not self.tokens.get(CredmgrProxy.ID_TOKEN):
            self._load_tokens(refresh=True)

        try:
            self._extract_project_and_user_info_from_token(cm_host=self.cm_host)
        except Exception as e:
            logging.debug(f"Non-fatal: could not decode id_token for project/user info: {e}")

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_id_token(self) -> Optional[str]:
        """
        Retrieve the current ID token.

        :return: The ID token string if available, otherwise ``None``.
        :rtype: str or None
        """
        return self.tokens.get(CredmgrProxy.ID_TOKEN)

    def get_refresh_token(self) -> Optional[str]:
        """
        Retrieve the current refresh token.

        :return: The refresh token string if available, otherwise ``None``.
        :rtype: str or None
        """
        return self.tokens.get(CredmgrProxy.REFRESH_TOKEN)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_tokens(self, refresh: bool = True) -> None:
        """
        Load tokens from file or environment.

        If an in-memory ``id_token`` already exists, this method is a no-op.

        :param refresh: Reserved for compatibility (currently unused)
        :type refresh: bool
        """
        if self.tokens.get(CredmgrProxy.ID_TOKEN):
            return

        if self.token_location and os.path.exists(self.token_location):
            try:
                with open(self.token_location, "r") as stream:
                    self.tokens = json.loads(stream.read()) or {}
            except Exception as e:
                logging.warning(f"Failed to read token file {self.token_location}: {e}")
                self.tokens = {}
            refresh_token = self.get_refresh_token()
        else:
            refresh_token = os.environ.get(Constants.CILOGON_REFRESH_TOKEN)
         # Renew the tokens to ensure any project_id changes are taken into account
        if refresh and self.auto_refresh and refresh_token:
            self.refresh_tokens(refresh_token=refresh_token)

    def _extract_project_and_user_info_from_token(self, cm_host: str) -> None:
        """
        Decode ``id_token`` to populate project/user attributes if missing.

        :param cm_host: Credential Manager hostname for decoding
        :type cm_host: str
        """
        if self.project_id and self.project_name and self.user_id and self.user_email:
            return

        tok = self.get_id_token()
        if not tok:
            return

        decoded_token = Utils.decode_token(cm_host=cm_host, token=tok) or {}
        self.project_id = self.project_id or decoded_token.get("project_id")
        self.project_name = self.project_name or decoded_token.get("project_name")
        self.user_id = self.user_id or decoded_token.get("uuid")
        self.user_email = self.user_email or decoded_token.get("email")

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    def id_token_issued_at(self) -> Optional[datetime]:
        """
        Return when the ID token was issued, if determinable.

        :return: Datetime of issuance or ``None`` if unavailable.
        :rtype: datetime or None
        """
        created_at = self.tokens.get("created_at")
        if created_at:
            try:
                return datetime.strptime(created_at, CredmgrProxy.TIME_FORMAT)
            except Exception:
                pass

        try:
            claims = Utils.decode_token(cm_host=self.cm_host, token=self.get_id_token()) or {}
            iat = claims.get("iat")
            if iat:
                return datetime.fromtimestamp(int(iat), timezone.utc)
        except Exception:
            pass
        return None

    def id_token_expires_at(self) -> Optional[datetime]:
        """
        Return when the ID token was issued, if determinable.

        :return: Datetime of issuance or ``None`` if unavailable.
        :rtype: datetime or None
        """
        expires_at = self.tokens.get("expires_at")
        if expires_at:
            try:
                return datetime.strptime(expires_at, CredmgrProxy.TIME_FORMAT)
            except Exception:
                pass

        try:
            claims = Utils.decode_token(cm_host=self.cm_host, token=self.get_id_token()) or {}
            exp = claims.get("exp")
            if exp:
                return datetime.fromtimestamp(int(exp), timezone.utc)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Token lifecycle
    # ------------------------------------------------------------------

    def create_token(self,
                     scope: str = "all",
                     project_id: str = None,
                     project_name: str = None,
                     file_name: str = None,
                     life_time_in_hours: int = 4,
                     comment: str = "Created via API",
                     browser_name: str = "chrome"
                     ) -> Tuple[Status, Union[dict, TokenManagerException]]:
        """
        Create token
        @param project_id: Project Id
        @param project_name: Project Name
        @param scope: scope
        @param file_name: File name
        @param life_time_in_hours: Token lifetime in hours
        @param comment: comment associated with the token
        @param browser_name: Browser name; allowed values: chrome, firefox, safari, edge
        @returns Tuple of Status, token json or Exception
        @raises Exception in case of failure
        """
        try:
            return self.cm_proxy.create(scope=scope,
                                        project_id=project_id,
                                        project_name=project_name,
                                        file_name=file_name,
                                        life_time_in_hours=life_time_in_hours,
                                        comment=comment,
                                        browser_name=browser_name)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, TokenManagerException(error_message)


    def refresh_tokens(self, *, refresh_token: str) -> Tuple[str, str]:
        """
        Refresh the tokens via Credential Manager.

        In MCP mode, tokens are updated in memory and not written to disk.

        :param refresh_token: Refresh token used to obtain a new ID token.
        :type refresh_token: str
        :return: Tuple of (new_id_token, new_refresh_token)
        :rtype: tuple(str, str)
        :raises TokenManagerException: If the refresh operation fails.
        """
        try:
            status, tokens = self.cm_proxy.refresh(
                project_id=self.project_id,
                scope=self.scope,
                refresh_token=refresh_token,
                file_name=(None if (self.no_write or not self.token_location) else self.token_location),
                project_name=self.project_name,
            )
            if status == CmStatus.OK:
                self.tokens[CredmgrProxy.ID_TOKEN] = tokens.get(CredmgrProxy.ID_TOKEN)
                self.tokens[CredmgrProxy.REFRESH_TOKEN] = tokens.get(CredmgrProxy.REFRESH_TOKEN)
                return (
                    self.tokens.get(CredmgrProxy.ID_TOKEN),
                    self.tokens.get(CredmgrProxy.REFRESH_TOKEN),
                )
            raise TokenManagerException(f"Refresh failed: {tokens}")
        except Exception as e:
            msg = Utils.extract_error_message(exception=e)
            raise TokenManagerException(msg)

    def revoke_token(
        self,
        *,
        refresh_token: str = None,
        id_token: str = None,
        token_hash: str = None,
        token_type: TokenType = TokenType.Refresh
    ) -> Tuple[Status, Union[TokenManagerException, str]]:
        """
        Revoke a token using the Credential Manager.

        :param refresh_token: Refresh token to revoke (optional)
        :type refresh_token: str or None
        :param id_token: Identity token to revoke (optional)
        :type id_token: str or None
        :param token_hash: Precomputed SHA-256 hash (optional)
        :type token_hash: str or None
        :param token_type type of the token being revoked
        :type token_type: TokenType or None
        :return: (Status, message_or_exception)
        :rtype: tuple(Status, Union[TokenManagerException, str])
        """
        try:
            if id_token is None:
                id_token = self.get_id_token()
            if token_hash is None and id_token:
                token_hash = Utils.generate_sha256(token=id_token)
            return self.cm_proxy.revoke(
                refresh_token=refresh_token,
                identity_token=id_token,
                token_hash=token_hash,
                token_type=token_type,
            )
        except Exception as e:
            msg = Utils.extract_error_message(exception=e)
            return Status.FAILURE, TokenManagerException(msg)

    def token_revoke_list(self, *, project_id: str) -> Tuple[Status, Union[TokenManagerException, List[str]]]:
        """
        Retrieve the token revoke list for a given project.

        :param project_id: Project UUID
        :type project_id: str
        :return: (Status, revoke_list_or_exception)
        :rtype: tuple(Status, Union[TokenManagerException, list[str]])
        """
        try:
            return self.cm_proxy.token_revoke_list(project_id=project_id)
        except Exception as e:
            msg = Utils.extract_error_message(exception=e)
            return Status.FAILURE, TokenManagerException(msg)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def clear_token_cache(self, *, file_name: Optional[str] = None) -> Tuple[Status, Any]:
        """
        Clear in-memory tokens and optionally remove the token file.

        :param file_name: Optional file to remove (defaults to ``self.token_location``)
        :type file_name: str or None
        """
        self.tokens = {}
        if not self.no_write:
            path = file_name or self.token_location
            status, exception = self.cm_proxy.clear_token_cache(file_name=path)
            if status == CmStatus.OK:
                return Status.OK, None
        return Status.FAILURE, f"Failed to clear token cache:"

    def ensure_valid_id_token(self) -> str:
        """
        Ensure a non-expired ID token, refreshing if possible.

        If a refresh token is present and the ID token is near expiry (within 60s),
        this method refreshes automatically.

        :return: The valid ID token.
        :rtype: str
        :raises TokenManagerException: If no token is available or refresh fails.
        """
        tok = self.get_id_token()
        if not tok:
            raise TokenManagerException("No id_token available. Provide id_token or configure token file.")
        if self.auto_refresh:
            if datetime.now(timezone.utc) >= (self.id_token_expires_at() - timedelta(minutes=30)):
                rtok = self.get_refresh_token()
                if rtok:
                    self.refresh_tokens(refresh_token=rtok)
                    return self.get_id_token()
        else:
            if datetime.now(timezone.utc) >= self.id_token_expires_at():
                raise TokenManagerException("Token expired")

        return tok
