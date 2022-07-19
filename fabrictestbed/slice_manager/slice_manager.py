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

import paramiko
from fabric_cf.orchestrator.swagger_client import Sliver, Slice

from fabrictestbed.slice_editor import ExperimentTopology, AdvertisedTopology, Node, GraphFormat
from fabrictestbed.slice_manager import CredmgrProxy, OrchestratorProxy, CmStatus, Status, SliceState
from fabrictestbed.util.constants import Constants


class SliceManagerException(Exception):
    """ Slice Manager Exception """


class SliceManager:
    """
    Implements User facing Control Framework API interface
    """
    def __init__(self, *, cm_host: str = None, oc_host: str = None, token_location: str = None,
                 project_id: str = None, scope: str = "all", initialize: bool = True):
        if cm_host is None:
            cm_host = os.environ[Constants.FABRIC_CREDMGR_HOST]
        if oc_host is None:
            oc_host = os.environ[Constants.FABRIC_ORCHESTRATOR_HOST]
        self.cm_proxy = CredmgrProxy(credmgr_host=cm_host)
        self.oc_proxy = OrchestratorProxy(orchestrator_host=oc_host)
        self.token_location = token_location
        self.tokens = {}
        self.project_id = project_id
        if self.project_id is None:
            self.project_id = os.environ[Constants.FABRIC_PROJECT_ID]
        self.scope = scope
        if self.token_location is None:
            self.token_location = os.environ[Constants.FABRIC_TOKEN_LOCATION]
        self.initialized = False
        # Validate the required parameters are set
        if self.cm_proxy is None or self.oc_proxy is None or self.token_location is None or self.project_id is None:
            raise SliceManagerException(f"Invalid initialization parameters: cm_proxy={self.cm_proxy}, "
                                        f"oc_proxy={self.oc_proxy}, token_location={self.token_location}, "
                                        f"project_id={self.project_id}")
        if initialize:
            self.initialize()

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

        if id_token is None or now - created_at_time >= timedelta(minutes=30):
            return True

        return False

    def __load_tokens(self):
        """
        Load Fabric Tokens from the tokens.json if it exists
        Otherwise, this is the first attempt, create the tokens and save them
        """
        # Load the tokens from the JSON
        refresh_token = None
        if os.path.exists(self.token_location):
            with open(self.token_location, 'r') as stream:
                self.tokens = json.loads(stream.read())
        else:
            # First time login, use environment variable to load the tokens
            refresh_token = os.environ[Constants.CILOGON_REFRESH_TOKEN]
        # Renew the tokens to ensure any project_id changes are taken into account
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

        status, tokens = self.cm_proxy.refresh(project_id=self.project_id, scope=self.scope,
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

    def clear_token_cache(self, *, file_name: str = None):
        """
        Clear the cached token
        Should be invoked when the user changes projects
        @return:
        """
        cache_file_name = file_name
        if cache_file_name is None:
            cache_file_name = self.token_location
        status, exception = self.cm_proxy.clear_token_cache(file_name=cache_file_name)
        if status == CmStatus.OK:
            return Status.OK
        raise SliceManagerException(f"Failed to clear token cache: {exception}")

    def create(self, *, slice_name: str, ssh_key: str, topology: ExperimentTopology = None, slice_graph: str = None,
               lease_end_time: str = None) -> Tuple[Status, Union[Exception, List[Sliver]]]:
        """
        Create a slice
        @param slice_name slice name
        @param ssh_key SSH Key
        @param topology Experiment topology
        @param slice_graph Slice Graph string
        @param lease_end_time Lease End Time
        @return Tuple containing Status and Exception/Json containing slivers created
        """
        if slice_name is None or not isinstance(slice_name, str) or ssh_key is None or not isinstance(ssh_key, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments")

        if topology is not None and not isinstance(topology, ExperimentTopology):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments")

        if slice_graph is not None and not isinstance(slice_graph, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments")

        if lease_end_time is not None and not isinstance(lease_end_time, str):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments")

        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.create(token=self.get_id_token(), slice_name=slice_name, ssh_key=ssh_key,
                                    topology=topology, slice_graph=slice_graph, lease_end_time=lease_end_time)

    def delete(self, *, slice_object: Slice) -> Tuple[Status, Union[Exception, None]]:
        """
        Delete slice(s)
        @param slice_object slice to be deleted
        @return Tuple containing Status and Exception/Json containing deletion status
        """
        if slice_object is None or not isinstance(slice_object, Slice):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments")
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.delete(token=self.get_id_token(), slice_id=slice_object.slice_id)

    def slices(self, includes: List[SliceState] = None, excludes: List[SliceState] = None, name: str = None,
               limit: int = 20, offset: int = 0, slice_id: str = None) -> Tuple[Status, Union[Exception, List[Slice]]]:
        """
        Get slices
        @param includes list of the slice state used to include the slices in the output
        @param excludes list of the slice state used to exclude the slices from the output
        @param name name of the slice
        @param limit maximum number of slices to return
        @param offset offset of the first slice to return
        @param slice_id slice id
        @return Tuple containing Status and Exception/Json containing slices
        """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.slices(token=self.get_id_token(), includes=includes, excludes=excludes,
                                    name=name, limit=limit, offset=offset, slice_id=slice_id)

    def get_slice_topology(self, *, slice_object: Slice,
                           graph_format: GraphFormat = GraphFormat.GRAPHML) -> Tuple[Status, Union[Exception, ExperimentTopology]]:
        """
        Get slice topology
        @param slice_object Slice for which to retrieve the topology
        @param graph_format
        @return Tuple containing Status and Exception/Json containing slice
        """
        if slice_object is None or not isinstance(slice_object, Slice):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments")
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.get_slice(token=self.get_id_token(), slice_id=slice_object.slice_id,
                                       graph_format=graph_format)

    def slivers(self, *, slice_object: Slice) -> Tuple[Status, Union[Exception, List[Sliver]]]:
        """
        Get slivers
        @param slice_object list of the slices
        @return Tuple containing Status and Exception/Json containing Sliver(s)
        """
        if slice_object is None or not isinstance(slice_object, Slice):
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments")

        if self.__should_renew():
            self.refresh_tokens()

        return self.oc_proxy.slivers(token=self.get_id_token(), slice_id=slice_object.slice_id)

    def resources(self, *, level: int = 1) -> Tuple[Status, Union[Exception, AdvertisedTopology]]:
        """
        Get resources
        @param level level
        @return Tuple containing Status and Exception/Json containing Resources
        """
        if self.__should_renew():
            self.refresh_tokens()
        return self.oc_proxy.resources(token=self.get_id_token(), level=level)

    def renew(self, *, slice_object: Slice, new_lease_end_time: str) -> Tuple[Status, Union[Exception, None]]:
        """
        Renew a slice
        @param slice_object slice to be renewed
        @param new_lease_end_time new_lease_end_time
        @return Tuple containing Status and List of Reservation Id failed to extend
       """
        if slice_object is None or not isinstance(slice_object, Slice) or new_lease_end_time is None:
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments")

        if self.__should_renew():
            self.refresh_tokens()

        return self.oc_proxy.renew(token=self.get_id_token(), slice_id=slice_object.slice_id,
                                   new_lease_end_time=new_lease_end_time)

    @staticmethod
    def __get_ssh_client() -> paramiko.SSHClient():
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    @staticmethod
    def execute(*, ssh_key_file: str, sliver: Node, username: str,
                command: str) -> Tuple[Status, Exception or Tuple]:
        """
        Execute a command on a sliver
        @param ssh_key_file: Location of SSH Private Key file to use to access the Sliver
        @param sliver: Node sliver
        @param username: Username to use to access the sliver
        @param command: Command to be executed on the sliver
        @return tuple as explained below:
        - Success: Status.OK and the stdout, and stderr of the executing command, as a 2-tuple
        - Failure: Status.Failure and exception
        Status indicates if the command could be executed(Status.OK) or not(Status.FAILURE).
        Success or failure of the command should be determined from the stdin, stdout and stderr
        """
        if sliver is None or not isinstance(sliver, Node) or ssh_key_file is None or\
                username is None or command is None:
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments")

        client = None
        try:
            key = paramiko.RSAKey.from_private_key_file(ssh_key_file)
            client = SliceManager.__get_ssh_client()
            client.connect(str(sliver.management_ip), username=username, pkey=key)
            stdin, stdout, stderr = client.exec_command(command=command)
            return Status.OK, (stdout.readlines(), stderr.readlines())
        except Exception as e:
            return Status.FAILURE, e
        finally:
            if client is not None:
                client.close()
