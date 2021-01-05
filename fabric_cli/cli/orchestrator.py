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

from fabric_cf.orchestrator import swagger_client
from fabric_cf.orchestrator.swagger_client.rest import ApiException as OrchestratorException

ORCHESTRATOR_API_PORT_SERVER = os.getenv('FABRIC_ORCHESTRATOR_HOST', 'dev-2.fabric-testbed.net:8700')


class Orchestrator:
    """
    Implements various orchestrator APIs
    """
    @staticmethod
    def resources(*, id_token: str):
        """
        Query resources
        @param id_token: id token
        """
        try:
            # create an instance of the API class
            configuration = swagger_client.Configuration()
            configuration.host = "http://{}/".format(ORCHESTRATOR_API_PORT_SERVER)
            configuration.api_key['Authorization'] = id_token
            configuration.api_key_prefix['Authorization'] = 'Bearer'

            api_instance = swagger_client.ApiClient(configuration)

            resources_api = swagger_client.ResourcesApi(api_client=api_instance)
            api_response = resources_api.resources_get()
            return api_response.to_dict()
        except OrchestratorException as e:
            #traceback.print_exc()
            raise Exception(e.reason, e.body)