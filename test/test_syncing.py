#!/usr/bin/python3
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
        os.environ['PYTHONPATH'] = '.:' + os.environ.get('PYTHONPATH', '')
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
        for key in os.environ.keys():
            if "ONECONF_" in key:
                os.environ.pop(key)
        try:
            shutil.rmtree(os.path.dirname(paths.ONECONF_CACHE_DIR))
        except OSError:
            pass

    def collect_debug_output(self, process):
        '''Get the full stderr output from a process'''
        output = []
        while True:
            additional_output = process.stderr.readline()
            print(additional_output)
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

    def check_msg_in_output(self, msg, check_errors=True):
        '''launch the subprocess and check if the msg is present in the output'''
        if not self.output:
            self.output = self.get_daemon_output()
        # ensure there is no traceback or error
        self.assertFalse(self.msg_in_output(self.output, 'Traceback'))
        if check_errors:
            self.assertFalse(self.msg_in_output(self.output, 'ERROR:'))
        return (self.msg_in_output(self.output, msg))

    def copy_state(self, test_ident):
        '''Set state from the test identifier.'''
        datadir = os.path.join(os.path.dirname(__file__), "data", "syncdatatests")
        self.src_hostdir = os.path.join(datadir, 'host_%s' % test_ident)
        self.result_hostdir = os.path.join(datadir, 'resulthost_%s' % test_ident)
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

    def compare_files(self, file1, file2):
        '''Compare file content'''
        src_content = open(file1).read().splitlines()
        dest_content = open(file2).read().splitlines()
        self.assertEqual(src_content, dest_content)

    def compare_dirs(self, source, dest):
        '''Compare directory files, ignoring the last_sync file on purpose'''
        for filename in os.listdir(source):
            if filename == paths.LAST_SYNC_DATE_FILENAME:
                continue
            self.compare_files(os.path.join(source, filename), os.path.join(dest, filename))

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
        '''Share a host, and then unshare it. Check that everything is cleaned in the silo'''
        self.copy_state('previously_shared_notshared')
        self.assertTrue(self.check_msg_in_output("Ensure that current host is not shared"))
        self.assertFalse(self.check_msg_in_output("Can't delete current host from infra: Host Not Found"))
        self.compare_silo_results({}, {})

    def test_share_host_with_packages(self):
        '''Share the current host with a package list'''
        self.copy_state('with_packages')
        self.assertTrue(self.check_msg_in_output("Check if packages for current host need to be pushed to infra"))
        self.assertTrue(self.check_msg_in_output("Push new packages"))
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
        self.assertFalse(self.check_msg_in_output("Can't delete current host from infra: Host Not Found"))
        self.compare_silo_results({}, {})

    def test_unshare_other_host(self):
        '''Unshare a host which is not the current one'''
        self.copy_state('unshare_other_host')
        self.assertTrue(self.check_msg_in_output("Removing machine AAAA requested as a pending change"))
        self.assertTrue(self.check_msg_in_output("No more pending changes remaining, removing the file"))
        self.compare_silo_results({}, {})

    def test_unshare_other_host_error(self):
        '''Unshare a host which is not the current one, raising an exception and keep it to the list of unsharing'''
        self.copy_state('unshare_other_host')
        os.environ["ONECONF_delete_machine_error"] = "True"
        self.assertTrue(self.check_msg_in_output("Removing machine AAAA requested as a pending change", check_errors=False))
        self.assertTrue(self.check_msg_in_output("WebClient server doesn't want to remove hostid (AAAA): Fake WebCatalogAPI raising fake exception", check_errors=False))
        self.assertFalse(self.check_msg_in_output("No more pending changes remaining, removing the file", check_errors=False))
        self.compare_silo_results({'AAAA': {'hostname': 'aaaa',
                                            'logo_checksum': None,
                                            'packages_checksum': 'packageaaaa'}},
                                  {'AAAA': {u'bar': {u'auto': True},
                                             'baz': {u'auto': False},
                                             'foo': {u'auto': False}}})
        self.compare_files(os.path.join(self.src_hostdir, paths.PENDING_UPLOAD_FILENAME), os.path.join(self.hostdir, paths.PENDING_UPLOAD_FILENAME))

    def test_update_host_no_change(self):
        '''Update a host without any change'''
        self.copy_state('only_current_host')
        self.assertTrue(self.check_msg_in_output("Check if packages for current host need to be pushed to infra"))
        self.assertFalse(self.check_msg_in_output("No more pending changes remaining, removing the file"))
        self.assertFalse(self.check_msg_in_output("Push new"))
        self.compare_silo_results({self.hostid: {'hostname': self.hostname,
                                                 'logo_checksum': None,
                                                 'packages_checksum': u'9c0d4e619c445551541af522b39ab483ba943b8b298fb96ccc3acd0b'}},
                                  {u'0000': {u'bar': {u'auto': True},
                                             u'baz': {u'auto': False},
                                             u'foo': {u'auto': False}}})


    def test_update_host_with_hostname_change(self):
        '''Update a host only changing the hostname'''
        self.hostname = "barmachine"
        os.environ["ONECONF_HOST"] = "%s:%s" % (self.hostid, self.hostname)
        self.copy_state('update_current_hostname')
        self.assertTrue(self.check_msg_in_output("Host data refreshed"))
        self.assertFalse(self.check_msg_in_output("Push new"))
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
        self.compare_silo_results({self.hostid: {'hostname': self.hostname,
                                                 'logo_checksum': None,
                                                 'packages_checksum': u'AAAA'}},
                                  {self.hostid: {u'fol': {u'auto': False},
                                                 u'bar': {u'auto': True},
                                                 u'baz': {u'auto': True}}})

    def test_get_firsttime_sync_other_host(self):
        '''First time getting another host, no package'''
        self.copy_state('firsttime_sync_other_host')
        self.assertTrue(self.check_msg_in_output("Refresh new host"))
        self.assertTrue(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/other_hosts to disk"))
        self.assertFalse(self.check_msg_in_output("Refresh new packages"))
        self.assertFalse(self.check_msg_in_output("Refresh new logo"))
        self.assertTrue(self.check_msg_in_output("emit_new_hostlist not bound to anything"))
        self.compare_dirs(self.result_hostdir, self.hostdir)

    def test_sync_other_host_with_packages(self):
        '''Sync another host with packages'''
        self.copy_state('sync_other_host_with_packages')
        self.assertTrue(self.check_msg_in_output("Refresh new packages"))
        self.assertTrue(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/package_list_AAAA to disk"))
        self.assertTrue(self.check_msg_in_output("Refresh new host"))
        self.assertTrue(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/other_hosts to disk"))
        self.assertTrue(self.check_msg_in_output("emit_new_hostlist not bound to anything"))
        self.assertTrue(self.check_msg_in_output("emit_new_packagelist(AAAA) not bound to anything"))
        self.compare_dirs(self.result_hostdir, self.hostdir)

    def test_sync_other_host_with_updated_packages(self):
        '''Sync another host with updated packages'''
        self.copy_state('sync_other_host_with_updated_packages')
        self.assertTrue(self.check_msg_in_output("Refresh new packages"))
        self.assertTrue(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/package_list_AAAA to disk"))
        self.assertTrue(self.check_msg_in_output("Refresh new host"))
        self.assertTrue(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/other_hosts to disk"))
        self.assertTrue(self.check_msg_in_output("emit_new_hostlist not bound to anything"))
        self.assertTrue(self.check_msg_in_output("emit_new_packagelist(AAAA) not bound to anything"))
        self.compare_dirs(self.result_hostdir, self.hostdir)

    def test_sync_other_host_with_updated_hostname(self):
        '''Sync another host with updated hostname'''
        self.copy_state('sync_other_host_with_updated_hostname')
        self.assertFalse(self.check_msg_in_output("Refresh new packages"))
        self.assertTrue(self.check_msg_in_output("Refresh new host"))
        self.assertTrue(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/other_hosts to disk"))
        self.assertTrue(self.check_msg_in_output("emit_new_hostlist not bound to anything"))
        self.compare_dirs(self.result_hostdir, self.hostdir)

    def test_sync_a_newhost_with_already_other_hosts(self):
        '''Add an additional host with some already there'''
        self.copy_state('sync_a_newhost_with_already_other_hosts')
        self.assertTrue(self.check_msg_in_output("Refresh new packages"))
        self.assertFalse(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/package_list_AAAA to disk"))
        self.assertTrue(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/package_list_BBBB to disk"))
        self.assertTrue(self.check_msg_in_output("Refresh new host"))
        self.assertTrue(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/other_hosts to disk"))
        self.assertTrue(self.check_msg_in_output("emit_new_hostlist not bound to anything"))
        self.compare_dirs(self.result_hostdir, self.hostdir)

    def test_sync_remove_other_host(self):
        '''Remove a host after a sync'''
        self.copy_state('sync_remove_other_host')
        self.assertTrue(self.check_msg_in_output("Refresh new host"))
        self.assertTrue(self.check_msg_in_output("Saving updated /tmp/oneconf-test/cache/0000/other_hosts to disk"))
        self.assertTrue(self.check_msg_in_output("emit_new_hostlist not bound to anything"))
        self.assertFalse(self.check_msg_in_output("emit_new_packagelist"))
        self.compare_dirs(self.result_hostdir, self.hostdir)

    def test_server_error(self):
        '''Test server not responsing at all'''
        self.copy_state('fake_server_errors')
        os.environ["ONECONF_server_response_error"] = "True"
        self.assertTrue(self.check_msg_in_output("WebClient server answer error: Fake WebCatalogAPI raising fake exception", check_errors=False))
        self.assertFalse(self.check_msg_in_output("Saving updated", check_errors=False))
        # Untouched silo and source dir
        self.compare_silo_results({self.hostid: {'hostname': 'barmachine',
                                                 'logo_checksum': None,
                                                 'packages_checksum': '9c0d4e619c445551541af522b39ab483ba943b8b298fb96ccc3acd0b'},
                                   'AAAA': {'hostname': 'aaaa',
                                            'logo_checksum': None,
                                            'packages_checksum': 'packageaaaa'},
                                   'BBBB': {'hostname': 'toremove',
                                            'logo_checksum': None,
                                            'packages_checksum': 'toremove'}},
                                  {self.hostid: {'bar': {'auto': True},
                                                 'baz': {'auto': False},
                                                 'foo': {'auto': False}},
                                   'AAAA': {'bar': {'auto': True},
                                            'baz': {'auto': False},
                                            'foo': {'auto': False}},
                                   'BBBB': {u'bar': {u'auto': False}}})
        self.compare_dirs(self.src_hostdir, self.hostdir)

    def test_get_all_machines_error(self):
        '''Test when getting all machines errors, we should stop syncing'''
        self.copy_state('fake_server_errors')
        os.environ["ONECONF_list_machines_error"] = "True"
        self.assertTrue(self.check_msg_in_output("Invalid machine list from server, stopping sync: Fake WebCatalogAPI raising fake exception", check_errors=False))
        # Stop the sync there
        self.assertFalse(self.check_msg_in_output("Saving updated", check_errors=False))

    def test_get_packages_error(self):
        '''Test when getting all packages errors'''
        self.copy_state('fake_server_errors')
        os.environ["ONECONF_list_packages_error"] = "True"
        self.assertTrue(self.check_msg_in_output("Invalid package data from server: Fake WebCatalogAPI raising fake exception", check_errors=False))
        self.assertTrue(self.check_msg_in_output("Saving updated", check_errors=False))

    def test_delete_current_host_error(self):
        '''Try to delete the current host and there is an error'''
        self.copy_state('delete_current_host_error')
        os.environ["ONECONF_delete_machine_error"] = "True"
        self.assertTrue(self.check_msg_in_output("Can't delete current host from infra: Fake WebCatalogAPI raising fake exception", check_errors=False))
        self.assertTrue(self.check_msg_in_output("Saving updated", check_errors=False))

    def test_update_current_host_error(self):
        '''Update an already registered current host and there is an error'''
        self.copy_state('fake_server_errors')
        os.environ["ONECONF_update_machine_error"] = "True"
        self.assertTrue(self.check_msg_in_output("Can't update machine: Fake WebCatalogAPI raising fake exception", check_errors=False))
        self.assertFalse(self.check_msg_in_output("Host data refreshed", check_errors=False))
        self.assertTrue(self.check_msg_in_output("Saving updated", check_errors=False))

    def test_create_current_host_error(self):
        '''Try to create the current host and there is an error'''
        self.copy_state('nosilo_nopackage_onlyhost')
        os.environ["ONECONF_update_machine_error"] = "True"
        self.assertTrue(self.check_msg_in_output("Can't register new host: Fake WebCatalogAPI raising fake exception", check_errors=False))
        self.assertFalse(self.check_msg_in_output("New host registered done", check_errors=False))
        self.assertTrue(self.check_msg_in_output("Saving updated", check_errors=False))

    def test_update_package_list_error(self):
        '''Try to update the remove package list and get an error'''
        self.copy_state('fake_server_errors')
        os.environ["ONECONF_update_packages_error"] = "True"
        self.assertTrue(self.check_msg_in_output("Can't push current package list: Fake WebCatalogAPI raising fake exception", check_errors=False))
        self.assertTrue(self.check_msg_in_output("Saving updated", check_errors=False))

    def test_sync_with_broken_pending_file(self):
        '''Try to update with a broken pending file, should just ignore it'''
        self.copy_state('broken_pending_file')
        self.check_msg_in_output("The pending file is broken, ignoring", check_errors=False)

    def test_no_sync_with_invalid_setup(self):
        '''Test that no sync and no traceback is happening if we have an invalid setup'''
        self.cmd_line = ["python", "oneconf/networksync/__init__.py", "--no-infra-client"]
        shutil.copy(os.path.join(os.path.dirname(__file__), "data", "oneconf.invaliddistro.override"), "/tmp/oneconf.override")
        self.assertFalse(self.check_msg_in_output("Start processing sync"))

#
# main
#
if __name__ == '__main__':
    print('''
    #########################################
    #         Test OneConf syncing          #
    #########################################
    ''')
    unittest.main(exit=False)
    os.remove("/tmp/oneconf.override")
