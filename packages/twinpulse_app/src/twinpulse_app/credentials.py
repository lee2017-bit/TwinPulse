"""OS credential adapter shared by the local app and legacy Extension."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from typing import Protocol, runtime_checkable


DEFAULT_CREDENTIAL_TARGET = "TwinPulse/OpenAIResponsesAPI"
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


@runtime_checkable
class CredentialStore(Protocol):
    @property
    def target_name(self) -> str: ...
    def save(self, secret: str) -> None: ...
    def load(self) -> str | None: ...
    def is_configured(self) -> bool: ...
    def delete(self) -> None: ...


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    """Use the existing TwinPulse Windows Credential Manager target."""

    def __init__(self, target_name: str = DEFAULT_CREDENTIAL_TARGET) -> None:
        self._target_name = target_name
        self._api = None
        if os.name == "nt":
            self._api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
            self._api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
            self._api.CredWriteW.restype = wintypes.BOOL
            self._api.CredReadW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                ctypes.POINTER(ctypes.POINTER(_Credential)),
            ]
            self._api.CredReadW.restype = wintypes.BOOL
            self._api.CredFree.argtypes = [ctypes.c_void_p]
            self._api.CredFree.restype = None
            self._api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            self._api.CredDeleteW.restype = wintypes.BOOL

    @property
    def target_name(self) -> str:
        return self._target_name

    def save(self, secret: str) -> None:
        if self._api is None:
            raise RuntimeError("Secure API key storage is available only on Windows")
        value = secret.strip()
        if not value:
            raise ValueError("API key cannot be empty")
        blob = value.encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = _Credential()
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = self._target_name
        credential.Comment = "TwinPulse LLM provider credential"
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "TwinPulse"
        if not self._api.CredWriteW(ctypes.byref(credential), 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def load(self) -> str | None:
        if self._api is None:
            return None
        pointer = ctypes.POINTER(_Credential)()
        if not self._api.CredReadW(self._target_name, _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            error = ctypes.get_last_error()
            if error == _ERROR_NOT_FOUND:
                return None
            raise ctypes.WinError(error)
        try:
            item = pointer.contents
            raw = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            self._api.CredFree(pointer)

    def is_configured(self) -> bool:
        return bool(self.load())

    def delete(self) -> None:
        if self._api is None:
            raise RuntimeError("Secure API key storage is available only on Windows")
        if not self._api.CredDeleteW(self._target_name, _CRED_TYPE_GENERIC, 0):
            error = ctypes.get_last_error()
            if error != _ERROR_NOT_FOUND:
                raise ctypes.WinError(error)
