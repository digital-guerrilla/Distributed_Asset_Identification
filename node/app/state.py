"""In-memory node liveness flag used to simulate this node going offline (demo kill-switch)."""

_offline: bool = False


def is_offline() -> bool:
    return _offline


def set_offline(value: bool) -> None:
    global _offline
    _offline = value


# In-memory override for encrypted storage opt-in, so the demo UI can flip a
# node's privacy/storage posture live without restarting it. None means "use
# the configured default from settings.ENCRYPTED_STORAGE_OPT_IN".
_storage_opt_in_override: bool | None = None


def is_storage_opt_in(default: bool) -> bool:
    return _storage_opt_in_override if _storage_opt_in_override is not None else default


def set_storage_opt_in(value: bool) -> None:
    global _storage_opt_in_override
    _storage_opt_in_override = value
