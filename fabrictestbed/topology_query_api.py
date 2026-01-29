
#!/usr/bin/env python3
# MIT License
#
# FabricManagerV2 Query API: sites, hosts, facility_ports, links with filtering & pagination.
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Literal

from fim.user.topology import AdvertizedTopology

from fabrictestbed.external_api.orchestrator_client import OrchestratorClient

Record = Dict[str, Any]
FilterFunc = Optional[Callable[[Record], bool]]

def get_logger(name: str = "fabric.manager", level: int = logging.INFO) -> logging.Logger:
    return logging.getLogger(name)


def _apply_filters(data: Iterable[Record], filters: FilterFunc) -> List[Record]:
    """
    Apply a lambda/callable filter function to records.

    :param data: Iterable of records to filter
    :param filters: Optional lambda function that takes a record and returns bool
    :return: List of records that match the filter

    Lambda Filter Best Practices:
        - Always use .get() with defaults: r.get('field', 0)
        - Check for None values: r.get('field') is not None
        - Use .lower() for case-insensitive string matching
        - Type safety: ensure comparisons match field types

    Site Filter Examples:
        # Sites with >= 64 cores available
        lambda r: r.get('cores_available', 0) >= 64

        # Sites at specific locations
        lambda r: r.get('name') in ['RENC', 'UCSD', 'STAR']

        # Sites with GPUs
        lambda r: 'GPU' in r.get('components', {})

        # Complex: Sites with GPUs AND high resources
        lambda r: 'GPU' in r.get('components', {}) and r.get('cores_available', 0) >= 100

    Host Filter Examples:
        # Hosts at UCSD
        lambda r: r.get('site') == 'UCSD'

        # Hosts with Tesla T4 GPUs
        lambda r: 'GPU-Tesla T4' in r.get('components', {})

        # Hosts with available GPUs (capacity > allocated)
        lambda r: any(
            r.get('components', {}).get(comp, {}).get('capacity', 0) >
            r.get('components', {}).get(comp, {}).get('allocated', 0)
            for comp in r.get('components', {}).keys() if 'GPU' in comp
        )

        # Complex: UCSD hosts with >=32 cores AND GPUs
        lambda r: (
            r.get('site') == 'UCSD' and
            r.get('cores_available', 0) >= 32 and
            any('GPU' in comp for comp in r.get('components', {}).keys())
        )

    Facility Port Filter Examples:
        # Ports at UCSD
        lambda r: r.get('site') == 'UCSD'

        # Ports at multiple sites
        lambda r: r.get('site') in ['UCSD', 'STAR', 'BRIST']

        # Ports with specific VLAN range (check labels)
        lambda r: '3110-3119' in r.get('labels', {}).get('vlan_range', [])

        # Cloud facility ports
        lambda r: r.get('site') in ['GCP', 'AWS', 'AZURE']

        # StarLight ports
        lambda r: 'StarLight' in r.get('name', '')

        # 400G ports
        lambda r: '400G' in r.get('name', '')

    Link Filter Examples:
        # High-bandwidth links (>=100 Gbps)
        lambda r: r.get('bandwidth', 0) >= 100

        # L1 links only
        lambda r: r.get('layer') == 'L1'

        # L2 links only
        lambda r: r.get('layer') == 'L2'

        # Links with HundredGigE ports
        lambda r: any('HundredGigE' in ep.get('port', '') for ep in r.get('endpoints', []))

        # Links connecting specific switches (by name)
        lambda r: 'ucsd-data-sw' in r.get('name', '').lower()

        # Links between specific switches
        lambda r: 'losa-data-sw' in r.get('name', '').lower() and 'ucsd-data-sw' in r.get('name', '').lower()
    """
    if filters is None:
        return list(data)
    return [r for r in data if filters(r)]


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
    ) -> AdvertizedTopology:
        return self.orch.resources(
            token=id_token,
            level=level,
            force_refresh=force_refresh,
            start=start_date,
            end=end_date,
            includes=includes,
            excludes=excludes,
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
    ) -> AdvertizedTopology:
        return self.orch.portal_resources(
            graph_format=graph_format,
            level=level,
            force_refresh=force_refresh,
            start=start_date,
            end=end_date,
            includes=includes,
            excludes=excludes,
        )

    def resources_summary(self, *, id_token: str = None, level: int = 2,
                           resource_type: str = None) -> Optional[Dict[str, Any]]:
        """
        Try to get resources summary (JSON) from the orchestrator.
        Returns None if the endpoint is not available.
        """
        try:
            if not id_token:
                token = self._resolve_token(id_token)
            if id_token:
                return self.orch.resources_summary(
                    token=id_token, level=level, resource_type=resource_type
                )
            else:
                return self.orch.portal_resources_summary(
                    level=level, resource_type=resource_type
                )
        except Exception:
            self.log.debug("resources_summary endpoint not available, falling back to graph-based path")
            return None

    def _resolve_token(self, id_token: Optional[str] = None) -> Optional[str]:
        """
        Resolve the id_token to use, either from parameter or from ensure_valid_id_token().

        :param id_token: Optional explicit token
        :return: Resolved token or None for unauthenticated calls
        """
        if id_token:
            return id_token
        # Check if subclass has ensure_valid_id_token (e.g., FabricManagerV2)
        if hasattr(self, 'ensure_valid_id_token'):
            try:
                return self.ensure_valid_id_token()
            except Exception:
                pass
        return None

    def query_sites(
        self,
        *,
        id_token: Optional[str] = None,
        filters: FilterFunc = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[List[Record]]:
        """
        Query sites with optional lambda filter.

        Site Record Fields:
            - name (str): Site identifier (e.g., "SRI", "RENC", "UCSD")
            - state (str/null): Site state
            - address (str): Physical address
            - location (list): [latitude, longitude]
            - ptp_capable (bool): PTP clock support
            - ipv4_management (bool): IPv4 management support
            - cores_capacity (int): Total CPU cores
            - cores_allocated (int): Cores in use
            - cores_available (int): Cores free
            - ram_capacity (int): Total RAM in GB
            - ram_allocated (int): RAM in use (GB)
            - ram_available (int): RAM free (GB)
            - disk_capacity (int): Total disk in GB
            - disk_allocated (int): Disk in use (GB)
            - disk_available (int): Disk free (GB)
            - hosts (list[str]): Worker hostnames
            - components (dict): Component details (GPUs, NICs, FPGAs)

        Filter Examples:
            # Sites with ≥64 cores available
            lambda r: r.get('cores_available', 0) >= 64

            # Sites with ≥256 GB RAM available
            lambda r: r.get('ram_available', 0) >= 256

            # Sites at specific locations
            lambda r: r.get('name') in ['RENC', 'UCSD', 'STAR']

            # Sites with GPUs
            lambda r: 'GPU' in r.get('components', {})

            # PTP-capable sites with high resources
            lambda r: r.get('ptp_capable') == True and r.get('cores_available', 0) >= 64

            # Complex: Sites with ≥32 cores AND ≥128 GB RAM
            lambda r: r.get('cores_available', 0) >= 32 and r.get('ram_available', 0) >= 128

        :param id_token: Optional authentication token. If not provided and the object has
                        ensure_valid_id_token(), it will be called automatically.
        :param filters: Optional lambda function string to filter sites (see examples above)
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: List of site records matching the filter
        """
        token = self._resolve_token(id_token)
        summary = self.resources_summary(id_token=token, level=2, resource_type="sites")
        if summary and "sites" in summary:
            items = summary["sites"]
            items = _apply_filters(items, filters)
            return _paginate(items, limit=limit, offset=offset)
        return None

    def query_hosts(
        self,
        *,
        id_token: Optional[str] = None,
        filters: FilterFunc = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[List[Record]]:
        """
        Query hosts with optional lambda filter.

        Host Record Fields:
            - name (str): Worker hostname (e.g., "ucsd-w5.fabric-testbed.net")
            - site (str): Site name (e.g., "UCSD", "RENC")
            - cores_capacity (int): Total CPU cores
            - cores_allocated (int): Cores in use
            - cores_available (int): Cores free
            - ram_capacity (int): Total RAM in GB
            - ram_allocated (int): RAM in use (GB)
            - ram_available (int): RAM free (GB)
            - disk_capacity (int): Total disk in GB
            - disk_allocated (int): Disk in use (GB)
            - disk_available (int): Disk free (GB)
            - components (dict): Component details with structure:
                {
                  "GPU-Tesla T4": {"capacity": 2, "allocated": 0},
                  "SmartNIC-ConnectX-5": {"capacity": 2, "allocated": 0},
                  "NVME-P4510": {"capacity": 4, "allocated": 0},
                  "SharedNIC-ConnectX-6": {"capacity": 127, "allocated": 8}
                }

        Filter Examples:
            # Hosts at UCSD
            lambda r: r.get('site') == 'UCSD'

            # Hosts with ≥32 cores available
            lambda r: r.get('cores_available', 0) >= 32

            # Hosts with any GPU
            lambda r: any('GPU' in comp for comp in r.get('components', {}).keys())

            # Hosts with Tesla T4 GPUs
            lambda r: 'GPU-Tesla T4' in r.get('components', {})

            # Hosts with available Tesla T4 GPUs (not fully allocated)
            lambda r: r.get('components', {}).get('GPU-Tesla T4', {}).get('capacity', 0) > r.get('components', {}).get('GPU-Tesla T4', {}).get('allocated', 0)

            # Hosts with ConnectX-6 NICs
            lambda r: any('ConnectX-6' in comp for comp in r.get('components', {}).keys())

            # Hosts with SmartNICs
            lambda r: any('SmartNIC' in comp for comp in r.get('components', {}).keys())

            # Complex: UCSD hosts with ≥32 cores AND GPUs
            lambda r: r.get('site') == 'UCSD' and r.get('cores_available', 0) >= 32 and any('GPU' in comp for comp in r.get('components', {}).keys())

            # Complex: High-resource hosts with Tesla T4
            lambda r: r.get('cores_available', 0) >= 64 and r.get('ram_available', 0) >= 256 and 'GPU-Tesla T4' in r.get('components', {})

        :param id_token: Optional authentication token. If not provided and the object has
                        ensure_valid_id_token(), it will be called automatically.
        :param filters: Optional lambda function string to filter hosts (see examples above)
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: List of host records matching the filter
        """
        token = self._resolve_token(id_token)
        summary = self.resources_summary(id_token=token, level=2, resource_type="hosts")
        if summary and "hosts" in summary:
            items = summary["hosts"]
            items = _apply_filters(items, filters)
            return _paginate(items, limit=limit, offset=offset)
        return None

    def query_facility_ports(
        self,
        *,
        id_token: Optional[str] = None,
        filters: FilterFunc = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[List[Record]]:
        """
        Query facility ports with optional lambda filter.

        Facility Port Record Fields:
            - site (str): Site name (e.g., "BRIST", "STAR", "UCSD", "GCP")
            - name (str): Facility port name (e.g., "SmartInternetLab-BRIST", "StarLight-400G-1-STAR")
            - port (str): Port identifier (e.g., "SmartInternetLab-BRIST-int")
            - switch (str): Switch port mapping (e.g., "port+brist-data-sw:HundredGigE0/0/0/21:facility+...")
            - labels (dict): Metadata including vlan_range and optional fields:
                {
                  "vlan_range": ["3110-3119"],
                  "local_name": "Bundle-Ether110",
                  "device_name": "agg4.sanj",
                  "region": "sjc-zone2-6"
                }
            - vlans (str): String representation of VLAN ranges (e.g., "['3110-3119']")
                Note: This is a STRING, not a list!
            - allocated_vlans (str/null): Allocated VLANs from label allocations (stringified)

        Filter Examples:
            # Ports at specific site
            lambda r: r.get('site') == 'UCSD'

            # Ports at multiple sites
            lambda r: r.get('site') in ['UCSD', 'STAR', 'BRIST']

            # Ports by name pattern
            lambda r: 'NRP' in r.get('name', '')

            # Ports with specific VLAN range (check labels, not vlans string)
            lambda r: '3110-3119' in r.get('labels', {}).get('vlan_range', [])

            # Cloud facility ports
            lambda r: r.get('site') in ['GCP', 'AWS', 'AZURE']

            # Ports with wide VLAN range (multiple ranges)
            lambda r: len(r.get('labels', {}).get('vlan_range', [])) > 2

            # StarLight facility ports
            lambda r: 'StarLight' in r.get('name', '')

            # 400G ports
            lambda r: '400G' in r.get('name', '')

            # Ports with HundredGigE switch connection
            lambda r: 'HundredGigE' in r.get('switch', '')

            # Ports in specific region (cloud)
            lambda r: r.get('labels', {}).get('region') == 'sjc-zone2-6'

        :param id_token: Optional authentication token. If not provided and the object has
                        ensure_valid_id_token(), it will be called automatically.
        :param filters: Optional lambda function string to filter facility ports (see examples above)
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: List of facility port records matching the filter
        """
        token = self._resolve_token(id_token)
        summary = self.resources_summary(id_token=token, level=2, resource_type="facility_ports")
        if summary and "facility_ports" in summary:
            items = summary["facility_ports"]
            items = _apply_filters(items, filters)
            return _paginate(items, limit=limit, offset=offset)
        return None

    def query_links(
        self,
        *,
        id_token: Optional[str] = None,
        filters: FilterFunc = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[List[Record]]:
        """
        Query links with optional lambda filter.

        Link Record Fields:
            - name (str): Link identifier (e.g., "link:local-port+losa-data-sw:HundredGigE0/0/0/15...")
            - layer (str): Network layer ("L1" or "L2")
            - labels (dict/null): Additional metadata
            - bandwidth (int): Link bandwidth in Gbps
            - allocated_bandwidth (int/null): Allocated link bandwidth in Gbps
            - sites (tuple[str, str, ...]/null): Site names derived from trunk interface names
            - endpoints (list): List of endpoint dicts with structure:
                [
                  {"site": "RENC", "node": "uuid-string", "port": "HundredGigE0/0/0/15.3370"},
                  {"site": "STAR", "node": "uuid-string", "port": "TenGigE0/0/0/22/0.3370"}
                ]

        Filter Examples:
            # Links with ≥100 Gbps bandwidth
            lambda r: r.get('bandwidth', 0) >= 100

            # L1 links only
            lambda r: r.get('layer') == 'L1'

            # L2 links only
            lambda r: r.get('layer') == 'L2'

            # High-bandwidth L1 links
            lambda r: r.get('layer') == 'L1' and r.get('bandwidth', 0) >= 80

            # Links with HundredGigE ports
            lambda r: any('HundredGigE' in ep.get('port', '') for ep in r.get('endpoints', []))

            # Links with TenGigE ports
            lambda r: any('TenGigE' in ep.get('port', '') for ep in r.get('endpoints', []))

            # Links connecting specific switches (by name in link identifier)
            lambda r: 'ucsd-data-sw' in r.get('name', '').lower()

            # Links between specific switches
            lambda r: (
                'losa-data-sw' in r.get('name', '').lower() and
                'ucsd-data-sw' in r.get('name', '').lower()
            )

            # Low-bandwidth L2 links (potential bottlenecks)
            lambda r: r.get('layer') == 'L2' and r.get('bandwidth', 0) < 10

        :param id_token: Optional authentication token. If not provided and the object has
                        ensure_valid_id_token(), it will be called automatically.
        :param filters: Optional lambda function string to filter links (see examples above)
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip
        :return: List of link records matching the filter
        """
        token = self._resolve_token(id_token)
        summary = self.resources_summary(id_token=token, level=2, resource_type="links")
        if summary and "links" in summary:
            items = summary["links"]
            items = _apply_filters(items, filters)
            return _paginate(items, limit=limit, offset=offset)
        return None

