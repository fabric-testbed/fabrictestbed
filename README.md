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
`tokens` | `issue`| Issue token with projectname and scope | `projectname` Project Name, `scope` Scope | Points user to Credential Manager to generate the tokens
`token` | `refresh`| Refresh token | `projectname` Project Name, `scope` Scope, `refreshtoken` Refresh Token | Returns new identity and refresh tokens
`token` | `revoke` | Revoke token |  `refreshtoken` Refresh Token | Success or Failure status
`slices` | `query` | Query user slice(s) |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope, `sliceid` Slice Id | List of Slices or Graph ML representing slice identified by Slice Id
`slices` | `create` | Create user slice |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope, `slicename` Slice Name, `slicegraph` Slice graph | List of Slivers created for the Slice
`slices` | `delete` | Delete user slice |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope, `sliceid` Slice Id | Success or Failure Status
`slivers` | `query` | Query user sliver(s) |  `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope, `sliceid` Slice Id, `sliverid` Sliver Id | List of Slivers for the slice identified by Slice Id or Sliver identified by Sliver Id
`resources` | `query` | Query resources | `idtoken` Identity Token, `refreshtoken` Refresh Token, `projectname` Project Name, `scope` Scope | Graph ML representing the available resources

### API
`SliceManager` class implements the API supporting the operations listed above. Check example in Usage below.

## Requirements
Python 3.7+

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
User API supports token and orchestrator commands:
```
from fabrictestbed.slice_manager import SliceManager, Status
from fabrictestbed.slice_editor import ExperimentTopology, Capacities, ComponentType

orchestrator_host = "<ORCHESTRATOR FQDN>"
credmgr_host = "<CREDENTIAL MANAGER FQDN>"
fabric_refresh_token = "<REFRESH TOKEN>"

# Create API Client object
# Users can request tokens with different Project and Scopes by altering `project_name` and `scope`
# parameters in the refresh call below.
client = SliceManager(oc_host=orchestrator_host, cm_host=credmgr_host,
                      refresh_token=fabric_refresh_token, project_name='all', scope='all')

# Get new Fabric Identity Token and update Fabric Refresh Token
try:
    id_token, refresh_token = client.refresh_tokens()
except Exception as e:
    print("Exception occurred while getting tokens:{}".format(e))

# User is expected to update the refresh token in JupyterHub environment such as below
# fabric_refresh_token=client.get_refresh_token()
# %store fabric_refresh_token

# Query Resources
status, advertised_topology = client.resources()

print(f"Status: {status}")
if status == Status.OK:
    print(f"Toplogy: {advertised_topology}")

# Create Slice
# Create topology
t = ExperimentTopology()

# Add node
n1 = t.add_node(name='n1', site='RENC')

# Set capacities
cap = Capacities()
cap.set_fields(core=4, ram=64, disk=500)

# Set Properties
n1.set_properties(capacities=cap, image_type='qcow2', image_ref='default_centos_8')

# Add PCI devices
n1.add_component(ctype=ComponentType.SmartNIC, model='ConnectX-5', name='nic1')

# Add node
n2 = t.add_node(name='n2', site='UKY')

# Set properties
n2.set_properties(capacities=cap, image_type='qcow2', image_ref='default_centos_8')

# Add PCI devices
n2.add_component(ctype=ComponentType.GPU, model='Tesla T4', name='nic2')

# Add node
n3 = t.add_node(name='n3', site='LBNL')

# Set properties
n3.set_properties(capacities=cap, image_type='qcow2', image_ref='default_centos_8')

# Add PCI devices
n3.add_component(ctype=ComponentType.GPU, model='Tesla T4', name='nic3')

# Generate Slice Graph
slice_graph = t.serialize()

ssh_key = None
with open("/home/fabric/.ssh/id_rsa.pub", "r") as myfile:
    ssh_key = myfile.read()
    ssh_key = ssh_key.strip()

# Request slice from Orchestrator
status, reservations = client.create(slice_name='JupyterSlice2', slice_graph=slice_graph, ssh_key=ssh_key)

print("Response Status {}".format(status))
if status == Status.OK:
    print("Reservations created {}".format(reservations))

slice_id = reservations[0].slice_id
# Delete Slice
status, result = client.delete(slice_id=slice_id)

print("Response Status {}".format(status))
if status == Status.OK:
    print("Response received {}".format(result))
```

## Usage (CLI)
### Configuration
User CLI expects the user to set `FABRIC_ORCHESTRATOR_HOST` and `FABRIC_CREDMGR_HOST` environment variables. 

In addition, User is expected to pass either Fabric Identity Token or Fabric Refresh Token to all the orchestrator commands. 
Alternatively, user is expected to set atleast one of the environment variables `FABRIC_ID_TOKEN` and `FABRIC_REFRESH_TOKEN`.

Create config.yml with default content as shown below. 
 
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
