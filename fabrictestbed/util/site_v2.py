#!/usr/bin/env python3
# MIT License
#
# Refined Site wrapper for FABRIC resources based on FIM AdvertizedTopology.
# Optimized for: strong typing, lazy extraction, normalized views, and speed.
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from fim.user.composite_node import CompositeNode
from fim.user.node import Node


# ---------------------------------------------------------------------
# Compact dataclasses (slots=True + frozen=True)
# ---------------------------------------------------------------------
@dataclass(slots=True, frozen=True)
class SwitchInfo:
    model: str
    capacity: Optional[int] = 0
    allocated: Optional[int] = 0


@dataclass(slots=True, frozen=True)
class ComponentInfo:
    model: str
    capacity: Optional[int] = 0
    allocated: Optional[int] = 0


@dataclass(slots=True, frozen=True)
class HostInfo:
    name: str
    site: str
    cores_capacity: Optional[int] = 0
    cores_allocated: Optional[int] = 0
    ram_capacity: Optional[int] = 0
    ram_allocated: Optional[int] = 0
    disk_capacity: Optional[int] = 0
    disk_allocated: Optional[int] = 0
    components: Dict[str, ComponentInfo] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "site": self.site,
            "cores_capacity": self.cores_capacity,
            "cores_allocated": self.cores_allocated,
            "cores_available": (
                0 if self.cores_capacity is None or self.cores_allocated is None
                else max(0, self.cores_capacity - self.cores_allocated)
            ),
            "ram_capacity": self.ram_capacity,
            "ram_allocated": self.ram_allocated,
            "ram_available": (
                0 if self.ram_capacity is None or self.ram_allocated is None
                else max(0, self.ram_capacity - self.ram_allocated)
            ),
            "disk_capacity": self.disk_capacity,
            "disk_allocated": self.disk_allocated,
            "disk_available": (
                0 if self.disk_capacity is None or self.disk_allocated is None
                else max(0, self.disk_capacity - self.disk_allocated)
            ),
            "components": {
                k: {"capacity": v.capacity, "allocated": v.allocated}
                for k, v in self.components.items()
            } if self.components else {}
        }


@dataclass(slots=True, frozen=True)
class FacilityPortInfo:
    site: str
    name: str
    port: Optional[str] = None
    switch: Optional[str] = None
    labels: Optional[Any] = None   # keep original object, defer conversion
    vlans: Optional[str] = None
    allocated_vlans: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        labs = self.labels.to_dict() if hasattr(self.labels, "to_dict") and self.labels else self.labels
        return {
            "site": self.site,
            "name": self.name,
            "port": self.port,
            "switch": self.switch,
            "labels": labs,
            "vlans": self.vlans,
            "allocated_vlans": self.allocated_vlans,
        }


@dataclass(slots=True, frozen=True)
class LinkEndpoint:
    site: Optional[str]
    node: Optional[str]
    port: Optional[str]


@dataclass(slots=True, frozen=True)
class LinkInfo:
    name: Optional[str]
    layer: Optional[str]
    labels: Optional[Any]
    bandwidth: Optional[int]
    allocated_bandwidth: Optional[int]
    sites: Optional[Tuple[str, ...]]
    endpoints: List[LinkEndpoint]

    def to_dict(self) -> Dict[str, Any]:
        labs = self.labels.to_dict() if hasattr(self.labels, "to_dict") and self.labels else self.labels
        return {
            "name": self.name,
            "layer": self.layer,
            "labels": labs,
            "bandwidth": self.bandwidth,
            "allocated_bandwidth": self.allocated_bandwidth,
            "sites": self.sites,
            "endpoints": [{"site": e.site, "node": e.node, "port": e.port} for e in self.endpoints],
        }


