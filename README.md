[![PyPI](https://img.shields.io/pypi/v/fabrictestbed?style=plastic)](https://pypi.org/project/fabrictestbed/)


# FABRIC TESTBED USER LIBRARY

FABRIC Python client library for managing testbed resources.

## Overview
This package supports User facing APIs for interacting with FABRIC testbed services.
- Tokens: Token management
- Slices: Slice management
- Slivers: Sliver management
- Resources: Resource management

**Note:** The CLI (`fabric-cli`) has moved to [fabrictestbed-extensions](https://github.com/fabric-testbed/fabrictestbed-extensions).

### API
`SliceManager` class implements the API supporting the operations listed above. Check example in Usage below.

## Requirements
Python 3.9+

## Installation
```
$ pip install fabrictestbed
```

For development, install from GitHub:
```
$ pip install git+https://github.com/fabric-testbed/fabrictestbed.git
```

## Usage
User API supports token and orchestrator commands. Please refer to Jupyter Notebooks [here](https://github.com/fabric-testbed/jupyter-examples/tree/master/fabric_examples/beta_functionality) for examples.

### Configuration
The following environment variables can be set:
```
export FABRIC_ORCHESTRATOR_HOST=orchestrator.fabric-testbed.net
export FABRIC_CREDMGR_HOST=cm.fabric-testbed.net
export FABRIC_TOKEN_LOCATION=<location of the token file downloaded from the Portal>
export FABRIC_PROJECT_ID=<Project Id of the project for which resources are being provisioned>
```
