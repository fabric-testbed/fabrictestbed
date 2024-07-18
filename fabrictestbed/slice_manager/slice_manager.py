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
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Tuple, Union, List, Any, Dict

import paramiko
from fabric_cf.orchestrator.swagger_client import Sliver, Slice
from fabric_cf.orchestrator.swagger_client.models import PoaData
from fabric_cm.credmgr.credmgr_proxy import TokenType

from fabrictestbed.external_api.core_api import CoreApi
from fabrictestbed.slice_editor import ExperimentTopology, AdvertisedTopology, Node, GraphFormat
from fabrictestbed.slice_manager import CredmgrProxy, OrchestratorProxy, CmStatus, Status, SliceState
from fabrictestbed.util.constants import Constants
from fabrictestbed.util.utils import Utils


class SliceManagerException(Exception):
    """ Slice Manager Exception """


class SliceManager:
    """
    Implements User facing Control Framework API interface
    """
    def __init__(self, *, cm_host: str = None, oc_host: str = None, core_api_host: str = None,
                 token_location: str = None,
                 project_id: str = None, scope: str = "all", initialize: bool = True,
                 project_name: str = None, auto_refresh: bool = True):
        self.auto_refresh = auto_refresh
        self.logger = logging.getLogger()
        if cm_host is None:
            cm_host = os.environ.get(Constants.FABRIC_CREDMGR_HOST)
        if oc_host is None:
            oc_host = os.environ.get(Constants.FABRIC_ORCHESTRATOR_HOST)
        if core_api_host is None:
            core_api_host = os.environ.get(Constants.FABRIC_CORE_API_HOST)
        self.cm_proxy = CredmgrProxy(credmgr_host=cm_host)
        self.oc_proxy = OrchestratorProxy(orchestrator_host=oc_host)
        self.core_api_host = core_api_host
        self.token_location = token_location
        self.tokens = {}
        self.project_id = project_id
        if self.project_id is None:
            self.project_id = os.environ.get(Constants.FABRIC_PROJECT_ID)
        self.project_name = project_name
        if self.project_name is None:
            self.project_name = os.environ.get(Constants.FABRIC_PROJECT_NAME)
        self.scope = scope
        if self.token_location is None:
            self.token_location = os.environ.get(Constants.FABRIC_TOKEN_LOCATION)
        self.initialized = False

        if cm_host is None or oc_host is None or self.core_api_host is None or self.token_location is None:
            raise SliceManagerException(f"Invalid initialization parameters: cm_host: {cm_host}, "
                                        f"oc_host: {oc_host} core_api_host: {core_api_host} "
                                        f"token_location: {self.token_location}")

        # Try to load the project_id or project_name from the Token
        if project_id is None and project_name is None:
            self.__determine_project(cm_host=cm_host)

        # Validate the required parameters are set
        if self.project_id is None and self.project_name is None:
            raise SliceManagerException(f"Invalid initialization parameters: project_id={self.project_id}, "
                                        f"project_name={self.project_name}")

        if initialize:
            self.initialize()

    def __determine_project(self, cm_host: str):
        self.__load_tokens(refresh=False)
        if self.get_id_token() is not None:
            logging.info("Project Id/Name not specified, trying to determine it from the token")
            decoded_token = Utils.decode_token(cm_host=cm_host, token=self.get_id_token())
            if decoded_token.get("projects") and len(decoded_token.get("projects")):
                self.project_id = decoded_token.get("projects")[0].get("uuid")
                self.project_name = decoded_token.get("projects")[0].get("name")

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
        Returns true if tokens are at least 30 minutes old
        @return true if tokens should be renewed; false otherwise
        """
        self.__check_initialized()

        id_token = self.get_id_token()
        created_at = self.tokens.get(CredmgrProxy.CREATED_AT, None)

        created_at_time = datetime.strptime(created_at, CredmgrProxy.TIME_FORMAT)
        now = datetime.now(timezone.utc)

        if id_token is None or now - created_at_time >= timedelta(minutes=180):
            return True

        return False

    def __load_tokens(self, refresh: bool = True):
        """
        Load Fabric Tokens from the tokens.json if it exists
        Otherwise, this is the first attempt, create the tokens and save them
        @note this function is invoked when reloading the tokens to ensure tokens
        from the token file are read instead of the local variables
        """
        # Load the tokens from the JSON
        if os.path.exists(self.token_location):
            with open(self.token_location, 'r') as stream:
                self.tokens = json.loads(stream.read())
            refresh_token = self.get_refresh_token()
        else:
            # First time login, use environment variable to load the tokens
            refresh_token = os.environ.get(Constants.CILOGON_REFRESH_TOKEN)
        # Renew the tokens to ensure any project_id changes are taken into account
        if refresh and self.auto_refresh:
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

    def create_token(self, scope: str = "all", project_id: str = None, project_name: str = None, file_name: str = None,
                     life_time_in_hours: int = 4, comment: str = "Created via API",
                     browser_name: str = "chrome") -> Tuple[Status, Union[dict, SliceManagerException]]:
        """
        Create token
        @param project_id: Project Id
        @param project_name: Project Name
        @param scope: scope
        @param file_name: File name
        @param life_time_in_hours: Token lifetime in hours
        @param comment: comment associated with the token
        @param browser_name: Browser name; allowed values: chrome, firefox, safari, edge
        @returns Tuple of Status, token json or Exception
        @raises Exception in case of failure
        """
        try:
            return self.cm_proxy.create(scope=scope, project_id=project_id, project_name=project_name,
                                        file_name=file_name, life_time_in_hours=life_time_in_hours, comment=comment,
                                        browser_name=browser_name)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def refresh_tokens(self, *, refresh_token: str) -> Tuple[str, str]:
        """
        Refresh tokens
        User is expected to invoke refresh token API before invoking any other APIs to ensure the token is not expired.
        User is also expected to update the returned refresh token in the JupyterHub environment.
        @returns tuple of id token and refresh token
        @note this exposes an API for the user to refresh tokens explicitly only. CredMgrProxy::refresh already
        updates the refresh tokens to the token file atomically.
        """
        try:
            status, tokens = self.cm_proxy.refresh(project_id=self.project_id, scope=self.scope,
                                                   refresh_token=refresh_token, file_name=self.token_location,
                                                   project_name=self.project_name)
            if status == CmStatus.OK:
                self.tokens = tokens
                return tokens.get(CredmgrProxy.ID_TOKEN, None), tokens.get(CredmgrProxy.REFRESH_TOKEN, None)
            else:
                error_message = Utils.extract_error_message(exception=tokens)
                raise SliceManagerException(error_message)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise SliceManagerException(error_message)

    def revoke_token(self, *, refresh_token: str = None, id_token: str = None, token_hash: str = None,
                     token_type: TokenType = TokenType.Refresh) -> Tuple[Status, Any]:
        """
        Revoke a refresh token
        @param refresh_token Refresh Token to be revoked
        @param id_token Identity Token
        @param token_hash Token Hash
        @param token_type type of the token being revoked
        @return Tuple of the status and revoked refresh token
        """
        if refresh_token is None:
            refresh_token = self.get_refresh_token()
        if id_token is None:
            id_token = self.get_id_token()
        if token_hash is None:
            token_hash = Utils.generate_sha256(token=id_token)

        try:
            return self.cm_proxy.revoke(refresh_token=refresh_token, identity_token=id_token, token_hash=token_hash,
                                        token_type=token_type)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def token_revoke_list(self, *, project_id: str) -> Tuple[Status, Union[SliceManagerException, List[str]]]:
        """
        Get Token Revoke list for a project
        @param project_id project_id
        @return token revoke list
        """
        try:
            return self.cm_proxy.token_revoke_list(project_id=project_id)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

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
            return Status.OK, None
        return Status.FAILURE, f"Failed to clear token cache: {Utils.extract_error_message(exception=exception)}"

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
            if self.__should_renew():
                self.__load_tokens()
            return self.oc_proxy.create(token=self.get_id_token(), slice_name=slice_name, ssh_key=ssh_key,
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
            if self.__should_renew():
                self.__load_tokens()
            return self.oc_proxy.modify(token=self.get_id_token(), slice_id=slice_id, topology=topology,
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
            if self.__should_renew():
                self.__load_tokens()
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
            if self.__should_renew():
                self.__load_tokens()
            slice_id = slice_object.slice_id if slice_object is not None else None
            return self.oc_proxy.delete(token=self.get_id_token(), slice_id=slice_id)
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
            if self.__should_renew():
                self.__load_tokens()
            return self.oc_proxy.slices(token=self.get_id_token(), includes=includes, excludes=excludes,
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
            if self.__should_renew():
                self.__load_tokens()
            return self.oc_proxy.get_slice(token=self.get_id_token(), slice_id=slice_object.slice_id,
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
            if self.__should_renew():
                self.__load_tokens()

            return self.oc_proxy.slivers(token=self.get_id_token(), slice_id=slice_object.slice_id, as_self=as_self)
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
            if self.__should_renew():
                self.__load_tokens()
            return self.oc_proxy.resources(token=self.get_id_token(), level=level, force_refresh=force_refresh,
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
            if self.__should_renew():
                self.__load_tokens()

            return self.oc_proxy.renew(token=self.get_id_token(), slice_id=slice_object.slice_id,
                                       new_lease_end_time=new_lease_end_time)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    def poa(self, *, sliver_id: str, operation: str, vcpu_cpu_map: List[Dict[str, str]] = None,
            node_set: List[str] = None,
            keys: List[Dict[str, str]] = None) ->Tuple[Status, Union[SliceManagerException, List[PoaData]]]:
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
            if self.__should_renew():
                self.__load_tokens()

            return self.oc_proxy.poa(token=self.get_id_token(), sliver_id=sliver_id, operation=operation,
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
            if self.__should_renew():
                self.__load_tokens()
            return self.oc_proxy.get_poas(token=self.get_id_token(), limit=limit, offset=offset,
                                          sliver_id=sliver_id, poa_id=poa_id)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)

    @staticmethod
    def __get_ssh_client() -> paramiko.SSHClient():
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    @staticmethod
    def execute(*, ssh_key_file: str, sliver: Node, username: str,
                command: str) -> Tuple[Status, SliceManagerException or Tuple]:
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
            return Status.INVALID_ARGUMENTS, SliceManagerException("Invalid arguments - sliver or "
                                                                   "ssh_key_file or username or command")

        client = None
        try:
            key = paramiko.RSAKey.from_private_key_file(ssh_key_file)
            client = SliceManager.__get_ssh_client()
            client.connect(str(sliver.management_ip), username=username, pkey=key)
            stdin, stdout, stderr = client.exec_command(command=command)
            return Status.OK, (stdout.readlines(), stderr.readlines())
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)
        finally:
            if client is not None:
                client.close()

    def get_ssh_keys(self, uuid: str = None, email: str = None) -> list:
        """
        Return SSH Keys
        :return list of ssh keys
        """
        try:
            if self.__should_renew():
                self.__load_tokens()
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.get_id_token())
            return core_api_proxy.get_ssh_keys(uuid=uuid, email=email)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise SliceManagerException(error_message)

    def create_ssh_keys(self, key_type: str, description: str, comment: str = "ssh-key-via-api",
                        store_pubkey: bool = True) -> list:
        """
        Create SSH Keys for a user
        :param description: Key Description
        :param comment: Comment
        :param store_pubkey: Flag indicating if public key should be saved
        :param key_type: Key Type (sliver or bastion)

        :return list of ssh keys
        """
        try:
            if self.__should_renew():
                self.__load_tokens()
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.get_id_token())
            return core_api_proxy.create_ssh_keys(key_type=key_type, comment=comment, store_pubkey=store_pubkey,
                                                  description=description)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise SliceManagerException(error_message)

    def get_user_info(self, uuid: str = None, email: str = None) -> dict:
        """
        Return User's uuid by querying via Core API

        @return User's information
        """
        try:
            if self.__should_renew():
                self.__load_tokens()
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.get_id_token())
            return core_api_proxy.get_user_info(uuid=uuid, email=email)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise SliceManagerException(error_message)

    def get_project_info(self, project_name: str = "all", project_id: str = "all", uuid: str = None) -> list:
        """
        Get User's projects either identified by project name, project id or all
        @param project_id: Project Id
        @param project_name Project name
        @param uuid User Id

        @return list of projects
        """
        try:
            if self.__should_renew():
                self.__load_tokens()
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.get_id_token())
            return core_api_proxy.get_user_projects(project_name=project_name, project_id=project_id, uuid=uuid)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise SliceManagerException(error_message)

    def get_metrics_overview(self, excluded_projects: List[str] = None,
                             authenticated: bool = False) -> Tuple[Status, Union[list, Exception]]:
        """
        Get Metrics overview
        @param excluded_projects: excluded_projects
        @param authenticated: Specific user metrics
        @return list of metrics
        """
        try:
            token = None
            if authenticated and self.__should_renew():
                self.__load_tokens()
                token = self.get_id_token()
            return self.oc_proxy.get_metrics_overview(token=token, excluded_projects=excluded_projects)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, SliceManagerException(error_message)