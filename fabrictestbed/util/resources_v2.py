
#!/usr/bin/env python3
# MIT License
#
# ResourcesV2: fast, typed, lazy index over FIM AdvertizedTopology
# providing normalized views for sites, hosts, facility ports, and links.
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

try:
    from fim.user.topology import AdvertizedTopology
except Exception:  # pragma: no cover
    AdvertizedTopology = object  # type: ignore

from site_v2 import SiteV2, HostInfo, ComponentInfo, FacilityPortInfo, LinkInfo, LinkEndpoint


@dataclass
class ResourcesV2:
    """
    A robust, normalized index over a FIM AdvertizedTopology (or compatible dict).
    - Fast lookups by site/host
    - Safe getattr with defensive fallbacks
    - Minimal assumptions about exact FIM internals; relies on common attributes
    """
    topology: Any
    _sites: Dict[str, SiteV2] = field(default_factory=dict, init=False, repr=False)

    # Internal caches
    _hosts_by_site: Dict[str, Dict[str, HostInfo]] = field(default_factory=dict, init=False, repr=False)
    _facility_ports_by_site: Dict[str, Dict[str, FacilityPortInfo]] = field(default_factory=dict, init=False, repr=False)
    _links_by_site: Dict[str, List[LinkInfo]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._index_everything()

    # ----------------------------
    # Public API
    # ----------------------------
    @property
    def sites(self) -> Mapping[str, SiteV2]:
        return self._sites

    def get_site(self, name: str) -> Optional[SiteV2]:
        return self._sites.get(name)

    def list_site_names(self) -> List[str]:
        return list(self._sites.keys())

    def list_hosts(self) -> List[HostInfo]:
        out: List[HostInfo] = []
        for hosts in self._hosts_by_site.values():
            out.extend(hosts.values())
        return out

    def list_facility_ports(self) -> List[FacilityPortInfo]:
        out: List[FacilityPortInfo] = []
        for fps in self._facility_ports_by_site.values():
            out.extend(fps.values())
        return out

    def list_links(self) -> List[LinkInfo]:
        out: List[LinkInfo] = []
        for links in self._links_by_site.values():
            out.extend(links)
        # Deduplicate by (name, endpoints) if some links are visible at multiple sites
        seen = set()
        deduped: List[LinkInfo] = []
        for l in out:
            key = (l.name, tuple((e.site, e.node, e.port) for e in l.endpoints))
            if key not in seen:
                seen.add(key)
                deduped.append(l)
        return deduped

    # ----------------------------
    # Indexing helpers
    # ----------------------------
    def _index_everything(self) -> None:
        """
        Build indices for sites, hosts, facility ports, and links.
        Tries both wrapper-friendly access and FIM-native access.
        """
        self._index_sites()
        self._index_hosts()
        self._index_facility_ports()
        self._index_links()
        # Bind indices back to SiteV2 objects for convenience access
        for site_name, site in self._sites.items():
            site._hosts_index = self._hosts_by_site.get(site_name, {})
            site._facility_ports_index = self._facility_ports_by_site.get(site_name, {})
            site._links_index = {site_name: self._links_by_site.get(site_name, [])}

    def _index_sites(self) -> None:
        # Try multiple ways to fetch sites from topology
        if hasattr(self.topology, "sites"):
            fim_sites = getattr(self.topology, "sites")
            if isinstance(fim_sites, dict):
                items = fim_sites.items()
            else:
                items = [(getattr(s, "name", f"site-{i}"), s) for i, s in enumerate(list(fim_sites))]
        elif hasattr(self.topology, "get_sites"):
            s_list = self.topology.get_sites()
            items = [(getattr(s, "name", f"site-{i}"), s) for i, s in enumerate(list(s_list))]
        else:
            # If topology is a plain dict (JSON) with similar structure
            sites_dict = self.topology.get("sites", {}) if isinstance(self.topology, dict) else {}
            items = list(sites_dict.items())

        for site_name, s in items:
            address = getattr(s, "address", None)
            location = getattr(s, "location", None)
            state = getattr(s, "state", None)
            ptp_capable = getattr(s, "ptp_capable", None)
            self._sites[site_name] = SiteV2(
                name=site_name,
                address=address,
                location=location,
                state=state,
                ptp_capable=ptp_capable,
            )

    def _index_hosts(self) -> None:
        for site_name in self._sites.keys():
            self._hosts_by_site[site_name] = {}

        # Look for nodes inside topology; different FIM versions expose via .nodes or getters
        nodes = []
        if hasattr(self.topology, "nodes"):
            maybe = getattr(self.topology, "nodes")
            nodes = list(maybe.values()) if isinstance(maybe, dict) else list(maybe)
        elif hasattr(self.topology, "get_all_nodes"):
            nodes = list(self.topology.get_all_nodes())
        elif isinstance(self.topology, dict):
            nodes = self.topology.get("nodes", [])

        for n in nodes:
            # Attempt to classify compute/host nodes; prefer robust attribute checks
            kind = getattr(n, "node_type", getattr(n, "class_kind", None))
            kind_s = str(kind).lower() if kind else ""
            if kind_s not in {"server", "node", "compute"}:
                # Skip non-host nodes (switches, routers, facility ports, etc.)
                continue

            host_name = getattr(n, "name", None)
            site_name = getattr(n, "site", None)
            if not host_name or not site_name or site_name not in self._sites:
                continue

            cores_cap = getattr(n, "cores_capacity", None)
            cores_alloc = getattr(n, "cores_allocated", None)
            ram_cap = getattr(n, "ram_capacity", None)
            ram_alloc = getattr(n, "ram_allocated", None)
            disk_cap = getattr(n, "disk_capacity", None)
            disk_alloc = getattr(n, "disk_allocated", None)

            # Components (if any)
            components_map: Dict[str, ComponentInfo] = {}
            comps = getattr(n, "components", None)
            if isinstance(comps, dict):
                for model, comp in comps.items():
                    cap = getattr(getattr(comp, "capacities", None), "unit", None)
                    alloc = getattr(getattr(comp, "allocations", None), "unit", None)
                    components_map[model] = ComponentInfo(model=model, capacity=cap, allocated=alloc)

            self._hosts_by_site[site_name][host_name] = HostInfo(
                name=host_name,
                site=site_name,
                cores_capacity=cores_cap,
                cores_allocated=cores_alloc,
                ram_capacity=ram_cap,
                ram_allocated=ram_alloc,
                disk_capacity=disk_cap,
                disk_allocated=disk_alloc,
                components=components_map,
            )

    def _index_facility_ports(self) -> None:
        for site_name in self._sites.keys():
            self._facility_ports_by_site[site_name] = {}

        # Facility ports may be attached to nodes or link endpoints. Scan links first.
        links = []
        if hasattr(self.topology, "links"):
            maybe = getattr(self.topology, "links")
            links = list(maybe.values()) if isinstance(maybe, dict) else list(maybe)
        elif hasattr(self.topology, "get_all_links"):
            links = list(self.topology.get_all_links())
        elif isinstance(self.topology, dict):
            links = self.topology.get("links", [])

        for l in links:
            endpoints = getattr(l, "interfaces", getattr(l, "endpoints", []))
            for ep in endpoints or []:
                cls = getattr(ep, "class_kind", getattr(ep, "type", ""))
                cls_s = str(cls).lower()
                if cls_s not in {"facilityport", "facility_port"}:
                    continue
                site_name = getattr(ep, "site", None)
                if site_name not in self._sites:
                    continue
                name = getattr(ep, "name", None) or getattr(ep, "port", None)
                labels = getattr(ep, "labels", None)
                vlans = getattr(ep, "vlans", None)
                port = getattr(ep, "port", None)
                switch = getattr(ep, "switch", None)
                if name:
                    self._facility_ports_by_site[site_name][name] = FacilityPortInfo(
                        site=site_name, name=name, labels=labels, vlans=vlans, port=port, switch=switch
                    )

    def _index_links(self) -> None:
        for site_name in self._sites.keys():
            self._links_by_site[site_name] = []

        links = []
        if hasattr(self.topology, "links"):
            maybe = getattr(self.topology, "links")
            links = list(maybe.values()) if isinstance(maybe, dict) else list(maybe)
        elif hasattr(self.topology, "get_all_links"):
            links = list(self.topology.get_all_links())
        elif isinstance(self.topology, dict):
            links = self.topology.get("links", [])

        for l in links:
            endpoints = getattr(l, "interfaces", getattr(l, "endpoints", [])) or []
            eps: List[LinkEndpoint] = []
            sites_seen: set = set()
            for ep in endpoints:
                site_name = getattr(ep, "site", None)
                node = getattr(ep, "node", None)
                port = getattr(ep, "name", None) or getattr(ep, "port", None)
                eps.append(LinkEndpoint(site=site_name, node=node, port=port))
                if site_name in self._sites:
                    sites_seen.add(site_name)

            link_info = LinkInfo(
                name=getattr(l, "name", None),
                layer=getattr(l, "layer", None),
                labels=getattr(l, "labels", None),
                bandwidth=getattr(l, "bandwidth", None),
                endpoints=eps,
            )
            for s in sites_seen:
                self._links_by_site[s].append(link_info)
