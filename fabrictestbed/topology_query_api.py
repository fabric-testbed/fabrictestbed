
#!/usr/bin/env python3
# MIT License
#
# FabricManagerV2 Query API: sites, hosts, facility_ports, links with filtering & pagination.
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Union, Literal

from fim.user.topology import AdvertizedTopology

from fabrictestbed.external_api.orchestrator_client import OrchestratorClient
from fabrictestbed.util.resources_v2 import ResourcesV2

Record = Dict[str, Any]
FilterSpec = Union[Callable[[Record], bool], Dict[str, Any]]

def get_logger(name: str = "fabric.manager", level: int = logging.INFO) -> logging.Logger:
    return logging.getLogger(name)

def _op_match(value: Any, spec: Dict[str, Any]) -> bool:
    for op, cond in spec.items():
        if op == "eq":
            if value != cond: return False
        elif op == "ne":
            if value == cond: return False
        elif op == "lt":
            if not (value is not None and value < cond): return False
        elif op == "lte":
            if not (value is not None and value <= cond): return False
        elif op == "gt":
            if not (value is not None and value > cond): return False
        elif op == "gte":
            if not (value is not None and value >= cond): return False
        elif op == "in":
            try:
                if value not in cond: return False
            except Exception:
                return False
        elif op == "contains":
            if value is None or str(cond) not in str(value): return False
        elif op == "icontains":
            if value is None or str(cond).lower() not in str(value).lower(): return False
        elif op == "regex":
            import re as _re
            if value is None or _re.search(cond, str(value)) is None: return False
        elif op == "any":
            if value is None: return False
            ok = False
            if callable(cond):
                ok = any(cond(v) for v in value)
            else:
                try:
                    ok = any(v in cond for v in value)
                except Exception:
                    ok = False
            if not ok: return False
        elif op == "all":
            if value is None: return False
            if callable(cond):
                ok = all(cond(v) for v in value)
            else:
                try:
                    ok = all(v in cond for v in value)
                except Exception:
                    ok = False
            if not ok: return False
    return True


def _record_matches(record: Record, flt: FilterSpec) -> bool:
    if flt is None:
        return True
    if callable(flt):
        return bool(flt(record))
    if "or" in flt and isinstance(flt["or"], list):
        return any(_record_matches(record, branch) for branch in flt["or"] if isinstance(branch, dict))
    for field, condition in flt.items():
        if field == "or":
            continue
        value = record.get(field, None)
        if isinstance(condition, dict):
            if not _op_match(value, condition):
                return False
        else:
            if value != condition:
                return False
    return True


def _apply_filters(data: Iterable[Record], filters: Optional[FilterSpec]) -> List[Record]:
    if filters is None:
        return list(data)
    return [r for r in data if _record_matches(r, filters)]


def _paginate(data: List[Record], *, limit: Optional[int], offset: int) -> List[Record]:
    start = max(0, int(offset or 0))
    if limit is None:
        return data[start:]
    return data[start : start + max(0, int(limit))]


class TopologyQueryAPI:
    """
    Add-on API for FabricManagerV2
    Requires host class to implement _get_resources_topology(id_token: str).
    """
    def __init__(
        self,
        *,
        orchestrator_host: str,
        logger: Optional[logging.Logger] = None,
        http_debug: bool = False,
    ):
        self.log = logger or get_logger()
        self.orch = OrchestratorClient(orchestrator_host, http_debug=http_debug, logger=self.log)

    def resources(
        self,
        *,
        id_token: str,
        level: int = 1,
        force_refresh: bool = False,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        includes: Optional[List[str]] = None,
        excludes: Optional[List[str]] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> Union[Dict[str, Any], AdvertizedTopology]:
        return self.orch.resources(
            token=id_token,
            level=level,
            force_refresh=force_refresh,
            start=start_date,
            end=end_date,
            includes=includes,
            excludes=excludes,
            return_fmt=return_fmt,
        )

    def portal_resources(
        self,
        *,
        graph_format: Literal["GRAPHML", "JSON_NODELINK", "CYTOSCAPE"] = "JSON_NODELINK",
        level: Optional[int] = None,
        force_refresh: Optional[bool] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        includes: Optional[List[str]] = None,
        excludes: Optional[List[str]] = None,
        return_fmt: Literal["dict", "dto"] = "dict",
    ) -> Union[Dict[str, Any], AdvertizedTopology]:
        return self.orch.portal_resources(
            graph_format=graph_format,
            level=level,
            force_refresh=force_refresh,
            start=start_date,
            end=end_date,
            includes=includes,
            excludes=excludes,
            return_fmt=return_fmt,
        )

    def _get_resources_topology(self, *, id_token: str):
        fim_topo = self.resources(id_token=id_token, return_fmt="dto")
        return fim_topo

    def _resources_v2(self, *, id_token: str):
        topo = self._get_resources_topology(id_token=id_token)
        try:
            topo = ResourcesV2(topology=topo)
        except Exception:
            pass
        return topo

    def query_sites(self, *, id_token: str, filters: Optional[FilterSpec] = None,
                    limit: Optional[int] = None, offset: int = 0) -> List[Record]:
        res = self._resources_v2(id_token=id_token)
        items = [s.to_summary() for s in res.sites.values()]
        items = _apply_filters(items, filters)
        return _paginate(items, limit=limit, offset=offset)

    def query_hosts(self, *, id_token: str, filters: Optional[FilterSpec] = None,
                    limit: Optional[int] = None, offset: int = 0) -> List[Record]:
        res = self._resources_v2(id_token=id_token)
        items = [h.to_dict() for h in res.list_hosts()]
        items = _apply_filters(items, filters)
        return _paginate(items, limit=limit, offset=offset)

    def query_facility_ports(self, *, id_token: str, filters: Optional[FilterSpec] = None,
                             limit: Optional[int] = None, offset: int = 0) -> List[Record]:
        res = self._resources_v2(id_token=id_token)
        items = [fp.to_dict() for fp in res.list_facility_ports()]
        items = _apply_filters(items, filters)
        return _paginate(items, limit=limit, offset=offset)

    def query_links(self, *, id_token: str, filters: Optional[FilterSpec] = None,
                    limit: Optional[int] = None, offset: int = 0) -> List[Record]:
        res = self._resources_v2(id_token=id_token)
        items = [l.to_dict() for l in res.list_links()]
        items = _apply_filters(items, filters)
        return _paginate(items, limit=limit, offset=offset)
