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
        headers = {
            'Accept': 'application/json',
            'Content-Type': "application/json",
            'authorization': f"Bearer {token}"
        }
        # Create Session
        self.session = requests.Session()
        self.session.headers.update(headers)

    def get_user_id(self) -> str:
        """
        Return User's uuid by querying via /whoami Core API
        
        @return User's uuid
        """
        url = f'{self.api_server}/whoami'
        response = self.session.get(url)
        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"GET WHOAMI Response : {response.json()}")

        return response.json().get("results")[0].get("uuid")

    def get_user_info(self) -> dict:
        """
        Return User's uuid by querying via /whoami Core API
        
        @return User's uuid and email
        """
        uuid = self.get_user_id()

        url = f'{self.api_server}/people/{uuid}?as_self=true'
        response = self.session.get(url)
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
        response = self.session.get(url)

        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"GET Project Response : {response.json()}")

        return response.json().get("results")

    def __get_user_projects(self, *, project_name: str = None) -> list:
        """
        Return user's project identified by project name
        
        @param project_name project name
        @return list of the projects
        """
        offset = 0
        limit = 50
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

            response = self.session.get(url)

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

    def get_user_projects(self, project_name: str = "all", project_id: str = "all") -> List[dict]:
        """
        Get User's projects either identified by project name, project id or all
        @param project_name Project name
        @param project_id Project Id
        @return list of projects
        """
        if project_id is not None and project_id != "all":
            return self.__get_user_project_by_id(project_id=project_id)
        elif project_name is not None and project_name != "all":
            return self.__get_user_projects(project_name=project_name)
        else:
            return self.__get_user_projects()

    def get_user_and_project_info(self, project_name: str = "all",
                                  project_id: str = "all") -> Tuple[dict, list]:
        """
        Get User's info and projects either identified by project name, project id or all

        @param project_id: Project Id
        @param project_name Project name

        @return a tuple containing email, uuid, list of projects
        """
        user_info = self.get_user_info()

        projects_res = self.get_user_projects(project_id=project_id, project_name=project_name)

        projects = []
        for p in projects_res:
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

            projects.append(project)

        if len(projects) == 0:
            raise CoreApiError(f"User is not a member of Project: {project_id}:{project_name}")

        return user_info, projects

    def get_ssh_keys(self) -> list:
        """
        Return SSH Keys, given user's uuid

        @return list of ssh keys
        """
        uuid = self.get_user_id()

        url = f'{self.api_server}/sshkeys?person_uuid={uuid}'
        response = self.session.get(url)
        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"GET SSH Keys Response : {response.json()}")
        return response.json().get("results")

    def create_ssh_keys(self, key_type: str, description: str,
                        comment: str = "Created via API", store_pubkey: bool = True) -> list:
        """
        Create SSH Keys for a user
        @param description: Key Description
        @param comment: Comment
        @param store_pubkey: Flag indicating if public key should be saved
        @param key_type: Key Type (sliver or bastion)

        @return list of ssh keys
        """
        uuid = self.get_user_id()

        ssh_data = {
            Constants.DESCRIPTION: description,
            Constants.COMMENT: comment,
            Constants.KEY_TYPE: key_type,
            Constants.STORE_PUBKEY: store_pubkey
        }
        url = f'{self.api_server}/sshkeys?person_uuid={uuid}'
        response = self.session.post(url, data=ssh_data)
        if response.status_code != 200:
            raise CoreApiError(f"Core API error occurred status_code: {response.status_code} "
                               f"message: {response.content}")

        logging.debug(f"POST SSH Keys Response : {response.json()}")
        return response.json().get("results")
