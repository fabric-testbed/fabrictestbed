#!/usr/bin/env python3
# MIT License
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from typing import Any, Dict, List, Literal, Optional, Union

from fim.user.topology import AdvertizedTopology, Topology

from fabrictestbed.external_api.credmgr_client import CredmgrClient
from fabrictestbed.external_api.orchestrator_client import OrchestratorClient, SliverDTO, SliceDTO, PoaDataDTO
from fabrictestbed.external_api.core_api import CoreApi
from fabrictestbed.fabric_manager import FabricManagerException
from fabrictestbed.topology_query_api import TopologyQueryAPI
from fabrictestbed.util.constants import Constants
from fabrictestbed.util.utils import Utils


class FabricManagerV2Exception(Exception):
    """Custom exception for FabricManagerV2-related errors."""
    pass


# =========================
# FabricManagerV2 façade
# =========================

class FabricManagerV2(TopologyQueryAPI):
    """
    One-stop façade over CredmgrClient + OrchestratorClient with integrated token management.

    Supports two token modes:
    1. **File-based (legacy)** — provide ``token_location`` path to a JSON file.
       Tokens are read/written on disk and auto-refreshed when near expiry.
    2. **In-memory (MCP-friendly)** — provide ``id_token`` and optionally
       ``refresh_token``; file I/O is skipped unless ``no_write=False``.

    All orchestrator methods can either:
    - Accept explicit ``id_token`` parameter, or
    - Use ``ensure_valid_id_token()`` when ``id_token`` is not passed

    :param credmgr_host: Credential Manager hostname (e.g., ``cm.fabric-testbed.net``).
    :param orchestrator_host: Orchestrator hostname (e.g., ``orchestrator.fabric-testbed.net``).
    :param core_api_host: Optional Core API hostname for user/project lookups.
    :param token_location: Path to tokens JSON file (file-based mode). Use ``None`` for in-memory mode.
    :param id_token: In-memory FABRIC ID token (JWT) for MCP mode.
    :param refresh_token: In-memory refresh token for MCP mode (optional).
    :param project_id: Optional project UUID for scoping token refresh.
    :param project_name: Optional project name for scoping token refresh.
    :param scope: Token scope for refresh flows (default: ``"all"``).
    :param no_write: If ``True``, never write tokens to disk (recommended for MCP).
    :param auto_refresh: If ``True``, automatically refresh tokens when near expiry (default: ``True``).
    :param logger: Optional custom logger.
    :param http_debug: Enable HTTP debug logging.
    """

    def __init__(
        self,
        *,
        credmgr_host: str,
        orchestrator_host: str,
        core_api_host: Optional[str] = None,
        token_location: Optional[str] = None,
        id_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        scope: str = "all",
        no_write: bool = False,
        auto_refresh: bool = True,
        logger: Optional[logging.Logger] = None,
        http_debug: bool = False,
    ):
        super().__init__(orchestrator_host=orchestrator_host, logger=logger, http_debug=http_debug)
        self.credmgr = CredmgrClient(credmgr_host, http_debug=http_debug, logger=self.log)
        self.orch = OrchestratorClient(orchestrator_host, http_debug=http_debug, logger=self.log)
        self.core_api_host = core_api_host

        # Token management attributes
        self.token_location = token_location
        self.no_write = no_write
        self.auto_refresh = auto_refresh
        self.scope = scope
        self.project_id = project_id
        self.project_name = project_name
        self.user_id: Optional[str] = None
        self.user_email: Optional[str] = None

        # In-memory token storage
        self._tokens: Dict[str, Any] = {}
        if id_token:
            self._tokens["id_token"] = id_token
        if refresh_token:
            self._tokens["refresh_token"] = refresh_token

        # Load tokens from file if not provided in-memory
        if not self._tokens.get("id_token"):
            self._load_tokens()

        # Extract project/user info from token
        try:
            self._extract_info_from_token()
        except Exception as e:
            self.log.debug(f"Non-fatal: could not decode id_token for project/user info: {e}")

    # ------------------------------------------------------------------
    # Token Management
    # ------------------------------------------------------------------

    def _load_tokens(self) -> None:
        """Load tokens from file or environment."""
        if self._tokens.get("id_token"):
            return

        if self.token_location and os.path.exists(self.token_location):
            try:
                self._tokens = CredmgrClient.load_file(self.token_location)
            except Exception as e:
                self.log.warning(f"Failed to read token file {self.token_location}: {e}")
                self._tokens = {}

        # Try environment variable as fallback
        refresh_token = self._tokens.get("refresh_token") or os.environ.get(Constants.CILOGON_REFRESH_TOKEN)

        # Auto-refresh on load if we have refresh token
        if self.auto_refresh and refresh_token and not self._tokens.get("id_token"):
            try:
                self.refresh_tokens(refresh_token=refresh_token)
            except Exception as e:
                self.log.warning(f"Auto-refresh on load failed: {e}")

    def _extract_info_from_token(self) -> None:
        """Decode id_token to populate project/user attributes if missing."""
        if self.project_id and self.project_name and self.user_id and self.user_email:
            return

        tok = self.get_id_token()
        if not tok:
            return

        try:
            decoded = self.credmgr.validate(id_token=tok, return_fmt="dict")
            token_info = decoded.get("token", {})
            self.project_id = self.project_id or token_info.get("project_id")
            self.project_name = self.project_name or token_info.get("project_name")
            self.user_id = self.user_id or token_info.get("uuid")
            self.user_email = self.user_email or token_info.get("email")
        except Exception as e:
            self.log.debug(f"Failed to decode token: {e}")

    def get_id_token(self) -> Optional[str]:
        """
        Retrieve the current ID token.

        :return: The ID token string if available, otherwise ``None``.
        """
        return self._tokens.get("id_token")

    def get_refresh_token(self) -> Optional[str]:
        """
        Retrieve the current refresh token.

        :return: The refresh token string if available, otherwise ``None``.
        """
        return self._tokens.get("refresh_token")

    def id_token_expires_at(self) -> Optional[datetime]:
        """
        Return when the ID token expires, if determinable.

        :return: Datetime of expiration or ``None`` if unavailable.
        """
        # Check stored expires_at first
        expires_at = self._tokens.get("expires_at")
        if expires_at:
            try:
                return datetime.strptime(expires_at, CredmgrClient.TIME_FORMAT)
            except Exception:
                pass

        # Decode from token claims
        tok = self.get_id_token()
        if tok:
            try:
                decoded = self.credmgr.validate(id_token=tok, return_fmt="dict")
                token_info = decoded.get("token", {})
                exp = token_info.get("exp")
                if exp:
                    return datetime.fromtimestamp(int(exp), timezone.utc)
            except Exception:
                pass
        return None

    def refresh_tokens(self, *, refresh_token: Optional[str] = None) -> tuple:
        """
        Refresh the tokens via Credential Manager.

        If ``no_write=False`` and ``token_location`` is set, saves refreshed tokens to file.

        :param refresh_token: Refresh token to use. If not provided, uses stored refresh token.
        :return: Tuple of (new_id_token, new_refresh_token)
        :raises FabricManagerV2Exception: If the refresh operation fails.
        """
        rtok = refresh_token or self.get_refresh_token()
        if not rtok:
            raise FabricManagerV2Exception("No refresh token available")

        if not self.project_id and not self.project_name:
            raise FabricManagerV2Exception("project_id or project_name must be set for token refresh")

        try:
            # Determine file path for saving
            file_path = None
            if not self.no_write and self.token_location:
                file_path = self.token_location

            tokens = self.credmgr.refresh(
                refresh_token=rtok,
                scope=self.scope,
                project_id=self.project_id,
                project_name=self.project_name,
                file_path=file_path,
                return_fmt="dict",
            )

            if tokens and len(tokens) > 0:
                first_token = tokens[0]
                self._tokens["id_token"] = first_token.get("id_token")
                self._tokens["refresh_token"] = first_token.get("refresh_token")
                self._tokens["expires_at"] = first_token.get("expires_at")
                self._tokens["created_at"] = first_token.get("created_at")

                return (
                    self._tokens.get("id_token"),
                    self._tokens.get("refresh_token"),
                )

            raise FabricManagerV2Exception("Refresh returned empty token list")

        except Exception as e:
            raise FabricManagerV2Exception(f"Token refresh failed: {e}")

    def ensure_valid_id_token(self, id_token: Optional[str] = None) -> str:
        """
        Ensure a non-expired ID token, refreshing if possible.

        If ``id_token`` is provided explicitly, returns it directly.
        Otherwise, checks the stored token and refreshes if near expiry (within 30 minutes).

        :param id_token: Optional explicit token to use (bypasses refresh logic).
        :return: A valid ID token.
        :raises FabricManagerV2Exception: If no token is available or refresh fails.
        """
        # If explicit token provided, use it directly
        if id_token:
            return id_token

        tok = self.get_id_token()
        if not tok:
            raise FabricManagerV2Exception(
                "No id_token available. Provide id_token parameter, set token_location, or pass tokens during init."
            )

        if self.auto_refresh:
            expires_at = self.id_token_expires_at()
            if expires_at and datetime.now(timezone.utc) >= (expires_at - timedelta(minutes=30)):
                rtok = self.get_refresh_token()
                if rtok:
                    self.log.info("Token near expiry, auto-refreshing...")
                    self.refresh_tokens(refresh_token=rtok)
                    return self.get_id_token()
                else:
                    self.log.warning("Token near expiry but no refresh token available")
        else:
            expires_at = self.id_token_expires_at()
            if expires_at and datetime.now(timezone.utc) >= expires_at:
                raise FabricManagerV2Exception("Token expired and auto_refresh is disabled")

        return tok

    def get_user_id(self) -> Optional[str]:
        """Retrieve the user ID from the token."""
        if not self.user_id and self.get_id_token():
            self._extract_info_from_token()
        return self.user_id

    def get_user_email(self) -> Optional[str]:
        """Retrieve the user email from the token."""
        if not self.user_email and self.get_id_token():
            self._extract_info_from_token()
        return self.user_email

    def get_project_name(self) -> Optional[str]:
        """Retrieve the project name from the token."""
        if not self.project_name and self.get_id_token():
            self._extract_info_from_token()
        return self.project_name

    def get_project_id(self) -> Optional[str]:
        """Retrieve the project id from the token."""
        return self.project_id

    def get_user_info(self, *, uuid: str = None, email: str = None) -> dict:
        """
        Retrieve user info by email or uuid.

        :param uuid: User's uuid.
        :type uuid: str
        :param email: User's email address.
        :type email: str
        :return: User info dict (shape per Core API).
        :rtype: dict
        :raises FabricManagerException: On Core API errors.
        """
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_id_token())
            return core_api_proxy.get_user_info(uuid=uuid, email=email)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    # -------- Token helpers (proxy) --------

    def tokens_create(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Create new FABRIC tokens.

        Proxies to CredmgrClient.create with dict return format for MCP compatibility.

        Args:
            **kwargs: Keyword arguments passed to CredmgrClient.create.

        Returns:
            List of token dictionaries with token details.
        """
        # Same signature as CredmgrV3.create; return dicts by default (MCP friendly)
        return self.credmgr.create(return_fmt="dict", **kwargs)  # type: ignore[arg-type]

    def tokens_refresh(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Refresh existing FABRIC tokens.

        Args:
            **kwargs: Keyword arguments passed to CredmgrClient.refresh.

        Returns:
            List of refreshed token dictionaries.
        """
        return self.credmgr.refresh(return_fmt="dict", **kwargs)  # type: ignore[arg-type]

    def tokens_validate(self, *, id_token: str) -> Dict[str, Any]:
        """
        Validate a FABRIC ID token.

        Args:
            id_token: The FABRIC ID token to validate.

        Returns:
            Dictionary containing validation result and token details.
        """
        return self.credmgr.validate(id_token=id_token, return_fmt="dict")  # type: ignore[return-value]

    def tokens_list(self, **kwargs) -> List[Dict[str, Any]]:
        """
        List all FABRIC tokens for the user.

        Args:
            **kwargs: Keyword arguments passed to CredmgrClient.tokens.

        Returns:
            List of token dictionaries.
        """
        return self.credmgr.tokens(return_fmt="dict", **kwargs)  # type: ignore[arg-type]

    def tokens_revoke(self, **kwargs) -> None:
        """
        Revoke a FABRIC token.

        Args:
            **kwargs: Keyword arguments passed to CredmgrClient.revoke.
        """
        return self.credmgr.revoke(**kwargs)

    def tokens_delete(self, **kwargs) -> None:
        """
        Delete a FABRIC token.

        Args:
            **kwargs: Keyword arguments passed to CredmgrClient.delete.
        """
        return self.credmgr.delete(**kwargs)

    def tokens_delete_all(self, **kwargs) -> None:
        """
        Delete all FABRIC tokens for the user.

        Args:
            **kwargs: Keyword arguments passed to CredmgrClient.delete_all.
        """
        return self.credmgr.delete_all(**kwargs)

    def tokens_revoke_list(self, **kwargs) -> List[str]:
        """
        Get list of revoked tokens.

        Args:
            **kwargs: Keyword arguments passed to CredmgrClient.revoke_list.

        Returns:
            List of revoked token identifiers.
        """
        return self.credmgr.revoke_list(**kwargs)

    # -------- Orchestrator helpers --------
    def create_slice(
        self,
        *,
        name: str,
        graph_model: str,
        ssh_keys: List[str],
        id_token: Optional[str] = None,
        lifetime: Optional[int] = None,
        lease_start_time: Optional[str] = None,
        lease_end_time: Optional[str] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[Union[Dict[str, Any], SliverDTO]]:
        """
        Create a new FABRIC slice.

        Args:
            name: Name of the slice to create.
            graph_model: Slice topology graph model (GRAPHML, JSON, etc.).
            ssh_keys: List of SSH public keys for slice access.
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
            lifetime: Optional slice lifetime in days.
            lease_start_time: Optional lease start time (UTC format).
            lease_end_time: Optional lease end time (UTC format).
            return_fmt: Return format - "dict" for dictionaries or "dto" for DTO objects.

        Returns:
            List of sliver dictionaries or DTO objects representing the created slice resources.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.create(
            token=token,
            slice_name=name,
            slice_graph=graph_model,
            ssh_keys=ssh_keys,
            lifetime=lifetime,
            lease_start_time=lease_start_time,
            lease_end_time=lease_end_time,
            return_fmt=return_fmt,
        )

    def modify_slice(
        self, *, slice_id: str, graph_model: str, id_token: Optional[str] = None, return_fmt: Literal["dict", "dto"] = "dict"
    ) -> List[Union[Dict[str, Any], SliverDTO]]:
        """
        Modify an existing FABRIC slice topology.

        Args:
            slice_id: UUID of the slice to modify.
            graph_model: Updated slice topology graph model.
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
            return_fmt: Return format - "dict" for dictionaries or "dto" for DTO objects.

        Returns:
            List of sliver dictionaries or DTO objects with modification results.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.modify(token=token, slice_id=slice_id, slice_graph=graph_model, return_fmt=return_fmt)

    def accept_modify(
        self, *, slice_id: str, id_token: Optional[str] = None, return_fmt: Literal["dict", "dto"] = "dict"
    ) -> Union[Dict[str, Any], SliceDTO]:
        """
        Accept pending slice modifications.

        Args:
            slice_id: UUID of the slice with pending modifications.
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
            return_fmt: Return format - "dict" for dictionaries or "dto" for DTO objects.

        Returns:
            Slice dictionary or DTO object with updated state.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.modify_accept(token=token, slice_id=slice_id, return_fmt=return_fmt)

    def renew_slice(self, *, slice_id: str, lease_end_time: str, id_token: Optional[str] = None) -> None:
        """
        Renew a FABRIC slice lease.

        Args:
            slice_id: UUID of the slice to renew.
            lease_end_time: New lease end time (UTC format).
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.renew(token=token, slice_id=slice_id, new_lease_end_time=lease_end_time)

    def delete_slice(self, *, slice_id: Optional[str] = None, id_token: Optional[str] = None) -> None:
        """
        Delete a FABRIC slice.

        Args:
            slice_id: Optional UUID of the slice to delete.
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.delete(token=token, slice_id=slice_id)

    def list_slices(
        self,
        *,
        id_token: Optional[str] = None,
        states: Optional[List[str]] = None,
        exclude_states: Optional[List[str]] = None,
        name: Optional[str] = None,
        search: Optional[str] = None,
        exact_match: bool = False,
        as_self: bool = True,
        limit: int = 200,
        offset: int = 0,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[Union[Dict[str, Any], SliceDTO]]:
        """
        List FABRIC slices with optional filtering.

        Args:
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
            states: Optional list of slice states to include (e.g., ["StableError", "StableOK"]). Allowed values: (Nascent, Configuring, StableOK,
                     StableError, ModifyOK, ModifyError, Closing, Dead).
            exclude_states: Optional list of slice states to exclude (e.g., for fetching active slices set exclude_states=["Closing", "Dead"]).
            name: Optional slice name filter.
            search: Optional search string for slice names.
            exact_match: If True, match slice name exactly; if False, use substring match.
            as_self: If True, list only user's own slices; if False, list all accessible slices.
            limit: Maximum number of slices to return (default: 200).
            offset: Pagination offset (default: 0).
            return_fmt: Return format - "dict" for dictionaries or "dto" for DTO objects.

        Returns:
            List of slice dictionaries or DTO objects.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.slices(
            token=token,
            includes=states,
            excludes=exclude_states,
            name=name,
            search=search,
            exact_match=exact_match,
            as_self=as_self,
            limit=limit,
            offset=offset,
            return_fmt=return_fmt,
        )

    def get_slice(
        self,
        *,
        slice_id: str,
        id_token: Optional[str] = None,
        graph_format: Literal["GRAPHML", "JSON_NODELINK", "CYTOSCAPE", "NONE"] = "GRAPHML",
        as_self: bool = True,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> Union[Dict[str, Any], SliceDTO]:
        """
        Get details of a specific FABRIC slice.

        Args:
            slice_id: UUID of the slice to retrieve.
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
            graph_format: Format for the slice topology graph (GRAPHML, JSON_NODELINK, CYTOSCAPE, or NONE).
            as_self: If True, retrieve as owner; if False, retrieve with delegated access.
            return_fmt: Return format - "dict" for dictionaries or "dto" for DTO objects.

        Returns:
            Slice dictionary or DTO object with full details.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.get_slice(token=token, slice_id=slice_id, graph_format=graph_format,
                                   as_self=as_self, return_fmt=return_fmt)

    def list_slivers(
        self, *, slice_id: str, id_token: Optional[str] = None, as_self: bool = True, return_fmt: Literal["dict", "dto"] = "dict"
    ) -> List[Union[Dict[str, Any], SliverDTO]]:
        """
        List all slivers (resource allocations) in a slice.

        Args:
            slice_id: UUID of the slice containing the slivers.
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
            as_self: If True, list as owner; if False, list with delegated access.
            return_fmt: Return format - "dict" for dictionaries or "dto" for DTO objects.

        Returns:
            List of sliver dictionaries or DTO objects.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.slivers(token=token, slice_id=slice_id, as_self=as_self, return_fmt=return_fmt)

    def get_sliver(
        self, *, slice_id: str, sliver_id: str, id_token: Optional[str] = None, as_self: bool = True, return_fmt: Literal["dict", "dto"] = "dict"
    ) -> List[Union[Dict[str, Any], SliverDTO]]:
        """
        Get details of a specific sliver.

        Args:
            slice_id: UUID of the slice containing the sliver.
            sliver_id: UUID of the sliver to retrieve.
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
            as_self: If True, retrieve as owner; if False, retrieve with delegated access.
            return_fmt: Return format - "dict" for dictionaries or "dto" for DTO objects.

        Returns:
            List containing the sliver dictionary or DTO object.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.slivers(token=token, slice_id=slice_id, sliver_id=sliver_id, as_self=as_self,
                                 return_fmt=return_fmt)

    def poa_create(
        self,
        *,
        sliver_id: str,
        operation: Literal["cpuinfo", "numainfo", "cpupin", "numatune", "reboot", "addkey", "removekey", "rescan"],
        id_token: Optional[str] = None,
        vcpu_cpu_map: Optional[List[Dict[str, str]]] = None,
        node_set: Optional[List[str]] = None,
        keys: Optional[List[Dict[str, str]]] = None,
        bdf: Optional[List[str]] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[Union[Dict[str, Any], PoaDataDTO]]:
        """
        Create a Perform Operational Action (POA) on a sliver.

        POAs allow runtime operations on deployed resources like CPU pinning,
        NUMA tuning, reboots, SSH key management, and device rescanning.

        Args:
            sliver_id: UUID of the sliver to perform the action on.
            operation: The POA operation to perform (cpuinfo, numainfo, cpupin, numatune,
                      reboot, addkey, removekey, rescan).
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
            vcpu_cpu_map: Optional list of vCPU-to-CPU mapping dictionaries for cpupin operation.
            node_set: Optional list of NUMA node identifiers for numatune operation.
            keys: Optional list of SSH key dictionaries for addkey/removekey operations.
            bdf: Optional list of Bus:Device.Function identifiers for rescan operation.
            return_fmt: Return format - "dict" for dictionaries or "dto" for DTO objects.

        Returns:
            List of POA result dictionaries or DTO objects.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.poa(
            token=token,
            sliver_id=sliver_id,
            operation=operation,
            vcpu_cpu_map=vcpu_cpu_map,
            node_set=node_set,
            keys=keys,
            bdf=bdf,
            return_fmt=return_fmt,
        )

    def poa(
        self,
        *,
        sliver_id: str,
        operation: str,
        id_token: Optional[str] = None,
        vcpu_cpu_map: Optional[List[Dict[str, str]]] = None,
        node_set: Optional[List[str]] = None,
        keys: Optional[List[Dict[str, str]]] = None,
        bdf: Optional[List[str]] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
        wait: bool = True,
        retry: int = 20,
        interval_seconds: int = 10,
    ) -> Union[List[Union[Dict[str, Any], PoaDataDTO]], str, Dict[str, Any]]:
        """
        Generic POA wrapper to invoke an operational action on a sliver.

        :param sliver_id: UUID of the sliver to act on.
        :param operation: POA operation (e.g., "reboot", "addkey", "removekey").
        :param id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        :param vcpu_cpu_map: Optional mapping for cpupin.
        :param node_set: Optional node set for numatune.
        :param keys: Optional list of key dicts for addkey/removekey (e.g., {"key": "<pub>", "comment": "..."}).
        :param bdf: Optional list of BDF identifiers for rescan.
        :param return_fmt: "dict" or "dto".
        :param wait: If True, poll until POA completes; else return submission response.
        :param retry: Max polling attempts (default 20).
        :param interval_seconds: Seconds between polls (default 10).
        :return: POA result list or final status/info if wait=True.
        """
        token = self.ensure_valid_id_token(id_token)
        submission = self.orch.poa(
            token=token,
            sliver_id=sliver_id,
            operation=operation,
            vcpu_cpu_map=vcpu_cpu_map,
            node_set=node_set,
            keys=keys,
            bdf=bdf,
            return_fmt=return_fmt,
        )
        # submission may be list of PoaDataDTO or dicts
        poa_id = None
        if isinstance(submission, list) and submission:
            first = submission[0]
            poa_id = getattr(first, "poa_id", None) or first.get("poa_id") if isinstance(first, dict) else None
        elif isinstance(submission, dict):
            poa_id = submission.get("poa_id")

        if not wait or not poa_id:
            return submission

        attempt = 0
        terminal_states = {"Success", "Failed"}
        latest = submission
        while attempt < retry:
            attempt += 1
            latest = self.orch.get_poas(
                token=token,
                poa_id=poa_id,
                limit=1,
                offset=0,
                return_fmt=return_fmt,
            )
            if isinstance(latest, list) and latest:
                entry = latest[0]
                state = getattr(entry, "state", None) or (entry.get("state") if isinstance(entry, dict) else None)
                if state in terminal_states:
                    if state == "Failed":
                        err = getattr(entry, "error", None) or (entry.get("error") if isinstance(entry, dict) else None)
                        raise ValueError(f"POA {poa_id}/{operation} failed: {err}")
                    info = getattr(entry, "info", None) or (entry.get("info") if isinstance(entry, dict) else None)
                    if isinstance(info, dict) and info.get(operation) is not None:
                        return info.get(operation)
                    return entry
            time.sleep(interval_seconds)

        return latest

    def poa_get(
        self,
        *,
        id_token: Optional[str] = None,
        sliver_id: Optional[str] = None,
        poa_id: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[Union[Dict[str, Any], PoaDataDTO]]:
        """
        Retrieve POA (Perform Operational Action) status and results.

        Args:
            id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
            sliver_id: Optional UUID of the sliver to filter POAs by.
            poa_id: Optional UUID of a specific POA to retrieve.
            limit: Maximum number of POAs to return (default: 200).
            offset: Pagination offset (default: 0).
            return_fmt: Return format - "dict" for dictionaries or "dto" for DTO objects.

        Returns:
            List of POA dictionaries or DTO objects with status and results.
        """
        token = self.ensure_valid_id_token(id_token)
        return self.orch.get_poas(
            token=token, sliver_id=sliver_id, poa_id=poa_id, limit=limit, offset=offset, return_fmt=return_fmt
        )

    # -------- Storage helpers (Core API) --------
    def list_storage(
        self, *, id_token: Optional[str] = None, offset: int = 0, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        List all storage volumes.

        :param id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        :param offset: Pagination offset (default: 0).
        :param limit: Maximum number of records to fetch (default: 200).
        :return: List of storage volume dictionaries.
        """
        if not self.core_api_host:
            raise ValueError("core_api_host must be provided during initialization to use storage methods")
        token = self.ensure_valid_id_token(id_token)
        core_api = CoreApi(core_api_host=self.core_api_host, token=token)
        return core_api.list_storage(offset=offset, limit=limit)

    def get_storage(self, *, uuid: str, id_token: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get a specific storage volume by UUID.

        :param uuid: Storage volume UUID.
        :param id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        :return: Storage volume details.
        """
        if not self.core_api_host:
            raise ValueError("core_api_host must be provided during initialization to use storage methods")
        token = self.ensure_valid_id_token(id_token)
        core_api = CoreApi(core_api_host=self.core_api_host, token=token)
        return core_api.get_storage(uuid=uuid)

    # -------- Project helpers (Core API) --------
    def get_project_info(
        self,
        *,
        id_token: Optional[str] = None,
        project_name: str = "all",
        project_id: str = "all",
        uuid: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve project info for the current user (or specified uuid) via Core API.

        :param id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        :param project_name: Project name filter (default "all").
        :param project_id: Project id filter (default "all").
        :param uuid: Optional user UUID; Core API infers current user if omitted.
        :return: List of matching project records.
        """
        if not project_name and not project_id:
            raise ValueError("project_name or project_id must be provided")
        if not self.core_api_host:
            raise ValueError("core_api_host must be provided during initialization to use project methods")
        token = self.ensure_valid_id_token(id_token)
        core_api = CoreApi(core_api_host=self.core_api_host, token=token)
        return core_api.get_user_projects(uuid=uuid, project_name=project_name, project_id=project_id)

    def list_project_users(
        self,
        *,
        project_uuid: str,
        id_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List users in a project (via Core API).

        :param project_uuid: Project UUID to inspect.
        :param id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        :return: List of user records with roles.
        """
        if not project_uuid:
            raise ValueError("project_uuid is required")
        if not self.core_api_host:
            raise ValueError("core_api_host must be provided during initialization to use project methods")

        token = self.ensure_valid_id_token(id_token)
        core_api = CoreApi(core_api_host=self.core_api_host, token=token)
        return core_api.list_project_users(project_uuid=project_uuid)

    def get_user_keys(
        self,
        *,
        user_uuid: str,
        id_token: Optional[str] = None,
        key_type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch SSH/public keys for a specific user (person_uuid).

        :param user_uuid: User UUID (person_uuid).
        :param id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        :param key_type_filter: Optional key type filter (e.g., "sliver", "bastion").
        :return: List of key records.
        """
        if not self.core_api_host:
            raise ValueError("core_api_host must be provided during initialization to use project methods")

        token = self.ensure_valid_id_token(id_token)
        core_api = CoreApi(core_api_host=self.core_api_host, token=token)
        keys = core_api.get_ssh_keys(uuid=user_uuid)

        if not key_type_filter:
            return keys

        def _kt(k: Dict[str, Any]) -> str:
            return str(
                k.get("keytype")
                or k.get("fabric_key_type")
                or k.get("fabric_keytype")
                or k.get("key_type")
                or ""
            ).lower()

        return [k for k in keys if _kt(k) == key_type_filter.lower()]

    def os_reboot(
        self,
        *,
        sliver_id: str,
        id_token: Optional[str] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[Union[Dict[str, Any], PoaDataDTO]]:
        """
        Issue a POA reboot on a sliver (NodeSliver only).

        :param sliver_id: Sliver UUID to reboot (NodeSliver only).
        :param id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        :param return_fmt: Return format - "dict" or "dto".
        :return: POA results.
        """
        return self.poa(
            id_token=id_token,
            sliver_id=sliver_id,
            operation="reboot",
            return_fmt=return_fmt,
        )

    def add_public_key(
        self,
        *,
        sliver_id: str,
        id_token: Optional[str] = None,
        sliver_key_name: Optional[str] = None,
        email: Optional[str] = None,
        sliver_public_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Add a public key to a sliver via POA addkey (NodeSliver only).

        :param sliver_id: Sliver UUID to act on (NodeSliver only).
        :param id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        :param sliver_key_name: Sliver key comment/name (portal) to fetch from Core API.
        :param email: Optional email for fetching another user's key by name.
        :param sliver_public_key: Raw public key string to add (if provided, overrides key lookup). MUST be "{ssh_key_type} {public_key}".
        :return: POA results from orchestrator.
        """
        if not sliver_key_name and not sliver_public_key:
            raise ValueError("Either sliver_key_name or sliver_public_key must be provided")

        token = self.ensure_valid_id_token(id_token)
        key_material = sliver_public_key
        if key_material and " " not in key_material.strip():
            raise ValueError(
                "sliver_public_key must include key type and key material, e.g., 'ecdsa-sha2-nistp256 AAAA...=='"
            )
        if not key_material and sliver_key_name:
            core_api = CoreApi(core_api_host=self.core_api_host, token=token)
            key_list = core_api.get_ssh_keys(email=email)
            for item in key_list or []:
                if sliver_key_name == item.get("comment"):
                    key_material = f"{item.get('ssh_key_type')} {item.get('public_key')}"
                    break
            if not key_material:
                raise ValueError(f"Sliver key '{sliver_key_name}' not found")

        if not key_material:
            raise ValueError("Key must be provided")

        key_comment = "addkey-by-api"
        if sliver_key_name or email:
            key_comment = f"{key_comment}:{sliver_key_name or ''}:{email or ''}"
        keys = [{"key": key_material, "comment": key_comment}]

        return self.poa(
            id_token=token,
            sliver_id=sliver_id,
            operation="addkey",
            keys=keys,
        )

    def remove_public_key(
        self,
        *,
        sliver_id: str,
        id_token: Optional[str] = None,
        sliver_key_name: Optional[str] = None,
        email: Optional[str] = None,
        sliver_public_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Remove a public key from a sliver via POA removekey (NodeSliver only).

        :param sliver_id: Sliver UUID to act on (NodeSliver only).
        :param id_token: Optional FABRIC ID token. If not provided, uses stored/auto-refreshed token.
        :param sliver_key_name: Sliver key comment/name (portal) to fetch from Core API.
        :param email: Optional email for fetching another user's key by name.
        :param sliver_public_key: Raw public key string to remove (if provided, overrides key lookup). MUST be "{ssh_key_type} {public_key}".
        :return: POA results from orchestrator.
        """
        if not sliver_key_name and not sliver_public_key:
            raise ValueError("Either sliver_key_name or sliver_public_key must be provided")

        token = self.ensure_valid_id_token(id_token)
        key_material = sliver_public_key
        if key_material and " " not in key_material.strip():
            raise ValueError(
                "sliver_public_key must include key type and key material, e.g., 'ecdsa-sha2-nistp256 AAAA...=='"
            )
        if not key_material and sliver_key_name:
            core_api = CoreApi(core_api_host=self.core_api_host, token=token)
            key_list = core_api.get_ssh_keys(email=email)
            for item in key_list or []:
                if sliver_key_name == item.get("comment"):
                    key_material = f"{item.get('ssh_key_type')} {item.get('public_key')}"
                    break
            if not key_material:
                raise ValueError(f"Sliver key '{sliver_key_name}' not found")

        if not key_material:
            raise ValueError("Key must be provided")

        key_comment = "removekey-by-api"
        if sliver_key_name or email:
            key_comment = f"{key_comment}:{sliver_key_name or ''}:{email or ''}"
        keys = [{"key": key_material, "comment": key_comment}]

        return self.poa(
            id_token=token,
            sliver_id=sliver_id,
            operation="removekey",
            keys=keys,
        )



if __name__ == "__main__":
    id_token = ""
    mgr = FabricManagerV2(credmgr_host="cm.fabric-testbed.net",
                          orchestrator_host="orchestrator.fabric-testbed.net",)

    start = time.perf_counter()
    sites = mgr.query_sites(id_token=id_token)
    print(json.dumps(sites, indent=2))
    print("Query sites time:", time.perf_counter() - start)


    start = time.perf_counter()
    hosts = mgr.query_hosts(id_token=id_token)
    print(json.dumps(hosts, indent=2))
    print("Query hosts time:", time.perf_counter() - start)

    start = time.perf_counter()
    fps = mgr.query_facility_ports(id_token=id_token)
    print(json.dumps(fps, indent=2))
    print("Query Facility Ports time:", time.perf_counter() - start)

    start = time.perf_counter()
    fps = mgr.query_links(id_token=id_token)
    print(json.dumps(fps, indent=2))
    print("Query Links time:", time.perf_counter() - start)
