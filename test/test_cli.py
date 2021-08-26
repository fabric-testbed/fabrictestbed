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


def test_token_refresh():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['token', 'refresh'])
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


if __name__ == '__main__':
    import os
    os.environ['FABRIC_CREDMGR_HOST'] = 'dev-2.fabric-testbed.net'
    os.environ['FABRIC_ORCHESTRATOR_HOST'] = 'dev-2.fabric-testbed.net'
    os.environ['FABRIC_TOKEN_LOCATION'] = "./tokens.json"
    test_token_refresh()
    test_token_revoke()
    test_resources_get()