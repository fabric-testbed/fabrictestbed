#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2020 FABRIC Testbed
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
#
# Author: Komal Thareja (kthare10@renci.org)
import os
from datetime import datetime
from typing import Tuple, Union, List, Dict

from fabric_cf.orchestrator.swagger_client import Sliver, Slice
from fabric_cf.orchestrator.swagger_client.models import PoaData

from fabrictestbed.token_manager.token_manager import TokenManager
from fabrictestbed.slice_editor import ExperimentTopology, AdvertisedTopology, GraphFormat
from fabrictestbed.slice_manager import OrchestratorProxy, Status, SliceState
from fabrictestbed.util.constants import Constants
from fabrictestbed.util.utils import Utils


class SliceManagerException(Exception):
    """ Slice Manager Exception """


class SliceManager(TokenManager):
    """
    Implements User facing Control Framework API interface
    """
    def __init__(self, *, cm_host: str = None, oc_host: str = None, token_location: str = None, project_id: str = None,
                 scope: str = "all", initialize: bool = True, project_name: str = None, auto_refresh: bool = True):
        super().__init__(cm_host=cm_host, token_location=token_location, project_id=project_id, scope=scope,
                         project_name=project_name, auto_refresh=auto_refresh, initialize=initialize)
        if oc_host is None:
            oc_host = os.environ.get(Constants.FABRIC_ORCHESTRATOR_HOST)

        if oc_host is None:
            raise SliceManagerException(f"Invalid initialization parameters: oc_host: {oc_host}")

        self.oc_proxy = OrchestratorProxy(orchestrator_host=oc_host)

    def create(self, *, slice_name: str, ssh_key: Union[str, List[str]], topology: ExperimentTopology = None,
               slice_graph: str = None, lease_start_time: str = None,
               lease_end_time: str = None) -> Tuple[Status, Union[SliceManagerException, List[Sliver]]]:
        """
        Create a slice
        @param slice_name slice name
        @param ssh_key SSH Key(s)
        @param topology Experiment topology
        @param slice_graph Slice Graph string
        @param lease_start_time Lease Start Time
        @param lease_end_time Lease End Time
        @return Tuple containing Status and Exception/Json containing slivers created
        """
        if slice_name is None or not isinstance(slice_name, str) or ssh_key is None:
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_name or ssh key")

        if topology is not None and not isinstance(topology, ExperimentTopology):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - topology")

        if slice_graph is not None and not isinstance(slice_graph, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_graph")

        if lease_end_time is not None and not isinstance(lease_end_time, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - lease_end_time")

        try:
            return self.oc_proxy.create(token=self.ensure_valid_token(), slice_name=slice_name, ssh_key=ssh_key,
                                        topology=topology, slice_graph=slice_graph, lease_end_time=lease_end_time,
                                        lease_start_time=lease_start_time)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def modify(self, *, slice_id: str, topology: ExperimentTopology = None,
               slice_graph: str = None) -> Tuple[Status, Union[SliceManagerException, List[Sliver]]]:
        """
        Modify an existing slice
        @param slice_id slice id
        @param topology Experiment topology
        @param slice_graph Slice Graph string
        @return Tuple containing Status and Exception/Json containing slivers created
        """
        if slice_id is None or not isinstance(slice_id, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_id")

        if topology is not None and not isinstance(topology, ExperimentTopology):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - topology")

        if slice_graph is not None and not isinstance(slice_graph, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid argument - slice_graph")

        try:
            return self.oc_proxy.modify(token=self.ensure_valid_token(), slice_id=slice_id, topology=topology,
                                        slice_graph=slice_graph)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def modify_accept(self, *, slice_id: str) -> Tuple[Status, Union[SliceManagerException, ExperimentTopology]]:
        """
        Modify an existing slice
        @param slice_id slice id
        @return Tuple containing Status and Exception/Json containing slivers created
        """
        if slice_id is None or not isinstance(slice_id, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_id")

        try:
            if self._should_renew():
                self._load_tokens()
            return self.oc_proxy.modify_accept(token=self.get_id_token(), slice_id=slice_id)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def delete(self, *, slice_object: Slice = None) -> Tuple[Status, Union[SliceManagerException, None]]:
        """
        Delete slice(s)
        @param slice_object slice to be deleted
        @return Tuple containing Status and Exception/Json containing deletion status
        """
        try:
            slice_id = slice_object.slice_id if slice_object is not None else None
            return self.oc_proxy.delete(token=self.ensure_valid_token(), slice_id=slice_id)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def slices(self, includes: List[SliceState] = None, excludes: List[SliceState] = None, name: str = None,
               limit: int = 20, offset: int = 0, slice_id: str = None,
               as_self: bool = True) -> Tuple[Status, Union[SliceManagerException, List[Slice]]]:
        """
        Get slices
        @param includes list of the slice state used to include the slices in the output
        @param excludes list of the slice state used to exclude the slices from the output
        @param name name of the slice
        @param limit maximum number of slices to return
        @param offset offset of the first slice to return
        @param slice_id slice id
        @param as_self
        @return Tuple containing Status and Exception/Json containing slices
        """
        try:
            return self.oc_proxy.slices(token=self.ensure_valid_token(), includes=includes, excludes=excludes,
                                        name=name, limit=limit, offset=offset, slice_id=slice_id, as_self=as_self)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def get_slice_topology(self, *, slice_object: Slice, graph_format: GraphFormat = GraphFormat.GRAPHML,
                           as_self: bool = True) -> Tuple[Status, Union[SliceManagerException, ExperimentTopology]]:
        """
        Get slice topology
        @param slice_object Slice for which to retrieve the topology
        @param graph_format
        @param as_self
        @return Tuple containing Status and Exception/Json containing slice
        """
        if slice_object is None or not isinstance(slice_object, Slice):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_object")
        try:
            return self.oc_proxy.get_slice(token=self.ensure_valid_token(), slice_id=slice_object.slice_id,
                                           graph_format=graph_format, as_self=as_self)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def slivers(self, *, slice_object: Slice,
                as_self: bool = True) -> Tuple[Status, Union[SliceManagerException, List[Sliver]]]:
        """
        Get slivers
        @param slice_object list of the slices
        @param as_self
        @return Tuple containing Status and Exception/Json containing Sliver(s)
        """
        if slice_object is None or not isinstance(slice_object, Slice):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - slice_object")

        try:
            return self.oc_proxy.slivers(token=self.ensure_valid_token(), slice_id=slice_object.slice_id,
                                         as_self=as_self)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def resources(self, *, level: int = 1, force_refresh: bool = False, start: datetime = None, end: datetime = None,
                  includes: List[str] = None,
                  excludes: List[str] = None) -> Tuple[Status, Union[SliceManagerException, AdvertisedTopology]]:
        """
        Get resources
        @param level level
        @param force_refresh force_refresh
        @param start start time
        @param end end time
        @param includes list of sites to include
        @param excludes list of sites to exclude
        @return Tuple containing Status and Exception/Json containing Resources
        """
        try:
            return self.oc_proxy.resources(token=self.ensure_valid_token(), level=level, force_refresh=force_refresh,
                                           start=start, end=end, includes=includes, excludes=excludes)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def renew(self, *, slice_object: Slice,
              new_lease_end_time: str) -> Tuple[Status, Union[SliceManagerException, None]]:
        """
        Renew a slice
        @param slice_object slice to be renewed
        @param new_lease_end_time new_lease_end_time
        @return Tuple containing Status and List of Reservation Id failed to extend
       """
        if slice_object is None or not isinstance(slice_object, Slice) or new_lease_end_time is None:
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - "
                                                                   "slice_object or new_lease_end_time")
        try:
            return self.oc_proxy.renew(token=self.ensure_valid_token(), slice_id=slice_object.slice_id,
                                       new_lease_end_time=new_lease_end_time)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def poa(self, *, sliver_id: str, operation: str, vcpu_cpu_map: List[Dict[str, str]] = None,
            node_set: List[str] = None,
            keys: List[Dict[str, str]] = None) -> Tuple[Status, Union[SliceManagerException, List[PoaData]]]:
        """
        Issue POA for a sliver
        @param sliver_id sliver Id for which to trigger POA
        @param operation operation
        @param vcpu_cpu_map list of mappings from virtual CPU to physical cpu
        @param node_set list of the numa nodes
        @param keys list of keys to add/remove
        @return Tuple containing Status and POA information
       """
        if sliver_id is None or operation is None:
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - sliver_id or operation")

        try:
            return self.oc_proxy.poa(token=self.ensure_valid_token(), sliver_id=sliver_id, operation=operation,
                                     vcpu_cpu_map=vcpu_cpu_map, node_set=node_set, keys=keys)

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def get_poas(self, sliver_id: str = None, poa_id: str = None, limit: int = 20,
                 offset: int = 0, ) -> Tuple[Status, Union[SliceManagerException, List[PoaData]]]:
        """
        Get POAs
        @param sliver_id sliver Id for which to trigger POA
        @param limit maximum number of slices to return
        @param offset offset of the first slice to return
        @param poa_id POA id identifying the POA
        @return Tuple containing Status and POA information
        """
        try:
            return self.oc_proxy.get_poas(token=self.ensure_valid_token(), limit=limit, offset=offset,
                                          sliver_id=sliver_id, poa_id=poa_id)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)
