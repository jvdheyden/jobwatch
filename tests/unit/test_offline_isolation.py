"""The offline guard must also protect Python launched by shell workflows."""
import socket
import sys

import pytest

from offline.sitecustomize import OfflineNetworkError


@pytest.mark.parametrize('method', ['connect', 'connect_ex'])
@pytest.mark.parametrize('host', ['203.0.113.1', 'jobs.example.com'])
def test_external_connections_fail_before_transport(method, host):
    with socket.socket() as client:
        with pytest.raises(OfflineNetworkError, match='Offline test attempted network'):
            getattr(client, method)((host, 443))


def test_loopback_connect_ex_keeps_socket_return_contract():
    with socket.socket() as server, socket.socket() as client:
        server.bind(('127.0.0.1', 0))
        server.listen()
        assert client.connect_ex(server.getsockname()) == 0


@pytest.mark.parametrize('env', [None, {'PYTHONPATH': ''}])
def test_child_python_inherits_offline_guard(run_cmd, env):
    result = run_cmd(sys.executable, '-c', "import socket; socket.create_connection(('203.0.113.1', 443))", env=env)
    assert result.returncode != 0
    assert 'OfflineNetworkError' in result.stderr
