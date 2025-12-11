#!/usr/bin/env python3
# MIT License
#
# ResourcesV2: fast, typed, lazy index over FIM AdvertizedTopology
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from fim.user.topology import AdvertizedTopology

from fabrictestbed.util.site_v2 import (
    SiteV2, HostInfo, FacilityPortInfo, LinkInfo, LinkEndpoint,
    load_site, SwitchInfo
)


@dataclass
class ResourcesV2:
    """Normalized, high-performance index over a FIM AdvertizedTopology."""
    topology: AdvertizedTopology

    _sites: Dict[str, SiteV2] = field(default_factory=dict, init=False, repr=False)
    _hosts_by_site: Dict[str, Dict[str, HostInfo]] = field(default_factory=dict, init=False, repr=False)
    _switches_by_site: Dict[str, Dict[str, SwitchInfo]] = field(default_factory=dict, init=False, repr=False)

    # Lazy caches
    _facility_ports_by_site: Optional[Dict[str, Dict[str, FacilityPortInfo]]] = field(default=None, init=False, repr=False)
    _node_index: Optional[Dict[str, Tuple[str, str]]] = field(default=None, init=False, repr=False)
    _links_by_site_idx: Optional[Dict[str, List[int]]] = field(default=None, init=False, repr=False)
    _all_links: Optional[List[LinkInfo]] = field(default=None, init=False, repr=False)

    # -----------------------------------------------------
    def __post_init__(self) -> None:
        self._index_sites()

    # -----------------------------------------------------
    @property
    def sites(self) -> Mapping[str, SiteV2]:
        return self._sites

    def get_site(self, name: str) -> Optional[SiteV2]:
        s = self._sites.get(name)
        if not s:
            return None
        s._hosts_index = self._hosts_by_site.get(name, {})
        if self._facility_ports_by_site:
            s._facility_ports_index = self._facility_ports_by_site.get(name, {})
        if self._links_by_site_idx and self._all_links:
            s._links_index = {name: [self._all_links[i] for i in self._links_by_site_idx.get(name, [])]}
        return s

    def list_site_names(self) -> List[str]:
        return list(self._sites.keys())

    def list_hosts(self) -> List[HostInfo]:
        out: List[HostInfo] = []
        for site_hosts in self._hosts_by_site.values():
            out.extend(site_hosts.values())
        return out

    def list_facility_ports(self) -> List[FacilityPortInfo]:
        self._ensure_facility_ports()
        out: List[FacilityPortInfo] = []
        for fps in self._facility_ports_by_site.values():
            out.extend(fps.values())
        return out

    def list_links(self) -> List[LinkInfo]:
        self._ensure_links()
        return list(self._all_links or [])

    # -----------------------------------------------------
    # Indexing helpers
    # -----------------------------------------------------
    def _index_sites(self) -> None:
        for site_name, site in self.topology.sites.items():
            loaded_site, hosts, switches = load_site(site)
            if not hosts:
                continue

            # Store in master dicts
            self._sites[site_name] = loaded_site
            self._hosts_by_site[site_name] = hosts
            self._switches_by_site[site_name] = switches

            # HYDRATE the SiteV2 so it’s self-contained
            loaded_site._hosts_index = hosts
            loaded_site._switches_index = switches
            # facility ports / links remain lazy; they’ll be attached later on demand

    def _ensure_facility_ports(self) -> None:
        if self._facility_ports_by_site is not None:
            return
        fps_by_site: Dict[str, Dict[str, FacilityPortInfo]] = {}
        for fp in self.topology.facilities.values():
            site_name = fp.site
            site_bucket = fps_by_site.setdefault(site_name, {})
            for idx, iface in enumerate(fp.interface_list):
                labs = getattr(iface, "labels", None)
                local_name = getattr(labs, "local_name", None) if labs else None
                device_name = getattr(labs, "device_name", None) if labs else None

                # Try peers to fill in local/device name if missing (fablib behavior)
                if not local_name:
                    try:
                        for peer in iface.get_peers():
                            peer_labels = getattr(peer, "labels", None)
                            if peer_labels and getattr(peer_labels, "local_name", None):
                                local_name = getattr(peer_labels, "local_name", None)
                                if not device_name:
                                    device_name = getattr(peer_labels, "device_name", None)
                                break
                    except Exception:
                        pass

                label_allocations = None
                try:
                    label_allocations = iface.get_property("label_allocations")
                except Exception:
                    # property may not exist; best-effort only
                    label_allocations = None

                vlan_range = None
                if labs:
                    vr = getattr(labs, "vlan_range", None)
                    if vr:
                        vlan_range = str(vr)
                    else:
                        v = getattr(labs, "vlan", None)
                        if v is not None:
                            vlan_range = str([v])

                allocated_vlans = None
                if label_allocations:
                    alloc_vlan = getattr(label_allocations, "vlan", None)
                    if alloc_vlan is not None:
                        allocated_vlans = str(alloc_vlan)

                port_name = local_name or device_name or getattr(iface, "name", None)
                # Use interface-specific key so multiple interfaces per facility are kept
                # Ensure uniqueness even if node_id is reused across interfaces
                fp_key_parts = [
                    fp.name,
                    getattr(iface, "node_id", "") or "",
                    getattr(iface, "name", "") or "",
                    str(idx),
                ]
                fp_key = "|".join(fp_key_parts)

                site_bucket[fp_key] = FacilityPortInfo(
                    site=site_name,
                    name=fp.name,
                    port=port_name,
                    switch=getattr(iface, "node_id", None),
                    labels=labs,
                    vlans=vlan_range,
                    allocated_vlans=allocated_vlans,
                )
        self._facility_ports_by_site = fps_by_site

    def _build_node_index(self) -> None:
        if self._node_index is not None:
            return
        idx: Dict[str, Tuple[str, str]] = {}
        for site_name, site in self.topology.sites.items():
            for node_name, child in getattr(site, "children", {}).items():
                node_id = getattr(child, "node_id", None)
                if node_id:
                    idx[node_id] = (site_name, node_name)
        self._node_index = idx

    def _ensure_links(self) -> None:
        if self._all_links is not None:
            return
        self._build_node_index()
        node_idx = self._node_index

        all_links: List[LinkInfo] = []
        site_to_indices: Dict[str, List[int]] = {}

        for _, L in self.topology.links.items():
            site_names: Optional[Tuple[str, ...]] = None
            if getattr(L, "interface_list", None):
                first_iface = L.interface_list[0]
                iface_type = getattr(getattr(first_iface, "type", None), "name", None)
                iface_name = getattr(first_iface, "name", None)
                if iface_type == "TrunkPort" and iface_name:
                    parts = iface_name.split("_")
                    if parts and "HundredGig" not in parts[0]:
                        site_names = tuple(parts)

            endpoints: List[LinkEndpoint] = []
            for idx, iface in enumerate(L.interface_list):
                site_name, node_name = (None, None)
                if node_idx and getattr(iface, "node_id", None) in node_idx:
                    site_name, node_name = node_idx[iface.node_id]
                if site_name is None and site_names and idx < len(site_names):
                    site_name = site_names[idx]

                labs = getattr(iface, "labels", None)
                port = getattr(labs, "local_name", None) or getattr(labs, "device_name", None)
                port = port or getattr(iface, "name", None)

                endpoints.append(LinkEndpoint(
                    site=site_name,
                    node=node_name or getattr(iface, "node_id", None),
                    port=port
                ))

            li = LinkInfo(
                name=getattr(L, "node_id", None),
                layer=str(getattr(L, "layer", None)) if getattr(L, "layer", None) else None,
                labels=getattr(L, "labels", None),
                bandwidth=getattr(getattr(L, "capacities", None), "bw", None),
                allocated_bandwidth=getattr(getattr(L, "capacity_allocations", None), "bw", None),
                sites=site_names,
                endpoints=endpoints,
            )
            idx = len(all_links)
            all_links.append(li)
            for ep in endpoints:
                if ep.site:
                    site_to_indices.setdefault(ep.site, []).append(idx)

        self._all_links = all_links
        self._links_by_site_idx = site_to_indices
