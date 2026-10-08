import socket

_ORIG_GETADDRINFO = socket.getaddrinfo

# Fast IP mapping for eMaktab hosts
_EMAKTAB_IPS = {
    "login.emaktab.uz": "84.54.112.60",
    "static.emaktab.uz": "84.54.112.60",
    "emaktab.uz": "84.54.112.60",
}


def apply_dns_patch():
    """Patches socket.getaddrinfo to resolve eMaktab domains in 0.0ms."""
    def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if isinstance(host, str) and host in _EMAKTAB_IPS:
            try:
                return _ORIG_GETADDRINFO(_EMAKTAB_IPS[host], port, family, type, proto, flags)
            except Exception:
                pass
        return _ORIG_GETADDRINFO(host, port, family, type, proto, flags)

    socket.getaddrinfo = patched_getaddrinfo


apply_dns_patch()
