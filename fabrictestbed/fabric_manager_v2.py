#!/usr/bin/env python3
# MIT License
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

import logging

from typing import Any, Dict, List, Literal, Optional, Union

from fim.user.topology import AdvertizedTopology, Topology

from fabrictestbed.external_api.credmgr_client import CredmgrClient
from fabrictestbed.external_api.orchestrator_client import OrchestratorClient, SliverDTO, SliceDTO, PoaDataDTO
from fabrictestbed.topology_query_api import TopologyQueryAPI

# =========================
# FabricManagerV2 façade
# =========================

class FabricManagerV2(TopologyQueryAPI):
    """
    One-stop façade over CredmgrClient + OrchestratorClient.

    - All methods accept `return_fmt="dict"|"dto"`.
    - For orchestrator calls, pass `id_token`.
    - Token helpers available via `credmgr`.
    """

    def __init__(
        self,
        *,
        credmgr_host: str,
        orchestrator_host: str,
        logger: Optional[logging.Logger] = None,
        http_debug: bool = False,
    ):
        super().__init__(orchestrator_host=orchestrator_host, logger=logger, http_debug=http_debug)
        self.credmgr = CredmgrClient(credmgr_host, http_debug=http_debug, logger=self.log)
        self.orch = OrchestratorClient(orchestrator_host, http_debug=http_debug, logger=self.log)

    # -------- Token helpers (proxy) --------

    def tokens_create(self, **kwargs) -> List[Dict[str, Any]]:
        # Same signature as CredmgrV3.create; return dicts by default (MCP friendly)
        return self.credmgr.create(return_fmt="dict", **kwargs)  # type: ignore[arg-type]

    def tokens_refresh(self, **kwargs) -> List[Dict[str, Any]]:
        return self.credmgr.refresh(return_fmt="dict", **kwargs)  # type: ignore[arg-type]

    def tokens_validate(self, *, id_token: str) -> Dict[str, Any]:
        return self.credmgr.validate(id_token=id_token, return_fmt="dict")  # type: ignore[return-value]

    def tokens_list(self, **kwargs) -> List[Dict[str, Any]]:
        return self.credmgr.tokens(return_fmt="dict", **kwargs)  # type: ignore[arg-type]

    def tokens_revoke(self, **kwargs) -> None:
        return self.credmgr.revoke(**kwargs)

    def tokens_delete(self, **kwargs) -> None:
        return self.credmgr.delete(**kwargs)

    def tokens_delete_all(self, **kwargs) -> None:
        return self.credmgr.delete_all(**kwargs)

    def tokens_revoke_list(self, **kwargs) -> List[str]:
        return self.credmgr.revoke_list(**kwargs)

    # -------- Orchestrator helpers --------
    def create_slice(
        self,
        *,
        id_token: str,
        name: str,
        graph_model: str,
        ssh_keys: List[str],
        lifetime: Optional[int] = None,
        lease_start_time: Optional[str] = None,
        lease_end_time: Optional[str] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[Union[Dict[str, Any], SliverDTO]]:
        return self.orch.create(
            token=id_token,
            slice_name=name,
            slice_graph=graph_model,
            ssh_keys=ssh_keys,
            lifetime=lifetime,
            lease_start_time=lease_start_time,
            lease_end_time=lease_end_time,
            return_fmt=return_fmt,
        )

    def modify_slice(
        self, *, id_token: str, slice_id: str, graph_model: str, return_fmt: Literal["dict", "dto"] = "dict"
    ) -> List[Union[Dict[str, Any], SliverDTO]]:
        return self.orch.modify(token=id_token, slice_id=slice_id, slice_graph=graph_model, return_fmt=return_fmt)

    def accept_modify(
        self, *, id_token: str, slice_id: str, return_fmt: Literal["dict", "dto"] = "dict"
    ) -> Union[Dict[str, Any], SliceDTO]:
        return self.orch.modify_accept(token=id_token, slice_id=slice_id, return_fmt=return_fmt)

    def renew_slice(self, *, id_token: str, slice_id: str, lease_end_time: str) -> None:
        return self.orch.renew(token=id_token, slice_id=slice_id, new_lease_end_time=lease_end_time)

    def delete_slice(self, *, id_token: str, slice_id: Optional[str] = None) -> None:
        return self.orch.delete(token=id_token, slice_id=slice_id)

    def list_slices(
        self,
        *,
        id_token: str,
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
        return self.orch.slices(
            token=id_token,
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
        id_token: str,
        slice_id: str,
        graph_format: Literal["GRAPHML", "JSON_NODELINK", "CYTOSCAPE", "NONE"] = "GRAPHML",
        as_self: bool = True,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> Union[Dict[str, Any], SliceDTO]:
        return self.orch.get_slice(token=id_token, slice_id=slice_id, graph_format=graph_format,
                                   as_self=as_self, return_fmt=return_fmt)

    def list_slivers(
        self, *, id_token: str, slice_id: str, as_self: bool = True, return_fmt: Literal["dict", "dto"] = "dict"
    ) -> List[Union[Dict[str, Any], SliverDTO]]:
        return self.orch.slivers(token=id_token, slice_id=slice_id, as_self=as_self, return_fmt=return_fmt)

    def get_sliver(
        self, *, id_token: str, slice_id: str, sliver_id: str, as_self: bool = True, return_fmt: Literal["dict", "dto"] = "dict"
    ) -> List[Union[Dict[str, Any], SliverDTO]]:
        return self.orch.slivers(token=id_token, slice_id=slice_id, sliver_id=sliver_id, as_self=as_self,
                                 return_fmt=return_fmt)

    def poa_create(
        self,
        *,
        id_token: str,
        sliver_id: str,
        operation: Literal["cpuinfo", "numainfo", "cpupin", "numatune", "reboot", "addkey", "removekey", "rescan"],
        vcpu_cpu_map: Optional[List[Dict[str, str]]] = None,
        node_set: Optional[List[str]] = None,
        keys: Optional[List[Dict[str, str]]] = None,
        bdf: Optional[List[str]] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[Union[Dict[str, Any], PoaDataDTO]]:
        return self.orch.poa(
            token=id_token,
            sliver_id=sliver_id,
            operation=operation,
            vcpu_cpu_map=vcpu_cpu_map,
            node_set=node_set,
            keys=keys,
            bdf=bdf,
            return_fmt=return_fmt,
        )

    def poa_get(
        self,
        *,
        id_token: str,
        sliver_id: Optional[str] = None,
        poa_id: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> List[Union[Dict[str, Any], PoaDataDTO]]:
        return self.orch.get_poas(
            token=id_token, sliver_id=sliver_id, poa_id=poa_id, limit=limit, offset=offset, return_fmt=return_fmt
        )
