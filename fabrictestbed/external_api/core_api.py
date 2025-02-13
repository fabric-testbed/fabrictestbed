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
from typing import List

import requests


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

    def list_quotas(self, project_uuid: str, offset: int = 0, limit: int = 200) -> List[dict]:
        """
        Fetch all quotas from the API.

        Parameters:
        project_uuid (str): The UUID of the project for which quotas are fetched.
        offset (int, optional): The starting point for fetching records. Defaults to 0.
        limit (int, optional): The maximum number of records to fetch. Defaults to 200.

        Returns:
        List[dict]: A list of quota records.
        """
        params = {"project_uuid": project_uuid,
                  "offset": offset,
                  "limit": limit}

        response = requests.get(f'{self.api_server}/quotas', headers=self.headers, params=params)
        self.raise_for_status(response=response)
        logging.debug(f"GET Quotas Response : {response.json()}")
        return response.json().get("results")

    def create_quota(self, project_uuid: str, resource_type: str, resource_unit: str,
                     quota_used: int = 0, quota_limit: int = 0) -> List[dict]:
        """
        Send a POST request to create a new quota.

        Parameters:
        project_uuid (str): The ID of the project to which the quota belongs.
        resource_type (str): The type of resource (e.g., CPU, RAM).
        resource_unit (str): The unit of the resource (e.g., cores, GB).
        quota_used (int, optional): The amount of resource currently used. Defaults to 0.
        quota_limit (int, optional): The limit for the resource. Defaults to 0.

        Returns:
        List[dict]: The created quota details.
        """
        data = {
            "project_uuid": project_uuid,
            "resource_type": resource_type,
            "resource_unit": resource_unit,
            "quota_used": quota_used,
            "quota_limit": quota_limit
        }
        response = requests.post(f'{self.api_server}/quotas', headers=self.headers, json=data)
        self.raise_for_status(response=response)
        logging.debug(f"POST Quotas Response : {response.json()}")
        return response.json().get("results")

    def get_quota(self, uuid: str) -> List[dict]:
        """
        Send a GET request to retrieve a quota by UUID.

        Parameters:
        uuid (str): The UUID of the quota to retrieve.

        Returns:
        List[dict]: The retrieved quota details.
        """
        response = requests.get(f'{self.api_server}/quotas/{uuid}', headers=self.headers)
        self.raise_for_status(response=response)
        logging.debug(f"GET Quotas Response : {response.json()}")
        return response.json().get("results")

    def update_quota_usage(self, uuid: str, project_uuid: str, quota_used: float):
        """
        Send a PUT request to update a quota usage by UUID.

        Parameters:
        uuid (str): The UUID of the quota to update.
        project_uuid (str): The ID of the project to which the quota belongs.
        quota_used (int, optional): The amount of resource currently used.

        Returns:
        List[dict]: The updated quota details.
        """
        current_quota = self.get_quota(uuid=uuid)[0]

        value = current_quota.get("quota_used") + quota_used
        if value < 0:
            value = 0

        data = {
            "project_uuid": project_uuid,
            "resource_type": current_quota.get("resource_type"),
            "resource_unit": current_quota.get("resource_unit"),
            "quota_used": value,
            "quota_limit": current_quota.get("quota_limit")
        }
        response = requests.put(f'{self.api_server}/quotas/{uuid}', headers=self.headers, json=data)
        self.raise_for_status(response=response)
        logging.debug(f"PUT Quotas Response : {response.json()}")
        return response.json().get("results")

    def update_quota(self, uuid: str, project_uuid: str, resource_type: str, resource_unit: str,
                     quota_used: float = 0, quota_limit: float = 0):
        """
        Send a PUT request to update a quota by UUID.

        Parameters:
        uuid (str): The UUID of the quota to update.
        project_uuid (str): The ID of the project to which the quota belongs.
        resource_type (str): The type of resource (e.g., CPU, RAM).
        resource_unit (str): The unit of the resource (e.g., cores, GB).
        quota_used (int, optional): The amount of resource currently used. Defaults to 0.
        quota_limit (int, optional): The limit for the resource. Defaults to 0.

        Returns:
        List[dict]: The updated quota details.
        """
        data = {
            "project_uuid": project_uuid,
            "resource_type": resource_type,
            "resource_unit": resource_unit,
            "quota_used": quota_used,
            "quota_limit": quota_limit
        }
        response = requests.put(f'{self.api_server}/quotas/{uuid}', headers=self.headers, json=data)
        self.raise_for_status(response=response)
        logging.debug(f"PUT Quotas Response : {response.json()}")
        return response.json().get("results")

    def delete_quota(self, uuid: str):
        """
        Send a DELETE request to delete a quota by UUID.

        Parameters:
        uuid (str): The UUID of the quota to delete.

        Returns:
        """
        response = requests.delete(f'{self.api_server}/quotas/{uuid}', headers=self.headers)
        self.raise_for_status(response=response)
        logging.debug(f"DEL Quotas Response : {response.json()}")

    @staticmethod
    def raise_for_status(response: requests.Response):
        """
        Checks the response status and raises an ArtifactManagerError if the request was unsuccessful.

        :param response: The response object returned from the API request.
        :raises ArtifactManagerError: If the response contains an HTTP error.
        """
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            try:
                message = response.json()
            except json.JSONDecodeError:
                message = {"message": "Unknown error occurred while processing the request."}

            raise CoreApiError(f"Error {response.status_code}: {e}. Message: {message}")


if __name__ == '__main__':
    project_id = ""
    token = ""
    core_api = CoreApi(core_api_host="alpha-6.fabric-testbed.net", token=token)

    quotas = core_api.list_quotas(project_uuid=project_id)
    print(f"Fetching quotas: {json.dumps(quotas,indent=4)}")
'''
    resources = ["core", "ram", "disk"]
    if len(quotas) == 0:
        for r in resources:
            core_api.create_quota(project_uuid=project_id, resource_type=r, resource_unit="hours",
                                  quota_limit=100, quota_used=0)
            print(f"Created quota for {r}")

    for q in quotas:
        core_api.update_quota(uuid=q.get("uuid"), project_uuid=q.get("project_uuid"),
                              quota_limit=q.get("quota_limit"), quota_used=q.get("quota_used") + 1,
                              resource_type=q.get("resource_type"),
                              resource_unit=q.get("resource_unit"))
        qq = core_api.get_quota(uuid=q.get("uuid"))
        print(f"Updated quota: {qq}")

    for q in quotas:
        print(f"Deleting quota: {q.get('uuid')}")
        core_api.delete_quota(uuid=q.get("uuid"))

    quotas = core_api.list_quotas(project_uuid="74a5b28b-c1a2-4fad-882b-03362dddfa71")
    print(f"Quotas after deletion!: {quotas}")


    #core_api.create_quota(project_uuid="74a5b28b-c1a2-4fad-882b-03362dddfa71",
    #                      resource_type="disk", resource_unit="hours", quota_limit=100)
'''