# ---------------------------------------------------------------------
# SiteV2 container
# ---------------------------------------------------------------------
@dataclass(slots=True)
class SiteV2:
    name: str
    address: Optional[str] = None
    location: Optional[Tuple[float, float]] = None
    state: Optional[str] = None
    ptp_capable: Optional[bool] = None
    ipv4_management: Optional[bool] = None

    _hosts_index: Mapping[str, HostInfo] = field(default_factory=dict, repr=False)
    _facility_ports_index: Mapping[str, FacilityPortInfo] = field(default_factory=dict, repr=False)
    _links_index: Mapping[str, List[LinkInfo]] = field(default_factory=dict, repr=False)
    _switches_index: Mapping[str, SwitchInfo] = field(default_factory=dict, repr=False)

    # Accessors
    def get_hosts(self) -> List[HostInfo]:
        return list(self._hosts_index.values())

    def get_switches(self) -> List[SwitchInfo]:
        return list(self._switches_index.values())

    def get_facility_ports(self) -> List[FacilityPortInfo]:
        return list(self._facility_ports_index.values())

    def get_links(self) -> List[LinkInfo]:
        return list(self._links_index.get(self.name, []))

    # Aggregations
    def aggregate_cores(self) -> Tuple[int, int]:
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

    def aggregate_components(self) -> Dict[str, Dict[str, Optional[int]]]:
        """
        Sum component capacity/allocated across all hosts by component model.
        Returns: { "<model>": {"capacity": int, "allocated": int, "available": int} }
        """
        agg: Dict[str, Dict[str, int]] = {}
        for h in self._hosts_index.values():
            for model, comp in (h.components or {}).items():
                entry = agg.setdefault(model, {"capacity": 0, "allocated": 0})
                entry["capacity"] += comp.capacity or 0
                entry["allocated"] += comp.allocated or 0
        # add available
        for model, vals in agg.items():
            cap = vals.get("capacity") or 0
            alloc = vals.get("allocated") or 0
            vals["available"] = max(0, cap - alloc)
        return agg

    def to_summary(self) -> Dict[str, Any]:
        cores_cap, cores_alloc = self.aggregate_cores()
        ram_cap, ram_alloc = self.aggregate_ram()
        disk_cap, disk_alloc = self.aggregate_disk()
        components = self.aggregate_components()

        return {
            "name": self.name,
            "state": self.state,
            "address": self.address,
            "location": self.location,
            "ptp_capable": self.ptp_capable,
            "ipv4_management": self.ipv4_management,

            "cores_capacity": cores_cap,
            "cores_allocated": cores_alloc,
            "cores_available": max(0, cores_cap - cores_alloc),

            "ram_capacity": ram_cap,
            "ram_allocated": ram_alloc,
            "ram_available": max(0, ram_cap - ram_alloc),

            "disk_capacity": disk_cap,
            "disk_allocated": disk_alloc,
            "disk_available": max(0, disk_cap - disk_alloc),

            # NEW: aggregate components, and host count instead of names
            "components": components,              # {model: {capacity, allocated, available}}
            "hosts_count": len(self._hosts_index), # integer
        }


# ---------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------
def load_site(site: CompositeNode) -> Tuple[SiteV2, Dict[str, HostInfo], Dict[str, SwitchInfo]]:
    hosts: Dict[str, HostInfo] = {}
    switches: Dict[str, SwitchInfo] = {}
    try:
        from fim.user import NodeType
        for c_name, child in site.children.items():
            if child.type == NodeType.Server:
                hosts[c_name] = load_host(site.site, c_name, child)
            elif child.type == NodeType.Switch:
                switches[c_name] = load_switch(c_name, child)

        site_v2 = SiteV2(
            name=site.site,
            address=getattr(site.location, "postal", None),
            location=(site.location.lat, site.location.lon) if site.location else None,
            ptp_capable=getattr(site.flags, "ptp", None),
            ipv4_management=getattr(site.flags, "ipv4_management", None),
        )
        return site_v2, hosts, switches
    except Exception as e:
        logging.error(f"Error in load_site: {e}")
        logging.error(traceback.format_exc())
        return SiteV2(name=site.site, state="Error"), hosts, switches


def load_switch(name: str, switch: Node) -> SwitchInfo:
    cap = getattr(getattr(switch, "capacities", None), "unit", None)
    alloc = getattr(getattr(switch, "capacity_allocations", None), "unit", None)
    return SwitchInfo(model=name, capacity=cap, allocated=alloc)


def load_host(site_name: str, host_name: str, host: Node) -> HostInfo:
    components: Dict[str, ComponentInfo] = {}
    for model_name, comp in getattr(host, "components", {}).items():
        cap = getattr(getattr(comp, "capacities", None), "unit", 0)
        alloc = getattr(getattr(comp, "capacity_allocations", None), "unit", 0)
        existing = components.get(model_name)
        if existing:
            components[model_name] = ComponentInfo(
                model=existing.model,
                capacity=(existing.capacity or 0) + (cap or 0),
                allocated=(existing.allocated or 0) + (alloc or 0),
            )
        else:
            components[model_name] = ComponentInfo(model=comp.model, capacity=cap, allocated=alloc)

    caps = getattr(host, "capacities", None)
    allocs = getattr(host, "capacity_allocations", None)
    return HostInfo(
        name=host_name,
        site=site_name,
        components=components,
        cores_capacity=getattr(caps, "core", 0),
        ram_capacity=getattr(caps, "ram", 0),
        disk_capacity=getattr(caps, "disk", 0),
        cores_allocated=getattr(allocs, "core", 0),
        ram_allocated=getattr(allocs, "ram", 0),
        disk_allocated=getattr(allocs, "disk", 0),
    )
