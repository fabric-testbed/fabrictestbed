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
# Author Komal Thareja (kthare10@renci.org)
import datetime
import json
import logging
from typing import Tuple, List

import requests
from fabrictestbed.util.constants import Constants


class CoreApiError(Exception):
    """
    Core Exception
    """
    pass


class CoreApi:
    """
    Class implements functionality to interface with Core API
    """
    def __init__(self, core_api_host: str, token: str):
        if "https" not in core_api_host:
            self.api_server = f"https://{core_api_host}"
        else:
            self.api_server = core_api_host

        # Set the headers
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    def get_user_id(self) -> str:
        """
        Return User's uuid by querying via /whoami Core API
        
        @return User's uuid
        """
        url = f'{self.api_server}/whoami'
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"GET WHOAMI Response : {response.json()}")

        return response.json().get("results")[0].get("uuid")

    def get_user_info_by_email(self, *, email: str) -> dict:
        if email is None:
            raise CoreApiError("Core API error email must be specified!")

        url = f'{self.api_server}/people?search={email}&exact_match=true&offset=0&limit=5'
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"GET PEOPLE Response : {response.json()}")
        results = response.json().get("results")
        if len(results):
            return response.json().get("results")[0]

    def get_user_info(self, *, uuid: str = None, email: str = None) -> dict:
        """
        Return User's uuid by querying via /whoami Core API
        @param uuid User's uuid
        @param email email
        
        @return User's uuid and email
        """
        if email is not None:
            return self.get_user_info_by_email(email=email)

        if uuid is None and email is None:
            uuid = self.get_user_id()

        url = f'{self.api_server}/people/{uuid}?as_self=true'
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"GET WHOAMI Response : {response.json()}")

        return response.json().get("results")[0]

    def __get_user_project_by_id(self, *, project_id: str) -> list:
        """
        Return user's project identified by project id
        
        @param project_id project id
        @return list of the projects
        """
        url = f"{self.api_server}/projects/{project_id}"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"GET Project Response : {response.json()}")

        return response.json().get("results")

    def __get_user_projects(self, *, project_name: str = None, uuid: str = None) -> list:
        """
        Return user's project identified by project name
        
        @param project_name project name
        @return list of the projects
        """
        offset = 0
        limit = 50
        if uuid is None:
            uuid = self.get_user_id()
        result = []
        total_fetched = 0

        while True:
            if project_name is not None:
                url = f"{self.api_server}/projects?search={project_name}&offset={offset}&limit={limit}" \
                      f"&person_uuid={uuid}&sort_by=name&order_by=asc"
            else:
                url = f"{self.api_server}/projects?offset={offset}&limit={limit}&person_uuid={uuid}" \
                      f"&sort_by=name&order_by=asc"

            response = requests.get(url, headers=self.headers)

            if response.status_code != 200:
                raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                                   f"message: {response.content}")

            logging.debug(f"GET Project Response : {response.json()}")

            size = response.json().get("size")
            total = response.json().get("total")
            projects = response.json().get("results")

            total_fetched += size

            for x in projects:
                result.append(x)

            if total_fetched == total:
                break
            offset = size
            limit += limit

        return result

    def get_user_projects(self, project_name: str = "all", project_id: str = "all", uuid: str = None) -> List[dict]:
        """
        Get User's projects either identified by project name, project id or all
        @param project_name Project name
        @param project_id Project Id
        @param uuid User Id
        @return list of projects
        """
        ret_val = []
        if project_id is not None and project_id != "all":
            projects = self.__get_user_project_by_id(project_id=project_id)
        elif project_name is not None and project_name != "all":
            projects = self.__get_user_projects(project_name=project_name, uuid=uuid)
        else:
            projects = self.__get_user_projects()

        for p in projects:
            expires_on = p.get("expires_on")
            if expires_on is not None:
                expires_on_dt = datetime.datetime.fromisoformat(expires_on)
                now = datetime.datetime.now(tz=datetime.timezone.utc)
                if now > expires_on_dt:
                    # Do not include the expired project in the token for "all" get slices
                    if project_id is not None and project_id.lower() == "all":
                        continue
                    # Do not include the expired project in the token for "all" get slices
                    elif project_name is not None and project_name.lower() == "all":
                        continue
                    # Fail a request of the token for an expired token
                    else:
                        raise CoreApiError(f"Project {p.get('name')} is expired!")

            project_memberships = p.get("memberships")

            if not project_memberships["is_member"] and not project_memberships["is_creator"] and \
                    not project_memberships["is_owner"]:
                raise CoreApiError(f"User is not a member of Project: {p.get('uuid')}")
            project = {
                "name": p.get("name"),
                "uuid": p.get("uuid")
            }

            # Only pass tags and membership when token is requested for a specific project
            if project_id.lower() != "all":
                project["tags"] = p.get("tags")
                project["memberships"] = p.get("memberships")

            ret_val.append(project)

        if len(ret_val) == 0:
            raise CoreApiError(f"User is not a member of Project: {project_id}:{project_name}")

        return ret_val

    def get_ssh_keys(self, *, uuid: str = None, email: str = None) -> list:
        """
        Return SSH Keys, given user's uuid
        @param uuid: uuid
        @param email:

        @return list of ssh keys
        """
        if email is not None:
            user_info = self.get_user_info(email=email)
            if user_info is None:
                raise CoreApiError(f"Core API error {email} not found")
            uuid = user_info.get("uuid")
        elif uuid is None:
            uuid = self.get_user_id()

        url = f'{self.api_server}/sshkeys?person_uuid={uuid}'
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"GET SSH Keys Response : {response.json()}")
        return response.json().get("results")

    def create_ssh_keys(self, key_type: str, description: str,
                        comment: str = "ssh-key-via-api", store_pubkey: bool = True) -> list:
        """
        Create SSH Keys for a user
        @param description: Key Description
        @param comment: Comment
        @param store_pubkey: Flag indicating if public key should be saved
        @param key_type: Key Type (sliver or bastion)

        @return list of ssh keys
        """
        data = {
            "comment": comment,
            "description": description,
            "keytype": key_type,
            "store_pubkey": store_pubkey
        }

        # Make a POST request to the core-api API
        response = requests.post(f'{self.api_server}/sshkeys', headers=self.headers, data=json.dumps(data))

        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"POST SSH Keys Response : {response.json()}")
        return response.json().get("results")
