from unittest import TestCase, SkipTest
from mock import patch
from os import name, environ
from infi.run_as import run_as


class RunAsTestCase(TestCase):
    def win_only(self):
        if name != 'nt':
            raise SkipTest("windows only")

    def test__on_unix_with_mock(self):
        if name == 'nt':
            raise SkipTest("unix only")
        with patch("infi.run_as.subprocess_runas_context"):
            self.assertEqual(0, run_as(["Administrator", "Password", "ifconfig"]))

    def test__on_windows_process(self):
        self.win_only()
        username, password = environ['RUNAS_USERNAME'], environ['RUNAS_PASSWORD']
        self.assertEqual(0, run_as([username, password, "ipconfig"]))

    def test__on_windows_binary_print(self):
        self.win_only()
        username, password = environ['RUNAS_USERNAME'], environ['RUNAS_PASSWORD']
        self.assertEqual(0, run_as([username, password, "printf", r"'%b\n'", r"'\0101'"]))
