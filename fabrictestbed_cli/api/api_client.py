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
from typing import Tuple, Union, List

from fabric_cf.orchestrator.elements.reservation import Reservation

from fabrictestbed_cli.user import ExperimentTopology

from fabrictestbed_cli.api import CredmgrProxy, OrchestratorProxy, Status, CmStatus, Slice, AdvertizedTopology


class ApiClientException(Exception):
    """ API Client Exception """


class ApiClient:
    """
    Implements User facing Control Framework API interface
    """
    def __init__(self, *, cm_host: str, oc_host: str, refresh_token: str, project_name: str = "all",
                 scope: str = "all"):
        self.cm_proxy = CredmgrProxy(credmgr_host=cm_host)
        self.oc_proxy = OrchestratorProxy(orchestrator_host=oc_host)
        self.refresh_token = refresh_token
        self.id_token = None
        self.project_name = project_name
        self.scope = scope

    def get_refresh_token(self) -> str:
        return self.refresh_token

    def get_id_token(self) -> str:
        return self.id_token

    def refresh_tokens(self) -> Tuple[str, str]:
        """
        Refresh tokens
        """
        status, id_token, self.refresh_token = self.cm_proxy.refresh(project_name=self.project_name, scope=self.scope,
                                                                     refresh_token=self.refresh_token)
        if status == CmStatus.OK:
            self.id_token = id_token
            return self.id_token, self.refresh_token
        raise ApiClientException(id_token)

    def create(self, *, slice_name: str, ssh_key: str, topology: ExperimentTopology = None, slice_graph: str = None,
               lease_end_time: str = None) -> Tuple[Status, Union[Exception, List[Reservation]]]:
        """
        Create a slice
        @param slice_name slice name
        @param ssh_key SSH Key
        @param topology Experiment topology
        @param slice_graph Slice Graph string
        @param lease_end_time Lease End Time
        @return Tuple containing Status and Exception/Json containing slivers created
        """
        return self.oc_proxy.create(token=self.id_token, slice_name=slice_name, ssh_key=ssh_key, topology=topology,
                                    slice_graph=slice_graph, lease_end_time=lease_end_time)

    def delete(self, *, slice_id: str) -> Tuple[Status, Union[Exception, None]]:
        """
        Delete a slice
        @param slice_id slice id
        @return Tuple containing Status and Exception/Json containing deletion status
        """
        return self.oc_proxy.delete(token=self.id_token, slice_id=slice_id)

    def slices(self) -> Tuple[Status, Union[Exception, List[Slice]]]:
        """
        Get slices
        @return Tuple containing Status and Exception/Json containing slices
        """
        return self.oc_proxy.slices(token=self.id_token)

    def get_slice(self, *, slice_id: str) -> Tuple[Status, Union[Exception, ExperimentTopology]]:
        """
        Get slice
        @param slice_id slice id
        @return Tuple containing Status and Exception/Json containing slice
        """
        return self.oc_proxy.get_slice(token=self.id_token, slice_id=slice_id)

    def slice_status(self, *, slice_id: str) -> Tuple[Status, Union[Exception, Slice]]:
        """
        Get slice status
        @param slice_id slice id
        @return Tuple containing Status and Exception/Json containing slice status
        """
        return self.oc_proxy.slice_status(token=self.id_token, slice_id=slice_id)

    def slivers(self, *, slice_id: str, sliver_id: str = None) -> Tuple[Status, Union[Exception, List[Reservation]]]:
        """
        Get slivers
        @param slice_id slice id
        @param sliver_id slice sliver_id
        @return Tuple containing Status and Exception/Json containing Sliver(s)
        """
        return self.oc_proxy.slivers(token=self.id_token, slice_id=slice_id, sliver_id=sliver_id)

    def sliver_status(self, *, slice_id: str, sliver_id: str) -> Tuple[Status, Union[Exception, Reservation]]:
        """
        Get slivers
        @param slice_id slice id
        @param sliver_id slice sliver_id
        @return Tuple containing Status and Exception/Json containing Sliver status
        """
        return self.oc_proxy.sliver_status(token=self.id_token, slice_id=slice_id, sliver_id=sliver_id)

    def resources(self, *, level: int = 1) -> Tuple[Status, Union[Exception, AdvertizedTopology]]:
        """
        Get resources
        @param level level
        @return Tuple containing Status and Exception/Json containing Resources
        """
        return self.oc_proxy.resources(token=self.id_token, level=level)

    def renew(self, *, slice_id: str, new_lease_end_time: str) -> Tuple[Status, Union[Exception, List, None]]:
        """
       Renew a slice
       @param slice_id slice_id
       @param new_lease_end_time new_lease_end_time
       @return Tuple containing Status and List of Reservation Id failed to extend
       """
        return self.oc_proxy.renew(token=self.id_token, slice_id=slice_id, new_lease_end_time=new_lease_end_time)
