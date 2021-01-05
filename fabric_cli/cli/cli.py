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

import click
import os
import json
from .credential import CredMgr
from .exceptions import TokenExpiredException
from .orchestrator import Orchestrator


def do_refresh_token(*, projectname: str, scope: str, refreshtoken: str):
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
            raise click.ClickException('Either specify refreshtoken parameter or set FABRIC_REFRESH_TOKEN environment variable')
    try:
        res = CredMgr.refresh_token(projectname, scope, refreshtoken)
        click.echo()
        click.echo("NOTE: Please reset your environment variable")
        cmd = "export FABRIC_REFRESH_TOKEN={}".format(res.get('refresh_token'))
        print(cmd)
        click.echo("NOTE: Please reset your environment variable")
        click.echo()
        return res
    except Exception as e:
        #traceback.print_exc()
        raise click.ClickException(str(e))

@click.group()
@click.option('-v', '--verbose', is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose


@click.group()
@click.pass_context
def token(ctx):
    """ issue/get/refresh/revoke FABRIC tokens.
        (set $FABRIC_CREDMGR_HOST to the Credential Manager Server)
    """
    credmgr_host = os.getenv('FABRIC_CREDMGR_HOST')
    if credmgr_host is None or credmgr_host == "":
        ctx.fail('$FABRIC_CREDMGR_HOST is not set')


@token.command()
@click.option('--projectname', default=None, help='project name')
@click.option('--scope', type=click.Choice(['control', 'measurement', 'all'], case_sensitive=False),
              default=None, help='scope')
@click.pass_context
def issue(ctx, projectname, scope):
    """ issue token with projectname and scope
    """
    if projectname is None:
        projectname = os.getenv('FABRIC_PROJECT_NAME', 'all')
        if projectname == '':
            projectname = 'all'
    if scope is None:
        scope = os.getenv('FABRIC_SCOPE', 'all')
        if scope == '':
            scope = 'all'
    try:
        res = CredMgr.create_token(projectname, scope.lower())
        url = res.get('url', None)
        click.echo('After visiting the URL: {}, use POST /tokens/create command to generate fabric_cli tokens'.format(url))
        click.echo('Set up the environment variables for FABRIC_ID_TOKEN and FABRIC_REFRESH_TOKEN')

        if ctx.obj['VERBOSE']:
            click.echo('projectname: %s, scope: %s' % (projectname, scope))
            click.echo(json.dumps(res))
    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabric_cli-cli token refresh\' to refresh token first')
    except Exception as e:
        raise click.ClickException(str(e))


@token.command()
@click.option('--refreshtoken', help='refreshtoken', required=True)
@click.option('--projectname', default=None, help='project name')
@click.option('--scope', type=click.Choice(['control', 'measurement', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.pass_context
def refresh(ctx, refreshtoken, projectname, scope):
    """refresh token
    """
    result = do_refresh_token(projectname=projectname, scope=scope, refreshtoken=refreshtoken)
    click.echo(json.dumps(result))


@token.command()
@click.option('--refreshtoken', help='refreshtoken', required=True)
@click.pass_context
def revoke(ctx, refreshtoken):
    """ revoke token
    """
    if refreshtoken is None:
        refreshtoken = os.getenv('FABRIC_REFRESH_TOKEN', None)
        if refreshtoken is None:
            raise click.ClickException('need refreshtoken parameter')
    try:
        res = CredMgr.revoke_token(refreshtoken)
        click.echo(json.dumps(res))
    except Exception as e:
        raise click.ClickException(str(e))


@click.group()
@click.pass_context
def slice(ctx):
    """ slice management
    """
    pass


@slice.command()
@click.option('--projectname', default='all', help='project name')
@click.option('--scope', type=click.Choice(['CF', 'MF', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.pass_context
def create(ctx, projectname, scope):
    """ create slice
    """
    if ctx.obj['VERBOSE']:
        click.echo('create slice not implemented yet. proj=%s scope=%s' % (projectname, scope))
    else:
        click.echo('not ready. %s, %s' % (projectname, scope))


@slice.command()
def delete(ctx, project, scope):
    """ delete slice
    """
    if ctx.obj['VERBOSE']:
        click.echo('delete slice not implemented yet. proj=%s scope=%s' % (project, scope))
    else:
        click.echo('not ready. %s, %s' % (project, scope))


@click.group()
@click.pass_context
def resources(ctx):
    """ Query Resources
        (set $FABRIC_ORCHESTRATOR_HOST to the Control Framework Orchestrator)
    """
    orchestrator_host = os.getenv('FABRIC_ORCHESTRATOR_HOST')
    if orchestrator_host is None or orchestrator_host == "":
        ctx.fail('FABRIC_ORCHESTRATOR_HOST is not set')


@resources.command()
@click.option('--idtoken', default=None, help='Fabric Identity Token')
@click.option('--refreshtoken', default=None, help='Fabric Refresh Token')
@click.option('--projectname', default='all', help='project name')
@click.option('--scope', type=click.Choice(['control', 'measurement', 'all'], case_sensitive=False),
              default='all', help='scope')
@click.pass_context
def query(ctx, idtoken: str, refreshtoken: str, projectname: str, scope: str):
    """ issue token with projectname and scope
    """
    tokens = None
    if refreshtoken is None:
        refreshtoken = os.getenv('FABRIC_REFRESH_TOKEN', None)

    if refreshtoken is not None:
        try:
            tokens = do_refresh_token(projectname=projectname, scope=scope, refreshtoken=refreshtoken)
            idtoken = tokens.get('id_token', None)
        except Exception as e:
            raise click.ClickException('Not a valid refreshtoken! Error: {}'.format(e))

    if idtoken is None:
        idtoken = os.getenv('FABRIC_ID_TOKEN', None)
        if idtoken is None: 
            raise click.ClickException('Either idtoken or refreshtoken must be specified or set environment variables FABRIC_ID_TOKEN or FABRIC_REFRESH_TOKEN')

    try:
        res = Orchestrator.resources(id_token=idtoken)
        click.echo(json.dumps(res))

        if ctx.obj['VERBOSE']:
            click.echo('idtoken: %s refreshtoken: %s projectname: %s, scope: %s' % (idtoken, refreshtoken,
                                                                                    projectname, scope))
    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabric_cli-cli token refresh\' to refresh token first')
    except Exception as e:
        raise click.ClickException(str(e))


cli.add_command(token)
cli.add_command(slice)
cli.add_command(resources)

