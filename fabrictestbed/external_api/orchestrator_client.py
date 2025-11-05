#!/usr/bin/env python3
# MIT License
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union, Literal

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from fim.user import GraphFormat
from fim.user.topology import ExperimentTopology, AdvertizedTopology


# ===========================
# Dataclasses (DTOs)
# ===========================

@dataclass(slots=True)
class SliceDTO:
    slice_id: str
    name: Optional[str] = None
    state: Optional[str] = None
    model: Optional[str] = None
    lease_start_time: Optional[str] = None
    lease_end_time: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    graph_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_email: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SliceDTO":
        return SliceDTO(
            slice_id=d.get("slice_id"),
            name=d.get("name"),
            state=d.get("state"),
            model=d.get("model"),
            lease_start_time=d.get("lease_start_time"),
            lease_end_time=d.get("lease_end_time"),
            project_id=d.get("project_id"),
            project_name=d.get("project_name"),
            graph_id=d.get("graph_id"),
            owner_user_id=d.get("owner_user_id"),
            owner_email=d.get("owner_email"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "name": self.name,
            "state": self.state,
            "model": self.model,
            "lease_start_time": self.lease_start_time,
            "lease_end_time": self.lease_end_time,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "graph_id": self.graph_id,
            "owner_user_id": self.owner_user_id,
            "owner_email": self.owner_email,
        }


@dataclass(slots=True)
class SliverDTO:
    sliver_id: str
    slice_id: str
    graph_node_id: Optional[str] = None
    sliver_type: Optional[str] = None
    sliver: Optional[Dict[str, Any]] = None
    lease_start_time: Optional[str] = None
    lease_end_time: Optional[str] = None
    state: Optional[str] = None
    pending_state: Optional[str] = None
    join_state: Optional[str] = None
    notice: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_email: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SliverDTO":
        return SliverDTO(
            sliver_id=d.get("sliver_id"),
            slice_id=d.get("slice_id"),
            graph_node_id=d.get("graph_node_id"),
            sliver_type=d.get("sliver_type"),
            sliver=d.get("sliver"),
            lease_start_time=d.get("lease_start_time"),
            lease_end_time=d.get("lease_end_time"),
            state=d.get("state"),
            pending_state=d.get("pending_state"),
            join_state=d.get("join_state"),
            notice=d.get("notice"),
            owner_user_id=d.get("owner_user_id"),
            owner_email=d.get("owner_email"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sliver_id": self.sliver_id,
            "slice_id": self.slice_id,
            "graph_node_id": self.graph_node_id,
            "sliver_type": self.sliver_type,
            "sliver": self.sliver,
            "lease_start_time": self.lease_start_time,
            "lease_end_time": self.lease_end_time,
            "state": self.state,
            "pending_state": self.pending_state,
            "join_state": self.join_state,
            "notice": self.notice,
            "owner_user_id": self.owner_user_id,
            "owner_email": self.owner_email,
        }


@dataclass(slots=True)
class PoaDataDTO:
    poa_id: Optional[str] = None
    operation: Optional[str] = None
    state: Optional[str] = None
    sliver_id: Optional[str] = None
    slice_id: Optional[str] = None
    error: Optional[str] = None
    info: Optional[Dict[str, Any]] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PoaDataDTO":
        return PoaDataDTO(
            poa_id=d.get("poa_id"),
            operation=d.get("operation"),
            state=d.get("state"),
            sliver_id=d.get("sliver_id"),
            slice_id=d.get("slice_id"),
            error=d.get("error"),
            info=d.get("info"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "poa_id": self.poa_id,
            "operation": self.operation,
            "state": self.state,
            "sliver_id": self.sliver_id,
            "slice_id": self.slice_id,
            "error": self.error,
            "info": self.info,
        }


# ===========================
# Exceptions
# ===========================

class OrchestratorError(Exception):
    """Base error for orchestrator client."""


class OrchestratorValidationError(OrchestratorError):
    """Raised when local validation fails (bad args / bad time format)."""


class OrchestratorHTTPError(OrchestratorError):
    """Raised on non-2xx responses."""
    def __init__(self, status_code: int, message: str, body_preview: str = ""):
        super().__init__(f"{status_code}: {message}\n{body_preview}")
        self.status_code = status_code
        self.body_preview = body_preview


# ===========================
# HTTP helpers
# ===========================

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


def _bearer_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _maybe_dict_list(objs: List[Any], return_fmt: Literal["dto", "dict"]) -> List[Any]:
    if return_fmt == "dict":
        return [o.to_dict() for o in objs]
    return objs


# ===========================
# Client (DTO or dict returns)
# ===========================

class OrchestratorClient:
    """
    Requests-based client with ergonomic returns:

      - Success -> typed DTOs (default) or plain dicts (return_fmt="dict")
      - Failure -> raises Orchestrator* exceptions

    Includes:
      - Dataclasses (SliceDTO, SliverDTO, PoaDataDTO) with .to_dict()
      - Structured logging (INFO per call; optional DEBUG dumps on failures)
    """

    TIME_FORMAT = "%Y-%m-%d %H:%M:%S %z"

    def __init__(
        self,
        orchestrator_host: str,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        backoff_factor: float = 0.3,
        logger: Optional[logging.Logger] = None,
        http_debug: bool = False,
    ):
        if not orchestrator_host:
            raise OrchestratorValidationError("orchestrator_host must be specified")

        base_url = orchestrator_host
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"
        if not base_url.endswith("/"):
            base_url += "/"

        self.base_url = base_url
        self.timeout = timeout
        self.session = _build_session(retries=retries, backoff=backoff_factor)
        self.log = logger or logging.getLogger("fabric.orchestrator")
        self.http_debug = http_debug

    # ------------- Core HTTP -------------

    def _req(
        self,
        method: str,
        path: str,
        *,
        token: Optional[str] = None,
        params: Optional[Union[Dict[str, Any], List[Tuple[str, Any]]]] = None,
        json_body: Optional[Dict] = None,
        text_body: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        url = self.base_url + path.lstrip("/")
        headers: Dict[str, str] = {}
        if token:
            headers.update(_bearer_headers(token))
        if extra_headers:
            headers.update(extra_headers)

        if text_body is not None and json_body is not None:
            raise OrchestratorValidationError("Provide either text_body or json_body, not both.")

        if json_body is not None and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        if text_body is not None and "Content-Type" not in headers:
            headers["Content-Type"] = "text/plain"

        t0 = time.perf_counter()
        try:
            resp = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
                data=text_body,
                timeout=self.timeout,
            )
            dt = (time.perf_counter() - t0) * 1000.0

            self.log.info(
                "orchestrator_http_call",
                extra={
                    "event": "http_call",
                    "http_method": method,
                    "url_path": path,
                    "status_code": resp.status_code,
                    "elapsed_ms": round(dt, 2),
                    "has_token": bool(token),
                    "params": params if isinstance(params, dict) else (params or []),
                    "payload_len": len(json.dumps(json_body)) if json_body is not None else (len(text_body) if text_body else 0),
                    "resp_len": len(resp.content or b""),
                },
            )

            if not (200 <= resp.status_code < 300):
                if self.http_debug:
                    self.log.debug(
                        "orchestrator_http_failure_dump",
                        extra={
                            "event": "http_failure",
                            "http_method": method,
                            "url": url,
                            "status_code": resp.status_code,
                            "request_headers": headers,
                            "request_params": params,
                            "request_json": json_body,
                            "request_text": text_body[:2000] if text_body else None,
                            "response_text": resp.text[:2000],
                        },
                    )
                raise OrchestratorHTTPError(resp.status_code, "HTTP request failed", resp.text[:2000])

            return resp
        except OrchestratorHTTPError:
            raise
        except Exception as e:
            dt = (time.perf_counter() - t0) * 1000.0
            self.log.error(
                "orchestrator_http_exception",
                extra={
                    "event": "http_exception",
                    "http_method": method,
                    "url_path": path,
                    "elapsed_ms": round(dt, 2),
                    "error": repr(e),
                },
            )
            raise OrchestratorError(repr(e)) from e

    @staticmethod
    def _json(resp: requests.Response) -> Dict[str, Any]:
        try:
            return resp.json() if resp.content else {}
        except Exception as e:
            raise OrchestratorError(f"Failed to parse JSON: {e}; status={resp.status_code}, text={resp.text[:500]}")

    # ------------- Public API (DTO or dict) -------------

    def create(
        self,
        *,
        token: str,
        slice_name: str,
        ssh_keys: Union[str, List[str]],
        topology: ExperimentTopology = None,
        slice_graph: str = None,
        lease_start_time: str = None,
        lease_end_time: str = None,
        lifetime: int = 24,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> List[SliverDTO] | List[Dict[str, Any]]:
        if not token:
            raise OrchestratorValidationError("Token must be specified")
        if not slice_name:
            raise OrchestratorValidationError("Slice Name must be specified")
        if (topology is None and slice_graph is None) or (topology is not None and slice_graph is not None):
            raise OrchestratorValidationError("Specify either topology or slice_graph")

        for lbl, ts in (("Lease Start Time", lease_start_time), ("Lease End Time", lease_end_time)):
            if ts:
                try:
                    datetime.strptime(ts, self.TIME_FORMAT)
                except Exception as e:
                    raise OrchestratorValidationError(f"{lbl} {ts} should be in format: {self.TIME_FORMAT} e: {e}")

        graph_str = slice_graph or topology.serialize()
        ssh_keys = [ssh_keys] if isinstance(ssh_keys, str) else list(ssh_keys)
        body = {"graph_model": graph_str, "ssh_keys": ssh_keys}

        params: Dict[str, Any] = {"name": slice_name, "lifetime": lifetime}
        if lease_start_time:
            params["lease_start_time"] = lease_start_time
        if lease_end_time:
            params["lease_end_time"] = lease_end_time

        resp = self._req("POST", "/slices/creates", token=token, params=params, json_body=body)
        data = self._json(resp).get("data") or []
        slivers = [SliverDTO.from_dict(x) for x in data]
        return _maybe_dict_list(slivers, return_fmt)

    def modify(
        self,
        *,
        token: str,
        slice_id: str,
        topology: ExperimentTopology = None,
        slice_graph: str = None,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> List[SliverDTO] | List[Dict[str, Any]]:
        if not token:
            raise OrchestratorValidationError("Token must be specified")
        if not slice_id:
            raise OrchestratorValidationError("Slice Id must be specified")
        if (topology is None and slice_graph is None) or (topology is not None and slice_graph is not None):
            raise OrchestratorValidationError("Specify either topology or slice_graph")

        graph_str = slice_graph or topology.serialize()
        resp = self._req(
            "PUT",
            f"/slices/modify/{slice_id}",
            token=token,
            text_body=graph_str,
            extra_headers={"Content-Type": "text/plain"},
        )
        data = self._json(resp).get("data") or []
        slivers = [SliverDTO.from_dict(x) for x in data]
        return _maybe_dict_list(slivers, return_fmt)

    def modify_accept(
        self,
        *,
        token: str,
        slice_id: str,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> Optional[ExperimentTopology] | Optional[Dict[str, str]]:
        if not token:
            raise OrchestratorValidationError("Token must be specified")
        if not slice_id:
            raise OrchestratorValidationError("Slice Id must be specified")

        resp = self._req("POST", f"/slices/modify/{slice_id}/accept", token=token)
        payload = self._json(resp)
        model = (payload.get("data") or [{}])[0].get("model")
        if not model:
            return None
        if return_fmt == "dict":
            return {"graph_format": GraphFormat.GRAPHML.name, "model": model}
        topo = ExperimentTopology()
        topo.load(graph_string=model)
        return topo

    def delete(self, *, token: str, slice_id: Optional[str] = None) -> None:
        if not token:
            raise OrchestratorValidationError("Token must be specified")
        path = f"/slices/delete/{slice_id}" if slice_id else "/slices/delete"
        self._req("DELETE", path, token=token)

    def slices(
        self,
        *,
        token: str,
        includes: Optional[List[str]] = None,  # state names (e.g., ["StableOK"])
        excludes: Optional[List[str]] = None,
        name: str = None,
        limit: int = 20,
        offset: int = 0,
        slice_id: str = None,
        as_self: bool = True,
        search: str = None,
        exact_match: bool = False,
        graph_format: str = GraphFormat.GRAPHML.name,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> List[SliceDTO] | List[Dict[str, Any]]:
        if not token:
            raise OrchestratorValidationError("Token must be specified")

        if slice_id:
            params = {"as_self": as_self, "graph_format": graph_format}
            resp = self._req("GET", f"/slices/{slice_id}", token=token, params=params)
            data = self._json(resp).get("data") or []
            slices = [SliceDTO.from_dict(x) for x in data]
            return _maybe_dict_list(slices, return_fmt)

        params: Dict[str, Union[str, int, bool]] = {
            "limit": limit,
            "offset": offset,
            "as_self": as_self,
            "exact_match": exact_match,
        }
        if name:
            params["name"] = name
        if search:
            params["search"] = search

        # API expects repeated "states" params if provided
        if includes or excludes:
            state_list = includes or [
                "StableError", "StableOK", "Nascent", "Configuring", "Closing", "Dead",
                "ModifyError", "ModifyOK", "Modifying", "AllocatedOK", "AllocatedError"
            ]
            if excludes:
                state_list = [s for s in state_list if s not in set(excludes)]

            params_list: List[Tuple[str, Any]] = list(params.items())
            for s in state_list:
                params_list.append(("states", s))
            resp = self._req("GET", "/slices", token=token, params=params_list)
        else:
            resp = self._req("GET", "/slices", token=token, params=params)

        data = self._json(resp).get("data") or []
        slices = [SliceDTO.from_dict(x) for x in data]
        return _maybe_dict_list(slices, return_fmt)

    def get_slice(
        self,
        *,
        token: str,
        slice_id: str,
        graph_format: str = str(GraphFormat.GRAPHML),
        as_self: bool = True,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> Optional[ExperimentTopology] | Optional[Dict[str, str]]:
        if not token:
            raise OrchestratorValidationError("Token must be specified")
        if not slice_id:
            raise OrchestratorValidationError("Slice Id must be specified")

        params = {"graph_format": graph_format, "as_self": as_self}
        resp = self._req("GET", f"/slices/{slice_id}", token=token, params=params)
        payload = self._json(resp)
        model = (payload.get("data") or [{}])[0].get("model")
        if not model:
            return None
        if return_fmt == "dict":
            return {"graph_format": graph_format, "model": model}
        topo = ExperimentTopology()
        topo.load(graph_string=model)
        return topo

    def slivers(
        self,
        *,
        token: str,
        slice_id: str,
        sliver_id: Optional[str] = None,
        as_self: bool = True,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> List[SliverDTO] | List[Dict[str, Any]]:
        if not token:
            raise OrchestratorValidationError("Token must be specified")
        if not slice_id:
            raise OrchestratorValidationError("Slice Id must be specified")

        params = {"slice_id": slice_id, "as_self": as_self}
        if sliver_id:
            resp = self._req("GET", f"/slivers/{sliver_id}", token=token, params=params)
        else:
            resp = self._req("GET", "/slivers", token=token, params=params)

        data = self._json(resp).get("data") or []
        slivers = [SliverDTO.from_dict(x) for x in data]
        return _maybe_dict_list(slivers, return_fmt)

    def resources(
        self,
        *,
        token: str,
        level: int = 1,
        force_refresh: bool = False,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        includes: Optional[List[str]] = None,
        excludes: Optional[List[str]] = None,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> Optional[AdvertizedTopology] | Optional[Dict[str, str]]:
        if not token:
            raise OrchestratorValidationError("Token must be specified")

        params: Dict[str, Union[str, int, bool]] = {
            "level": level,
            "force_refresh": force_refresh,
        }
        if start:
            params["start_date"] = start.strftime(self.TIME_FORMAT)
        if end:
            params["end_date"] = end.strftime(self.TIME_FORMAT)
        if includes:
            params["includes"] = ", ".join(includes)
        if excludes:
            params["excludes"] = ", ".join(excludes)

        resp = self._req("GET", "/resources", token=token, params=params)
        payload = self._json(resp)
        graph_string = (payload.get("data") or [{}])[0].get("model")
        if not graph_string:
            return None
        if return_fmt == "dict":
            return {"graph_format": GraphFormat.GRAPHML.name, "model": graph_string}
        substrate = AdvertizedTopology()
        substrate.load(graph_string=graph_string)
        return substrate

    def portal_resources(
        self,
        *,
        graph_format: str,
        level: Optional[int] = None,
        force_refresh: Optional[bool] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        includes: Optional[List[str]] = None,
        excludes: Optional[List[str]] = None,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> Optional[AdvertizedTopology] | Optional[Dict[str, str]]:
        params: Dict[str, Union[str, int, bool]] = {"graph_format": graph_format}
        if level is not None:
            params["level"] = level
        if force_refresh is not None:
            params["force_refresh"] = force_refresh
        if start:
            params["start_date"] = start.strftime(self.TIME_FORMAT)
        if end:
            params["end_date"] = end.strftime(self.TIME_FORMAT)
        if includes:
            params["includes"] = ", ".join(includes)
        if excludes:
            params["excludes"] = ", ".join(excludes)

        resp = self._req("GET", "/portalresources", params=params)
        payload = self._json(resp)
        graph_string = (payload.get("data") or [{}])[0].get("model")
        if not graph_string:
            return None
        if return_fmt == "dict":
            return {"graph_format": graph_format, "model": graph_string}
        substrate = AdvertizedTopology()
        substrate.load(graph_string=graph_string)
        return substrate

    def renew(self, *, token: str, slice_id: str, new_lease_end_time: str) -> None:
        if not token or not slice_id or not new_lease_end_time:
            raise OrchestratorValidationError("Token, slice_id, and new_lease_end_time must be specified")
        try:
            datetime.strptime(new_lease_end_time, self.TIME_FORMAT)
        except Exception:
            raise OrchestratorValidationError(f"Lease End Time {new_lease_end_time} should be in format: {self.TIME_FORMAT}")

        params = {"lease_end_time": new_lease_end_time}
        self._req("POST", f"/slices/renew/{slice_id}", token=token, params=params)

    def poa(
        self,
        *,
        token: str,
        sliver_id: str,
        operation: str,
        vcpu_cpu_map: Optional[List[Dict[str, str]]] = None,
        node_set: Optional[List[str]] = None,
        keys: Optional[List[Dict[str, str]]] = None,
        bdf: Optional[List[str]] = None,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> List[PoaDataDTO] | List[Dict[str, Any]]:
        if not token:
            raise OrchestratorValidationError("Token must be specified")
        if not sliver_id:
            raise OrchestratorValidationError("Sliver Id must be specified")

        body: Dict[str, Union[str, Dict, List]] = {"operation": operation}
        pdata: Dict[str, Union[List, Dict]] = {}
        if vcpu_cpu_map is not None:
            pdata["vcpu_cpu_map"] = vcpu_cpu_map
        if node_set is not None:
            pdata["node_set"] = node_set
        if keys is not None:
            pdata["keys"] = keys
        if bdf is not None:
            pdata["bdf"] = bdf
        if pdata:
            body["data"] = pdata

        resp = self._req("POST", f"/poas/create/{sliver_id}", token=token, json_body=body)
        data = self._json(resp).get("data") or []
        poas = [PoaDataDTO.from_dict(x) for x in data]
        return _maybe_dict_list(poas, return_fmt)

    def get_poas(
        self,
        *,
        token: str,
        sliver_id: Optional[str] = None,
        poa_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        return_fmt: Literal["dto", "dict"] = "dto",
    ) -> List[PoaDataDTO] | List[Dict[str, Any]]:
        if not token:
            raise OrchestratorValidationError("Token must be specified")
        if sliver_id is None and poa_id is None:
            raise OrchestratorValidationError("Sliver Id or Poa Id must be specified")

        if poa_id:
            resp = self._req("GET", f"/poas/{poa_id}", token=token)
        else:
            params: List[Tuple[str, Union[str, int]]] = [("limit", limit), ("offset", offset)]
            if sliver_id:
                params.append(("sliver_id", sliver_id))
            resp = self._req("GET", "/poas/", token=token, params=params)

        data = self._json(resp).get("data") or []
        poas = [PoaDataDTO.from_dict(x) for x in data]
        return _maybe_dict_list(poas, return_fmt)
