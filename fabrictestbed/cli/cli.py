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
import webbrowser

import click
import os


from .exceptions import TokenExpiredException
from ..slice_manager.slice_manager import SliceManager, Status


def __get_slice_manager(*, oc_host: str = None, cm_host: str, project_name: str = None, scope: str = None,
                        id_token: str = None, refresh_token: str, do_not_refresh: bool = False) -> SliceManager:
    """
    Get Environment Variables
    @param oc_host Orchestrator host
    @param cm_host Credmgr Host
    @param project_name Project Name
    @param scope Scope
    @param id_token Id Token
    @param refresh_token Refresh Token
    @raises ClickException in case of error
    """
    # Grab ID Token from Environment variable, if not available
    if id_token is None:
        id_token = os.getenv('FABRIC_ID_TOKEN', None)

    # Grab Project Name from Environment variable, if not available
    if project_name is None:
        project_name = os.getenv('FABRIC_PROJECT_NAME', 'all')
        if project_name == '':
            project_name = 'all'

    # Grab Scope from Environment variable, if not available
    if scope is None:
        scope = os.getenv('FABRIC_SCOPE', 'all')
        if scope == '':
            scope = 'all'

    # Grab Refresh from Environment variable, if not available
    if id_token is None and refresh_token is None:
        refresh_token = os.getenv('FABRIC_REFRESH_TOKEN', None)
        if refresh_token is None:
            raise click.ClickException(f'Either specify refreshtoken parameter or set '
                                       f'FABRIC_REFRESH_TOKEN environment variable')

    slice_manager = SliceManager(oc_host=oc_host, cm_host=cm_host, project_name=project_name, scope=scope,
                                 refresh_token=refresh_token)

    if id_token is not None:
        slice_manager.set_id_token(id_token=id_token)
    else:
        if not do_not_refresh:
            slice_manager.refresh_tokens()
            click.echo()
            click.echo("NOTE: Please reset your environment variable by executing the following command:")
            cmd = f"export FABRIC_REFRESH_TOKEN={slice_manager.get_refresh_token()}"
            print(cmd)
            click.echo()

    return slice_manager


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

        click.echo(f'After visiting the URL: {url}, use POST /tokens/create command to generate fabrictestbed tokens')
        click.echo('Set up the environment variables for FABRIC_ID_TOKEN and FABRIC_REFRESH_TOKEN')

    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabrictestbed-cli token refresh\' to refresh token first')
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
    slice_manager = __get_slice_manager(cm_host=ctx.obj['credmgr_host'], project_name=projectname, scope=scope,
                                        refresh_token=refreshtoken)
    slice_manager.refresh_tokens(file_name="tokens.json")

    click.echo(f"ID Token: {slice_manager.get_id_token()}")
    click.echo(f"Refresh Token: {slice_manager.get_refresh_token()}")


@tokens.command()
@click.option('--refreshtoken', help='refreshtoken', required=True)
@click.pass_context
def revoke(ctx, refreshtoken):
    """ Revoke token
    """
    slice_manager = __get_slice_manager(cm_host=ctx.obj['credmgr_host'],
                                        refresh_token=refreshtoken, do_not_refresh=True)

    status, error_str = slice_manager.revoke_token()
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
@click.option('--state', default="Active", help='Slice State')
@click.pass_context
def query(ctx, idtoken: str, refreshtoken: str, projectname: str, scope: str, sliceid: str, state: str):
    """ Query slice_editor slice(s)
    """
    try:
        slice_manager = __get_slice_manager(oc_host=ctx.obj['orchestrator_host'], cm_host=ctx.obj['credmgr_host'],
                                            project_name=projectname, scope=scope,
                                            id_token=idtoken, refresh_token=refreshtoken)
        status = None
        response = None

        if sliceid is None:
            status, response = slice_manager.slices(state=state)
        else:
            status, response = slice_manager.get_slice(slice_id=sliceid)

        if status == Status.OK:
            click.echo(response)
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
    """ Create slice_editor slice
    """
    try:
        slice_manager = __get_slice_manager(oc_host=ctx.obj['orchestrator_host'], cm_host=ctx.obj['credmgr_host'],
                                            project_name=projectname, scope=scope,
                                            id_token=idtoken, refresh_token=refreshtoken)
        status, response = slice_manager.create(slice_name=slicename, slice_graph=slicegraph, ssh_key=sshkey,
                                        lease_end_time=leaseend)

        if status == Status.OK:
            click.echo(response)
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
    """ Delete slice_editor slice
    """
    try:
        slice_manager = __get_slice_manager(oc_host=ctx.obj['orchestrator_host'], cm_host=ctx.obj['credmgr_host'],
                                            project_name=projectname, scope=scope,
                                            id_token=idtoken, refresh_token=refreshtoken)
        status, response = slice_manager.delete(slice_id=sliceid)

        if status == Status.OK:
            click.echo(response)
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
    """ Query slice_editor slice sliver(s)
    """
    try:
        slice_manager = __get_slice_manager(oc_host=ctx.obj['orchestrator_host'], cm_host=ctx.obj['credmgr_host'],
                                            project_name=projectname, scope=scope,
                                            id_token=idtoken, refresh_token=refreshtoken)

        status, response = slice_manager.slivers(slice_id=sliceid, sliver_id=sliverid)

        if status == Status.OK:
            click.echo(response)
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
    try:
        slice_manager = __get_slice_manager(oc_host=ctx.obj['orchestrator_host'], cm_host=ctx.obj['credmgr_host'],
                                            project_name=projectname, scope=scope,
                                            id_token=idtoken, refresh_token=refreshtoken)

        status, response = slice_manager.resources()

        if status == Status.OK:
            click.echo(response)
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

