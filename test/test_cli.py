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
from click.testing import CliRunner

from fabrictestbed.cli import cli


def test_token_issue():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['token', 'issue'])
    print(result.output)
    assert result.exit_code == 0
    assert 'FABRIC_ID_TOKEN' in result.output


def test_token_issue_verbose():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['--verbose', 'token', 'issue'])
    print(result.output)
    assert result.exit_code == 0
    assert 'scope: all' in result.output
    assert 'FABRIC_ID_TOKEN' in result.output


def test_token_refresh():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['token', 'refresh', '--refreshtoken', 'https://cilogon.org/oauth2/refreshToken/4884e9b835260111384cf83c2617efbf/1604534366554'])
    print(result.output)
    assert result.exit_code != 0


def test_token_revoke():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['token', 'revoke', '--refreshtoken', 'https://cilogon.org/oauth2/refreshToken/4884e9b835260111384cf83c2617efbf/1604534366554'])
    print(result.output)
    assert result.exit_code != 0


def test_resources_get():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['resources', 'query'])
    print(result.output)
    assert result.exit_code != 0


def test_resources_get_with_id_token():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['resources', 'query', '--idtoken',
                                     'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJlbWFpbCI6Imt0aGFyZTEwQGVtYWlsLnVuYy5lZHUiLCJnaXZlbl9uYW1lIjoiS29tYWwiLCJmYW1pbHlfbmFtZSI6IlRoYXJlamEiLCJuYW1lIjoiS29tYWwgVGhhcmVqYSIsImlzcyI6Imh0dHBzOi8vY2lsb2dvbi5vcmciLCJzdWIiOiJodHRwOi8vY2lsb2dvbi5vcmcvc2VydmVyQS91c2Vycy8xMTkwNDEwMSIsImF1ZCI6ImNpbG9nb246L2NsaWVudF9pZC8xMjUzZGVmYzYwYTMyM2ZjYWEzYjQ0OTMyNjQ3NjA5OSIsInRva2VuX2lkIjoiaHR0cHM6Ly9jaWxvZ29uLm9yZy9vYXV0aDIvaWRUb2tlbi8zNzY5NDgzNTcxNGM5MjUyNDc3M2MxYmYxOGVkOWVjYS8xNjA0NTQyMTI0OTU2IiwiYXV0aF90aW1lIjoiMTYwNDU0MjEyNCIsImV4cCI6MTYwNDU0NTc0NiwiaWF0IjoxNjA0NTQyMTQ2LCJyb2xlcyI6WyJDTzptZW1iZXJzOmFjdGl2ZSIsIkNPOkNPVTpKdXB5dGVyaHViOm1lbWJlcnM6YWN0aXZlIiwiQ086Q09VOnByb2plY3QtbGVhZHM6bWVtYmVyczphY3RpdmUiXSwic2NvcGUiOiJhbGwiLCJwcm9qZWN0IjoiYWxsIn0.V_tQCx97g5KS4dJH20f7XtIHyRQIu5U0yhmxLs8R9DMXhWZn51f8bBGogisYivs3bGXHIsR3YwJP8GEFJbjyZRFKyj9RgnqWhttug3UmbL09AgqtZs2mbLfmFIZGub-5wreM625GLX4el8IdxrUfV1H8W5o0b-7cCA7n006lRZI0L0rbZiKVJNBhuXn8vV8KdgLaKKQ-ixL1zTfi_-g7bvPXy6FEOxBgNeDETb9svmidjGneuexuH66xa8MTrYSj0gfXDHRC__MzAGNkfCpCKMcUc0kNlPtXCpoa-fVgY2Lw3qEbD16BhHMHvSNQdAyFIcL7UvRXxs7OPEsz8KLObA'])
    print(result.output)
    assert result.exit_code != 0


def test_resources_get_with_refresh_token():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['resources', 'query', '--refreshtoken',
                                     'https://cilogon.org/oauth2/refreshToken/5ff57e742945eed9b2377b3f123ecc8d/1604543301530'])
    print(result.output)
    assert result.exit_code != 0


if __name__ == '__main__':
    import os
    os.environ['FABRIC_CREDMGR_HOST'] = 'dev-2.fabric-testbed.net'
    os.environ['FABRIC_ORCHESTRATOR_HOST'] = 'dev-2.fabric-testbed.net'
    test_token_issue()
    test_token_issue_verbose()
    test_token_refresh()
    test_token_revoke()
    test_resources_get()
    test_resources_get_with_id_token()
    test_resources_get_with_refresh_token()
