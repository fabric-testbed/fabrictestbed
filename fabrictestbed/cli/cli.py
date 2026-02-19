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

import json
import click

from ..util.constants import Constants

_DEFAULT_CREDMGR_HOST = "cm.fabric-testbed.net"
_DEFAULT_ORCHESTRATOR_HOST = "orchestrator.fabric-testbed.net"
_DEFAULT_CORE_API_HOST = "uis.fabric-testbed.net"
_FABRIC_RC_PATH = os.path.expanduser("~/work/fabric_config/fabric_rc")


def _load_fabric_rc():
    """Load config from ~/work/fabric_config/fabric_rc if it exists.

    Returns a dict of key-value pairs. Supports 'export KEY=VALUE' and
    'KEY=VALUE' lines; comments and blank lines are ignored.
    """
    config = {}
    if not os.path.exists(_FABRIC_RC_PATH):
        return config
    try:
        with open(_FABRIC_RC_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('export '):
                    line = line[len('export '):]
                if '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and value:
                        config[key] = value
    except Exception:
        pass
    return config


def __get_fabric_manager(*, oc_host=None, cm_host=None, project_id=None,
                         scope="all", token_location=None, project_name=None):
    """Construct a FabricManagerV2 from CLI args, env vars, fabric_rc, and defaults."""
    from ..fabric_manager_v2 import FabricManagerV2
    rc = _load_fabric_rc()
    cm = cm_host or os.getenv(Constants.FABRIC_CREDMGR_HOST) or rc.get(Constants.FABRIC_CREDMGR_HOST) or _DEFAULT_CREDMGR_HOST
    oc = oc_host or os.getenv(Constants.FABRIC_ORCHESTRATOR_HOST) or rc.get(Constants.FABRIC_ORCHESTRATOR_HOST) or _DEFAULT_ORCHESTRATOR_HOST
    pid = project_id or os.getenv(Constants.FABRIC_PROJECT_ID) or rc.get(Constants.FABRIC_PROJECT_ID)
    pname = project_name or os.getenv(Constants.FABRIC_PROJECT_NAME) or rc.get(Constants.FABRIC_PROJECT_NAME)
    tl = token_location or os.getenv(Constants.FABRIC_TOKEN_LOCATION) or rc.get(Constants.FABRIC_TOKEN_LOCATION) or os.path.join(os.getcwd(), "tokens.json")
    core = os.getenv(Constants.FABRIC_CORE_API_HOST) or rc.get(Constants.FABRIC_CORE_API_HOST) or _DEFAULT_CORE_API_HOST
    return FabricManagerV2(
        credmgr_host=cm, orchestrator_host=oc, core_api_host=core,
        token_location=tl, project_id=pid, project_name=pname, scope=scope,
    )


def __resolve_tokenlocation(tokenlocation: str) -> str:
    """Resolve token file location from arg, env var, fabric_rc, or default to ./tokens.json."""
    if tokenlocation is None:
        tokenlocation = os.getenv(Constants.FABRIC_TOKEN_LOCATION)
    if tokenlocation is None:
        rc = _load_fabric_rc()
        tokenlocation = rc.get(Constants.FABRIC_TOKEN_LOCATION)
    if tokenlocation is None:
        tokenlocation = os.path.join(os.getcwd(), "tokens.json")
    return tokenlocation


def __resolve_cmhost(cmhost: str) -> str:
    """Resolve credential manager host from arg, env var, fabric_rc, or default."""
    if cmhost is None:
        cmhost = os.getenv(Constants.FABRIC_CREDMGR_HOST)
    if cmhost is None:
        rc = _load_fabric_rc()
        cmhost = rc.get(Constants.FABRIC_CREDMGR_HOST)
    if cmhost is None:
        cmhost = _DEFAULT_CREDMGR_HOST
    return cmhost


@click.group()
@click.option('-v', '--verbose', is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose


@click.group()
@click.pass_context
def tokens(ctx):
    """Token management

    Manage FABRIC identity and refresh tokens. Set $FABRIC_CREDMGR_HOST
    to avoid passing --cmhost on every command. Set $FABRIC_TOKEN_LOCATION
    to set the default token file path (defaults to ./tokens.json).
    """


@tokens.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--projectid', default=None, help='Project UUID (uses first project if not specified)')
@click.option('--projectname', default=None, help='Project name (uses first project if not specified)')
@click.option('--lifetime', default=4, help='Token lifetime in hours')
@click.option('--comment', default=None, help='Comment/note to associate with the token')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Token scope')
@click.option('--tokenlocation', help='Path to save token JSON (defaults to ./tokens.json)', default=None)
@click.option('--no-browser', is_flag=True, default=False, help='Do not attempt to open a browser automatically')
@click.pass_context
def create(ctx, cmhost: str, projectid: str, projectname: str, lifetime: int, comment: str,
           scope: str, tokenlocation: str, no_browser: bool):
    """Create token

    Opens a browser for CILogon authentication (or prints the URL if the
    browser cannot be opened). After login, the token is automatically
    captured via a localhost callback. If running on a remote VM, press
    Ctrl+C and paste the authorization code shown in the browser.

    Token is saved to --tokenlocation, $FABRIC_TOKEN_LOCATION, or
    ./tokens.json (in that order). If no project is specified, the
    user's first project is used.
    """
    try:
        cmhost = __resolve_cmhost(cmhost)
        tokenlocation = __resolve_tokenlocation(tokenlocation)
        cookie_name = os.getenv(Constants.FABRIC_COOKIE_NAME)

        from ..external_api.credmgr_client import CredmgrClient
        client = CredmgrClient(credmgr_host=cmhost,
                                cookie_name=cookie_name or "fabric-service")

        rc = _load_fabric_rc()
        if projectid is None:
            projectid = os.getenv(Constants.FABRIC_PROJECT_ID) or rc.get(Constants.FABRIC_PROJECT_ID)
        if projectname is None:
            projectname = os.getenv(Constants.FABRIC_PROJECT_NAME) or rc.get(Constants.FABRIC_PROJECT_NAME)

        tokens = client.create_cli(
            scope=scope,
            project_id=projectid,
            project_name=projectname,
            lifetime_hours=lifetime,
            comment=comment or "Create Token via CLI",
            file_path=tokenlocation,
            open_browser=not no_browser,
            return_fmt="dto",
        )

        project_label = ""
        if tokens and tokens[0].id_token:
            try:
                decoded = client.validate(id_token=tokens[0].id_token, return_fmt="dto")
                if decoded.projects:
                    p = decoded.projects[0]
                    project_label = f" for project: '{p.name}' ({p.uuid})"
            except Exception:
                pass

        click.echo(f"\nToken saved at: {tokenlocation}{project_label}")
    except click.ClickException as e:
        raise e
    except Exception as e:
        raise click.ClickException(str(e))


@tokens.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--tokenlocation', help='Path to token JSON file (defaults to ./tokens.json)', default=None)
@click.option('--projectid', default=None, help='Project UUID')
@click.option('--projectname', default=None, help='Project name')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Token scope')
@click.pass_context
def refresh(ctx, cmhost: str, tokenlocation: str, projectid: str, projectname: str, scope: str):
    """Refresh token

    Reads the existing token file, uses the refresh_token to obtain a new
    identity token, and saves the result back. Token file is read from
    --tokenlocation, $FABRIC_TOKEN_LOCATION, or ./tokens.json.
    """
    try:
        cmhost = __resolve_cmhost(cmhost)
        tokenlocation = __resolve_tokenlocation(tokenlocation)

        if not os.path.exists(tokenlocation):
            raise click.ClickException(f"Token file not found: {tokenlocation}")

        with open(tokenlocation, 'r') as f:
            existing = json.load(f)

        refresh_token = existing.get("refresh_token")
        if not refresh_token:
            raise click.ClickException(f"No refresh_token found in {tokenlocation}")

        rc = _load_fabric_rc()
        if projectid is None:
            projectid = os.getenv(Constants.FABRIC_PROJECT_ID) or rc.get(Constants.FABRIC_PROJECT_ID)
        if projectname is None:
            projectname = os.getenv(Constants.FABRIC_PROJECT_NAME) or rc.get(Constants.FABRIC_PROJECT_NAME)

        cookie_name = os.getenv(Constants.FABRIC_COOKIE_NAME)

        from ..external_api.credmgr_client import CredmgrClient
        client = CredmgrClient(credmgr_host=cmhost,
                                cookie_name=cookie_name or "fabric-service")

        result = client.refresh(
            refresh_token=refresh_token,
            scope=scope,
            project_id=projectid,
            project_name=projectname,
            file_path=tokenlocation,
            return_fmt="dto",
        )

        click.echo(f"Token refreshed and saved at: {tokenlocation}")
    except click.ClickException as e:
        raise e
    except Exception as e:
        raise click.ClickException(str(e))


@tokens.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--tokenlocation', help='Path to token JSON file (defaults to ./tokens.json)', default=None)
@click.option('--refreshtoken', help='Refresh token to revoke (overrides token file)', default=None)
@click.option('--identitytoken', help='Identity token for authentication (overrides token file)', default=None)
@click.option('--tokenhash', help='SHA256 hash of the token to revoke', default=None)
@click.pass_context
def revoke(ctx, cmhost: str, tokenlocation: str, refreshtoken: str, identitytoken: str, tokenhash: str):
    """Revoke token

    Revokes a refresh or identity token. Reads tokens from --tokenlocation
    (or $FABRIC_TOKEN_LOCATION or ./tokens.json) unless --refreshtoken
    and --identitytoken are provided explicitly.

    If --refreshtoken is provided, it is revoked. Otherwise the identity
    token (by --tokenhash) is revoked.
    """
    try:
        cmhost = __resolve_cmhost(cmhost)
        cookie_name = os.getenv(Constants.FABRIC_COOKIE_NAME)

        # Load from file if explicit tokens not provided
        if refreshtoken is None and identitytoken is None:
            tokenlocation = __resolve_tokenlocation(tokenlocation)
            if not os.path.exists(tokenlocation):
                raise click.ClickException(f"Token file not found: {tokenlocation}")

            with open(tokenlocation, 'r') as f:
                file_tokens = json.load(f)

            refreshtoken = file_tokens.get("refresh_token")
            identitytoken = file_tokens.get("id_token")
            tokenhash = tokenhash or file_tokens.get("token_hash")

        if not identitytoken:
            raise click.ClickException("Identity token is required for revocation")

        from ..external_api.credmgr_client import CredmgrClient
        client = CredmgrClient(credmgr_host=cmhost,
                                cookie_name=cookie_name or "fabric-service")

        if refreshtoken:
            client.revoke(id_token=identitytoken, token_type="refresh",
                          refresh_token=refreshtoken)
        else:
            if not tokenhash:
                raise click.ClickException("Token hash is required to revoke an identity token")
            client.revoke(id_token=identitytoken, token_type="identity",
                          token_hash=tokenhash)

        click.echo("Token revoked successfully")
    except click.ClickException as e:
        raise e
    except Exception as e:
        raise click.ClickException(str(e))


@tokens.command()
@click.option('--tokenlocation', help='Path to token JSON file to delete', default=None)
@click.pass_context
def clear_cache(ctx, tokenlocation):
    """Clear cached token

    Deletes the token file at --tokenlocation, $FABRIC_TOKEN_LOCATION,
    or ./tokens.json.
    """
    try:
        tokenlocation = __resolve_tokenlocation(tokenlocation)

        if os.path.exists(tokenlocation):
            os.remove(tokenlocation)
            click.echo(f"Token cache cleared: {tokenlocation}")
        else:
            click.echo(f"No token file found at: {tokenlocation}")

    except click.ClickException as e:
        raise e
    except Exception as e:
        raise click.ClickException(str(e))


@click.group()
@click.pass_context
def slices(ctx):
    """Slice management

    Create, query, modify, and delete slices. Requires $FABRIC_ORCHESTRATOR_HOST,
    $FABRIC_CREDMGR_HOST, $FABRIC_TOKEN_LOCATION, and $FABRIC_PROJECT_ID.
    """


@slices.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--ochost', help='Orchestrator host', default=None)
@click.option('--tokenlocation', help='Path to token JSON file (defaults to $FABRIC_TOKEN_LOCATION or ./tokens.json)', default=None)
@click.option('--projectid', default=None, help='Project UUID')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Token scope')
@click.option('--sliceid', default=None, help='Slice UUID (omit to list all)')
@click.option('--state', default=None, help='Filter by slice state')
@click.pass_context
def query(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str, state: str):
    """Query slices

    List all slices or query a specific slice by --sliceid. Optionally
    filter by --state.
    """
    try:
        fm = __get_fabric_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                  token_location=tokenlocation)
        states = [state] if state else None
        result = fm.list_slices(slice_id=sliceid, states=states, return_fmt="dict")
        click.echo(json.dumps(result, indent=2))
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--ochost', help='Orchestrator host', default=None)
@click.option('--tokenlocation', help='Path to token JSON file (defaults to $FABRIC_TOKEN_LOCATION or ./tokens.json)', default=None)
@click.option('--projectid', default=None, help='Project UUID')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Token scope')
@click.option('--slicename', help='Slice name', required=True)
@click.option('--slicegraph', help='Slice graph definition', required=True)
@click.option('--sshkey', help='SSH public key', required=True)
@click.option('--leaseend', help='Lease end time', default=None)
@click.pass_context
def create(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, slicename: str,
           slicegraph: str, sshkey: str, leaseend: str):
    """Create a slice

    Create a new slice with the given name, graph, and SSH key.
    """
    try:
        fm = __get_fabric_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                  token_location=tokenlocation)
        result = fm.create_slice(name=slicename, graph_model=slicegraph, ssh_keys=[sshkey],
                                 lease_end_time=leaseend, return_fmt="dict")
        click.echo(json.dumps(result, indent=2))
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--ochost', help='Orchestrator host', default=None)
@click.option('--tokenlocation', help='Path to token JSON file (defaults to $FABRIC_TOKEN_LOCATION or ./tokens.json)', default=None)
@click.option('--projectid', default=None, help='Project UUID')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Token scope')
@click.option('--sliceid', help='Slice UUID', required=True)
@click.option('--slicegraph', help='Updated slice graph definition', required=True)
@click.pass_context
def modify(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str,
           slicegraph: str):
    """Modify a slice

    Update an existing slice with a new graph definition.
    """
    try:
        fm = __get_fabric_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                  token_location=tokenlocation)
        result = fm.modify_slice(slice_id=sliceid, graph_model=slicegraph, return_fmt="dict")
        click.echo(json.dumps(result, indent=2))
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--ochost', help='Orchestrator host', default=None)
@click.option('--tokenlocation', help='Path to token JSON file (defaults to $FABRIC_TOKEN_LOCATION or ./tokens.json)', default=None)
@click.option('--projectid', default=None, help='Project UUID')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Token scope')
@click.option('--sliceid', help='Slice UUID', required=True)
@click.pass_context
def modifyaccept(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str):
    """Accept a modified slice

    Accept the pending modifications on a slice.
    """
    try:
        fm = __get_fabric_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                  token_location=tokenlocation)
        result = fm.accept_modify(slice_id=sliceid, return_fmt="dict")
        click.echo(json.dumps(result, indent=2))
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))


