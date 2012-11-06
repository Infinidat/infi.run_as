from unittest import TestCase, SkipTest
from mock import patch
from os import name, environ

class RunAsTestCase(TestCase):
    def test__on_unix_with_mock(self):
        if name == 'nt':
            raise SkipTest("unix only")
        with patch("infi.run_as.subprocess_runas_context"):
            from infi.run_as import run_as
            self.assertEquals(0, run_as(["Administrator", "Password", "ifconfig"]))

    def test__on_windows(self):
        from infi.run_as import run_as
        if name != 'nt':
            raise SkipTest("windows only")
        username, password = environ['RUNAS_USERNAME'], environ['RUNAS_PASSWORD']
        self.assertEquals(0, run_as([username, password, "ipconfig"]))
