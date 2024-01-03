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
#
import os
import traceback
from typing import Any

import json
import click
from fabric_cf.orchestrator.orchestrator_proxy import SliceState
from fabric_cm.credmgr.credmgr_proxy import TokenType
from fabrictestbed.util.utils import Utils
from fim.slivers.network_node import NodeSliver

from .exceptions import TokenExpiredException
from ..slice_manager import CredmgrProxy
from ..slice_manager.slice_manager import SliceManager, Status
from ..util.constants import Constants


def __get_slice_manager(*, oc_host: str = None, cm_host: str = None, project_id: str = None, scope: str = "all",
                        token_location: str = None, project_name: str = None) -> SliceManager:
    """
    Get Environment Variables
    @param oc_host Orchestrator host
    @param cm_host Credmgr Host
    @param project_id Project Id
    @param project_name Project Name
    @param scope Scope
    @param token_location Absolute location of the tokens JSON file
    @raises ClickException in case of error
    """
    return SliceManager(oc_host=oc_host, cm_host=cm_host, project_id=project_id, scope=scope,
                        token_location=token_location, project_name=project_name)


def __unpack(data: Any) -> Any:
    """
    Recursivly unpacks JSON dictionaries or lists embedded in a list or dict.
    @param Any to unpack
    """
    if isinstance(data, str):
        if data and data[0] in ('{','['): ## starts with - json loads will catch errors
            data=__unpack(json.loads(data))
    elif isinstance(data, list):
        for i,v in enumerate(data):
            data[i]=__unpack(v)
    elif isinstance(data, dict):
        for k,v in data.items():
            data[k]=__unpack(v)
    return data


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
        (set $FABRIC_CREDMGR_HOST => CredentialManager, $FABRIC_project_id => Project Id)
    """


@tokens.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--projectid', default=None, help='Project id')
@click.option('--projectname', default=None, help='Project name')
@click.option('--lifetime', default=4, help='Token lifetime in hours')
@click.option('--comment', default=None, help='Comment/note to associate with the token')
@click.option('--browser', default="chrome", type=click.Choice(['chrome', 'firefox', 'safari', 'edge'],
                                                               case_sensitive=False),
              help='Browser to use to launch the web app!')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--tokenlocation', help='Location and name of the while in which to store tokens', default=None)
@click.pass_context
def create(ctx, cmhost: str, projectid: str, projectname: str, lifetime: int, comment: str,
           browser: str, scope: str, tokenlocation: str):
    """Create token
    """
    try:
        if cmhost is None and os.environ.get(Constants.FABRIC_CREDMGR_HOST) is None:
            raise click.ClickException(f"Credential Manager Host must be specified!")

        if projectname is None and os.environ.get(Constants.FABRIC_PROJECT_NAME) is None and projectid is None and \
                os.environ.get(Constants.FABRIC_PROJECT_ID) is None:
            raise click.ClickException(f"Either Project Name or Project Id must be specified!")

        cookie_name = os.getenv(Constants.FABRIC_COOKIE_NAME)
        if cmhost is None:
            cmhost = os.getenv(Constants.FABRIC_CREDMGR_HOST)

        if cookie_name is not None:
            cm_proxy = CredmgrProxy(credmgr_host=cmhost, cookie_name=cookie_name)
        else:
            cm_proxy = CredmgrProxy(credmgr_host=cmhost)

        if tokenlocation is None:
            tokenlocation = os.getenv(Constants.FABRIC_TOKEN_LOCATION)

        status, token_or_exception = cm_proxy.create(project_id=projectid, project_name=projectname,
                                                     life_time_in_hours=lifetime, comment=comment,
                                                     browser_name=browser, scope=scope, file_name=tokenlocation)

        from fabric_cm.credmgr.credmgr_proxy import Status as CmStatus
        if status == CmStatus.OK:
            if tokenlocation is None:
                click.echo(f"Fabric Token: {token_or_exception}")
            else:
                click.echo(f"Fabric Token saved at: {tokenlocation}")
        else:
            raise click.ClickException(f"{Utils.extract_error_message(exception=token_or_exception)}")
    except click.ClickException as e:
        raise e
    except Exception as e:
        raise click.ClickException(str(e))


@tokens.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--tokenlocation', help='Location of the file which contains the valid tokens', default=None)
@click.option('--projectid', default=None, help='Project Id')
@click.option('--projectname', default=None, help='Project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Scope')
@click.pass_context
def refresh(ctx, cmhost: str, tokenlocation: str, projectid: str, projectname: str, scope: str):
    """Refresh token
    """
    try:
        if cmhost is None and os.environ.get(Constants.FABRIC_CREDMGR_HOST) is None:
            raise click.ClickException(f"Credential Manager Host must be specified!")

        if tokenlocation is None and os.environ.get(Constants.FABRIC_TOKEN_LOCATION) is None:
            raise click.ClickException(f"Token location must be specified !")

        if projectname is None and os.environ.get(Constants.FABRIC_PROJECT_NAME) is None and projectid is None and \
                os.environ.get(Constants.FABRIC_PROJECT_ID) is None:
            raise click.ClickException(f"Either Project Name or Project Id must be specified!")

        if tokenlocation is None:
            tokenlocation = os.getenv(Constants.FABRIC_TOKEN_LOCATION)

        slice_manager = __get_slice_manager(cm_host=cmhost, project_id=projectid, scope=scope,
                                            token_location=tokenlocation, project_name=projectname)

        click.echo(f"ID Token: {slice_manager.get_id_token()}")
        click.echo(f"Refresh Token: {slice_manager.get_refresh_token()}")
        click.echo(f"Refreshed token saved at: {tokenlocation}")
    except click.ClickException as e:
        raise e
    except Exception as e:
        raise click.ClickException(str(e))


@tokens.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--tokenlocation', help='Location of the file which contains the valid tokens', default=None)
@click.option('--refreshtoken', help='Refresh token to be revoked; '
                                     'If specified refresh token from tokenlocation is ignored!', default=None)
@click.option('--identitytoken', help='Identity token to be revoked or to authenticate the user when revoking a '
                                      'refresh token; If specified identity token from tokenlocation is ignored',
              default=None)
@click.option('--tokenhash', help='SHA256 hash for the token being revoked; If not specified, '
                                  'it is assumed that the identity token being passed is being revoked', default=None)
@click.pass_context
def revoke(ctx, cmhost: str, tokenlocation: str, refreshtoken: str, identitytoken: str, tokenhash: str):
    """ Revoke token
    """
    try:
        fail = False
        if cmhost is None and os.environ.get(Constants.FABRIC_CREDMGR_HOST) is None:
            raise click.ClickException(f"Credential Manager Host must be specified!")

        if tokenlocation is None and os.environ.get(Constants.FABRIC_TOKEN_LOCATION) is None and \
                refreshtoken is None and identitytoken is None:
            raise click.ClickException(f"Either Token location must be specified or pass refresh "
                                       f"token and identity token!")

        # Token in the file located at tokenlocation is being revoked
        if tokenlocation is not None or os.environ.get(Constants.FABRIC_TOKEN_LOCATION) is not None:
            if tokenlocation is None:
                tokenlocation = os.getenv(Constants.FABRIC_TOKEN_LOCATION)

            if os.path.exists(tokenlocation):
                with open(tokenlocation, 'r') as stream:
                    tokens = json.loads(stream.read())
                    refreshtoken = tokens.get(CredmgrProxy.REFRESH_TOKEN)
                    identitytoken = tokens.get(CredmgrProxy.ID_TOKEN)
                    tokenhash = tokens.get("token_hash")
            else:
                raise click.ClickException(f"Token file '{tokenlocation}' does not exist!")

        if cmhost is None:
            cmhost = os.environ.get(Constants.FABRIC_CREDMGR_HOST)

        cm_proxy = CredmgrProxy(credmgr_host=cmhost)
        if refreshtoken is None:
            status, error_str = cm_proxy.revoke(identity_token=identitytoken, token_hash=tokenhash,
                                                token_type=TokenType.Identity)
        else:

            status, error_str = cm_proxy.revoke(refresh_token=refreshtoken, identity_token=identitytoken,
                                                token_type=TokenType.Refresh)
        from fabric_cm.credmgr.credmgr_proxy import Status as CmStatus
        if status == CmStatus.OK:
            click.echo("Token revoked successfully")
        else:
            raise click.ClickException(f"{Utils.extract_error_message(exception=error_str)}")
    except click.ClickException as e:
        raise e
    except Exception as e:
        traceback.print_exc()
        raise click.ClickException(str(e))


@tokens.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--tokenlocation', help='location for the tokens', default=None)
@click.pass_context
def clear_cache(ctx, cmhost, tokenlocation):
    """ Clear cached token
    """
    try:
        if cmhost is None and os.environ.get(Constants.FABRIC_CREDMGR_HOST) is None:
            raise click.ClickException(f"Credential Manager Host must be specified!")

        if tokenlocation is None:
            raise click.ClickException(f"Token location must be specified !")

        slice_manager = __get_slice_manager(cm_host=cmhost, token_location=tokenlocation)

        status, error_str = slice_manager.clear_token_cache(file_name=tokenlocation)
        if status == Status.OK:
            click.echo("Token cache cleared successfully")
        else:
            raise click.ClickException(f"{Utils.extract_error_message(exception=error_str)}")

    except click.ClickException as e:
        raise e
    except Exception as e:
        raise click.ClickException(str(e))


@click.group()
@click.pass_context
def slices(ctx):
    """ Slice management
        (set $FABRIC_ORCHESTRATOR_HOST => Orchestrator, $FABRIC_CREDMGR_HOST => CredentialManager,
        $FABRIC_TOKEN_LOCATION => Location of the token file, $FABRIC_PROJECT_ID => Project Id)
    """


@slices.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--ochost', help='Orchestrator Host', default=None)
@click.option('--tokenlocation', help='location for the tokens', default=None)
@click.option('--projectid', default=None, help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--sliceid', default=None, help='Slice Id')
@click.option('--state', default=None, help='Slice State')
@click.pass_context
def query(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str, state: str):
    """ Query slice_editor slice(s)
    """
    try:
        slice_manager = __get_slice_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                            token_location=tokenlocation)
        status = None
        response = None
        includes = []
        if state is not None:
            slice_state = SliceState.state_from_str(state)
            if slice_state is not None:
                includes.append(slice_state)

        status, response = slice_manager.slices(includes=includes, slice_id=sliceid)

        if status == Status.OK and not isinstance(response, Exception):
            click.echo(json.dumps(list(map(lambda i: i.to_dict(), response)),indent=2))
        else:
            click.echo(Utils.extract_error_message(exception=response))

    except TokenExpiredException:
        raise click.ClickException("Unauthorized: Valid token required")
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--ochost', help='Orchestrator Host', default=None)
@click.option('--tokenlocation', help='location for the tokens', default=None)
@click.option('--projectid', default=None, help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--slicename', help='Slice Name', required=True)
@click.option('--slicegraph', help='Slice Graph', required=True)
@click.option('--sshkey', help='SSH Key', required=True)
@click.option('--leaseend', help='Lease End', default=None)
@click.pass_context
def create(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, slicename: str,
           slicegraph: str, sshkey: str, leaseend: str):
    """ Create slice_editor slice
    """
    try:
        slice_manager = __get_slice_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                            token_location=tokenlocation)
        status, response = slice_manager.create(slice_name=slicename, slice_graph=slicegraph, ssh_key=sshkey,
                                                lease_end_time=leaseend)

        if status == Status.OK:
            click.echo(response)
        else:
            click.echo(Utils.extract_error_message(exception=response))

    except TokenExpiredException:
        raise click.ClickException("Unauthorized: Valid token required")
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--ochost', help='Orchestrator Host', default=None)
@click.option('--tokenlocation', help='location for the tokens', default=None)
@click.option('--projectid', default=None, help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--sliceid', help='Slice Id', required=True)
@click.option('--slicegraph', help='Slice Graph', required=True)
@click.pass_context
def modify(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str,
           slicegraph: str):
    """ Modify an existing slice
    """
    try:
        slice_manager = __get_slice_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                            token_location=tokenlocation)
        status, response = slice_manager.modify(slice_id=sliceid, slice_graph=slicegraph)

        if status == Status.OK:
            click.echo(response)
        else:
            click.echo(Utils.extract_error_message(exception=response))

    except TokenExpiredException:
        raise click.ClickException("Unauthorized: Valid token required")
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--ochost', help='Orchestrator Host', default=None)
@click.option('--tokenlocation', help='location for the tokens', default=None)
@click.option('--projectid', default=None, help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--sliceid', help='Slice Id', required=True)
@click.pass_context
def modifyaccept(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str):
    """ Accept the modified slice
    """
    try:
        slice_manager = __get_slice_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                            token_location=tokenlocation)
        status, response = slice_manager.modify_accept(slice_id=sliceid)

        if status == Status.OK:
            click.echo(response)
        else:
            click.echo(Utils.extract_error_message(exception=response))

    except TokenExpiredException:
        raise click.ClickException("Unauthorized: Valid token required")
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--ochost', help='Orchestrator Host', default=None)
@click.option('--tokenlocation', help='location for the tokens', default=None)
@click.option('--projectid', default=None, help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--sliceid', help='Slice Id', required=False)
@click.pass_context
def delete(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str):
    """ Delete slice_editor slice
    """
    try:
        slice_manager = __get_slice_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                            token_location=tokenlocation)
        slice_object = None
        if sliceid is not None:
            status, response = slice_manager.slices(slice_id=sliceid)
            if status != Status.OK or isinstance(response, Exception):
                click.echo(f'Delete Slice failed: {status.interpret(exception=response)}')
                return
            slice_object = response[0]

        status, response = slice_manager.delete(slice_object=slice_object)

        if status == Status.OK:
            click.echo(response)
        else:
            click.echo(Utils.extract_error_message(exception=response))

    except TokenExpiredException:
        raise click.ClickException("Unauthorized: Valid token required")
    except Exception as e:
        raise click.ClickException(str(e))


@click.group()
@click.pass_context
def slivers(ctx):
    """ Sliver management
        (set $FABRIC_ORCHESTRATOR_HOST => Orchestrator, $FABRIC_CREDMGR_HOST => CredentialManager,
        $FABRIC_TOKEN_LOCATION => Location of the token file, $FABRIC_PROJECT_ID => Project Id)
    """


@slivers.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--ochost', help='Orchestrator Host', default=None)
@click.option('--tokenlocation', help='location for the tokens', default=None)
@click.option('--projectid', default=None, help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--sliceid', help='Slice Id')
@click.option('--sliverid', default=None, help='Sliver Id')
@click.pass_context
def query(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str, sliverid: str):
    """ Query slice_editor slice sliver(s)
    """
    try:
        slice_manager = __get_slice_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                            token_location=tokenlocation)

        status, response = slice_manager.slices(slice_id=sliceid)
        if status != Status.OK:
            click.echo(f'Query Sliver(s) failed: {status.interpret(exception=response)}')
            return

        slice_object = response[0]
        status, response = slice_manager.slivers(slice_object=slice_object)

        if status == Status.OK and not isinstance(response, Exception):
            click.echo(json.dumps(list(map(lambda i: __unpack(i.to_dict()), response)),indent=2))
        else:
            click.echo(Utils.extract_error_message(exception=response))

    except TokenExpiredException:
        raise click.ClickException("Unauthorized: Valid token required")
    except Exception as e:
        raise click.ClickException(str(e))


@slivers.command()
@click.option('--sshkeyfile', help='Location of SSH Private Key file to use to access the Sliver')
@click.option('--sliceaddress', help='IP address or the connection string to use to access the sliver')
@click.option('--username', default=None, help='Username to use to access the sliver')
@click.option('--command', default=None, help='Command to be executed on the sliver')
@click.pass_context
def execute(ctx, sshkeyfile: str, sliceaddress: str, username: str, command: str):
    """ Query slice_editor slice sliver(s)
    """
    try:
        slice_manager = __get_slice_manager()

        sliver = NodeSliver()
        sliver.management_ip = sliceaddress
        status, response = slice_manager.execute(ssh_key_file=sshkeyfile, sliver=sliver,
                                                 username=username, command=command)

        if status == Status.OK:
            output, error = response
            click.echo(f"Output: {output}")
            click.echo(f"Error: {error}")
        else:
            click.echo(Utils.extract_error_message(exception=response))
    except Exception as e:
        raise click.ClickException(str(e))


@click.group()
@click.pass_context
def resources(ctx):
    """ Resource management
        (set $FABRIC_ORCHESTRATOR_HOST => Orchestrator, $FABRIC_CREDMGR_HOST => CredentialManager, $FABRIC_PROJECT_ID => Project Id)
    """


@resources.command()
@click.option('--cmhost', help='Credmgr Host', default=None)
@click.option('--ochost', help='Orchestrator Host', default=None)
@click.option('--tokenlocation', help='location for the tokens', default=None)
@click.option('--projectid', default=None, help='project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.option('--force', default=False, help='Force current snapshot')
@click.pass_context
def query(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, force: bool):
    """ Query resources
    """
    try:
        slice_manager = __get_slice_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                            token_location=tokenlocation)

        status, response = slice_manager.resources(force_refresh=force)

        if status == Status.OK:
            click.echo(response)
        else:
            click.echo(Utils.extract_error_message(exception=response))

    except TokenExpiredException:
        raise click.ClickException("Unauthorized: Valid token required")
    except Exception as e:
        raise click.ClickException(str(e))


cli.add_command(tokens)
cli.add_command(slices)
cli.add_command(slivers)
cli.add_command(resources)

