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
import traceback
import webbrowser
from typing import Tuple

import click
import os
import json

from .api import CredmgrProxy, OrchestratorProxy, Status, CmStatus

from .exceptions import TokenExpiredException


def __do_refresh_token(*, credmgr_host: str, projectname: str, scope: str, refreshtoken: str) -> Tuple[str, str]:
    """
    Refresh Token by invoking Credential Manager Proxy
    @param credmgr_host Credential Manager
    @param projectname Project Name
    @param scope Scope
    @param refreshtoken Refresh Token
    @return Id token and Refresh Token
    @raises ClickException in case of error
    """
    if projectname is None:
        projectname = os.getenv('FABRIC_PROJECT_NAME', 'all')
        if projectname == '':
            projectname = 'all'
    if scope is None:
        scope = os.getenv('FABRIC_SCOPE', 'all')
        if scope == '':
            scope = 'all'

    if refreshtoken is None:
        refreshtoken = os.getenv('FABRIC_REFRESH_TOKEN', None)
        if refreshtoken is None:
            raise click.ClickException(f'Either specify refreshtoken parameter or set '
                                       f'FABRIC_REFRESH_TOKEN environment variable')

    cm_proxy = CredmgrProxy(credmgr_host=credmgr_host)
    status, id_token_or_error, refresh_token = cm_proxy.refresh(project_name=projectname, scope=scope,
                                                                refresh_token=refreshtoken)
    if status == CmStatus.OK:
        click.echo()
        click.echo("NOTE: Please reset your environment variable")
        cmd = f"export FABRIC_REFRESH_TOKEN={refresh_token}"
        print(cmd)
        click.echo("NOTE: Please reset your environment variable")
        click.echo()
        return id_token_or_error, refresh_token
    else:
        raise click.ClickException(id_token_or_error)


def __get_tokens(*, credmgr_host: str, idtoken: str, refreshtoken: str, projectname: str,
                 scope: str) -> Tuple[str, str]:
    """
    Get Tokens for Orchestrator APIs using either FABRIC_ID_TOKEN or FABRIC_REFRESH_TOKEN environment variables
    """
    if refreshtoken is not None:
        idtoken, refreshtoken = __do_refresh_token(credmgr_host=credmgr_host, projectname=projectname,
                                                   scope=scope, refreshtoken=refreshtoken)

    if idtoken is None:
        idtoken = os.getenv('FABRIC_ID_TOKEN', None)
        if idtoken is None:
            raise click.ClickException(f'Either idtoken or refreshtoken must be specified or set environment variables '
                                       f'FABRIC_ID_TOKEN or FABRIC_REFRESH_TOKEN')

    return idtoken, refreshtoken


def __do_context_validation(ctx):
    orchestrator_host = os.getenv('FABRIC_ORCHESTRATOR_HOST')
    if orchestrator_host is None or orchestrator_host == "":
        ctx.fail('FABRIC_ORCHESTRATOR_HOST is not set')
    ctx.obj['orchestrator_host'] = orchestrator_host

    credmgr_host = os.getenv('FABRIC_CREDMGR_HOST')
    if credmgr_host is None or credmgr_host == "":
        ctx.fail('$FABRIC_CREDMGR_HOST is not set')
    ctx.obj['credmgr_host'] = credmgr_host


@click.group()
@click.option('-v', '--verbose', is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose


@click.group()
@click.pass_context
def tokens(ctx):
    """ Token management
        (set $FABRIC_CREDMGR_HOST to the Credential Manager Server)
    """
    credmgr_host = os.getenv('FABRIC_CREDMGR_HOST')
    if credmgr_host is None or credmgr_host == "":
        ctx.fail('$FABRIC_CREDMGR_HOST is not set')
    ctx.obj['credmgr_host'] = credmgr_host


@tokens.command()
@click.pass_context
def issue(ctx):
    """ Issue token
    """
    credmgr_host = ctx.obj['credmgr_host']
    try:
        url = "https://{}/ui/".format(credmgr_host)
        webbrowser.open(url, new=2)

        click.echo(f'After visiting the URL: {url}, use POST /tokens/create command to generate fabrictestbed_cli tokens')
        click.echo('Set up the environment variables for FABRIC_ID_TOKEN and FABRIC_REFRESH_TOKEN')

    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabrictestbed_cli-cli token refresh\' to refresh token first')
    except Exception as e:
        raise click.ClickException(str(e))


