import click
import os
import json
from .credential import CredMgr
from .exceptions import TokenExpiredException
from pprint import pprint, pformat


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
        if projectname is '':
            projectname = 'all'
    if scope is None:
        scope = os.getenv('FABRIC_SCOPE', 'all')
        if scope is '':
            scope = 'all'
    try:
        res = CredMgr.create_token(projectname, scope.lower())
        userid = res.userid
        url = res.rawdata['value']['authorization_url']
        click.echo(url)
        click.echo('after visiting the URL above, use following command:')
        click.echo('fabric-cli token get --uid ' + userid + '\n')

        if ctx.obj['VERBOSE']:
            click.echo('projectname: %s, scope: %s' % (projectname, scope))
            click.echo(json.dumps(res.rawdata))
    except TokenExpiredException as e:
        raise click.ClickException(str(e) +
                                   ', use \'fabric-cli token refresh\' to refresh token first')
    except Exception as e:
        raise click.ClickException(str(e))


@token.command()
@click.option('-u', '--uid',
              help='User ID to request tokens', required=True)
@click.pass_context
def get(ctx, uid):
    """ get token by user-id
    """
    try:
        res = CredMgr.get_token(uid)
        click.echo(json.dumps(res.tokens))
        if ctx.obj['VERBOSE']:
            click.echo('\n' + json.dumps(res.rawdata))
        return
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
    if projectname is None:
        projectname = os.getenv('FABRIC_PROJECT_NAME', 'all')
        if projectname is '':
            projectname = 'all'
    if scope is None:
        scope = os.getenv('FABRIC_SCOPE', 'all')
        if scope is '':
            scope = 'all'

    if refreshtoken is None:
        refreshtoken = os.getenv('FABRIC_REFRESH_TOKEN', None)
        if refreshtoken is None:
            raise click.ClickException('need refreshtoken parameter')
    try:
        res = CredMgr.refresh_token(projectname, scope, refreshtoken)
        click.echo(json.dumps(res.tokens))
        if ctx.obj['VERBOSE']:
            click.echo('\n' + json.dumps(res.rawdata))
    except Exception as e:
        raise click.ClickException(str(e))


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
        click.echo(res.rawdata['message'])
        if ctx.obj['VERBOSE']:
            click.echo('\n' + json.dumps(res.rawdata))
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


cli.add_command(token)
cli.add_command(slice)
