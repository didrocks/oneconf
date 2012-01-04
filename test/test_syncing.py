#!/usr/bin/python
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

import json
import os
import shutil
import sys
import subprocess
import time
import unittest

sys.path.insert(0, os.path.abspath('.'))

shutil.copy(os.path.join(os.path.dirname(__file__), "data", "oneconf.override"), "/tmp/oneconf.override")
from oneconf import paths
from oneconf.networksync.fake_webcatalog_silo import FakeWebCatalogSilo

class OneConfSyncing(unittest.TestCase):

    def setUp(self):
        self.cmd_line = ["python", "oneconf/networksync/__init__.py"]
        self.hostid = "0000"
        self.hostname = "foomachine"
        self.output = None
        os.environ["ONECONF_HOST"] = "%s:%s" % (self.hostid, self.hostname)
        os.environ["ONECONF_NET_CONNECTED"] = "True"
        os.environ["ONECONF_SSO_CRED"] = "True"
        self.hostdir = os.path.join(paths.ONECONF_CACHE_DIR, self.hostid)
        self.src_hostdir = None

    def tearDown(self):
        try:
            shutil.rmtree(os.path.dirname(paths.ONECONF_CACHE_DIR))
            pass
        except OSError:
            pass

    def collect_debug_output(self, process):
        '''Get the full stderr output from a process'''
        output = []
        while True:
            additional_output = process.stderr.readline()
            print additional_output
            if not additional_output:
                break
            output.append(additional_output)
        return output

    def msg_in_output(self, output, msg):
        found = False
        for line in output:
            found = found or msg in line
        return found

    def get_daemon_output(self):
        '''Return the daemon output and ensure it's stopped'''
        p = subprocess.Popen(self.cmd_line, stderr=subprocess.PIPE)      
        output = self.collect_debug_output(p)
        p.wait()
        p = None
        return output

    def check_msg_in_output(self, msg):
        '''launch the subprocess and check if the msg is present in the output'''
        if not self.output:
            self.output = self.get_daemon_output()
        # ensure there is no traceback or error
        self.assertFalse(self.msg_in_output(self.output, 'Traceback'))
        self.assertFalse(self.msg_in_output(self.output, 'ERROR:'))
        return (self.msg_in_output(self.output, msg))

    def copy_state(self, test_ident):
        '''Set state from the test identifier.'''
        datadir = os.path.join(os.path.dirname(__file__), "data", "syncdatatests")
        self.src_hostdir = os.path.join(datadir, 'host_%s' % test_ident)
        shutil.copytree(self.src_hostdir, self.hostdir)
        if not os.path.isdir(paths.WEBCATALOG_SILO_DIR):
            os.makedirs(paths.WEBCATALOG_SILO_DIR)
        try:
            shutil.copy(os.path.join(datadir, 'silo_%s' % test_ident), paths.WEBCATALOG_SILO_SOURCE)
        except IOError:
            pass # some tests have no silo source file

    def compare_silo_results(self, hosts_medata, packages_metadata):
        '''Return True if start and result silos contains identical hosts and pkg'''
        fakecatalog = FakeWebCatalogSilo(paths.WEBCATALOG_SILO_RESULT)
        self.assertEqual(fakecatalog._FAKE_SETTINGS['hosts_metadata'], hosts_medata)
        self.assertEqual(fakecatalog._FAKE_SETTINGS['packages_metadata'], packages_metadata)

    def compare_dirs(self, source, dest):
        '''Compare directory files, ignoring the last_sync file on purpose'''
        for filename in os.listdir(source):
            if filename == paths.LAST_SYNC_DATE_FILENAME:
                continue
            src_content = open(os.path.join(source, filename)).readlines()
            dest_content = open(os.path.join(dest, filename)).readlines()
            self.assertEqual(src_content, dest_content)

    def test_no_sync_no_network(self):
        '''Test that no sync is happening if no network'''
        os.environ["ONECONF_NET_CONNECTED"] = "False"
        self.assertFalse(self.check_msg_in_output("Start processing sync"))

    def test_no_sync_no_sso(self):
        '''Test that no sync is happening if no sso'''
        os.environ["ONECONF_SSO_CRED"] = "False"
        self.assertFalse(self.check_msg_in_output("Start processing sync"))

    def test_sync_with_network_and_sso(self):
        '''Test that a sync is there if we have network and sso enabled'''
        self.assertTrue(self.check_msg_in_output("Start processing sync"))

    def test_first_sync(self):
        '''Test a first synchronisation without any data on the webcatalog'''
        self.copy_state('nosilo_nopackage_onlyhost')
        self.assertTrue(self.check_msg_in_output("Push current host to infra now"))
        self.assertTrue(self.check_msg_in_output("New host registered done"))
        self.assertFalse(self.check_msg_in_output("emit_new_hostlist"))
        self.assertFalse(self.check_msg_in_output("emit_new_packagelist"))
        self.assertFalse(self.check_msg_in_output("emit_new_logo"))
        self.compare_silo_results({self.hostid: {'hostname': self.hostname,
                                                 'logo_checksum': None,
                                                 'packages_checksum': None}},
                                  {})
        self.compare_dirs(self.src_hostdir, self.hostdir) # Ensure nothing changed in the source dir

    def test_date_synchro(self):
        '''Ensure a synchro date is written, older than current time, and right signal emitted'''
        self.copy_state('nosilo_nopackage_onlyhost')
        now = time.time()
        sync_file = os.path.join(self.hostdir, paths.LAST_SYNC_DATE_FILENAME)
        self.assertTrue(self.check_msg_in_output("Saving updated %s to disk" % sync_file))
        self.assertTrue(self.check_msg_in_output("emit_new_lastestsync"))
        with open(sync_file, 'r') as f:
            current_host = self.assertTrue(json.load(f)["last_sync"] > now)

    def test_host_not_shared(self):
        '''Test a non shared host is really not shared'''
        self.copy_state('nosilo_nopackage_onlyhost_noshare')
        self.assertFalse(self.check_msg_in_output("Push current host to infra now"))
        self.assertFalse(self.check_msg_in_output("New host registered done"))
        self.assertTrue(self.check_msg_in_output("Ensure that current host is not shared"))
        self.compare_silo_results({}, {})
        self.compare_dirs(self.src_hostdir, self.hostdir) # Ensure nothing changed in the source dir        

    def test_unshare_shared_host(self):
        '''Share a host, and then unshare it. Check that everything is cleaned in the shilo'''
        self.copy_state('previously_shared_notshared')
        self.assertTrue(self.check_msg_in_output("Ensure that current host is not shared"))
        self.compare_silo_results({}, {})

    def test_share_host_with_packages(self):
        '''Share the current host with a package list'''
        self.copy_state('with_packages')
        self.assertTrue(self.check_msg_in_output("Check if packages for current host need to be pushed to infra"))
        self.assertTrue(self.check_msg_in_output("Push new packages"))
        self.assertTrue(self.check_msg_in_output("refresh done"))
        self.compare_silo_results({self.hostid: {'hostname': self.hostname,
                                                 'logo_checksum': None,
                                                 'packages_checksum': u'9c0d4e619c445551541af522b39ab483ba943b8b298fb96ccc3acd0b'}},
                                  {self.hostid: {u'bar': {u'auto': True},
                                                 u'baz': {u'auto': False},
                                                 u'foo': {u'auto': False}}})
        self.compare_dirs(self.src_hostdir, self.hostdir) # Ensure nothing changed in the source dir

    def test_unshare_host_with_packages(self):
        '''Unshare an existing host with packages'''
        self.copy_state('previously_shared_with_packages_notshared')
        self.assertTrue(self.check_msg_in_output("Ensure that current host is not shared"))
        self.compare_silo_results({}, {})

    def test_update_host_no_change(self):
        '''Update a host without any change'''
        self.copy_state('update_current_host')
        self.assertTrue(self.check_msg_in_output("Check if packages for current host need to be pushed to infra"))
        self.assertFalse(self.check_msg_in_output("Push new"))
        self.assertFalse(self.check_msg_in_output("refresh done"))
        # No silo result has nothing changed
        self.assertFalse(os.path.exists(paths.WEBCATALOG_SILO_RESULT))
        

    def test_update_host_with_hostname_change(self):
        '''Update a host only changing the hostname'''
        self.hostname = "barmachine"
        os.environ["ONECONF_HOST"] = "%s:%s" % (self.hostid, self.hostname)
        self.copy_state('update_current_hostname')
        self.assertTrue(self.check_msg_in_output("Host data refreshed"))
        self.assertFalse(self.check_msg_in_output("Push new"))
        self.assertFalse(self.check_msg_in_output("refresh done"))
        self.compare_silo_results({self.hostid: {'hostname': self.hostname,
                                                 'logo_checksum': None,
                                                 'packages_checksum': u'9c0d4e619c445551541af522b39ab483ba943b8b298fb96ccc3acd0b'}},
                                  {self.hostid: {u'bar': {u'auto': True},
                                                 u'baz': {u'auto': False},
                                                 u'foo': {u'auto': False}}})

    def test_update_packages_for_host(self):
        '''Update a package list for current host'''
        self.copy_state('update_packages_for_current_host')
        self.assertTrue(self.check_msg_in_output("Check if packages for current host need to be pushed to infra"))
        self.assertTrue(self.check_msg_in_output("Push new packages"))
        self.assertTrue(self.check_msg_in_output("refresh done"))
        self.compare_silo_results({self.hostid: {'hostname': self.hostname,
                                                 'logo_checksum': None,
                                                 'packages_checksum': u'AAAA'}},
                                  {self.hostid: {u'fol': {u'auto': False},
                                                 u'bar': {u'auto': True},
                                                 u'baz': {u'auto': True}}})

    def test_get_firsttime_other_host(self):
        '''First time getting another host, no package'''
        

    # TODO: unshare host which is not hostid
    #       other update a package list
    #       other with a host removed
    #       other with an additional host
    #       other with a host with some packages
    

    # TODO: cache interaction for sync and pkg list, host list

#
# main
#
if __name__ == '__main__':
    print '''
    #########################################
    #         Test OneConf syncing          #
    #########################################
    '''
    unittest.main(exit=False)
    os.remove("/tmp/oneconf.override")
