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
# Author Komal Thareja (kthare10@renci.org)

"""
High-level FABRIC manager that composes slice, user/project, and artifact operations.

This module defines :class:`FabricManager`, which extends your local
:class:`slice_manager.SliceManager` to add convenience methods for:

- User SSH key management (via Core API)
- User/project lookup (via Core API)
- Artifact CRUD and file upload/download (via Artifact Manager)

It honors **in-memory tokens** (``id_token`` / ``refresh_token``) for MCP-based
workflows and falls back to legacy file-based tokens when a token file path is
provided.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple, Union

from fabric_cf.orchestrator.orchestrator_proxy import Status

from fabrictestbed.external_api.core_api import CoreApi
from fabrictestbed.external_api.artifact_manager import ArtifactManager, Visibility
from fabrictestbed.util.utils import Utils
from fabrictestbed.util.constants import Constants

from fabrictestbed.slice_manager import SliceManager


class FabricManagerException(Exception):
    """Custom exception for FabricManager-related errors."""
    pass


class FabricManager(SliceManager):
    """
    High-level orchestrator for FABRIC tasks across slices, users/projects, and artifacts.

    Inherits token handling and slice operations from :class:`slice_manager.SliceManager`,
    which itself uses an MCP-friendly :class:`token_manager.TokenManager`.

    :param cm_host: Credential Manager host (for token decoding / optional refresh).
    :type cm_host: str or None
    :param oc_host: Orchestrator host (e.g., ``orchestrator.fabric-testbed.net``).
                    If ``None``, read from ``FABRIC_ORCHESTRATOR_HOST`` env var.
    :type oc_host: str or None
    :param core_api_host: Core API host (e.g., ``alpha-6.fabric-testbed.net``).
                          If ``None``, read from ``FABRIC_CORE_API_HOST`` env var.
    :type core_api_host: str or None
    :param am_host: Artifact Manager base URL. If ``None``, read from ``FABRIC_AM_HOST`` env var.
    :type am_host: str or None
    :param token_location: Token JSON path (legacy mode). Use ``None`` for in-memory (MCP) mode.
    :type token_location: str or None
    :param project_id: Optional project UUID for scoping.
    :type project_id: str or None
    :param project_name: Optional project name for scoping.
    :type project_name: str or None
    :param scope: Token scope (default: ``"all"``) used if refresh is performed via CredMgr.
    :type scope: str
    :param id_token: In-memory FABRIC ID token (JWT) for MCP usage.
    :type id_token: str or None
    :param refresh_token: In-memory refresh token (optional) for MCP usage.
    :type refresh_token: str or None
    :param no_write: If ``True``, never write tokens to disk (recommended for MCP).
    :type no_write: bool

    :raises FabricManagerException: If required env/hosts are not provided.
    """

    def __init__(
        self,
        *,
        cm_host: Optional[str] = None,
        oc_host: Optional[str] = None,
        core_api_host: Optional[str] = None,
        am_host: Optional[str] = None,
        token_location: Optional[str] = None,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        scope: str = "all",
        id_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        no_write: bool = False,
    ):
        super().__init__(
            cm_host=cm_host,
            oc_host=oc_host,
            token_location=token_location,
            project_id=project_id,
            project_name=project_name,
            scope=scope,
            id_token=id_token,
            refresh_token=refresh_token,
            no_write=no_write,
        )

        if core_api_host is None:
            core_api_host = os.environ.get(Constants.FABRIC_CORE_API_HOST)
        if not core_api_host:
            raise FabricManagerException(f"Invalid initialization parameters: core_api_host={core_api_host!r}")
        self.core_api_host = core_api_host

        if am_host is None:
            am_host = os.environ.get(Constants.FABRIC_AM_HOST)
        if not am_host:
            raise FabricManagerException(f"Invalid initialization parameters: am_host={am_host!r}")
        self.am_host = am_host

    # -------------------------------------------------------------------------
    # SSH Keys (Core API)
    # -------------------------------------------------------------------------

    def get_ssh_keys(self, uuid: str = None, email: str = None) -> list:
        """
        Retrieve SSH keys associated with a user.

        :param uuid: User UUID to query (optional).
        :type uuid: str or None
        :param email: User email to query (optional).
        :type email: str or None
        :return: List of SSH key objects (shape as returned by Core API).
        :rtype: list
        :raises FabricManagerException: On Core API errors.
        """
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_id_token())
            return core_api_proxy.get_ssh_keys(uuid=uuid, email=email)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def create_ssh_keys(
        self,
        *,
        key_type: str,
        description: str,
        comment: str = "ssh-key-via-api",
        store_pubkey: bool = True,
    ) -> list:
        """
        Create (register) SSH keys for the current user.

        :param key_type: Key type (e.g., ``"sliver"`` or ``"bastion"``).
        :type key_type: str
        :param description: Description to store for the key.
        :type description: str
        :param comment: Comment (often the public key's trailing comment).
        :type comment: str
        :param store_pubkey: If ``True``, store the public key.
        :type store_pubkey: bool
        :return: List of key records after creation (shape per Core API).
        :rtype: list
        :raises FabricManagerException: On Core API errors.
        """
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_id_token())
            return core_api_proxy.create_ssh_keys(
                key_type=key_type,
                comment=comment,
                store_pubkey=store_pubkey,
                description=description,
            )
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    # -------------------------------------------------------------------------
    # User / Project Info (Core API)
    # -------------------------------------------------------------------------

    def get_user_info(self, *, uuid: str = None, email: str = None) -> dict:
        """
        Retrieve user info by email or uuid.

        :param uuid: User's uuid.
        :type uuid: str
        :param email: User's email address.
        :type email: str
        :return: User info dict (shape per Core API).
        :rtype: dict
        :raises FabricManagerException: On Core API errors.
        """
        if not email and not uuid:
            raise FabricManagerException("email or uuid must be provided")
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_id_token())
            return core_api_proxy.get_user_info(uuid=uuid, email=email)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def get_user_id(self) -> str:
        """
        Retrieve user id

        :return: User Guid
        :rtype: str
        :raises FabricManagerException: On Core API errors.
        """
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_id_token())
            return core_api_proxy.get_user_id()
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def get_project_info(self, *, project_name: str = "all", project_id: str = "all", uuid: Optional[str] = None) -> list:
        """
        Retrieve project info for the current user.

        :param project_name: Project name filter (exact match in most deployments).
        :type project_name: str
        :param project_id: Project id filter (exact match in most deployments).
        :type project_id: str
        :param uuid: Optional user UUID; if omitted, the Core API may infer current user.
        :type uuid: str or None
        :return: List of matching project records (shape per Core API).
        :rtype: list
        :raises FabricManagerException: On Core API errors.
        """
        if not project_name and not project_id:
            raise FabricManagerException("project_name or project_id must be provided")
        try:
            core_api_proxy = CoreApi(core_api_host=self.core_api_host, token=self.ensure_valid_id_token())
            return core_api_proxy.get_user_projects(uuid=uuid, project_name=project_name, project_id=project_id)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def get_metrics_overview(self,
                             excluded_projects: List[str] = None,
                             authenticated: bool = False
                             ) -> Tuple[Status, Union[list, Exception]]:
        """
        Fetch aggregate Core API metrics/overview.

        :param excluded_projects: List of projects to exclude from the metrics
        :param authenticated: Flag indicating whether to retrieve metrics for a specific user
        :return: Tuple containing the status and a list of metrics or an exception
        """
        try:
            token = self.ensure_valid_id_token() if authenticated else None
            return self.oc_proxy.get_metrics_overview(token=token,
                                                      excluded_projects=excluded_projects)

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def create_artifact(self,
                        artifact_title: str,
                        description_short: str,
                        description_long: str,
                        authors: List[str],
                        tags: List[str],
                        visibility: Visibility = Visibility.Author,
                        update_existing: bool = True
                        ) -> dict:
        """
        Create a new artifact.

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
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_id_token())
            existing_artifacts = am_proxy.list_artifacts(search=artifact_title)

            artifact = None
            if update_existing:
                for e in existing_artifacts:
                    for author in e.get("authors"):
                        if author.get("uuid") == self.get_user_id():
                            artifact = e
                            break
                    if artifact:
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
                                         authors=author_ids, project_id=self.project_id)
            return artifact

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def list_artifacts(self,
                       search: str = None,
                       artifact_id: str = None) -> list:
        """
        List artifacts with optional filters.

        :param artifact_id: Specific artifact UUID filter.
        :type artifact_id: str or None
        :param search: Search string (title substring match).
        :type search: str or None
        :param owner: Owner (email or subject) to filter.
        :type owner: str or None
        :param visibility: Visibility filter (e.g., PRIVATE, PROJECT, PUBLIC).
        :type visibility: Visibility or None
        :param limit: Max items to return (default: ``50``).
        :type limit: int
        :param offset: Pagination offset (default: ``0``).
        :type offset: int
        :return: List of artifact records.
        :rtype: list
        :raises FabricManagerException: On Artifact Manager errors.
        """
        try:
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_id_token())
            if not artifact_id:
                return am_proxy.list_artifacts(search=search)
            else:
                return [am_proxy.get_artifact(artifact_id=artifact_id)]
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def delete_artifact(self, *, artifact_id: str) -> str:
        """
        Delete an artifact by UUID.

        :param artifact_id: Artifact UUID to delete.
        :type artifact_id: str
        :return: Confirmation message from Artifact Manager.
        :rtype: str
        :raises FabricManagerException: On Artifact Manager errors.
        """
        if not artifact_id:
            raise FabricManagerException("artifact_id must be provided")
        try:
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_id_token())
            return am_proxy.delete_artifact(artifact_id=artifact_id)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def get_tags(self) -> list:
        """
        Retrieve available artifact tags.

        :return: List of tag strings.
        :rtype: list
        :raises FabricManagerException: On Artifact Manager errors.
        """
        try:
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_id_token())
            return am_proxy.get_tags()
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def upload_file_to_artifact(self,
                                file_to_upload: str,
                                artifact_id: str = None,
                                artifact_title: str = None) -> dict:
        """
        Upload a file as a new artifact version.

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
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_id_token())
            artifacts = self.list_artifacts(artifact_id=artifact_id, search=artifact_title)
            if len(artifacts) != 1:
                raise ValueError(f"Requested artifact: {artifact_id}/{artifact_title} has 0 or more than versions "
                                 f"available, Please specify the version to download!")
            artifact = artifacts[0]
            artifact_id = artifact.get("uuid")
            return am_proxy.upload_file_to_artifact(artifact_id=artifact_id, file_path=file_to_upload)
        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)

    def download_artifact(
        self,
        *,
        download_dir: str,
        artifact_id: Optional[str] = None,
        artifact_title: Optional[str] = None,
        version: Optional[str] = None,
        version_urn: Optional[str] = None,
    ) -> str:
        """
        Download an artifact (by id/title/version or a specific version URN).

        Provide either ``artifact_id`` or ``artifact_title`` (with optional ``version``),
        **or** pass a concrete ``version_urn`` for direct download.

        :param download_dir: Destination directory for the downloaded file(s).
        :type download_dir: str
        :param artifact_id: Artifact UUID to resolve (optional).
        :type artifact_id: str or None
        :param artifact_title: Artifact title to search (optional).
        :type artifact_title: str or None
        :param version: Specific version label to download (optional).
        :type version: str or None
        :param version_urn: Exact version URN to download (bypasses listing).
        :type version_urn: str or None
        :return: Path to the downloaded file (or directory), per Artifact Manager behavior.
        :rtype: str
        :raises ValueError: If neither an artifact identifier nor a version URN is provided.
        :raises FabricManagerException: On Artifact Manager errors.
        """
        if not download_dir:
            raise FabricManagerException("download_dir must be provided")

        if artifact_id is None and artifact_title is None and version_urn is None:
            raise ValueError("Either artifact_id, artifact_title, or version_urn must be specified!")

        try:
            am_proxy = ArtifactManager(api_url=self.am_host, token=self.ensure_valid_id_token())

            if not version_urn:
                # Resolve to a specific version URN
                artifacts = self.list_artifacts(artifact_id=artifact_id, search=artifact_title)
                if len(artifacts) != 1:
                    raise ValueError(
                        f"Ambiguous artifact resolution for id={artifact_id!r} title={artifact_title!r}: "
                        f"expected exactly one artifact, got {len(artifacts)}"
                    )
                artifact = artifacts[0]
                versions = artifact.get("versions", []) or []
                version_urn = None

                if version:
                    # Find matching version entry by label
                    for v in versions:
                        if v.get("version") == version:
                            version_urn = v.get("urn")
                            break
                    if not version_urn:
                        raise ValueError(f"Version {version!r} not found for artifact {artifact.get('uuid')}")
                else:
                    # Choose the first/primary version if no version specified
                    if versions:
                        version_urn = versions[0].get("urn")

                if not version_urn:
                    raise ValueError("Could not resolve a version URN for the requested artifact")

            # Perform the download by URN
            return am_proxy.download_artifact(urn=version_urn, download_dir=download_dir, version=version)

        except Exception as e:
            error_message = Utils.extract_error_message(exception=e)
            raise FabricManagerException(error_message)
