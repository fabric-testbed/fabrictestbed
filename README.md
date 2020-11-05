# FABRIC User CLI

Fabric User CLI for experiments

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
$ https://github.com/fabric-testbed/fabric-cli.git
```
For inclusion in tools, etc, use PyPi
```
$ mkvirtualenv cli
$ workon cli
$ pip install cli
```
### To enable CLI auto-completion, add following line to your ~/.bashrc
```
eval "$(_FABRIC_CLI_COMPLETE=source_bash fabric-cli)"
```
Open a new shell to enable completion.
Or run the eval command directly in your current shell to enable it temporarily.