@tokens.command()
@click.option('--refreshtoken', help='refreshtoken', required=True)
@click.option('--projectname', default=None, help='project name')
@click.option('--scope', type=click.Choice(['control', 'measurement', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.pass_context
def refresh(ctx, refreshtoken, projectname, scope):
    """Refresh token
    """
    credmgr_host = ctx.obj['credmgr_host']
    id_token, refresh_token = __do_refresh_token(credmgr_host=credmgr_host, projectname=projectname,
                                                 scope=scope, refreshtoken=refreshtoken)
    click.echo(f"ID Token: {id_token}")
    click.echo(f"Refresh Token: {refresh_token}")


@tokens.command()
@click.option('--refreshtoken', help='refreshtoken', required=True)
@click.pass_context
def revoke(ctx, refreshtoken):
    """ Revoke token
    """
    credmgr_host = ctx.obj['credmgr_host']
    status, error_str = CredmgrProxy(credmgr_host=credmgr_host).revoke(refresh_token=refreshtoken)
    if status == Status.OK:
        click.echo("Token revoked successfully")
    else:
        raise click.ClickException(f"Token could not be revoked! Error encountered: {error_str}")


@click.group()
@click.pass_context
def slices(ctx):
    """ Slice management
        (set $FABRIC_ORCHESTRATOR_HOST to the Orchestrator and set $FABRIC_CREDMGR_HOST to the Credential Manager Server)
    """
    __do_context_validation(ctx)


@slices.command()
@click.option('--idtoken', default=None, help='Fabric Identity Token')
@click.option('--refreshtoken', default=None, help='Fabric Refresh Token')
@click.option('--projectname', default='all', help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--sliceid', default=None, help='Slice Id')
@click.pass_context
def query(ctx, idtoken: str, refreshtoken: str, projectname: str, scope: str, sliceid: str):
    """ Query user slice(s)
    """
    idtoken, refreshtoken = __get_tokens(credmgr_host=ctx.obj['credmgr_host'], idtoken=idtoken,
                                         refreshtoken=refreshtoken, projectname=projectname, scope=scope)

    try:
        proxy = OrchestratorProxy(orchestrator_host=ctx.obj['orchestrator_host'])
        status = None
        response = None

        if sliceid is None:
            status, response = proxy.slices(token=idtoken)
        else:
            status, response = proxy.get_slice(token=idtoken, slice_id=sliceid)

        if status == Status.OK:
            click.echo(json.dumps(response))
        else:
            click.echo(f'Query Slice(s) failed: {status.interpret(exception=response)}')

    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabric-cli token refresh\' to refresh token first')
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--idtoken', default=None, help='Fabric Identity Token')
@click.option('--refreshtoken', default=None, help='Fabric Refresh Token')
@click.option('--projectname', default='all', help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--slicename', help='Slice Name', required=True)
@click.option('--slicegraph', help='Slice Graph', required=True)
@click.option('--sshkey', help='SSH Key', required=True)
@click.option('--leaseend', help='Lease End', default=None)
@click.pass_context
def create(ctx, idtoken: str, refreshtoken: str, projectname: str, scope: str, slicename: str, slicegraph: str,
           sshkey: str, leaseend: str):
    """ Create user slice
    """
    idtoken, refreshtoken = __get_tokens(credmgr_host=ctx.obj['credmgr_host'], idtoken=idtoken,
                                         refreshtoken=refreshtoken, projectname=projectname, scope=scope)

    try:
        proxy = OrchestratorProxy(orchestrator_host=ctx.obj['orchestrator_host'])
        status, response = proxy.create(token=idtoken, slice_name=slicename, slice_graph=slicegraph, ssh_key=sshkey,
                                        lease_end_time=leaseend)

        if status == Status.OK:
            click.echo(json.dumps(response))
        else:
            click.echo(f'Create Slice failed: {status.interpret(exception=response)}')

    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabric-cli token refresh\' to refresh token first')
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--idtoken', default=None, help='Fabric Identity Token')
@click.option('--refreshtoken', default=None, help='Fabric Refresh Token')
@click.option('--projectname', default='all', help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--sliceid', help='Slice Id', required=True)
@click.pass_context
def delete(ctx, idtoken: str, refreshtoken: str, projectname: str, scope: str, sliceid: str):
    """ Delete user slice
    """
    idtoken, refreshtoken = __get_tokens(credmgr_host=ctx.obj['credmgr_host'], idtoken=idtoken,
                                         refreshtoken=refreshtoken, projectname=projectname, scope=scope)

    try:
        proxy = OrchestratorProxy(orchestrator_host=ctx.obj['orchestrator_host'])
        status, response = proxy.delete(token=idtoken, slice_id=sliceid)

        if status == Status.OK:
            click.echo(json.dumps(response))
        else:
            click.echo(f'Delete Slice failed: {status.interpret(exception=response)}')

    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabric-cli token refresh\' to refresh token first')
    except Exception as e:
        raise click.ClickException(str(e))


@click.group()
@click.pass_context
def slivers(ctx):
    """ Sliver management
        (set $FABRIC_ORCHESTRATOR_HOST to the Orchestrator and set $FABRIC_CREDMGR_HOST to the Credential Manager Server)
    """
    __do_context_validation(ctx)


@slivers.command()
@click.option('--idtoken', default=None, help='Fabric Identity Token')
@click.option('--refreshtoken', default=None, help='Fabric Refresh Token')
@click.option('--projectname', default='all', help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--sliceid', help='Slice Id')
@click.option('--sliverid', default=None, help='Sliver Id')
@click.pass_context
def query(ctx, idtoken: str, refreshtoken: str, projectname: str, scope: str, sliceid: str, sliverid: str):
    """ Query user slice sliver(s)
    """
    idtoken, refreshtoken = __get_tokens(credmgr_host=ctx.obj['credmgr_host'], idtoken=idtoken,
                                         refreshtoken=refreshtoken, projectname=projectname, scope=scope)

    try:
        proxy = OrchestratorProxy(orchestrator_host=ctx.obj['orchestrator_host'])
        status, response = proxy.slivers(token=idtoken, slice_id=sliceid, sliver_id=sliverid)

        if status == Status.OK:
            click.echo(json.dumps(response))
        else:
            click.echo(f'Query Sliver(s) failed: {status.interpret(exception=response)}')

    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabric-cli token refresh\' to refresh token first')
    except Exception as e:
        raise click.ClickException(str(e))


@click.group()
@click.pass_context
def resources(ctx):
    """ Resource management
        (set $FABRIC_ORCHESTRATOR_HOST to the Orchestrator and set $FABRIC_CREDMGR_HOST to the Credential Manager Server)
    """
    __do_context_validation(ctx)


@resources.command()
@click.option('--idtoken', default=None, help='Fabric Identity Token')
@click.option('--refreshtoken', default=None, help='Fabric Refresh Token')
@click.option('--projectname', default='all', help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.pass_context
def query(ctx, idtoken: str, refreshtoken: str, projectname: str, scope: str):
    """ Query resources
    """
    idtoken, refreshtoken = __get_tokens(credmgr_host=ctx.obj['credmgr_host'], idtoken=idtoken,
                                         refreshtoken=refreshtoken, projectname=projectname, scope=scope)

    try:
        proxy = OrchestratorProxy(orchestrator_host=ctx.obj['orchestrator_host'])
        status, response = proxy.resources(token=idtoken)

        if status == Status.OK:
            click.echo(json.dumps(response))
        else:
            click.echo(f'Query Resources failed: {status.interpret(exception=response)}')

    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabric-cli token refresh\' to refresh token first')
    except Exception as e:
        raise click.ClickException(str(e))


cli.add_command(tokens)
cli.add_command(slices)
cli.add_command(slivers)
cli.add_command(resources)

