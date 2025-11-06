#!/usr/bin/env python3
# MIT License
#
# Refined Site wrapper for FABRIC resources based on FIM AdvertizedTopology.
# Focus: strong typing, lazy extraction, normalized views, and robust fallbacks.
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from fim.user.composite_node import CompositeNode
from fim.user.node import Node


@dataclass(frozen=True)
class SwitchInfo:
    """Normalized P4 Switch inventory of a host."""
    model: str
    capacity: Optional[int] = None
    allocated: Optional[int] = None


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
    ipv4_management: Optional[bool] = None

    _hosts_index: Mapping[str, HostInfo] = field(default_factory=dict, repr=False)
    _facility_ports_index: Mapping[str, FacilityPortInfo] = field(default_factory=dict, repr=False)
    _links_index: Mapping[str, List[LinkInfo]] = field(default_factory=dict, repr=False)
    _switches_index: Mapping[str, SwitchInfo] = field(default_factory=dict, repr=False)

    def get_host_names(self) -> List[str]:
        return list(self._hosts_index.keys())

    def get_hosts(self) -> List[HostInfo]:
        return list(self._hosts_index.values())

    def get_switch_names(self) -> List[str]:
        return list(self._switches_index.keys())

    def get_switches(self) -> List[SwitchInfo]:
        return list(self._switches_index.values())

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
            "hosts": self.get_host_names(),
        }


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
            address=site.location.postal if site.location else None,
            location=(site.location.lat, site.location.lon) if site.location else None,
            state=None,
            ptp_capable=site.flags.ptp if site.flags else None,
            ipv4_management=site.flags.ipv4_management if site.flags else None,
        )

        return site_v2, hosts, switches
    except Exception as e:
        logging.error(f"Error occurred in load_site - {e}")
        logging.error(traceback.format_exc())
        return SiteV2(name=site.site, state="Error"), hosts, switches


def load_switch(switch_name: str, switch: Node) -> SwitchInfo:
    return SwitchInfo(model=switch_name,
                      capacity=switch.capacities.unit if switch.capacities else None,
                      allocated=switch.capacity_allocations.unit if switch.capacity_allocations else None)


def load_host(site_name: str, host_name: str, host: Node) -> HostInfo:
    components = {}
    for model_name, component in host.components.items():
        capacity = component.capacities.unit if component.capacities else None
        alloc = component.capacity_allocations.unit if component.capacity_allocations else None

        # The original code's logic for aggregating components is flawed for dataclasses/frozen.
        # It's better to replace the component if the model name is the same.
        if model_name not in components:
            components[model_name] = ComponentInfo(model=component.model,
                                                   capacity=capacity,
                                                   allocated=alloc)
        else:
            # Aggregate capacity/allocation if multiple components have the same model name
            existing = components[model_name]
            components[model_name] = ComponentInfo(
                model=existing.model,
                capacity=(existing.capacity or 0) + (capacity or 0),
                allocated=(existing.allocated or 0) + (alloc or 0),
            )

    return HostInfo(
        name=host_name,
        site=site_name,
        components=components,
        cores_capacity=host.capacities.core if host.capacities else None,
        ram_capacity=host.capacities.ram if host.capacities else None,
        disk_capacity=host.capacities.disk if host.capacities else None,
        cores_allocated=host.capacity_allocations.core if host.capacity_allocations else None,
        ram_allocated=host.capacity_allocations.ram if host.capacity_allocations else None,
        disk_allocated=host.capacity_allocations.disk if host.capacity_allocations else None,
    )

