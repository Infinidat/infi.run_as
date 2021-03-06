__import__("pkg_resources").declare_namespace(__name__)

import sys
from infi.winver import Windows
from infi.pyutils.contexts import contextmanager
from mock import patch
from logging import getLogger
from os import environ, path
from sys import argv, stderr, stdout
from .c_api import Environment, StartupInfoW, ProcessInformation, CreateProcessWithLogonW, WaitForInputIdle, Handle
from .c_api import create_buffer, create_unicode_buffer, Ctypes, get_token, CreateProcessAsUserW, INFINITE, to_bytes


logger = getLogger(__name__)


class CreateProcess(object):
    def __init__(self, username, password):
        super(CreateProcess, self).__init__()
        self.username = username
        self.password = password
        self.method = self._CreateProcessAsUser if \
                      self._can_we_not_use_create_process_with_login() else \
                      self._CreateProcessWithLogon

    def _can_we_not_use_create_process_with_login(self):
        # http://msdn.microsoft.com/en-us/library/windows/desktop/ms68243a1(v=vs.85).aspx
        # Windows XP with SP2 and Windows Server 2003:
        # You cannot call CreateProcessWithLogonW from a process that is running under the "LocalSystem" account,
        # because the function uses the logon SID in the caller token,
        # and the token for the "LocalSystem" account does not contain this SID.
        # As an alternative, use the CreateProcessAsUser and LogonUser functions.
        return Windows().is_windows_2003() and environ.get('USERNAME', 'SYSTEM') == 'SYSTEM'

    def create_process_as_administrator(self, *args, **kwargs):
        """ A drop-in replacement for _subprocess.CreateProcess that creates the process as an administrator
        :returns: a 4-tuple (proc_handle, thread_handle, pid, tid)"""
        return self.method(*args, **kwargs)

    def _CreateProcessWithLogon(self, app_name, cmd_line, proc_attrs, thread_attrs, inherit,
                                flags, env_mapping, curdir, startup_info):
        """ A drop-in replacement for _subprocess.CreateProcess that creates the process as an administrator
        :returns: a 4-tuple (proc_handle, thread_handle, pid, tid)"""

        username = create_unicode_buffer(self.username)
        domain = Ctypes.NULL
        password = create_unicode_buffer(self.password)
        logonFlags = Ctypes.DWORD(0x00000001)
        applicationName = Ctypes.NULL if app_name is None else create_unicode_buffer(app_name)
        commandLine = Ctypes.NULL if cmd_line is None else create_unicode_buffer(cmd_line)
        creationFlags = Ctypes.DWORD(0x00000010 | 0x00000400)
        environment = Environment.from_dict(env_mapping)
        currentDirectory = create_unicode_buffer(path.abspath('.') if curdir is None else curdir)
        startupInfo = StartupInfoW.from_subprocess_startupinfo(startup_info)
        processInformation = create_buffer(ProcessInformation.min_max_sizeof().max)
        logger.debug("Calling CreateProcessWithLogonW for {} {}".format(app_name, cmd_line))
        result = CreateProcessWithLogonW(username, domain, password, logonFlags,
                                         applicationName, commandLine, creationFlags,
                                         environment, currentDirectory, startupInfo, processInformation)
        processInformation_ = ProcessInformation.create_from_string(to_bytes(processInformation))
        logger.debug("Call returned {} with {!r}".format(result, processInformation_))
        logger.debug("Waiting for process to finish initalization")
        WaitForInputIdle(processInformation_.hProcess, INFINITE)
        logger.debug("Done waiting")
        h_process, h_thread = self._get_hprocess_hthread(processInformation_)
        result = (h_process, h_thread, processInformation_.dwProcessId, processInformation_.dwThreadId)
        return result

    def _CreateProcessAsUser(self, app_name, cmd_line, proc_attrs, thread_attrs, inherit,
                             flags, env_mapping, curdir, startup_info):
        """ A drop-in replacement for _subprocess.CreateProcess that creates the process as an administrator
        :returns: a 4-tuple (proc_handle, thread_handle, pid, tid)"""

        token = get_token(self.username, self.password)
        applicationName = Ctypes.NULL if app_name is None else create_unicode_buffer(app_name)
        commandLine = Ctypes.NULL if cmd_line is None else create_unicode_buffer(cmd_line)
        environment = Environment.from_dict(env_mapping)
        currentDirectory = create_unicode_buffer(path.abspath('.') if curdir is None else curdir)
        startupInfo = StartupInfoW.from_subprocess_startupinfo(startup_info)
        processInformation = create_buffer(ProcessInformation.min_max_sizeof().max)
        logger.debug("Calling CreateProcessWithLogonW for {} {}".format(app_name, cmd_line))
        result = CreateProcessAsUserW(Ctypes.HANDLE(token), applicationName, commandLine,
                                      Ctypes.NULL, Ctypes.NULL,
                                      Ctypes.BOOL(False), 0, environment, currentDirectory,
                                      startupInfo, processInformation)
        Handle(token).Close()
        processInformation_ = ProcessInformation.create_from_string(to_bytes(processInformation))
        logger.debug("Call returned {} with {!r}".format(result, processInformation_))
        logger.debug("Waiting for process to finish initalization")
        WaitForInputIdle(processInformation_.hProcess, INFINITE)
        logger.debug("Done waiting")
        h_process, h_thread = self._get_hprocess_hthread(processInformation_)
        result = (h_process, h_thread, processInformation_.dwProcessId, processInformation_.dwThreadId)
        return result

    def _get_hprocess_hthread(self, processInformation_):
        if sys.version_info[0] < 3:
            return Handle(processInformation_.hProcess), Handle(processInformation_.hThread)
        return processInformation_.hProcess, processInformation_.hThread


@contextmanager
def subprocess_runas_context(username, password):
    if sys.version_info[0] < 3:
        create_process_path = "_subprocess.CreateProcess"
    else:
        create_process_path = "_winapi.CreateProcess"
    side_effect = CreateProcess(username, password).create_process_as_administrator
    with patch(create_process_path, new=side_effect):
        yield


def write_to_stream(stream, content):
    if sys.version_info[0] < 3:
        stream.write(content)
    else:
        stream.buffer.write(content)
    stream.flush()


def run_as(argv=argv[1:]):
    from infi.execute import execute
    username, password, args = argv[0], argv[1], argv[2:]
    with subprocess_runas_context(username, password):
        pid = execute(args)
    write_to_stream(stdout, pid.get_stdout())
    write_to_stream(stderr, pid.get_stderr())
    return pid.get_returncode()


__all__ = ['subprocess_runas_context', 'run_as']