@slices.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--ochost', help='Orchestrator host', default=None)
@click.option('--tokenlocation', help='Path to token JSON file (defaults to $FABRIC_TOKEN_LOCATION or ./tokens.json)', default=None)
@click.option('--projectid', default=None, help='Project UUID')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Token scope')
@click.option('--sliceid', help='Slice UUID', required=True)
@click.pass_context
def delete(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str):
    """Delete a slice

    Delete a slice by --sliceid.
    """
    try:
        fm = __get_fabric_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                  token_location=tokenlocation)
        fm.delete_slice(slice_id=sliceid)
        click.echo(f"Slice {sliceid} deleted successfully")
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))


@click.group()
@click.pass_context
def slivers(ctx):
    """Sliver management

    Query slivers within a slice. Requires $FABRIC_ORCHESTRATOR_HOST,
    $FABRIC_CREDMGR_HOST, $FABRIC_TOKEN_LOCATION, and $FABRIC_PROJECT_ID.
    """


@slivers.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--ochost', help='Orchestrator host', default=None)
@click.option('--tokenlocation', help='Path to token JSON file (defaults to $FABRIC_TOKEN_LOCATION or ./tokens.json)', default=None)
@click.option('--projectid', default=None, help='Project UUID')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Token scope')
@click.option('--sliceid', help='Slice UUID', required=True)
@click.option('--sliverid', default=None, help='Sliver UUID (omit to list all)')
@click.pass_context
def query(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, sliceid: str, sliverid: str):
    """Query slivers

    List all slivers in a slice, or query a specific sliver by --sliverid.
    """
    try:
        fm = __get_fabric_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                  token_location=tokenlocation)
        if sliverid:
            result = fm.get_sliver(slice_id=sliceid, sliver_id=sliverid, return_fmt="dict")
        else:
            result = fm.list_slivers(slice_id=sliceid, return_fmt="dict")
        click.echo(json.dumps(result, indent=2))
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))


