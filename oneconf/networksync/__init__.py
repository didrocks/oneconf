#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2011 Canonical
#
# Authors:
#  Didier Roche
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import gobject
import json
import logging
import os

from infraclient import InfraClient
from netstatus import NetworkStatusWatcher
from ssohandler import LoginBackendDbusSSO

TIME_BEFORE_SYNCING = 60*5+10
TIME_BEFORE_SYNCING = 60

from paths import ONECONF_CACHE_DIR, OTHER_HOST_FILENAME, HOST_DATA_FILENAME, PACKAGE_LIST_FILENAME

LOG = logging.getLogger(__name__)

class SyncHandler(gobject.GObject):
    '''Handle sync request with the server from the dbus service'''

    def __init__(self, hosts, package_handler=None, infraclient=None):
        gobject.GObject.__init__(self)

        self._netstate = NetworkStatusWatcher()
        self._sso_login = LoginBackendDbusSSO()
        self._can_sync = False
        self.credential = None
        self.hosts = hosts
        self.infraclient = infraclient
        self.package_handler = package_handler
        if not self.infraclient:
            self.infraclient = InfraClient()

        self._netstate.connect("changed", self._network_state_changed)
        self._sso_login.connect("login-result", self._sso_login_result)

    def _refresh_can_sync(self):
        '''compute current syncable state before asking for refresh the value'''
        if self.credential is None:
            new_can_sync = False
        else:
            new_can_sync = self._netstate.connected

        if self._can_sync == new_can_sync:
            return
        self._can_sync = new_can_sync

        if self._can_sync:
            self._process_sync()

    def _sso_login_result(self, sso_login, credential):
        self.credential = credential
        self._refresh_can_sync()

    def _network_state_changed(self, netstate, connected):
        if connected:
            # refresh credential as we are interested (this will call _compute_can_sync)
            self._sso_login.get_credential()
        else:
            self._refresh_can_sync()

    def _save_local_file_update(self, file_uri, content):
        '''Save local file in an atomatic transaction'''
        
        LOG.debug("Saving updated %s to disk", file_uri)
        new_file = file_uri + '.new'
    
        try:
            with open(new_file, 'w') as f:
                json.dump(content, f)
            os.rename(new_file, file_uri)
            return True
        except IOError:
            LOG.error("Can't save update file for %s", self._url_to_file(url))
            return False
            
    def _get_local_file_etag(self, uri):
        '''Get local file etag from an uri'''
        try:
            with open(uri, 'r') as f:
                return json.load(f)['ETag']
        except IOError:
            LOG.debug("No file found for %s", uri)
            return None
            
    def _check_and_sync_from_method(self, getter_method, local_filename, hostid_for_request):
        '''Meta function for request sync from distant infra
        
            return True if an updated processed, False otherwise'''

        LOG.debug("Look for refresh %s", local_filename)

        distant_etag = getter_method(hostid_for_request, only_etag=True)
        if distant_etag != self._get_local_file_etag(local_filename):
            if self._save_local_file_update(local_filename, getter_method(hostid_for_request)):
                return True
        return False
            
 
    def _process_sync(self):
        '''start syncing what's needed if can sync'''

        # if no more connection, don't try syncing in the main loop
        if not self._can_sync:
            return False
        LOG.debug("Start processing sync")

        current_hostid = self.hosts.current_host['hostid']
        infra = self.infraclient

        # other hosts list
        other_host_filename = os.path.join(ONECONF_CACHE_DIR, current_hostid, OTHER_HOST_FILENAME)
        if self._check_and_sync_from_method(infra.get_other_hosts, other_host_filename, current_hostid):
            self.hosts.update_other_hosts()
            # TODO: dbus signal for 'hosts_changed'

        # now refresh package list for every hosts (creating directory if needed)
        for hostid in self.hosts.other_hosts:
            other_host_dir = os.path.join(ONECONF_CACHE_DIR, hostid)
            if not os.path.isdir(other_host_dir):
                os.mkdir(other_host_dir)
            packagelist_filename = os.path.join(other_host_dir, PACKAGE_LIST_FILENAME)
            if self._check_and_sync_from_method(infra.get_packages_for_host, packagelist_filename, hostid):
                # if already loaded, unload the package cache
                if package_handler:
                    try:
                        package_handler.package_list[hostid]['valid'] = False
                    except KeyError:
                        pass
                # TODO: dbus signal for 'package list change, hostid'
            

        # continue syncing in the main loop
        return True
        

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    
    from hosts import Hosts
    from infraclient import MockInfraClient

    sync_handler = SyncHandler(Hosts(), infraclient=MockInfraClient())
    loop = gobject.MainLoop()

    loop.run()
