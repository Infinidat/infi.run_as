__import__("pkg_resources").declare_namespace(__name__)

from sys import maxsize
from infi.winver import Windows
from infi.cwrap import WrappedFunction, IN, IN_OUT, errcheck_zero, errcheck_nothing
from infi.instruct import Struct, ULInt16, ULInt32, ULInt64, Padding
from ctypes import c_void_p, c_ulong, c_buffer, create_string_buffer, create_unicode_buffer, byref
from infi.pyutils.contexts import contextmanager
from mock import patch, MagicMock
from os import environ
from logging import getLogger

logger = getLogger(__name__)
# pylint: disable=C0103

def is_64bit():
    return maxsize > 2 ** 32

class Ctypes(object):
    BOOL = c_ulong
    DWORD = c_ulong
    NULL = c_void_p(None)
    HANDLE = c_void_p

class Instruct(object):
    POINTER = ULInt64 if is_64bit() else ULInt32
    DWORD = ULInt32
    WORD = ULInt16
    HANDLE = ULInt64 if is_64bit() else ULInt32

class ProcessInformation(Struct):
    # http://msdn.microsoft.com/en-us/library/windows/desktop/ms684873(v=vs.85).aspx
    _fields_ = [Instruct.HANDLE("hProcess"), Instruct.HANDLE("hThread"),
                Instruct.DWORD("dwProcessId"), Instruct.DWORD("dwThreadId")]

class StartupInfoW(Struct):
    # http://msdn.microsoft.com/en-us/library/windows/desktop/ms686331(v=vs.85).aspx
    _fields_ = [Instruct.DWORD("cb")] + ([Padding(4)] if is_64bit() else [])
    _fields_ += [ Instruct.POINTER("reserved"), Instruct.POINTER("desktop"), Instruct.POINTER("title")]
    _fields_ += [Instruct.DWORD("dwX"), Instruct.DWORD("dxY"),
                 Instruct.DWORD("dwXSize"), Instruct.DWORD("dwYSize"),
                 Instruct.DWORD("dwXCountChars"), Instruct.DWORD("dwYCountChars"),
                 Instruct.DWORD("dwFillAttribute"), Instruct.DWORD("dwFlags"),
                 Instruct.WORD("wShowWindow"), Instruct.WORD("cbReserved2")] + ([Padding(4)] if is_64bit() else [])
    _fields_ += [Instruct.POINTER("lpReserved2"), Instruct.HANDLE("hStdInput"),
                 Instruct.HANDLE("hStdOutput"), Instruct.HANDLE("hStdError")]

    @classmethod
    def from_subprocess_startupinfo(cls, startup_info):
        size = StartupInfoW.min_max_sizeof().max
        this = cls.create_from_string(create_buffer(size))
        this.dwFlags = startup_info.dwFlags
        this.hStdInput = startup_info.hStdInput or 0
        this.hStdOutput = startup_info.hStdOutput or 0
        this.hStdError = startup_info.hStdError or 0
        this.cb = size
        return this.write_to_string(this)

def errcheck_bool():
    from ctypes import GetLastError
    def errcheck(result, func, args):
        if result == 0:
            last_error = GetLastError()
            raise RuntimeError(last_error)
        return result
    return errcheck

class WaitForInputIdle(WrappedFunction):
    return_value = Ctypes.DWORD

    @classmethod
    def get_errcheck(cls):
        return errcheck_nothing()

    @classmethod
    def get_library_name(cls):
        return 'user32'

    @classmethod
    def get_parameters(cls):
        return ((Ctypes.HANDLE, IN, 'hProcess'),
                (Ctypes.DWORD, IN, 'dwMilliseconds'))

class CloseHandle(WrappedFunction):
    return_value = Ctypes.DWORD

    @classmethod
    def get_errcheck(cls):
        return errcheck_bool()

    @classmethod
    def get_library_name(cls):
        return 'kernel32'

    @classmethod
    def get_parameters(cls):
        return ((Ctypes.HANDLE, IN, 'hObject'),)

