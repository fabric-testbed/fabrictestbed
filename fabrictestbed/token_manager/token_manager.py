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
from abc import ABC
from datetime import datetime, timezone, timedelta
from typing import Tuple, List, Union, Any

from fabric_cm.credmgr.credmgr_proxy import CredmgrProxy, Status, TokenType
from fabrictestbed.slice_manager import CmStatus

from fabrictestbed.util.utils import Utils

from fabrictestbed.util.constants import Constants


class TokenManagerException(Exception):
    pass


class TokenManager(ABC):
    def __init__(self, *, cm_host: str = None, token_location: str = None, project_id: str = None, scope: str = "all",
                 project_name: str = None, auto_refresh: bool = True, initialize: bool = True):
        """
        Initialize a TokenManager instance.

        This constructor sets up the TokenManager with the necessary parameters for managing tokens, including
        optional initialization of the manager. It also configures settings related to the project and scope.

        @param cm_host: (Optional) The host address of the credential manager. If not provided, it may be
                        retrieved from environment variables or other sources.
        @param token_location: (Optional) The location of the token file. This is where the token is stored
                               or retrieved from.
        @param project_id: (Optional) The ID of the project associated with the token. This can be used to
                           filter or manage tokens for a specific project.
        @param scope: (Optional) The scope of the token's validity. Defaults to "all". It determines the
                      extent or range of access the token provides.
        @param project_name: (Optional) The name of the project associated with the token. This can be used
                             to filter or manage tokens for a specific project.
        @param auto_refresh: (Optional) A flag indicating whether the token should be automatically refreshed
                              when it expires. Defaults to True.
        @param initialize: (Optional) A flag indicating whether the manager should be initialized upon
                            creation. Defaults to True. If set to False, initialization tasks are skipped.

        @return: None
        """

        self.auto_refresh = auto_refresh
        self.logger = logging.getLogger()
        self.initialized = False
        if cm_host is None:
            cm_host = os.environ.get(Constants.FABRIC_CREDMGR_HOST)
        self.cm_proxy = CredmgrProxy(credmgr_host=cm_host)
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

        if cm_host is None or self.token_location is None:
            raise TokenManagerException(f"Invalid initialization parameters: cm_host: {cm_host}, "
                                        f"token_location: {self.token_location}")

        # Try to load the project_id or project_name from the Token
        if project_id is None and project_name is None:
            self._extract_project_and_user_info_from_token(cm_host=cm_host)

        # Validate the required parameters are set
        if self.project_id is None and self.project_name is None:
            raise TokenManagerException(f"Invalid initialization parameters: project_id={self.project_id}, "
                                        f"project_name={self.project_name}")

        self.user_id = None
        self.user_email = None

        if initialize:
            self.initialize()

    def initialize(self):
        """
        Initialize the Slice Manager object
        - Load the tokens
        - Refresh if needed
        """
        if not self.initialized:
            self._load_tokens()
            self.initialized = True

    def _check_initialized(self):
        """
        Check if Slice Manager has been initialized
        @raises Exception if slice manager has been initialized
        """
        if not self.initialized:
            raise TokenManagerException("Fabric Client has not been initialized!")

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

    def _extract_project_and_user_info_from_token(self, cm_host: str):
        """
        Extract project and user information from the identity token.

        This method determines the project ID, project name, user ID, and user email
        by decoding the identity token, if these details are not explicitly provided.

        @param: cm_host (str): The hostname of the credential manager (CM) to be used for decoding the token.

        Notes:
            - This method assumes that tokens have already been loaded.
            - If project and user information is successfully extracted from the token, it will be stored in the
              instance variables `project_id`, `project_name`, `user_id`, and `user_email`.
        """
        self._load_tokens(refresh=False)
        if self.get_id_token() is not None:
            logging.info("Project Id/Name not specified, trying to determine it from the token")
            decoded_token = Utils.decode_token(cm_host=cm_host, token=self.get_id_token())
            if decoded_token.get("projects") and len(decoded_token.get("projects")):
                self.project_id = decoded_token.get("projects")[0].get("uuid")
                self.project_name = decoded_token.get("projects")[0].get("name")
            self.user_id = decoded_token.get("uuid")
            self.user_email = decoded_token.get("email")

    def _load_tokens(self, refresh: bool = True):
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
        if refresh and self.auto_refresh and refresh_token:
            self.refresh_tokens(refresh_token=refresh_token)

    def _should_renew(self) -> bool:
        """
        Check if tokens should be renewed
        Returns true if tokens are at least 30 minutes old
        @return true if tokens should be renewed; false otherwise
        """
        self._check_initialized()

        id_token = self.get_id_token()
        created_at = self.tokens.get(CredmgrProxy.CREATED_AT, None)

        created_at_time = datetime.strptime(created_at, CredmgrProxy.TIME_FORMAT)
        now = datetime.now(timezone.utc)

        if id_token is None or now - created_at_time >= timedelta(minutes=180):
            return True

        return False

    def create_token(self, scope: str = "all", project_id: str = None, project_name: str = None, file_name: str = None,
                     life_time_in_hours: int = 4, comment: str = "Created via API",
                     browser_name: str = "chrome") -> Tuple[Status, Union[dict, TokenManagerException]]:
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
            return Status.FAILURE, TokenManagerException(error_message)

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
                raise TokenManagerException(error_message)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise TokenManagerException(error_message)

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
            return Status.FAILURE, TokenManagerException(error_message)

    def token_revoke_list(self, *, project_id: str) -> Tuple[Status, Union[TokenManagerException, List[str]]]:
        """
        Get Token Revoke list for a project
        @param project_id project_id
        @return token revoke list
        """
        try:
            return self.cm_proxy.token_revoke_list(project_id=project_id)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, TokenManagerException(error_message)

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

    def ensure_valid_token(self) -> str:
        """
        Ensures the token is valid and renews it if required.
        @return valid identity token
        """
        if self._should_renew():
            self._load_tokens()
        return self.get_id_token()

    def get_user_id(self) -> str:
        """
        Retrieve the user ID associated with the current session.

        This method returns the user ID if it has already been determined. If the user ID
        has not been set and an identity token is available, it will attempt to extract
        the user ID by decoding the token using the credential manager proxy.

        @return: The user ID if available; otherwise, None.
        """
        if not self.user_id and self.get_id_token() and self.cm_proxy:
            self._extract_project_and_user_info_from_token(cm_host=self.cm_proxy.host)
        return self.user_id

    def get_user_email(self) -> str:
        """
        Retrieve the user email associated with the current session.

        This method returns the user email if it has already been determined. If the user email
        has not been set and an identity token is available, it will attempt to extract
        the user email by decoding the token using the credential manager proxy.

        @return: The user email if available; otherwise, None.
        """
        if not self.user_email and self.get_id_token() and self.cm_proxy:
            self._extract_project_and_user_info_from_token(cm_host=self.cm_proxy.host)
        return self.user_email
