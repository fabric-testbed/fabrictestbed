#!/usr/bin/env python3
# MIT License
#
# ResourcesV2: fast, typed, lazy index over FIM AdvertizedTopology
# providing normalized views for sites, hosts, facility ports, and links.
#
# Author: Komal Thareja (kthare10@renci.org)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from fim.user.topology import AdvertizedTopology
from fim.user import interface, link


from fabrictestbed.util.site_v2 import SiteV2, HostInfo, ComponentInfo, FacilityPortInfo, LinkInfo, LinkEndpoint, \
    load_site, SwitchInfo


@dataclass
class ResourcesV2:
    """
    A robust, normalized index over a FIM AdvertizedTopology (or compatible dict).
    - Fast lookups by site/host
    - Safe getattr with defensive fallbacks
    - Minimal assumptions about exact FIM internals; relies on common attributes
    """
    topology: AdvertizedTopology
    _sites: Dict[str, SiteV2] = field(default_factory=dict, init=False, repr=False)

    # Internal caches
    _hosts_by_site: Dict[str, Dict[str, HostInfo]] = field(default_factory=dict, init=False, repr=False)
    _switches_by_site: Dict[str, Dict[str, SwitchInfo]] = field(default_factory=dict, init=False, repr=False)
    _facility_ports_by_site: Dict[str, Dict[str, FacilityPortInfo]] = field(default_factory=dict, init=False,
                                                                            repr=False)
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
        for site_hosts in self._hosts_by_site.values():
            out.extend(site_hosts.values())
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
            # Sort endpoints for consistent key
            endpoints_key = tuple(sorted((e.site, e.node, e.port) for e in l.endpoints))
            key = (l.name, endpoints_key)
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
        self._index_facility_ports()
        self._index_links()
        # Bind indices back to SiteV2 objects for convenience access
        for site_name, site in self._sites.items():
            site._hosts_index = self._hosts_by_site.get(site_name, {})
            site._facility_ports_index = self._facility_ports_by_site.get(site_name, {})
            site._links_index = {site_name: self._links_by_site.get(site_name, [])}

    def _index_sites(self) -> None:
        """
        Load SiteV2 objects from the topology's sites.
        """
        sites_dict = self.topology.sites
        for site_name, site in sites_dict.items():
            loaded_site, hosts, switches = load_site(site)
            if len(hosts) == 0:
                continue
            self._sites[site_name] = loaded_site
            # The loaded_site has a 'hosts' attribute from load_site; extract it for the main index
            self._hosts_by_site[site_name] = hosts
            self._switches_by_site[site_name] = switches

    def _index_facility_ports(self) -> None:
        """
        Build index of facility ports from the topology's facilities.
        """
        self._facility_ports_by_site.clear()

        for fp in self.topology.facilities.values():
            site_name = fp.site
            if site_name not in self._facility_ports_by_site:
                self._facility_ports_by_site[site_name] = {}

            for iface in fp.interface_list:
                # Assuming iface is a fim.user.interface.Interface
                # Determine VLANS
                vlan_range = None
                if iface.labels and iface.labels.vlan_range:
                    vlan_range = str(iface.labels.vlan_range)
                elif iface.labels and iface.labels.vlan:
                    vlan_range = str([iface.labels.vlan])

                facility_port_info = FacilityPortInfo(
                    site=site_name,
                    name=fp.name,
                    port=iface.name,  # Using interface name as port name, or could use local_name/device_name
                    switch=iface.node_id,  # The node_id of the interface is the switch's node_id
                    labels=iface.labels.to_dict() if iface.labels else None,
                    vlans=vlan_range,
                )

                # Use the unique facility name (fp.name) as the primary key for the port
                self._facility_ports_by_site[site_name][fp.name] = facility_port_info

    def _index_links(self) -> None:
        """
        Build index of links from the topology's links.
        """
        self._links_by_site.clear()

        for _, l in self.topology.links.items():
            link_info = self._link_to_linkinfo(l)
            if link_info:
                # Distribute the link_info to the sites it touches
                for endpoint in link_info.endpoints:
                    if endpoint.site:
                        if endpoint.site not in self._links_by_site:
                            self._links_by_site[endpoint.site] = []
                        self._links_by_site[endpoint.site].append(link_info)

    def _link_to_linkinfo(self, l: link.Link) -> Optional[LinkInfo]:
        """Convert a FIM Link object into a LinkInfo dataclass."""
        endpoints = []
        for iface in l.interface_list:
            # Extract site/node/port from the interface
            # Note: FIM interfaces on links often only have node_id/name.
            # We must derive site and node from the overall topology if needed,
            # but for simplicity, we use the name components if available.

            # Common FABRIC Link Interface naming: site_node_port
            parts = iface.name.split('_')
            site_name = parts[0] if len(parts) >= 1 else None
            node_name = parts[1] if len(parts) >= 2 else None
            port_name = parts[-1] if len(parts) >= 3 else None

            # Fallback/refinement: iface.node_id is often the node's FIM ID,
            # and iface.labels.local_name/device_name can be the port.
            if site_name not in self.topology.sites:
                # Try to get the site from the node_id
                # This requires a deeper search into the topology which is costly.
                # Assuming the name is canonical (site_node_port) for now.
                pass

            endpoints.append(LinkEndpoint(
                site=site_name,
                node=node_name or iface.node_id,
                port=port_name or iface.name
            ))

        return LinkInfo(
            name=l.node_id,  # Link's node_id is its FIM name
            layer=str(l.layer) if l.layer else None,
            labels=l.labels.to_dict() if l.labels else None,
            bandwidth=l.capacities.bw if l.capacities else None,
            endpoints=endpoints
        )
