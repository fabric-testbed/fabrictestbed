[![Requirements Status](https://requires.io/github/fabric-testbed/fabric-cli/requirements.svg?branch=master)](https://requires.io/github/fabric-testbed/fabric-cli/requirements/?branch=master)

# FABRIC User CLI

Fabric User CLI for experiments

## Overview
User CLI supports following kinds commands:
- Token : Commands to issue, refresh or revoke tokens
- Orchestrator Commands : Query/Request/Modify/Delete Resources

Command | SubCommand | Action | Input | Output
:--------|:----:|:----:|:---:|:---:
`token` | `issue`| Issue Fabric Tokens | `projectname` Project Name, `scope` Scope | Points user to Credential Manager to generate the tokens
`token` | `refresh`| Refresh Fabric Tokens | `projectname` Project Name, `scope` Scope, `refreshtoken` Refresh Token | Returns new identity and refresh tokens
`token` | `revoke` | Revoke a Refresh Token |  `refreshtoken` Refresh Token | Success or Failure status
`resources` | `query` | Query available resources from Orchestrator |  | Graph ML representing the available resources

## Requirements
Python 3.7+

## Pre-requisites
Ensure that following are installed
- `virtualenv`
- `virtualenvwrapper`

## Installation
Multiple installation options possible. For CF development the recommended method is to install from GitHub MASTER branch:
```
$ mkvirtualenv cli
$ workon cli
$ pip install git+https://github.com/fabric-testbed/fabric-cli.git
```
For inclusion in tools, etc, use PyPi
```
$ mkvirtualenv cli
$ workon cli
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
$ fabric-cli
Usage: fabric-cli [OPTIONS] COMMAND [ARGS]...

Options:
  -v, --verbose
  --help         Show this message and exit.

Commands:
  resources  Query Resources (set $FABRIC_ORCHESTRATOR_HOST to the Control...
  slice      slice management
  token      issue/get/refresh/revoke FABRIC tokens.
```

### Token Commands
List of the token commands supported can be found below:
```
$ fabric-cli token
Usage: fabric-cli token [OPTIONS] COMMAND [ARGS]...

  issue/get/refresh/revoke FABRIC tokens. (set $FABRIC_CREDMGR_HOST to the
  Credential Manager Server)

Options:
  --help  Show this message and exit.

Commands:
  issue    issue token with projectname and scope
  refresh  refresh token
  revoke   revoke token
```

### Resources Commands
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
