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
# Author Komal Thareja (kthare10@renci.org)

"""
User-facing Slice Manager wrapper for FABRIC Orchestrator.

This module provides :class:`SliceManager`, a convenience facade over
:class:`fabrictestbed.slice_manager.OrchestratorProxy` that:

- Accepts **in-memory tokens** (``id_token``/``refresh_token``) for MCP-based workflows.
- Preserves legacy file-based operation if a token file path is provided.
- Exposes high-level methods for slice CRUD, listing, renewal, POA, etc.

It derives from :class:`TokenManager` (your updated in-memory/file dual-mode implementation)
and consistently uses ``ensure_valid_id_token()`` to obtain a usable bearer token.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import os
from typing import Tuple, Union, List, Optional, Dict

from fabrictestbed.slice_editor import ExperimentTopology, AdvertisedTopology, GraphFormat
from fabrictestbed.slice_manager import OrchestratorProxy, Status, SliceState
from fabrictestbed.slice_manager import Slice, Sliver, PoaData

from fabrictestbed.util.constants import Constants
from fabrictestbed.util.utils import Utils

from fabrictestbed.token_manager.token_manager import TokenManager


class SliceManagerException(Exception):
    """Slice Manager raised error."""
    pass


class SliceManager(TokenManager):
    """
    Implements the user-facing Control Framework API interface for slice operations.

    This class delegates to :class:`fabrictestbed.slice_manager.OrchestratorProxy`
    while handling bearer token management via :class:`TokenManager`.

    :param cm_host: Credential Manager host used by :class:`TokenManager`.
    :type cm_host: str or None
    :param oc_host: Orchestrator hostname (e.g., ``orchestrator.fabric-testbed.net``).
                    If ``None``, reads from ``FABRIC_ORCHESTRATOR_HOST`` env var.
    :type oc_host: str or None
    :param token_location: Path to a token JSON file (legacy mode). Use ``None`` for MCP (in-memory) mode.
    :type token_location: str or None
    :param project_id: Optional project UUID to scope certain operations.
    :type project_id: str or None
    :param project_name: Optional project name to scope certain operations.
    :type project_name: str or None
    :param scope: Token scope for CredMgr refresh flows (default: ``"all"``).
    :type scope: str
    :param id_token: In-memory FABRIC ID token (JWT) for MCP mode.
    :type id_token: str or None
    :param refresh_token: In-memory refresh token for MCP mode (optional).
    :type refresh_token: str or None
    :param no_write: If ``True``, never write tokens to disk (recommended for MCP).
    :type no_write: bool

    :raises SliceManagerException: If required parameters are missing/invalid.
    """

    def __init__(
        self,
        *,
        cm_host: Optional[str] = None,
        oc_host: Optional[str] = None,
        token_location: Optional[str] = None,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        scope: str = "all",
        id_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        no_write: bool = False,
    ):
        super().__init__(
            token_location=token_location,
            cm_host=cm_host,
            scope=scope,
            project_id=project_id,
            project_name=project_name,
            id_token=id_token,
            refresh_token=refresh_token,
            no_write=no_write,
        )

        if oc_host is None:
            oc_host = os.environ.get(Constants.FABRIC_ORCHESTRATOR_HOST)

        if not oc_host:
            raise SliceManagerException(f"Invalid initialization parameters: oc_host={oc_host!r}")

        self.oc_proxy = OrchestratorProxy(orchestrator_host=oc_host)

    # -------------------------------------------------------------------------
    # Slice CRUD
    # -------------------------------------------------------------------------

    def create(
        self,
        *,
        slice_name: str,
        ssh_key: Union[str, List[str]],
        topology: ExperimentTopology = None,
        slice_graph: str = None,
        lease_start_time: str = None,
        lease_end_time: str = None,
        lifetime: int = 24,
    ) -> Tuple[Status, Union[SliceManagerException, List[Sliver]]]:
        """
        Create a slice.

        :param slice_name: Desired slice name.
        :type slice_name: str
        :param ssh_key: SSH public key (string) or list of keys to inject.
        :type ssh_key: str or list[str]
        :param topology: Experiment topology model (optional).
        :type topology: ExperimentTopology or None
        :param slice_graph: Topology as a graph string (optional).
        :type slice_graph: str or None
        :param lease_start_time: ISO8601 lease start time (optional).
        :type lease_start_time: str or None
        :param lease_end_time: ISO8601 lease end time (optional).
        :type lease_end_time: str or None
        :param lifetime: Desired slice lifetime in hours (default: ``24``).
        :type lifetime: int
        :return: ``(Status, Sliver list)`` on success, or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, list[Sliver]])
        """
        if not slice_name or not isinstance(slice_name, str) or ssh_key is None:
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_name or ssh_key")

        if topology is not None and not isinstance(topology, ExperimentTopology):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - topology")

        if slice_graph is not None and not isinstance(slice_graph, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_graph")

        if lease_end_time is not None and not isinstance(lease_end_time, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - lease_end_time")

        try:
            return self.oc_proxy.create(
                token=self.ensure_valid_id_token(),
                slice_name=slice_name,
                ssh_key=ssh_key,
                topology=topology,
                slice_graph=slice_graph,
                lease_end_time=lease_end_time,
                lease_start_time=lease_start_time,
                lifetime=lifetime,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def modify(
        self,
        *,
        slice_id: str,
        topology: ExperimentTopology = None,
        slice_graph: str = None,
    ) -> Tuple[Status, Union[SliceManagerException, List[Sliver]]]:
        """
        Modify an existing slice.

        :param slice_id: Target slice UUID.
        :type slice_id: str
        :param topology: Updated experiment topology (optional).
        :type topology: ExperimentTopology or None
        :param slice_graph: Updated graph string (optional).
        :type slice_graph: str or None
        :return: ``(Status, Sliver list)`` on success, or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, list[Sliver]])
        """
        if not slice_id or not isinstance(slice_id, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_id")

        if topology is not None and not isinstance(topology, ExperimentTopology):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - topology")

        if slice_graph is not None and not isinstance(slice_graph, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid argument - slice_graph")

        try:
            return self.oc_proxy.modify(
                token=self.ensure_valid_id_token(),
                slice_id=slice_id,
                topology=topology,
                slice_graph=slice_graph,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def modify_accept(self, *, slice_id: str) -> Tuple[Status, Union[SliceManagerException, ExperimentTopology]]:
        """
        Accept a pending slice modification (if orchestrator requires explicit accept).

        :param slice_id: Target slice UUID.
        :type slice_id: str
        :return: ``(Status, ExperimentTopology)`` on success, or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, ExperimentTopology])
        """
        if not slice_id or not isinstance(slice_id, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_id")

        try:
            return self.oc_proxy.modify_accept(
                token=self.ensure_valid_id_token(),
                slice_id=slice_id,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def delete(self, *, slice_id: str = None) -> Tuple[Status, Union[SliceManagerException, Exception, str]]:
        """
        Delete a slice.

        :param slice_id: Slice UUID to delete. If not specified, all slices will be deleted.
        :type slice_id: str
        :return: ``(Status, message)`` on success, or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, str])
        """
        if slice_id and not isinstance(slice_id, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_id")

        try:
            return self.oc_proxy.delete(
                token=self.ensure_valid_id_token(),
                slice_id=slice_id,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    # -------------------------------------------------------------------------
    # Listings & Topology
    # -------------------------------------------------------------------------

    def slices(
        self,
        *,
        includes: List[SliceState] = None,
        excludes: List[SliceState] = None,
        name: str = None,
        limit: int = 50,
        offset: int = 0,
        slice_id: str = None,
        as_self: bool = True,
        graph_format: str = str(GraphFormat.GRAPHML),
    ) -> Tuple[Status, Union[SliceManagerException, List[Slice]]]:
        """
        List slices with optional filters.

        :param includes: Slice states to include.
        :type includes: list[SliceState] or None
        :param excludes: Slice states to exclude.
        :type excludes: list[SliceState] or None
        :param name: Name filter.
        :type name: str or None
        :param limit: Max number of records (default: ``50``).
        :type limit: int
        :param offset: Offset for pagination (default: ``0``).
        :type offset: int
        :param slice_id: Filter by specific slice UUID.
        :type slice_id: str or None
        :param as_self: If ``True``, query as current user.
        :type as_self: bool
        :param graph_format: Format for any inlined graph data (default: ``GRAPHML``).
        :type graph_format: GraphFormat
        :return: ``(Status, Slice list)`` or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, list[Slice]])
        """
        try:
            return self.oc_proxy.slices(
                token=self.ensure_valid_id_token(),
                includes=includes,
                excludes=excludes,
                name=name,
                limit=limit,
                offset=offset,
                slice_id=slice_id,
                as_self=as_self,
                graph_format=graph_format,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def get_slice_topology(self, *, slice_id: str,
                           graph_format: GraphFormat = GraphFormat.GRAPHML,
                           as_self: bool = True
                           ) -> Tuple[Status, Union[SliceManagerException, ExperimentTopology]]:
        """
        Get the experiment topology for a slice.

        :param slice_id: Target slice UUID.
        :type slice_id: str
        :param as_self: If ``True``, query as current user.
        :type as_self: bool
        :param graph_format: Format for any inlined graph data (default: ``GRAPHML``).
        :type graph_format: GraphFormat
        :return: ``(Status, ExperimentTopology)`` or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, ExperimentTopology])
        """
        if not slice_id or not isinstance(slice_id, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_id")

        try:
            return self.oc_proxy.get_slice(
                token=self.ensure_valid_id_token(),
                slice_id=slice_id,
                graph_format=graph_format,
                as_self=as_self,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def slivers(
        self,
        *,
        slice_object: Slice,
        as_self: bool = True,
    ) -> Tuple[Status, Union[SliceManagerException, List[Sliver]]]:
        """
        List slivers in a given slice.

        :param slice_object: Slice object to enumerate slivers from.
        :type slice_object: Slice
        :param as_self: If ``True``, query as current user.
        :type as_self: bool
        :return: ``(Status, Sliver list)`` or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, list[Sliver]])
        """
        if slice_object is None or not isinstance(slice_object, Slice):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid argument - slice_object")

        try:
            return self.oc_proxy.slivers(
                token=self.ensure_valid_id_token(),
                slice_id=slice_object.slice_id,
                as_self=as_self,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def resources(self, *,
                  level: int = 1,
                  force_refresh: bool = False,
                  start: datetime = None,
                  end: datetime = None,
                  includes: List[str] = None,
                  excludes: List[str] = None
                  ) -> Tuple[Status, Union[SliceManagerException, AdvertisedTopology]]:
        """
        Get resources
        @param level: level
        @param force_refresh: force_refresh
        @param start: start time
        @param end: end time
        @param includes: list of sites to include
        @param excludes: list of sites to exclude
        @return Tuple containing Status and Exception/Json containing Resources
        """
        try:
            return self.oc_proxy.resources(
                token=self.ensure_valid_id_token(),
                level=level,
                force_refresh=force_refresh,
                start=start,
                end=end,
                includes=includes,
                excludes=excludes,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def renew(
        self,
        *,
        slice_id: str,
        lease_end_time: str = None,
        lifetime: Optional[int] = None,
    ) -> Tuple[Status, Union[SliceManagerException, List[Sliver]]]:
        """
        Renew a slice.

        :param slice_id: Target slice UUID.
        :type slice_id: str
        :param lease_end_time: New lease end time (ISO8601). Mutually compatible with ``lifetime`` if supported.
        :type lease_end_time: str or None
        :param lifetime: New lifetime in hours (optional).
        :type lifetime: int or None
        :return: ``(Status, Sliver list)`` or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, list[Sliver]])
        """
        if not slice_id or not isinstance(slice_id, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_id")

        if lifetime:
            new_end = datetime.now(timezone.utc) + timedelta(hours=lifetime)
            lease_end_time = new_end.strftime("%Y-%m-%d %H:%M:%S %z")

        if lease_end_time is not None and not isinstance(lease_end_time, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - lease_end_time")

        try:
            return self.oc_proxy.renew(
                token=self.ensure_valid_id_token(),
                slice_id=slice_id,
                new_lease_end_time=lease_end_time,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def poa(self, *,
            sliver_id: str,
            operation: str,
            vcpu_cpu_map: List[Dict[str, str]] = None,
            node_set: List[str] = None,
            keys: List[Dict[str, str]] = None,
            bdf: List[Dict[str, str]] = None
            ) -> Tuple[Status, Union[SliceManagerException, List[PoaData]]]:
        """
        Trigger a POA (Perform Operational Action) on a sliver.

        :param sliver_id: Target sliver UUID.
        :type sliver_id: str
        :param operation: POA action (e.g., ``"reboot"``, ``"poa_execute"``, etc.).
        :type operation: str
        :param vcpu_cpu_map: Optional CPU Mapping.
        :type vcpu_cpu_map: dict or None
        :param node_set: Optional subset of node names to target (if supported).
        :type node_set: list[str] or None
        :param keys: List of ssh keys.
        :type keys: list[str] or None
        :param bdf: List of pci ids.
        :type bdf: list[str] or None
        :return: ``(Status, PoaData)`` or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, PoaData])
        """
        if not sliver_id or not isinstance(sliver_id, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - sliver_id")

        if not operation or not isinstance(operation, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - operation")

        try:
            return self.oc_proxy.poa(
                token=self.ensure_valid_id_token(),
                sliver_id=sliver_id,
                operation=operation,
                vcpu_cpu_map=vcpu_cpu_map,
                node_set=node_set,
                keys=keys,
                bdf=bdf,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def get_poas(
        self,
        *,
        sliver_id: Optional[str] = None,
        poa_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[Status, Union[SliceManagerException, List[PoaData]]]:
        """
        Fetch POA records.

        :param sliver_id: Optional sliver UUID filter.
        :type sliver_id: str or None
        :param poa_id: Optional specific POA UUID filter.
        :type poa_id: str or None
        :param limit: Max number of records (default: ``50``).
        :type limit: int
        :param offset: Offset for pagination (default: ``0``).
        :type offset: int
        :return: ``(Status, PoaData list)`` or ``(Status.FAILURE, SliceManagerException)``.
        :rtype: tuple(Status, Union[SliceManagerException, list[PoaData]])
        """
        try:
            return self.oc_proxy.get_poas(
                token=self.ensure_valid_id_token(),
                limit=limit,
                offset=offset,
                sliver_id=sliver_id,
                poa_id=poa_id,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)
