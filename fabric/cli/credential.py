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
# Author: Erica Fu (ericafu@renci.org), Komal Thareja (kthare10@renci.org)

"""Handles Credential Management: create/get/revoke/refresh tokens.

  usage example:

  res = CredMgr.create_token(projectname, scope)
  res = CredMgr.refresh_token(projectname, scope, refreshtoken)
  res = CredMgr.revoke_token(refreshtoken)
"""
import os
import webbrowser
from fabric.credmgr import swagger_client
from fabric.credmgr.swagger_client.rest import ApiException as CredMgrException


CREDMGR_SERVER_API_PORT = os.getenv('FABRIC_CREDMGR_API_PORT', 7000)
CREDMGR_SERVER_AUTH_PORT = os.getenv('FABRIC_CREDMGR_AUTH_PORT', 8443)
CREDMGR_SERVER = os.getenv('FABRIC_CREDMGR_HOST', 'dev-2.fabric-testbed.net')

# create an instance of the API class
configuration = swagger_client.configuration.Configuration()
configuration.host = "http://{}:{}/".format(CREDMGR_SERVER, CREDMGR_SERVER_API_PORT)
api_instance = swagger_client.ApiClient(configuration)


class CredMgr(object):
    @staticmethod
    def create_token(project_name, scope) -> dict:
        """ issue create_post request to Credential Manager.

            Args:
                project_name: FABRIC project name
                scope: FABRIC scope

            Returns:
                Raw Credential Manager response
            Raises:
                Exception: An error occurred while creating the tokens.
        """
        try:
            # Generate OAuth tokens for an user
            url = "https://{}:{}/ui/".format(CREDMGR_SERVER, CREDMGR_SERVER_AUTH_PORT)
            webbrowser.open(url, new=2)

            return {'url': url}
        except CredMgrException as e:
            #traceback.print_exc()
            raise Exception(e.reason, e.body)

    @staticmethod
    def revoke_token(refresh_token):
        try:
            # revoke tokens for an user
            body = swagger_client.Request(refresh_token)
            tokens_api = swagger_client.TokensApi(api_client=api_instance)
            api_response = tokens_api.tokens_revoke_post(body=body)
            return api_response.to_dict()
        except CredMgrException as e:
            #traceback.print_exc()
            raise Exception(e.reason, e.body)

    @staticmethod
    def refresh_token(project_name, scope, refresh_token):
        try:
            # revoke tokens for an user
            body = swagger_client.Request(refresh_token)
            tokens_api = swagger_client.TokensApi(api_client=api_instance)
            api_response = tokens_api.tokens_refresh_post(body=body,
                                                          project_name=project_name,
                                                          scope=scope)

            tokens = api_response.to_dict()
            return api_response.to_dict()
        except CredMgrException as e:
            #traceback.print_exc()
            raise Exception(e.reason, e.body)