@click.group()
@click.pass_context
def resources(ctx):
    """Resource management

    Query available testbed resources. Requires $FABRIC_ORCHESTRATOR_HOST,
    $FABRIC_CREDMGR_HOST, and $FABRIC_PROJECT_ID.
    """


@resources.command()
@click.option('--cmhost', help='Credential Manager host', default=None)
@click.option('--ochost', help='Orchestrator host', default=None)
@click.option('--tokenlocation', help='Path to token JSON file (defaults to $FABRIC_TOKEN_LOCATION or ./tokens.json)', default=None)
@click.option('--projectid', default=None, help='Project UUID')
@click.option('--scope', type=click.Choice(['cf', 'mf', 'all'], case_sensitive=False),
              default='all', help='Token scope')
@click.option('--force', is_flag=True, default=False, help='Force a fresh snapshot instead of using cache')
@click.option('--summary', is_flag=True, default=True, help='Show JSON summary instead of full topology')
@click.pass_context
def query(ctx, cmhost: str, ochost: str, tokenlocation: str, projectid: str, scope: str, force: bool, summary: bool):
    """Query resources

    Show available testbed resources. Use --force to bypass the cache.
    Use --summary for a compact JSON overview.
    """
    try:
        fm = __get_fabric_manager(cm_host=cmhost, oc_host=ochost, project_id=projectid, scope=scope,
                                  token_location=tokenlocation)
        if summary:
            result = fm.resources_summary(force_refresh=force)
            click.echo(json.dumps(result, indent=2))
        else:
            result = fm.resources(force_refresh=force)
            click.echo(result)
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))


cli.add_command(tokens)
cli.add_command(slices)
cli.add_command(slivers)
cli.add_command(resources)
