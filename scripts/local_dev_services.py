"""Persistent adapters for the existing loopback Auth/Storage test simulator.

Development tools only. Nothing in app/ imports this module.
"""
import json
import os
import tempfile
import time
from collections.abc import MutableMapping
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from integrated_services import LocalServices


def atomic_write(path, contents):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, value):
    atomic_write(path, (json.dumps(value, indent=2) + "\n").encode())


class DiskObjects(MutableMapping):
    """Never resolve an object outside the dedicated local storage directory."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def location(self, key):
        if not isinstance(key, str) or not key or "\\" in key or "\x00" in key:
            raise KeyError("Invalid local object path")
        relative = PurePosixPath(key)
        if relative.is_absolute() or any(part in {".", "..", ""} for part in key.split("/")):
            raise KeyError("Invalid local object path")
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root) or candidate == self.root:
            raise KeyError("Invalid local object path")
        return candidate

    def __getitem__(self, key):
        try:
            return self.location(key).read_bytes()
        except FileNotFoundError:
            raise KeyError(key) from None

    def __setitem__(self, key, value):
        atomic_write(self.location(key), value)

    def __delitem__(self, key):
        try:
            self.location(key).unlink()
        except FileNotFoundError:
            raise KeyError(key) from None

    def __iter__(self):
        return (p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file() and p.suffix != ".tmp")

    def __len__(self):
        return sum(1 for _ in self)


class DiskTokens(MutableMapping):
    """Atomic local refresh/signed URL tokens, with expiry, never printed."""
    def __init__(self, path, ttl):
        self.path, self.ttl = Path(path), ttl
        self.entries = json.loads(self.path.read_text()) if self.path.exists() else {}

    def __getitem__(self, key):
        value = self.entries[key]
        if value["expires"] <= time.time():
            raise KeyError(key)
        return value["value"]

    def __setitem__(self, key, value):
        now = time.time()
        self.entries = {k: v for k, v in self.entries.items() if v["expires"] > now}
        self.entries[key] = {"value": value, "expires": now + self.ttl}
        write_json(self.path, self.entries)

    def __delitem__(self, key):
        del self.entries[key]
        write_json(self.path, self.entries)

    def __iter__(self):
        return (k for k, v in self.entries.items() if v["expires"] > time.time())

    def __len__(self):
        return sum(1 for _ in self)


class PersistentServices(LocalServices):
    def __init__(self, profiles, origins, directory, credentials):
        super().__init__(profiles, origins[0])  # Includes mandatory isolated DB marker check.
        directory = Path(directory)
        self.origins = set(origins)
        self.password = credentials["auth_password"]
        self.key = serialization.load_pem_private_key((directory / "auth-signing.key").read_bytes(), password=None)
        if not isinstance(self.key, ec.EllipticCurvePrivateKey) or not isinstance(self.key.curve, ec.SECP256R1):
            raise ValueError("Local signing key is not ES256")
        self.kid = credentials["kid"]
        self.refresh = DiskTokens(directory / "refresh-tokens.json", 7 * 24 * 3600)
        self.read_tokens = DiskTokens(directory / "read-tokens.json", 300)
        self.objects = DiskObjects(directory / "storage")
        if "controls/keep.png" not in self.objects:
            self.objects["controls/keep.png"] = b"fictitious-control-do-not-delete"

    def session(self, user_id):
        with self.lock:
            return super().session(user_id)
