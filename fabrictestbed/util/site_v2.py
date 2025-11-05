
#!/usr/bin/env python3
# MIT License
#
# Refined Site wrapper for FABRIC resources based on FIM AdvertizedTopology.
# Focus: strong typing, lazy extraction, normalized views, and robust fallbacks.
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

try:
    # Strong type for the canonical FIM topology class
    from fim.user.topology import AdvertizedTopology  # noqa: F401
except Exception:  # pragma: no cover - keeps import optional for typing-only environments
    AdvertizedTopology = object  # type: ignore


@dataclass(frozen=True)
class ComponentInfo:
    """Normalized component (NIC/GPU/FPGA/etc.) inventory of a host."""
    model: str
    capacity: Optional[int] = None
    allocated: Optional[int] = None


@dataclass(frozen=True)
class HostInfo:
    """Normalized host inventory and capacities."""
    name: str
    site: str
    # Core resources (if exposed by wrappers or via node properties)
    cores_capacity: Optional[int] = None
    cores_allocated: Optional[int] = None
    ram_capacity: Optional[int] = None
    ram_allocated: Optional[int] = None
    disk_capacity: Optional[int] = None
    disk_allocated: Optional[int] = None
    # Optional components map: model -> ComponentInfo
    components: Dict[str, ComponentInfo] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "name": self.name,
            "site": self.site,
            "cores_capacity": self.cores_capacity,
            "cores_allocated": self.cores_allocated,
            "cores_available": (
                None if self.cores_capacity is None or self.cores_allocated is None
                else max(0, self.cores_capacity - self.cores_allocated)
            ),
            "ram_capacity": self.ram_capacity,
            "ram_allocated": self.ram_allocated,
            "ram_available": (
                None if self.ram_capacity is None or self.ram_allocated is None
                else max(0, self.ram_capacity - self.ram_allocated)
            ),
            "disk_capacity": self.disk_capacity,
            "disk_allocated": self.disk_allocated,
            "disk_available": (
                None if self.disk_capacity is None or self.disk_allocated is None
                else max(0, self.disk_capacity - self.disk_allocated)
            ),
        }
        if self.components:
            d["components"] = {
                k: {"capacity": v.capacity, "allocated": v.allocated} for k, v in self.components.items()
            }
        return d


@dataclass(frozen=True)
class FacilityPortInfo:
    site: str
    name: str
    port: Optional[str] = None
    switch: Optional[str] = None
    labels: Optional[Dict[str, Any]] = None
    vlans: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site": self.site,
            "name": self.name,
            "port": self.port,
            "switch": self.switch,
            "labels": self.labels,
            "vlans": self.vlans,
        }


@dataclass(frozen=True)
class LinkEndpoint:
    site: Optional[str]
    node: Optional[str]
    port: Optional[str]


@dataclass(frozen=True)
class LinkInfo:
    name: Optional[str]
    layer: Optional[str]
    labels: Optional[Dict[str, Any]]
    bandwidth: Optional[int]
    endpoints: List[LinkEndpoint]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "layer": self.layer,
            "labels": self.labels,
            "bandwidth": self.bandwidth,
            "endpoints": [
                {"site": e.site, "node": e.node, "port": e.port} for e in self.endpoints
            ],
        }


@dataclass
class SiteV2:
    """
    Site-level view constructed from a topology index (prepared by ResourcesV2).
    The constructor is intentionally lightweight; expensive work is deferred.
    """
    name: str
    address: Optional[str] = None
    location: Optional[Tuple[float, float]] = None
    state: Optional[str] = None
    ptp_capable: Optional[bool] = None

    # Indexed views injected by ResourcesV2
    _hosts_index: Mapping[str, HostInfo] = field(default_factory=dict, repr=False)
    _facility_ports_index: Mapping[str, FacilityPortInfo] = field(default_factory=dict, repr=False)
    _links_index: Mapping[str, List[LinkInfo]] = field(default_factory=dict, repr=False)

    def get_host_names(self) -> List[str]:
        return list(self._hosts_index.keys())

    def get_hosts(self) -> List[HostInfo]:
        return list(self._hosts_index.values())

    def get_facility_ports(self) -> List[FacilityPortInfo]:
        return list(self._facility_ports_index.values())

    def get_links(self) -> List[LinkInfo]:
        # Only return links that have this site as an endpoint (pre-indexed by ResourcesV2)
        return list(self._links_index.get(self.name, []))

    # Convenience aggregations
    def aggregate_cores(self) -> Tuple[int, int]:
        """(capacity, allocated) for cores across hosts at this site; missing values treated as 0."""
        cap = sum(h.cores_capacity or 0 for h in self._hosts_index.values())
        alloc = sum(h.cores_allocated or 0 for h in self._hosts_index.values())
        return cap, alloc

    def aggregate_ram(self) -> Tuple[int, int]:
        cap = sum(h.ram_capacity or 0 for h in self._hosts_index.values())
        alloc = sum(h.ram_allocated or 0 for h in self._hosts_index.values())
        return cap, alloc

    def aggregate_disk(self) -> Tuple[int, int]:
        cap = sum(h.disk_capacity or 0 for h in self._hosts_index.values())
        alloc = sum(h.disk_allocated or 0 for h in self._hosts_index.values())
        return cap, alloc

    def to_summary(self) -> Dict[str, Any]:
        cores_cap, cores_alloc = self.aggregate_cores()
        ram_cap, ram_alloc = self.aggregate_ram()
        disk_cap, disk_alloc = self.aggregate_disk()
        return {
            "name": self.name,
            "state": self.state,
            "address": self.address,
            "location": self.location,
            "ptp_capable": self.ptp_capable,
            "cores_capacity": cores_cap,
            "cores_allocated": cores_alloc,
            "cores_available": max(0, cores_cap - cores_alloc),
            "ram_capacity": ram_cap,
            "ram_allocated": ram_alloc,
            "ram_available": max(0, ram_cap - ram_alloc),
            "disk_capacity": disk_cap,
            "disk_allocated": disk_alloc,
            "disk_available": max(0, disk_cap - disk_alloc),
            "hosts": self.get_host_names(),
        }
