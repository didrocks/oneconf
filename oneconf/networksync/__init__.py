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

from paths import ONECONF_CACHE_DIR, OTHER_HOST_FILENAME, HOST_DATA_FILENAME, PACKAGE_LIST_FILENAME

LOG = logging.getLogger(__name__)

class SyncHandler(gobject.GObject):
    '''Handle sync request with the server from the dbus service'''

    def __init__(self, hosts, package_handler=None, infraclient=None, dbusemitter=None):
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
        
        if dbusemitter:
            self.emit_new_hostlist = dbusemitter.hostlist_changed
            self.emit_new_packagelist = dbusemitter.packagelist_changed

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
            self.process_sync()

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
        except (TypeError, ValueError), e:
            LOG.warning("Invalid local file of %s: %s" % (uri, e))
            return None

    def _filename_to_requestid(self, filename):
        '''sprint a filename to an requestid for infra'''
        return '/'.join(filename.split(os.path.sep)[-2:])
            
    def _check_and_sync(self, local_filename):
        '''Meta function for request sync from distant infra
        
            return True if an sync processed, False otherwise'''

        requestid = self._filename_to_requestid(local_filename)
        LOG.debug("Check for refreshing %s from infra" % requestid)
        try:
            distant_etag = self.infraclient.get_content(requestid, only_etag=True)
            if distant_etag != self._get_local_file_etag(local_filename):
                if self._save_local_file_update(local_filename, self.infraclient.get_content(requestid)):
                    LOG.debug("%s refreshed" % local_filename)
                    return True
        except ValueError, e:
            LOG.warning("Got a ValueError while getting content related to %s: %s" % (requestid, e))
        return False

    def _check_and_push(self, local_filename):
        '''Meta function for request upload to distant infra'''

        requestid = self._filename_to_requestid(local_filename)
        LOG.debug("Check for uploading %s to infra" % requestid)

        try:
            distant_etag = self.infraclient.get_content(requestid, only_etag=True)
            if distant_etag != self._get_local_file_etag(local_filename):
                with open(local_filename, 'r') as f:
                    self.infraclient.upload_content(requestid, json.load(f))
                    LOG.debug("infra refreshed from %s" % local_filename)
        except ValueError, e:
            LOG.warning("Got a ValueError while getting content related to %s: %s" % (requestid, e))
            
    def emit_new_hostlist(self):
        '''this signal will be bound at init time'''
        LOG.warning("emit_new_hostlist not bound to anything")
        
    def emit_new_packagelist(self, hostid):
        '''this signal will be bound at init time'''
        

    def process_sync(self):
        '''start syncing what's needed if can sync
        
        process sync can be either started directly, or when can_sync changed'''

        # if no more connection, don't try syncing in the main loop
        if not self._can_sync:
            return False
        LOG.debug("Start processing sync")

        current_hostid = self.hosts.current_host['hostid']
        hostlist_changed = None
        packagelist_changed = []

        # other hosts list
        other_host_filename = os.path.join(ONECONF_CACHE_DIR, current_hostid, OTHER_HOST_FILENAME)
        if self._check_and_sync(other_host_filename):
            self.hosts.update_other_hosts()
            hostlist_changed = True

        # now refresh package list for every hosts (creating directory if needed)
        for hostid in self.hosts.other_hosts:
            other_host_dir = os.path.join(ONECONF_CACHE_DIR, hostid)
            if not os.path.isdir(other_host_dir):
                os.mkdir(other_host_dir)
            packagelist_filename = os.path.join(other_host_dir, PACKAGE_LIST_FILENAME)
            if self._check_and_sync(packagelist_filename):
                # if already loaded, unload the package cache
                if self.package_handler:
                    try:
                       self.package_handler.package_list[hostid]['valid'] = False
                    except KeyError:
                        pass
                packagelist_changed.append(hostid)

        # now push current host
        if self.hosts.current_host['share_inventory']:
            current_host_filename = os.path.join(ONECONF_CACHE_DIR, current_hostid, HOST_DATA_FILENAME)
            self._check_and_push(current_host_filename)
            
            # and last but not least, local package list
            local_packagelist_filename = os.path.join(ONECONF_CACHE_DIR, current_hostid, PACKAGE_LIST_FILENAME)
            self._check_and_push(local_packagelist_filename)
        else:
            LOG.debug("This hostid doesn't allow to share its inventory, no push to infra")


        # send dbus signal if needed events (just now so that we don't block on remaining operations)
        if hostlist_changed:
            self.emit_new_hostlist()
        for hostid in packagelist_changed:
            self.emit_new_packagelist(hostid)

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
