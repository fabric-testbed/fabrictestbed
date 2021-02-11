[![Requirements Status](https://requires.io/github/fabric-testbed/fabric-cli/requirements.svg?branch=master)](https://requires.io/github/fabric-testbed/fabric-cli/requirements/?branch=master)

[![PyPI](https://img.shields.io/pypi/v/fabric-cli?style=plastic)](https://pypi.org/project/fabric-cli/)


# FABRIC User CLI

Fabric User CLI for experiments

## Overview
User CLI supports following kinds commands:
- Tokens: Token management
- Slices: Slice management
- Slivers: Sliver management
- Resources: Resource management

Command | SubCommand | Action | Input | Output
:--------|:----:|:----:|:---:|:---:
`tokens` | `issue`| Issue token with projectname and scope | `projectname` Project Name, `scope` Scope | Points user to Credential Manager to generate the tokens
`token` | `refresh`| Refresh token | `projectname` Project Name, `scope` Scope, `refreshtoken` Refresh Token | Returns new identity and refresh tokens
`token` | `revoke` | Revoke token |  `refreshtoken` Refresh Token | Success or Failure status
`slices` | `query` | Query user slice(s) |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope, `sliceid` Slice Id | List of Slices or Graph ML representing slice identified by Slice Id
`slices` | `create` | Create user slice |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope, `slicename` Slice Name, `slicegraph` Slice graph | List of Slivers created for the Slice
`slices` | `delete` | Delete user slice |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope, `sliceid` Slice Id | Success or Failure Status
`slivers` | `query` | Query user sliver(s) |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope, `sliceid` Slice Id, `sliverid` Sliver Id | List of Slivers for the slice identified by Slice Id or Sliver identified by Sliver Id
`resources` | `query` | Query resources | `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope | Graph ML representing the available resources

## Requirements
Python 3.7+

## Pre-requisites
Ensure that following are installed
- `virtualenv`
- `virtualenvwrapper`

## Installation
Multiple installation options possible. For CF development the recommended method is to install from GitHub MASTER branch:
```
$ mkvirtualenv usercli
$ workon usercli
$ pip install git+https://github.com/fabric-testbed/fabric-cli.git
```
For inclusion in tools, etc, use PyPi
```
$ mkvirtualenv usercli
$ workon usercli
$ pip install fabric-cli
```

## Configuration
User CLI expects the user to set `FABRIC_ORCHESTRATOR_HOST` and `FABRIC_CREDMGR_HOST` environment variables. 

In addition, User is expected to pass either Fabric Identity Token or Fabric Refresh Token to all the orchestrator commands. 
Alternatively, user is expected to set atleast one of the environment variables `FABRIC_ID_TOKEN` and `FABRIC_REFRESH_TOKEN`.

Create config.yml with default content as shown below. 
 
### To enable CLI auto-completion, add following line to your ~/.bashrc
```
eval "$(_FABRIC_CLI_COMPLETE=source_bash fabric-cli)"
```
Open a new shell to enable completion.
Or run the eval command directly in your current shell to enable it temporarily.

## Usage
User CLI supports token and resources commands:
```
(usercli) $ fabric-cli
Usage: fabric-cli [OPTIONS] COMMAND [ARGS]...

Options:
  -v, --verbose
  --help         Show this message and exit.

Commands:
  resources  Resource management (set $FABRIC_ORCHESTRATOR_HOST to the...
  slices     Slice management (set $FABRIC_ORCHESTRATOR_HOST to the...
  slivers    Sliver management (set $FABRIC_ORCHESTRATOR_HOST to the...
  tokens     Token management (set $FABRIC_CREDMGR_HOST to the Credential...
```

### Token Management Commands
List of the token commands supported can be found below:
```
(usercli) $ fabric-cli tokens
Usage: fabric-cli tokens [OPTIONS] COMMAND [ARGS]...

  Token management (set $FABRIC_CREDMGR_HOST to the Credential Manager
  Server)

Options:
  --help  Show this message and exit.

Commands:
  issue    Issue token with projectname and scope
  refresh  Refresh token
  revoke   Revoke token
```

### Resource Management Commands
List of the resource commands supported can be found below:
```
$ fabric-cli resources
Usage: fabric-cli resources [OPTIONS] COMMAND [ARGS]...

  Query Resources (set $FABRIC_ORCHESTRATOR_HOST to the Control Framework
  Orchestrator)

Options:
  --help  Show this message and exit.

Commands:
  query  issue token with projectname and scope
```
### Slice Management Commands
```
(usercli) $ fabric-cli slices
Usage: fabric-cli slices [OPTIONS] COMMAND [ARGS]...

  Slice management (set $FABRIC_ORCHESTRATOR_HOST to the Orchestrator)

Options:
  --help  Show this message and exit.

Commands:
  create  Create user slice
  delete  Delete user slice
  query   Query user slice(s)
```
### Sliver Management Commands
```
(usercli) $ fabric-cli slivers
Usage: fabric-cli slivers [OPTIONS] COMMAND [ARGS]...

  Sliver management (set $FABRIC_ORCHESTRATOR_HOST to the Orchestrator)

Options:
  --help  Show this message and exit.

Commands:
  query  Query user slice sliver(s)
```