class LogonUserW(WrappedFunction):
    # http://msdn.microsoft.com/en-us/library/windows/desktop/aa378184(v=vs.85).aspx
    return_value = Ctypes.BOOL

    @classmethod
    def get_errcheck(cls):
        return errcheck_bool()

    @classmethod
    def get_library_name(cls):
        return 'advapi32'

    @classmethod
    def get_parameters(cls):
        return ((c_void_p, IN, 'username'),
                (c_void_p, IN, "domain"),
                (c_void_p, IN, "password"),
                (Ctypes.DWORD, IN, "logonType"),
                (Ctypes.DWORD, IN, "logonProvider"),
                (c_void_p, IN, "pToken"))

class CreateProcessAsUserW(WrappedFunction):
    # http://msdn.microsoft.com/en-us/library/windows/desktop/ms682429(v=vs.85).aspx
    return_value = Ctypes.BOOL

    @classmethod
    def get_errcheck(cls):
        return errcheck_bool()

    @classmethod
    def get_library_name(cls):
        return 'advapi32'

    @classmethod
    def get_parameters(cls):
        return ((c_void_p, IN, 'token'),
                (c_void_p, IN, "applicationName"),
                (c_void_p, IN, "commandLine"),
                (c_void_p, IN, 'processAttributes'),
                (c_void_p, IN, 'threadAttributes'),
                (Ctypes.BOOL, IN, 'inheritFlags'),
                (Ctypes.DWORD, IN, 'creationFlags'),
                (c_void_p, IN, "environment"),
                (c_void_p, IN, "currentDirectory"),
                (c_void_p, IN, "startupInfo"),
                (c_void_p, IN, "processInformation"))

INVALID_HANDLE_VALUE = -1
INFINITE = 2147483647
LOGON32_PROVIDER_WINNT50 = 3
LOGON32_LOGON_INTERACTIVE = 2

class CreateProcessWithLogonW(WrappedFunction):
    # http://msdn.microsoft.com/en-us/library/ms682431(VS.85).aspx
    return_value = Ctypes.BOOL

    @classmethod
    def get_errcheck(cls):
        return errcheck_zero()

    @classmethod
    def get_library_name(cls):
        return 'advapi32'

    @classmethod
    def get_parameters(cls):
        return ((c_void_p, IN, 'username'),
                (c_void_p, IN, "domain"),
                (c_void_p, IN, "password"),
                (Ctypes.DWORD, IN, "logonFlags"),
                (c_void_p, IN, "applicationName"),
                (c_void_p, IN, "commandLine"),
                (Ctypes.DWORD, IN, "creationFlags"),
                (c_void_p, IN, "environment"),
                (c_void_p, IN, "currentDirectory"),
                (c_void_p, IN, "startupInfo"),
                (c_void_p, IN, "processInformation"))

class Handle(object):
    # Mocked from _subprocess.c
    def __init__(self, handle):
        super(Handle, self).__init__()
        self._handle = handle

    def Detach(self):
        handle = self._handle
        self._handle = INVALID_HANDLE_VALUE
        return handle

    def Close(self):
        if self._handle != INVALID_HANDLE_VALUE:
            CloseHandle(self._handle)
            self._handle = INVALID_HANDLE_VALUE

    def __int__(self):
        return self._handle

    def __del__(self):
        self.Close()

class Environment(object):
    @classmethod
    def from_dict(cls, env=None):
        """A pointer to the environment block for the new process.
        If this parameter is NULL, the new process uses the environment of the calling process.
        An environment block consists of a null-terminated block of null-terminated strings.
        Each string is in the following form:
        name=value\0
        """
        if env == None:
            return Ctypes.NULL
        pairs = ["{}={}".format(key, value) for key, value in env.items()]
        string = "\0".join([pairs])
        buffer = create_unicode_buffer(string)
        return buffer

def create_buffer(size):
    logger.debug("Allocating buffer of size {}".format(size))
    return c_buffer('\x00' * size, size)

def get_token(username, password):
    username = create_unicode_buffer(username)
    domain = create_unicode_buffer(environ['COMPUTERNAME'])
    password = create_unicode_buffer(password)
    token = Ctypes.HANDLE(0)
    LogonUserW(username, domain, password,
               Ctypes.DWORD(LOGON32_LOGON_INTERACTIVE),
               Ctypes.DWORD(LOGON32_PROVIDER_WINNT50), byref(token))
    return token.value
