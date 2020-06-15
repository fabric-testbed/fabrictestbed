from click.testing import CliRunner
from fabric import cli


def test_token_issue():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['token', 'issue'])
    print(result.output)
    assert result.exit_code == 0
    assert 'fabric-cli token get --uid' in result.output


def test_token_issue_verbose():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['--verbose', 'token', 'issue'])
    print(result.output)
    assert result.exit_code == 0
    assert 'scope: all' in result.output
    assert 'fabric-cli token get --uid' in result.output


def test_token_get_unknown_uid():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['token', 'get', '--uid', 'FA1C76805DD54FDBBC8945F5B5F514C7'])
    print(result.output)
    assert result.exit_code == 1
    print(result.exception)


def test_token_get_unknown_uid_verbose():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['--verbose', 'token', 'get', '--uid', 'FA1C76805DD54FDBBC8945F5B5F514C7'])
    print(result.output)
    assert result.exit_code == 1
    print(result.exception)


def test_token_get_success():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['token', 'issue'])
    print(result.output)
    getcommand = []
    for line in result.output.split('\n'):
        if 'fabric-cli token get --uid' in line:
            getcommand = line.split()[1:]
            break
    input("\nLogin at the URL, then Press Enter to continue...\n")
    result = runner.invoke(cli.cli, getcommand)
    print(result.output)
    assert result.exit_code == 0
    assert 'id_token' in result.output
    assert 'refresh_token' in result.output

