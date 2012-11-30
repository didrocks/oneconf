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

import json
import os
import shutil
import sys
import subprocess
import unittest

from gettext import gettext as _

sys.path.insert(0, os.path.abspath('.'))

# XXX This seriously makes me cry, but because of the way paths.py does its
# thing, and the order dependencies, it's hard to fix without a big rewrite.
shutil.copy(
    os.path.join(os.path.dirname(__file__), "data", "oneconf.override"),
    "/tmp/oneconf.override")

from oneconf import paths
from oneconf.hosts import HostError
from oneconf.directconnect import DirectConnect

class IntegrationTests(unittest.TestCase):

    def setUp(self):
        self.dbus_service_process = None
        self.hostid = "0000"
        self.hostname = "foomachine"
        os.environ["ONECONF_HOST"] = "%s:%s" % (self.hostid, self.hostname)
        self.oneconf = DirectConnect()
        self.hostdir = os.path.join(paths.ONECONF_CACHE_DIR, self.hostid)
        src = os.path.join(os.path.dirname(__file__), "data", "hostdata")
        shutil.copytree(src, self.hostdir)
        self.src_hostdir = None

    def tearDown(self):
        shutil.rmtree(os.path.dirname(paths.ONECONF_CACHE_DIR))

    def is_same_logo_than_original(self):
        src_content = open(os.path.join(os.path.dirname(__file__), "data", "hostdata", "%s_%s.png" % (paths.LOGO_PREFIX, self.hostid))).readlines()
        dest_content = open(os.path.join(paths.ONECONF_CACHE_DIR, self.hostid, "%s_%s.png" % (paths.LOGO_PREFIX, self.hostid))).readlines()
        return (src_content == dest_content)

    def copy_state(self, test_ident):
        '''Set state from the test identifier.'''
        datadir = os.path.join(os.path.dirname(__file__), "data", "integrationdatatests")
        self.src_hostdir = os.path.join(datadir, 'host_%s' % test_ident)
        self.result_hostdir = os.path.join(datadir, 'resulthost_%s' % test_ident)
        shutil.rmtree(os.path.dirname(paths.ONECONF_CACHE_DIR))
        shutil.copytree(self.src_hostdir, self.hostdir)

    def test_load_host_data(self):
        """Load existing hosts data, check that nothing change for current
        host as well
        """
        hosts = self.oneconf.get_all_hosts()
        self.assertEqual(hosts, {
            u'AAAAAA': (False, u'julie-laptop', True),
            u'BBBBBB': (False, u'yuna', True),
            '0000': (True, 'foomachine', True),
            })
        # check that nothing changed
        host_file = os.path.join(paths.ONECONF_CACHE_DIR,
                                 self.hostid, paths.HOST_DATA_FILENAME)
        with open(host_file, 'r') as f:
            current_host = json.load(f)
        self.assertEqual(current_host['hostid'], self.hostid)
        self.assertEqual(current_host['hostname'], self.hostname)
        self.assertEqual(
            current_host['packages_checksum'],
            "9c0d4e619c445551541af522b39ab483ba943b8b298fb96ccc3acd0b")
        self.assertEqual(current_host['share_inventory'], True)
        # XXX PIL is not available for Python 3, so there will be no
        # logo_checksum.
        ## self.assertEqual(
        ##     current_host['logo_checksum'],
        ##     'c7e18f80419ea665772fef10e347f244d5ba596cc2764a8e611603060000000000.000042')
        ## self.assertTrue(self.is_same_logo_than_original())

    def test_create_new_host(self):
        '''Creating a new host, for oneconf first run'''
        shutil.rmtree(os.path.dirname(paths.ONECONF_CACHE_DIR))
        self.oneconf.get_all_hosts()
        host_file = os.path.join(
            paths.ONECONF_CACHE_DIR, self.hostid, paths.HOST_DATA_FILENAME)
        with open(host_file, 'r') as f:
            current_host = json.load(f)
        self.assertEqual(current_host['hostid'], self.hostid)
        self.assertEqual(current_host['hostname'], self.hostname)
        self.assertEqual(current_host['packages_checksum'], None)
        self.assertEqual(current_host['share_inventory'], False)
        # XXX PIL is not available for Python 3, so there will be no
        # logo_checksum.
        ## self.assertEqual(
        ##     current_host['logo_checksum'],
        ##     'c7e18f80419ea665772fef10e347f244d5ba596cc2764a8e611603060000000000.000042')
        ## self.assertTrue(self.is_same_logo_than_original())

    def test_update_host(self):
        '''Update an existing hostid and hostname, checking that the "host" file is changed'''
        self.oneconf.update()
        host_file = os.path.join(paths.ONECONF_CACHE_DIR, self.hostid, paths.HOST_DATA_FILENAME)
        with open(host_file, 'r') as f:
            current_host = json.load(f)
        self.assertEqual(current_host['hostid'], self.hostid)
        self.assertEqual(current_host['hostname'], self.hostname)
        self.assertEqual(current_host["packages_checksum"], "60f28c520e53c65cc37e9b68fe61911fb9f73ef910e08e988cb8ad52")
        self.assertEqual(current_host["share_inventory"], True)
        # XXX PIL is not available for Python 3, so there will be no
        # logo_checksum.
        ## self.assertEqual(current_host['logo_checksum'], 'c7e18f80419ea665772fef10e347f244d5ba596cc2764a8e611603060000000000.000042')
        ## self.assertTrue(self.is_same_logo_than_original())

    def test_diff_host(self):
        """Create a diff between current host and AAAAA. This handle the case
        with auto and manual packages
        """
        self.assertEqual(self.oneconf.diff('AAAAAA', None),
                         ([u'libqtdee2', u'ttf-lao'], [u'bar', u'baz']))

    def test_diff_with_no_valid_host(self):
        '''Test with no valid host'''
        from oneconf.packagesethandler import PackageSetHandler
        self.assertRaises(HostError, PackageSetHandler().diff, 'A')

    def test_with_only_localhost(self):
        '''List machine with only localhost'''
        shutil.rmtree(os.path.dirname(paths.ONECONF_CACHE_DIR))
        self.oneconf.update()
        self.assertEqual(len(self.oneconf.get_all_hosts()), 1)

    def test_list_packages(self):
        '''List packages for machine with default options'''
        self.assertEqual(self.oneconf.get_packages(self.hostid, None, False), {u'baz': {u'auto': False}, u'foo': {u'auto': False}, u'bar': {u'auto': True}})

    def test_list_packages_manual_only(self):
        '''List packages for machine for only manual package'''
        # FIXME: the result is not in the same format, that sux…
        self.assertEqual(
            sorted(self.oneconf.get_packages(self.hostid, None, True)),
            [u'baz', u'foo'])

    def test_list_invalid_machine(self):
        '''List packages for an invalid machine'''
        from oneconf.packagesethandler import PackageSetHandler
        self.assertRaises(HostError, PackageSetHandler().get_packages, 'A')

    def test_list_machine_by_hostname(self):
        '''List packages for machine using hostname'''
        list_pkg1 = self.oneconf.get_packages(self.hostid, None, False)
        list_pkg2 = self.oneconf.get_packages(None, self.hostname, False)
        self.assertEqual(list_pkg1, list_pkg2)

    def test_diff_between_me_and_me(self):
        '''Diff between the same computer which should end up in an empty list'''
        self.assertEqual(self.oneconf.diff(self.hostid, None), ('', ''))

    def test_disable_enable_inventory_for_current_host(self):
        '''Try to disable and the inventory for 0000 host (current host)'''
        hosts = self.oneconf.get_all_hosts()
        self.assertEqual(hosts, {u'AAAAAA': (False, u'julie-laptop', True), u'BBBBBB': (False, u'yuna', True), '0000': (True, 'foomachine', True)})
        self.oneconf.set_share_inventory(False, '0000')
        hosts = self.oneconf.get_all_hosts()
        self.assertEqual(hosts, {u'AAAAAA': (False, u'julie-laptop', True), u'BBBBBB': (False, u'yuna', True), '0000': (True, 'foomachine', False)})
        # software-center does it without using the hostid
        self.oneconf.set_share_inventory(True, '')
        hosts = self.oneconf.get_all_hosts()
        self.assertEqual(hosts, {u'AAAAAA': (False, u'julie-laptop', True), u'BBBBBB': (False, u'yuna', True), '0000': (True, 'foomachine', True)})
        host_file = os.path.join(paths.ONECONF_CACHE_DIR, self.hostid, paths.HOST_DATA_FILENAME)
        with open(host_file, 'r') as f:
            current_host = json.load(f)
        self.assertEqual(current_host['share_inventory'], True)
        self.assertFalse(os.path.isfile(os.path.join(paths.ONECONF_CACHE_DIR, self.hostid, paths.PENDING_UPLOAD_FILENAME)))

    def test_disable_enable_inventory_for_other_host(self):
        '''Try to disable the current inventory for another host (put the request in pending) and then enable it again'''
        hosts = self.oneconf.get_all_hosts()
        self.assertEqual(hosts, {u'AAAAAA': (False, u'julie-laptop', True), u'BBBBBB': (False, u'yuna', True), '0000': (True, 'foomachine', True)})
        self.oneconf.set_share_inventory(False, 'AAAAAA')
        with open(os.path.join(paths.ONECONF_CACHE_DIR, self.hostid, paths.PENDING_UPLOAD_FILENAME), 'r') as f:
            self.assertEqual(json.load(f), {u'AAAAAA': {u'share_inventory': False}})

    def test_dummy_last_sync_state(self):
        '''Get a dummy last sync state'''
        self.assertEqual(self.oneconf.get_last_sync_date(), '123456789.00')

    def test_bootstrap_without_any_sync(self):
        '''Bootstrap without any sync before'''
        os.remove(os.path.join(paths.ONECONF_CACHE_DIR, self.hostid, paths.LAST_SYNC_DATE_FILENAME))
        self.assertEqual(self.oneconf.get_last_sync_date(), 'Was never synced')

    def test_daemon_query_cant_run_root(self):
        '''Test that the daemon or the querier can't run as root'''
        self.assertEqual(subprocess.call(["fakeroot", "./oneconf-query"]), 1)
        self.assertEqual(subprocess.call(["fakeroot", "./oneconf-service"]), 1)

    def test_broken_host_file(self):
        '''Test that we recreate a new host file if the file is broken'''
        self.copy_state('brokenhostfile')
        self.assertEqual(self.oneconf.get_all_hosts(), {self.hostid: (True, self.hostname, False)})
        host_file = os.path.join(paths.ONECONF_CACHE_DIR, self.hostid, paths.HOST_DATA_FILENAME)
        with open(host_file, 'r') as f:
            current_host = json.load(f)
        self.assertEqual(current_host['hostid'], self.hostid)
        self.assertEqual(current_host['hostname'], self.hostname)
        self.assertEqual(current_host['packages_checksum'], None)
        self.assertEqual(current_host['share_inventory'], False)

    def test_broken_otherhosts_file(self):
        '''Test that we discare the other hosts file if the file is broken (a future sync will rewrite it)'''
        self.copy_state('brokenotherhosts')
        from oneconf.hosts import Hosts
        host = Hosts()
        self.assertEqual(host._load_other_hosts(), {})

    def test_broken_pending_file(self):
        '''Test that we discare the other hosts file if the file is broken (a future sync will rewrite it)'''
        self.copy_state('brokenpending')
        from oneconf.hosts import Hosts
        host = Hosts()
        self.assertEqual(host.get_hostid_pending_change('foo', 'bar'), None)
        host.add_hostid_pending_change({'foo': {'bar': 'baz'}})
        self.assertEqual(host.get_hostid_pending_change('foo', 'bar'), 'baz')

    def test_broken_latestsync_file(self):
        '''Test that we return a dummy latest sync date if we can't load it. Next update will rewrite it'''
        self.copy_state('brokenlatestsync')
        from oneconf.hosts import Hosts
        host = Hosts()
        self.assertEqual(host.get_last_sync_date(), _("Was never synced"))

    def test_broken_packageset_file(self):
        """Test that we discare the other hosts file if the file is broken (a
        future sync will rewrite it)
        """
        self.copy_state('brokenpackageset')
        from oneconf.packagesethandler import PackageSetHandler
        packageset = PackageSetHandler()
        self.assertEqual(
            packageset._get_packagelist_from_store(self.hostid),
            {'foo': {'auto': False}, 'pool': {'auto': True}})
        self.assertEqual(
            packageset.hosts.current_host['packages_checksum'],
            '60f28c520e53c65cc37e9b68fe61911fb9f73ef910e08e988cb8ad52')

    # TODO: ensure a logo is updated

#
# main
#
if __name__ == '__main__':
    print('''
    #########################################
    #          Main OneConf tests           #
    #########################################
    ''')
    unittest.main(exit=False)
    os.remove("/tmp/oneconf.override")
