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
import os
from typing import List, Tuple, Union

from fabric_cf.orchestrator.orchestrator_proxy import Status

from fabrictestbed.external_api.artifact_manager import ArtifactManager, Visibility
from fabrictestbed.util.utils import Utils

from fabrictestbed.external_api.core_api import CoreApi

from fabrictestbed.util.constants import Constants

from fabrictestbed.slice_manager import SliceManager


class FabricManagerException(Exception):
    """Custom exception for FabricManager-related errors."""
    pass


class FabricManager(SliceManager):
    """
    FabricManager extends SliceManager to integrate capabilities for interacting with
    the FABRIC testbed, including managing SSH keys, retrieving user/project information,
    and handling artifacts.

    :param cm_host: Credential Manager host
    :param oc_host: Orchestrator host
    :param core_api_host: Core API host for user/project info
    :param am_host: Artifact Manager host for managing artifacts
    :param token_location: Location of the token file
    :param project_id: Identifier for the project
    :param scope: Scope of the API access (default is 'all')
    :param initialize: Flag to initialize the SliceManager
    :param project_name: Name of the project
    :param auto_refresh: Flag to enable automatic token refresh
    """
    def __init__(self, *, cm_host: str = None, oc_host: str = None, core_api_host: str = None, am_host: str = None,
                 token_location: str = None, project_id: str = None, scope: str = "all", initialize: bool = True,
                 project_name: str = None, auto_refresh: bool = True):
        super().__init__(cm_host=cm_host, oc_host=oc_host, token_location=token_location,
                         project_id=project_id, scope=scope, initialize=initialize, project_name=project_name,
                         auto_refresh=auto_refresh)
        if core_api_host is None:
            core_api_host = os.environ.get(Constants.FABRIC_CORE_API_HOST)

        if core_api_host is None is None:
            raise FabricManagerException(f"Invalid initialization parameters: oc_host: {oc_host}")

        self.core_api_host = core_api_host

        if am_host is None:
            am_host = os.environ.get(Constants.FABRIC_AM_HOST)

        if am_host is None is None:
            raise FabricManagerException(f"Invalid initialization parameters: am_host: {am_host}")

        self.am_host = am_host

    def get_ssh_keys(self, uuid: str = None, email: str = None) -> list:
        """
        Retrieve SSH keys associated with a user.

        :param uuid: User's UUID
        :param email: User's email address
        :return: List of SSH keys
        :raises FabricManagerException: If there is an error in retrieving SSH keys.
        """
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_token())
            return core_api_proxy.get_ssh_keys(uuid=uuid, email=email)

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def create_ssh_keys(self, key_type: str, description: str, comment: str = "ssh-key-via-api",
                        store_pubkey: bool = True) -> list:
        """
        Create new SSH keys for a user.

        :param key_type: Type of the SSH key (e.g., 'sliver' or 'bastion')
        :param description: Description of the key
        :param comment: Comment to associate with the SSH key
        :param store_pubkey: Flag indicating whether the public key should be stored
        :return: List of SSH keys
        :raises FabricManagerException: If there is an error in creating SSH keys.
        """
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_token())
            return core_api_proxy.create_ssh_keys(key_type=key_type, comment=comment, store_pubkey=store_pubkey,
                                                  description=description)

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def get_user_info(self, uuid: str = None, email: str = None) -> dict:
        """
        Retrieve user information using Core API.

        :param uuid: User's UUID
        :param email: User's email address
        :return: Dictionary containing user information
        :raises FabricManagerException: If there is an error in retrieving user information.
        """
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_token())
            return core_api_proxy.get_user_info(uuid=uuid, email=email)

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def get_project_info(self, project_name: str = "all", project_id: str = "all", uuid: str = None) -> list:
        """
        Retrieve information about the user's projects.

        :param project_name: Name of the project (default is "all")
        :param project_id: Identifier of the project (default is "all")
        :param uuid: User's UUID
        :return: List of projects
        :raises FabricManagerException: If there is an error in retrieving project information.
        """
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_token())
            return core_api_proxy.get_user_projects(project_name=project_name, project_id=project_id, uuid=uuid)

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def get_metrics_overview(self, excluded_projects: List[str] = None,
                             authenticated: bool = False) -> Tuple[Status, Union[list, Exception]]:
        """
        Retrieve an overview of metrics.

        :param excluded_projects: List of projects to exclude from the metrics
        :param authenticated: Flag indicating whether to retrieve metrics for a specific user
        :return: Tuple containing the status and a list of metrics or an exception
        """
        try:
            token = self.ensure_valid_token() if authenticated else None
            return self.oc_proxy.get_metrics_overview(token=token, excluded_projects=excluded_projects)

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            return Status.FAILURE, FabricManagerException(error_message)

    def create_artifact(self, artifact_title: str, description_short: str, description_long: str, authors: List[str],
                        tags: List[str], visibility: Visibility = Visibility.Author,
                        update_existing: bool = True) -> dict:
        """
        Create a new artifact or update an existing one.

        :param artifact_title: Title of the artifact
        :param description_short: Short description of the artifact
        :param description_long: Long description of the artifact
        :param authors: List of authors associated with the artifact
        :param tags: List of tags associated with the artifact
        :param visibility: Visibility level of the artifact
        :param update_existing: Flag indicating whether to update an existing artifact
        :return: Dictionary containing the artifact details
        :raises FabricManagerException: If there is an error in creating or updating the artifact.
        """
        try:
            if not authors:
                authors = []
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_token())
            existing_artifacts = am_proxy.list_artifacts(search=artifact_title)

            artifact = None
            if update_existing:
                for e in existing_artifacts:
                    if any(author.get('uuid') == self.user_id for author in e.get('authors')):
                        artifact = e
                        break

            author_ids = [self.get_user_id()]
            if self.user_email in authors:
                authors.remove(self.user_email)
            for a in authors:
                author_info = self.get_user_info(email=a)
                if author_info and author_info.get('uuid') and author_info.get('uuid') not in author_ids:
                    author_ids.append(author_info.get('uuid'))

            if not artifact:
                artifact = am_proxy.create_artifact(
                    artifact_title=artifact_title,
                    description_short=description_short,
                    description_long=description_long,
                    tags=tags,
                    visibility=visibility,
                    authors=author_ids,
                    project_id=self.project_id
                )
            else:
                am_proxy.update_artifact(artifact_id=artifact.get("uuid"),
                                         artifact_title=artifact_title,
                                         description_short=description_short,
                                         description_long=description_long,
                                         tags=tags,
                                         visibility=visibility,
                                         authors=authors, project_id=self.project_id)
            return artifact

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def list_artifacts(self, search: str = None, artifact_id: str = None) -> list:
        """
        List artifacts based on a search query.

        :param search: Search can be tag or title query for filtering artifacts
        :param artifact_id: The unique identifier of the artifact to retrieve.
        :return: List of artifacts
        :raises FabricManagerException: If there is an error in listing the artifacts.
        """
        try:
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_token())
            if not artifact_id:
                return am_proxy.list_artifacts(search=search)
            else:
                return [am_proxy.get_artifact(artifact_id=artifact_id)]
        except Exception as e:
            raise FabricManagerException(Utils.extract_error_message(exception=e))

    def delete_artifact(self, artifact_id: str = None, artifact_title: str = None):
        """
        Delete an artifact by its ID or title.

        This method deletes an artifact from the system. Either the `artifact_id` or `artifact_title`
        must be provided to identify the artifact to be deleted. If `artifact_id` is not provided,
        the method will search for the artifact using `artifact_title` and then delete it.

        :param artifact_id: The unique identifier of the artifact to be deleted.
        :param artifact_title: The title of the artifact to be deleted.
        :raises ValueError: If neither `artifact_id` nor `artifact_title` is provided.
        :raises FabricManagerException: If an error occurs during the deletion process.
        """
        if artifact_id is None and artifact_title is None:
            raise ValueError("Either artifact_id or artifact_title must be specified!")

        try:
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_token())
            existing_artifacts = self.list_artifacts(search=artifact_title, artifact_id=artifact_id)

            artifact = None
            for e in existing_artifacts:
                if any(author.get('uuid') == self.user_id for author in e.get('authors')):
                    artifact = e
                    break
            if artifact:
                artifact_id = artifact.get("uuid")

            if artifact_id:
                am_proxy.delete_artifact(artifact_id=artifact_id)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def get_tags(self):
        """
        Retrieve all tags associated with artifacts.

        This method returns a list of all tags that are associated with artifacts in the system.
        Tags are useful for categorizing and searching for artifacts.

        :return: A list of tags.
        :raises FabricManagerException: If an error occurs while retrieving the tags.
        """
        try:
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_token())
            return am_proxy.get_tags()
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def upload_file_to_artifact(self, file_to_upload: str, artifact_id: str = None, artifact_title: str = None) -> dict:
        """
        Upload a file to an existing artifact.

        This method uploads a file to an artifact identified by either its `artifact_id` or `artifact_title`.
        If `artifact_id` is not provided, the method will search for the artifact using `artifact_title` before uploading the file.

        :param file_to_upload: The path to the file that should be uploaded.
        :param artifact_id: The unique identifier of the artifact to which the file will be uploaded.
        :param artifact_title: The title of the artifact to which the file will be uploaded.
        :return: A dictionary containing the details of the uploaded file.
        :raises ValueError: If neither `artifact_id` nor `artifact_title` is provided.
        :raises FabricManagerException: If an error occurs during the upload process.
        """
        if artifact_id is None and artifact_title is None:
            raise ValueError("Either artifact_id or artifact_title must be specified!")

        try:
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_token())
            artifacts = self.list_artifacts(artifact_id=artifact_id, search=artifact_title)
            if len(artifacts) != 1:
                raise ValueError(f"Requested artifact: {artifact_id}/{artifact_title} has 0 or more than versions "
                                 f"available, Please specify the version to download!")
            artifact = artifacts[0]
            artifact_id = artifact.get(artifact.get("uuid"))
            return am_proxy.upload_file_to_artifact(artifact_id=artifact_id, file_path=file_to_upload)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def download_artifact(self, download_dir: str, artifact_id: str = None, artifact_title: str = None,
                          version: str = None, version_urn: str = None):
        """
        Download an artifact to a specified directory.

        This method downloads an artifact identified by either its `artifact_id` or `artifact_title` to the specified `download_dir`.
        If `artifact_id` is not provided, the method will search for the artifact using `artifact_title`.

        :param download_dir: The directory where the artifact will be downloaded.
        :param artifact_id: The unique identifier of the artifact to download.
        :param artifact_title: The title of the artifact to download.
        :param version: The specific version of the artifact to download (optional).
        :param version_urn: Version urn for the artifact.
        :return: The path to the downloaded artifact.
        :raises ValueError: If neither `artifact_id` nor `artifact_title` is provided.
        :raises FabricManagerException: If an error occurs during the download process.
        """
        if artifact_id is None and artifact_title is None and version_urn is None:
            raise ValueError("Either artifact_id, artifact_title or version_urn must be specified!")
        try:
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_token())
            if not version_urn:
                artifacts = self.list_artifacts(artifact_id=artifact_id, search=artifact_title)
                if len(artifacts) != 1:
                    raise ValueError(f"Requested artifact: {artifact_id}/{artifact_title} has 0 or more than versions "
                                     f"available, Please specify the version to download!")
                artifact = artifacts[0]
                for v in artifact.get("versions"):
                    if not version:
                        version = v.get("version")
                        version_urn = v.get("urn")
                        break
                    if version in v:
                        version_urn = v.get("urn")
                        break
            if not version_urn:
                raise ValueError(f"Requested artifact: {artifact_id}/{artifact_title} with {version}/{version_urn} "
                                 f"can not be found!")
            return am_proxy.download_artifact(urn=version_urn, download_dir=download_dir, version=version)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)
