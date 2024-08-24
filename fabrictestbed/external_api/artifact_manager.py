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
import enum
import json
import os
from typing import List
from urllib.parse import quote

import requests


class Visibility(enum.Enum):
    Author = enum.auto()
    Project = enum.auto()
    Public = enum.auto()

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name


class ArtifactManagerError(Exception):
    """
    Custom exception for errors raised by the ArtifactManager.
    """
    pass


class ArtifactManager:
    def __init__(self, api_url: str, token: str):
        """
        Initializes the ArtifactManager with the API base URL and authentication token.

        :param api_url: The base URL for the artifact API. The URL should start with 'https'.
                        If not provided, it will be automatically prefixed.
        :param token: The authentication token required for accessing the API.
                      This token will be included in the Authorization header for all API requests.
        """
        if "https" not in api_url:
            self.api_url = f"https://{api_url}/api"
        else:
            self.api_url = f"{api_url}/api"

        # Set the headers for API requests
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    def create_artifact(self, artifact_title: str, description_short: str, description_long: str, authors: List[str],
                        project_id: str, tags: List[str], visibility: Visibility = Visibility.Author) -> str:
        """
        Creates a new artifact in the FABRIC Testbed.

        :param artifact_title: The title of the artifact to create.
        :param description_short: A brief description of the artifact.
        :param description_long: A detailed description of the artifact.
        :param authors: A list of authors associated with the artifact.
        :param project_id: The unique identifier for the project associated with the artifact.
        :param tags: A list of tags to associate with the artifact for easier searching.
        :param visibility: The visibility level of the artifact. Defaults to 'Author' level visibility.
        :return: The ID of the newly created artifact.
        :raises ArtifactManagerError: If the artifact creation fails.
        """
        create_artifact_url = f"{self.api_url}/artifacts"

        data = {
            "authors": authors,
            "description_short": description_short,
            "description_long": description_long,
            "project_uuid": project_id,
            "title": artifact_title,
            "visibility": str(visibility).lower()
        }
        if tags:
            data["tags"] = tags

        response = requests.post(create_artifact_url, headers=self.headers, json=data)
        self.raise_for_status(response=response)

        return response.json()

    def update_artifact(self, artifact_id: str, artifact_title: str, description_short: str, description_long: str,
                        authors: List[str], project_id: str, tags: List[str],
                        visibility: Visibility = Visibility.Author):
        """
        Updates an existing artifact in the FABRIC Testbed.

        :param artifact_id: The unique identifier of the artifact to update.
        :param artifact_title: The updated title of the artifact.
        :param description_short: The updated short description of the artifact.
        :param description_long: The updated long description of the artifact.
        :param authors: A list of updated authors associated with the artifact.
        :param project_id: The unique identifier for the project associated with the artifact.
        :param tags: A list of updated tags to associate with the artifact.
        :param visibility: The updated visibility level of the artifact. Defaults to 'Author' level visibility.
        :return: None
        :raises ArtifactManagerError: If the artifact update fails.
        """
        update_artifact_url = f"{self.api_url}/artifacts/{artifact_id}"

        data = {
            "authors": authors,
            "description_short": description_short,
            "description_long": description_long,
            "project_uuid": project_id,
            "title": artifact_title,
            "visibility": str(visibility).lower()
        }
        if tags:
            data["tags"] = tags

        response = requests.put(update_artifact_url, headers=self.headers, json=data)
        self.raise_for_status(response=response)

    def upload_file_to_artifact(self, artifact_id: str, file_path: str, storage_type: str = "fabric",
                                storage_repo: str = "renci") -> dict:
        """
        Uploads a file to an existing artifact in the FABRIC Testbed.

        :param artifact_id: The ID of the artifact to which the file will be uploaded.
        :param file_path: The local path to the file that will be uploaded.
        :param storage_type: The type of storage to use (default: 'fabric').
        :param storage_repo: The storage repository to use (default: 'renci').
        :return: The response from the API as a JSON object.
        :raises ArtifactManagerError: If the file upload fails.
        """
        upload_content_url = f"{self.api_url}/contents"

        headers = self.headers.copy()
        headers.pop("Content-Type")

        # Prepare the multipart form data
        files = {
            'file': (os.path.basename(file_path), open(file_path, 'rb'), 'application/gzip'),
            'data': (None, json.dumps({
                "artifact": artifact_id,
                "storage_type": storage_type,
                "storage_repo": storage_repo
            }), 'application/json')
        }

        response = requests.post(upload_content_url, headers=headers, files=files)
        self.raise_for_status(response=response)

        return response.json()

    def list_artifacts(self, search: str = None) -> List[dict]:
        """
        Lists all artifacts in the FABRIC Testbed artifact repository, with optional filtering by search term.
        Fetches all pages of results.

        :param search: Optional search filter (e.g., tag, project name).
                       If provided, only artifacts matching the search filter will be returned.
        :return: A list of artifacts as a list of JSON objects.
        :raises ArtifactManagerError: If the listing of artifacts fails.
        """
        list_url = f"{self.api_url}/artifacts"

        params = {}
        if search:
            params['search'] = search

        all_artifacts = []
        page = 1

        while True:
            params['page'] = page
            response = requests.get(list_url, headers=self.headers, params=params)
            self.raise_for_status(response=response)

            data = response.json()
            all_artifacts.extend(data['results'])

            if not data.get('next'):
                break
            page += 1

        return all_artifacts

    def get_artifact(self, artifact_id: str) -> dict:
        """
        Retrieves the details of a specific artifact by its ID.

        :param artifact_id: The unique identifier of the artifact to retrieve.
        :return: A dictionary representing the artifact's details.
        :raises ArtifactManagerError: If the retrieval of the artifact fails.
        """
        get_url = f"{self.api_url}/artifacts/{artifact_id}"

        response = requests.get(get_url, headers=self.headers)
        self.raise_for_status(response=response)

        return response.json()

    def download_artifact(self, urn: str, version: str, download_dir: str) -> str:
        """
        Downloads a specific artifact by its URN from the artifact repository and saves it in a version-specific subdirectory.

        :param urn: The unique identifier of the specific version of the artifact to download.
        :param version: The version of the artifact to create a subdirectory for.
        :param download_dir: The directory where the downloaded artifact will be saved.
        :return: The file path of the downloaded artifact.
        :raises ArtifactManagerError: If the download fails.
        """
        # Construct the download URL
        download_url = f"{self.api_url}/contents/download/{urn}"

        # Define headers to match the curl command
        headers = {
            'accept': 'application/json'
        }

        try:
            response = requests.get(download_url, headers=headers, stream=True)
            self.raise_for_status(response)  # Raises HTTPError for bad responses

            # Extract the file name from headers or URL
            content_disposition = response.headers.get('content-disposition', '')
            file_name = content_disposition.split('filename=')[-1].strip(
                '\"') if 'filename=' in content_disposition else 'artifact'

            # Remove all file extensions for directory name
            base_name = file_name
            while '.' in base_name:
                base_name = os.path.splitext(base_name)[0]

            # Create directory structure
            outer_dir = os.path.join(download_dir, base_name)
            version_dir = os.path.join(outer_dir, version)

            os.makedirs(version_dir, exist_ok=True)

            # Define the file path in the version directory
            file_path = os.path.join(version_dir, file_name)

            # Save the file to the specified directory
            with open(file_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
            return file_path
        except requests.HTTPError as e:
            raise ArtifactManagerError(f"HTTPError: {e}")
        except Exception as e:
            raise ArtifactManagerError(f"Exception: {e}")

    def delete_artifact(self, artifact_id: str):
        """
        Deletes a specific artifact by its ID from the artifact repository.

        :param artifact_id: The unique identifier of the artifact to delete.
        :raises ArtifactManagerError: If the deletion fails.
        """
        delete_url = f"{self.api_url}/artifacts/{artifact_id}"

        response = requests.delete(delete_url, headers=self.headers)
        self.raise_for_status(response=response)

    def get_tags(self) -> List[str]:
        """
        Retrieves all defined tags from the FABRIC Testbed artifact repository.

        :return: A list of all tags as strings.
        :raises ArtifactManagerError: If the retrieval of tags fails.
        """
        get_url = f"{self.api_url}/meta/tags"

        response = requests.get(get_url, headers=self.headers)
        self.raise_for_status(response=response)

        return response.json().get("results")

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

            raise ArtifactManagerError(f"Error {response.status_code}: {e}. Message: {message}")
