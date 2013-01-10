#!/usr/bin/env python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (C) 2011 Didier Roche <didrocks@ubuntu.com>
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE

import atexit
import errno
import os
import shutil
import sys
import subprocess
import time
import unittest

sys.path.insert(0, os.path.abspath('.'))

# Create the override file, but ensure that it gets cleaned up when this test
# exits.  Because of the way oneconf.paths operates, this file must exist
# before the import.
def cleanup():
    try:
        os.remove('/tmp/oneconf.override')
    except OSError as error:
        if error.errno != errno.ENOENT:
            raise
    try:
        shutil.rmtree('/tmp/oneconf-test')
    except OSError as error:
        if error.errno != errno.ENOENT:
            raise
atexit.register(cleanup)
shutil.copy(
    os.path.join(os.path.dirname(__file__), "data", "oneconf.override"),
    '/tmp/oneconf.override')

from oneconf import paths
from oneconf.enums import MIN_TIME_WITHOUT_ACTIVITY

class DaemonTests(unittest.TestCase):

    def setUp(self):
        self.dbus_service_process = None
        self.hostid = "0000"
        self.hostname = "foomachine"
        os.environ["ONECONF_HOST"] = "%s:%s" % (self.hostid, self.hostname)
        self.dbus_service_process = subprocess.Popen(
            ["./oneconf-service", '--debug', '--mock'])
        self.time_start = time.time()
        time.sleep(1) # let the main daemon starting

    def tearDown(self):
        '''Kill the dbus service if there, and clean things'''

        if self.dbus_service_process:
            self.dbus_service_process.terminate()
            self.dbus_service_process.wait()
        try:
            shutil.rmtree(os.path.dirname(paths.ONECONF_CACHE_DIR))
        except OSError:
            pass

    def daemon_still_there(self, pid=None):
        '''Return True if the daemon is still running'''
        if not pid and self.dbus_service_process:
            pid = self.dbus_service_process.pid
        if pid:
            for line in os.popen("ps xa"):
                fields = line.split()
                if (str(pid) == fields[0]):
                    return True
        return False

    def test_daemon_stop(self):
        '''Test that the daemon effectively stops when requested'''
        self.assertTrue(self.daemon_still_there())
        subprocess.Popen(["./oneconf-query", "--stop"])
        self.dbus_service_process.wait() # let it proceeding quitting
        time_stop = time.time()
        self.assertFalse(self.daemon_still_there())
        self.assertTrue(time_stop - self.time_start < MIN_TIME_WITHOUT_ACTIVITY)
        self.dbus_service_process = None

    def test_unique_daemon(self):
        '''Try to spaw a second daemon and check it can't be there'''
        try:
            close = False
            try:
                devnull = subprocess.DEVNULL
            except AttributeError:
                # Python 2
                devnull = open(os.devnull, 'wb')
                close = True
            daemon2 = subprocess.Popen(["./oneconf-service"],
                                       stdout=devnull, stderr=devnull)
            daemon2.wait() # let it proceeding quitting
            time_stop = time.time()
            self.assertFalse(self.daemon_still_there(daemon2.pid))
            self.assertTrue(
                time_stop - self.time_start < MIN_TIME_WITHOUT_ACTIVITY)
        finally:
            if close:
                devnull.close()

    def test_daemon_stop_after_timeout(self):
        '''Test that the daemon effectively stops after a timeout'''
        self.assertTrue(self.daemon_still_there())
        self.dbus_service_process.wait() # let it proceeding quitting
        time_stop = time.time()
        self.assertFalse(self.daemon_still_there())
        self.assertTrue(time_stop - self.time_start > MIN_TIME_WITHOUT_ACTIVITY)
        self.dbus_service_process = None

    def test_daemon_keep_alive_if_activity(self):
        '''Test that the daemon is kept alive if you have activity'''
        self.assertTrue(self.daemon_still_there())
        subprocess.Popen(["./oneconf-query", '--host'])
        time.sleep(MIN_TIME_WITHOUT_ACTIVITY + 2)
        subprocess.Popen(["./oneconf-query", '--host'])
        self.dbus_service_process.wait() # let it proceeding quitting
        time_stop = time.time()
        self.assertFalse(self.daemon_still_there())
        self.assertTrue(time_stop - self.time_start > 2*MIN_TIME_WITHOUT_ACTIVITY)
        self.dbus_service_process = None

    def test_no_daemon_crash_if_invalid_setup(self):
        '''Test that the daemon doesn't crash in case of invalid setup'''
        shutil.copy(os.path.join(os.path.dirname(__file__), "data", "oneconf.invaliddistro.override"), "/tmp/oneconf.override")
        self.assertTrue(self.daemon_still_there())
        self.dbus_service_process.terminate()
        self.dbus_service_process.wait() # let the existing daemon quitting
        self.assertFalse(self.daemon_still_there())
        self.dbus_service_process = None
        self.dbus_service_process = subprocess.Popen(["./oneconf-service", '--debug', '--mock'])
        self.assertTrue(self.daemon_still_there())
        from oneconf import dbusconnect
        oneconf = dbusconnect.DbusConnect()
        oneconf.get_packages(self.hostid, '', False)
        oneconf.update()
        # try to wait for it syncing (for additional invalid data loading)
        for i in range(5):
          oneconf.get_all_hosts()
          time.sleep(MIN_TIME_WITHOUT_ACTIVITY)
        subprocess.Popen(["./oneconf-query", "--stop"])

#
# main
#
if __name__ == '__main__':
    print('''
    #########################################
    #       Use the OneConf service         #
    #########################################
    ''')
    unittest.main(exit=False)
    os.remove("/tmp/oneconf.override")
