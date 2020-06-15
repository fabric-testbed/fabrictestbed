"""Handles Credential Management: create/get/revoke/refresh tokens.

  usage example:

  res = CredMgr.create_token(projectname, scope)
  res = CredMgr.get_token(user_id)
  res = CredMgr.refresh_token(projectname, scope, refreshtoken)
  res = CredMgr.revoke_token(refreshtoken)
"""

from http import HTTPStatus
from pathlib import Path
import os
import typing
import webbrowser
import fabric_credmgr
from fabric_credmgr.rest import ApiException as CredMgrException
from .exceptions import TokenExpiredException
from pprint import pprint


class CredMgrRes(typing.NamedTuple):
    userid: str
    tokens: dict
    rawdata: dict


CREDMGR_SERVER_API_PORT = os.getenv('FABRIC_CREDMGR_API_PORT', 8082)
CREDMGR_SERVER_AUTH_PORT = os.getenv('FABRIC_CREDMGR_AUTH_PORT', 443)
CREDMGR_SERVER = os.getenv('FABRIC_CREDMGR_HOST')

# create an instance of the API class
configuration = fabric_credmgr.Configuration()
configuration.host = "http://{}:{}/fabric/credmgr".format(CREDMGR_SERVER, CREDMGR_SERVER_API_PORT)
api_instance = fabric_credmgr.DefaultApi(fabric_credmgr.ApiClient(configuration))


class CredMgr(object):
    @staticmethod
    def create_token(project_name, scope):
        """ issue create_post request to Credential Manager.

            Args:
                project_name: FABRIC project name
                scope: FABRIC scope

            Returns:
                CredMgrRes
                (CredMgrRes.userid: userid)
                (CredMgrRes.rawdata: original response from Credential Manager)

            Raises:
                Exception: An error occurred while creating the tokens.
        """
        try:
            # Generate OAuth tokens for an user
            api_response = api_instance.create_post(project_name=project_name, scope=scope)
            if HTTPStatus.OK == api_response.status:
                url = "https://{}:{}/key/{}".format(CREDMGR_SERVER, CREDMGR_SERVER_AUTH_PORT, api_response.value.user_id)
                webbrowser.open(url, new=2)
                api_response.message = "Please visit {}".format(url)
                api_response.value.authorization_url = url
                return CredMgrRes(userid=api_response.value.user_id, tokens={}, rawdata=api_response.to_dict())
            else:
                raise Exception(api_response.message, str(api_response))
        except CredMgrException as e:
            # print("Exception when calling create_post: %s\n" % e)
            raise Exception(e.reason, e.body)


    @staticmethod
    def get_token(userid):
        try:
            # get tokens for an user
            api_response = api_instance.get_get(userid)
            # pprint(api_response)
            if HTTPStatus.OK == api_response.status:
                tokens = api_response.value.to_dict()
                # remove empty fields
                if 'authorization_url' in tokens:
                    del tokens['authorization_url']
                if 'user_id' in tokens:
                    del tokens['user_id']
                return CredMgrRes(userid, tokens, api_response.to_dict())
            else:
                raise Exception(api_response.message, str(api_response))
        except CredMgrException as e:
            # print("Exception when calling DefaultApi->get_get: %s\n" % e)
            raise Exception(e.reason, e.body)

    @staticmethod
    def revoke_token(refreshtoken):
        try:
            # revoke tokens for an user
            revoke_req = fabric_credmgr.RefreshRevokeRequest(refreshtoken)
            api_response = api_instance.revoke_post(revoke_req)
            # pprint(api_response)
            if HTTPStatus.OK == api_response.status:
                return CredMgrRes('', {}, api_response.to_dict())
            else:
                raise Exception(api_response.message, "")
        except CredMgrException as e:
            # print("Exception when calling DefaultApi->revoke_post: %s\n" % e)
            raise Exception(e.reason, e.body)

    @staticmethod
    def refresh_token(project_name, scope, refreshtoken):
        try:
            # revoke tokens for an user
            refresh_req = fabric_credmgr.RefreshRevokeRequest(refreshtoken)
            api_response = api_instance.refresh_post(refresh_req,
                                                     project_name=project_name,
                                                     scope=scope)
            # pprint(api_response)
            if HTTPStatus.OK == api_response.status:
                tokens = api_response.value.to_dict()
                # remove empty fields
                if 'authorization_url' in tokens:
                    del tokens['authorization_url']
                if 'user_id' in tokens:
                    del tokens['user_id']

                return CredMgrRes(userid='', tokens=tokens, rawdata=api_response.to_dict())
            else:
                raise Exception(api_response.message)
        except CredMgrException as e:
            # print("Exception when calling DefaultApi->revoke_post: %s\n" % e)
            raise Exception(e.reason, e.body)
