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
import json
import os
from datetime import datetime, timedelta
from typing import Tuple, Union, List, Any

from fabrictestbed.slice_editor import ExperimentTopology, AdvertisedTopology
from fabrictestbed.slice_manager import CredmgrProxy, OrchestratorProxy, CmStatus, Status, Reservation, Slice


class SliceManagerException(Exception):
    """ Slice Manager Exception """


class SliceManager:
    """
    Implements User facing Control Framework API interface
    """
    CILOGON_REFRESH_TOKEN = "CILOGON_REFRESH_TOKEN"
    DEFAULT_TOKEN_LOCATION = "FABRIC_TOKEN_LOCATION"

    def __init__(self, *, cm_host: str, oc_host: str, token_location: str = None,
                 project_name: str = "all",
                 scope: str = "all"):
        self.cm_proxy = CredmgrProxy(credmgr_host=cm_host)
        self.oc_proxy = OrchestratorProxy(orchestrator_host=oc_host)
        self.token_location = token_location
        self.tokens = {}
        self.project_name = project_name
        self.scope = scope
        if self.token_location is None:
            self.token_location = os.environ[self.DEFAULT_TOKEN_LOCATION]
        self.initialized = False

    def initialize(self):
        """
        Initialize the Slice Manager object
        - Load the tokens
        - Refresh if needed
        """
        if not self.initialized:
            self.__load_tokens()
            self.initialized = True

    def __check_initialized(self):
        """
        Check if Slice Manager has been initialized
        @raises Exception if slice manager has been initialized
        """
        if not self.initialized:
            raise SliceManagerException("Slice Manager has not been initialized!")

    def __should_renew(self) -> bool:
        """
        Check if tokens should be renewed
        Returns true if tokens are atleast 30 minutes old
        @return true if tokens should be renewed; false otherwise
        """
        self.__check_initialized()

        id_token = self.get_id_token()
        refresh_token = self.get_refresh_token()
        created_at = self.tokens.get(CredmgrProxy.CREATED_AT, None)

        created_at_time = datetime.strptime(created_at, CredmgrProxy.TIME_FORMAT)
        now = datetime.utcnow()

        if now - created_at_time >= timedelta(minutes=30):
            return True

        return False

    def __load_tokens(self):
        """
        Load Fabric Tokens from the tokens.json if it exists
        Otherwise, this is the first attempt, create the tokens and save them
        """
        # Load the tokens from the JSON
        if os.path.exists(self.token_location):
            with open(self.token_location, 'r') as stream:
                self.tokens = json.loads(stream.read())
        else:
            # First time login, use environment variable to load the tokens
            refresh_token = os.environ[self.CILOGON_REFRESH_TOKEN]
            self.refresh_tokens(refresh_token=refresh_token)

    def get_refresh_token(self) -> str:
        """
        Get Refresh Token
        @return refresh token
        """
        return self.tokens.get(CredmgrProxy.REFRESH_TOKEN, None)

    def get_id_token(self) -> str:
        """
        Get Id token
        @return id token
        """
        return self.tokens.get(CredmgrProxy.ID_TOKEN, None)

    def set_token_location(self, *, token_location: str):
        """
        Set token location: path of the file where tokens should be saved
        @param token_location file name along with complete path where tokens should be stored
        """
        self.token_location = token_location

    def refresh_tokens(self, *, refresh_token: str = None) -> Tuple[str, str]:
        """
        Refresh tokens
        User is expected to invoke refresh token API before invoking any other APIs to ensure the token is not expired.
        User is also expected to update the returned refresh token in the JupyterHub environment.
        @returns tuple of id token and refresh token
        """
        if refresh_token is None:
            refresh_token = self.get_refresh_token()

        status, tokens = self.cm_proxy.refresh(project_name=self.project_name, scope=self.scope,
                                               refresh_token=refresh_token, file_name=self.token_location)
        if status == CmStatus.OK:
            self.tokens = tokens
            return tokens.get(CredmgrProxy.ID_TOKEN, None), tokens.get(CredmgrProxy.REFRESH_TOKEN, None)
        raise SliceManagerException(tokens.get(CredmgrProxy.ERROR))

    def revoke_token(self, *, refresh_token: str = None) -> Tuple[Status, Any]:
        """
        Revoke a refresh token
        @param refresh_token Refresh Token to be revoked
        @return Tuple of the status and revoked refresh token
        """
        token_to_be_revoked = refresh_token
        if token_to_be_revoked is None:
            token_to_be_revoked = self.get_refresh_token()

        if token_to_be_revoked is not None:
            return self.cm_proxy.revoke(refresh_token=token_to_be_revoked)
        return Status.FAILURE, "Refresh Token cannot be None"

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
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.create(token=self.get_id_token(), slice_name=slice_name, ssh_key=ssh_key,
                                    topology=topology, slice_graph=slice_graph, lease_end_time=lease_end_time)

    def delete(self, *, slice_id: str) -> Tuple[Status, Union[Exception, None]]:
        """
        Delete a slice
        @param slice_id slice id
        @return Tuple containing Status and Exception/Json containing deletion status
        """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.delete(token=self.get_id_token(), slice_id=slice_id)

    def slices(self, state: str = "Active") -> Tuple[Status, Union[Exception, List[Slice]]]:
        """
        Get slices
        @param state Slice state
        @return Tuple containing Status and Exception/Json containing slices
        """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.slices(token=self.get_id_token(), state=state)

    def get_slice(self, *, slice_id: str) -> Tuple[Status, Union[Exception, ExperimentTopology]]:
        """
        Get slice
        @param slice_id slice id
        @return Tuple containing Status and Exception/Json containing slice
        """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.get_slice(token=self.get_id_token(), slice_id=slice_id)

    def slice_status(self, *, slice_id: str) -> Tuple[Status, Union[Exception, Slice]]:
        """
        Get slice status
        @param slice_id slice id
        @return Tuple containing Status and Exception/Json containing slice status
        """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.slice_status(token=self.get_id_token(), slice_id=slice_id)

    def slivers(self, *, slice_id: str, sliver_id: str = None) -> Tuple[Status, Union[Exception, List[Reservation]]]:
        """
        Get slivers
        @param slice_id slice id
        @param sliver_id slice sliver_id
        @return Tuple containing Status and Exception/Json containing Sliver(s)
        """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.slivers(token=self.get_id_token(), slice_id=slice_id, sliver_id=sliver_id)

    def sliver_status(self, *, slice_id: str, sliver_id: str) -> Tuple[Status, Union[Exception, Reservation]]:
        """
        Get slivers
        @param slice_id slice id
        @param sliver_id slice sliver_id
        @return Tuple containing Status and Exception/Json containing Sliver status
        """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.sliver_status(token=self.get_id_token(), slice_id=slice_id, sliver_id=sliver_id)

    def resources(self, *, level: int = 1) -> Tuple[Status, Union[Exception, AdvertisedTopology]]:
        """
        Get resources
        @param level level
        @return Tuple containing Status and Exception/Json containing Resources
        """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.resources(token=self.get_id_token(), level=level)

    def renew(self, *, slice_id: str, new_lease_end_time: str) -> Tuple[Status, Union[Exception, List, None]]:
        """
        Renew a slice
        @param slice_id slice_id
        @param new_lease_end_time new_lease_end_time
        @return Tuple containing Status and List of Reservation Id failed to extend
       """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.renew(token=self.get_id_token(), slice_id=slice_id, new_lease_end_time=new_lease_end_time)
