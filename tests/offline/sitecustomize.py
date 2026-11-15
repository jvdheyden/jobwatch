"""Network guard inherited by Python subprocesses through test PYTHONPATH.

No live checks belong in pytest. Loopback fixture servers are allowed.
"""
import socket
import ipaddress

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


class OfflineNetworkError(BaseException):
    """Fail even if production handles ordinary transport errors as coverage."""


def _check_address(self, address):
    # Local fixture servers exercise real HTTP without contacting the internet.
    if self.family not in (socket.AF_INET, socket.AF_INET6):
        return
    try:
        if ipaddress.ip_address(address[0]).is_loopback:
            return
    except ValueError:
        pass
    raise OfflineNetworkError(f"Offline test attempted network access to {address!r}; mock the transport")


def deny_network(self, address):
    _check_address(self, address)
    return _connect(self, address)


def deny_network_ex(self, address):
    _check_address(self, address)
    return _connect_ex(self, address)


socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network_ex
