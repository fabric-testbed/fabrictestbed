[![Requirements Status](https://requires.io/github/fabric-testbed/fabric-cli/requirements.svg?branch=master)](https://requires.io/github/fabric-testbed/fabric-cli/requirements/?branch=master)

[![PyPI](https://img.shields.io/pypi/v/fabrictestbed?style=plastic)](https://pypi.org/project/fabrictestbed/)


# FABRIC TESTBED USER LIBRARY AND CLI

Fabric User CLI for experiments

## Overview
This package supports User facing APIs as well as CLI.
- Tokens: Token management
- Slices: Slice management
- Slivers: Sliver management
- Resources: Resource management

### CLI Commands
Command | SubCommand | Action | Input | Output
:--------|:----:|:----:|:---:|:---:
`tokens` | `issue`| Issue token with projectId and scope | `projectId` Project Id, `scope` Scope | Points user to Credential Manager to generate the tokens
`token` | `refresh`| Refresh token | `projectId` Project Id, `scope` Scope, `refreshtoken` Refresh Token | Returns new identity and refresh tokens
`token` | `revoke` | Revoke token |  `refreshtoken` Refresh Token | Success or Failure status
`slices` | `query` | Query user slice(s) |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectId` Project Id, `scope` Scope, `sliceid` Slice Id | List of Slices or Graph ML representing slice identified by Slice Id
`slices` | `create` | Create user slice |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectId` Project Id, `scope` Scope, `slicename` Slice Name, `slicegraph` Slice graph | List of Slivers created for the Slice
`slices` | `delete` | Delete user slice |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectId` Project Id, `scope` Scope, `sliceid` Slice Id | Success or Failure Status
`slivers` | `query` | Query user sliver(s) |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectId` Project Id, `scope` Scope, `sliceid` Slice Id, `sliverid` Sliver Id | List of Slivers for the slice identified by Slice Id or Sliver identified by Sliver Id
`resources` | `query` | Query resources | `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectId` Project Id, `scope` Scope | Graph ML representing the available resources

### API
`SliceManager` class implements the API supporting the operations listed above. Check example in Usage below.

## Requirements
Python 3.9+

## Pre-requisites
Ensure that following are installed
- `virtualenv`
- `virtualenvwrapper`

## Installation
Multiple installation options possible. For CF development the recommended method is to install from GitHub MASTER branch:
```
$ mkvirtualenv fabrictestbed
$ workon fabrictestbed
$ pip install git+https://github.com/fabric-testbed/fabric-cli.git
```
For inclusion in tools, etc, use PyPi
```
$ mkvirtualenv fabrictestbed
$ workon fabrictestbed
$ pip install fabrictestbed
```

## Usage (API)
User API supports token and orchestrator commands. Please refer to Jupyter Notebooks [here](https://github.com/fabric-testbed/jupyter-examples/tree/master/fabric_examples/beta_functionality) for examples.

## Usage (CLI)
### Configuration
User CLI expects the user to set following environment variables:
```
export FABRIC_ORCHESTRATOR_HOST=orchestrator.fabric-testbed.net
export FABRIC_CREDMGR_HOST=cm.fabric-testbed.net
export FABRIC_TOKEN_LOCATION=<location of the token file downloaded from the Portal>
export FABRIC_PROJECT_ID=<Project Id of the project for which resources are being provisioned>
```

Alternatively, user can pass these as parameters to the commands.

#### To enable CLI auto-completion, add following line to your ~/.bashrc
```
eval "$(_FABRIC_CLI_COMPLETE=source_bash fabric-cli)"
```
Open a new shell to enable completion.
Or run the eval command directly in your current shell to enable it temporarily.

User CLI supports token and orchestrator commands:
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
  issue    Issue token with projectId and scope
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
  query  issue token with projectId and scope
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
