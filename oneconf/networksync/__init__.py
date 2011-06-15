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
import logging

from netstatus import NetworkStatusWatcher
from ssohandler import LoginBackendDbusSSO

TIME_BEFORE_SYNCING = 60*5+10
TIME_BEFORE_SYNCING = 60

LOG = logging.getLogger(__name__)

class SyncHandler(gobject.GObject):
    '''Handle sync request with the server from the dbus service'''

    __gsignals__ = {'packagelist_changed':(gobject.SIGNAL_RUN_FIRST,
                                           gobject.TYPE_NONE, (str,)),
                    'hostlist_changed':(gobject.SIGNAL_RUN_FIRST,
                                        gobject.TYPE_NONE, ()),
                   }

    def __init__(self):
        gobject.GObject.__init__(self)

        self._netstate = NetworkStatusWatcher()
        self._sso_login = LoginBackendDbusSSO()
        self._can_sync = False
        self.credential = None

        self._netstate.connect("changed", self._network_state_changed)
        self._sso_login.connect("login-result", self._sso_login_result)


    # TODO: both be replaced by a property
    def get_can_sync(self):
        '''simple helper stating if we can sync or not'''
        return self._can_sync

    def _compute_can_sync(self):
        '''compute current syncable state before asking for refresh the value'''
        if self.credential is None:
            new_can_sync = False
        else:
            if self.netstate.is_connected():
                new_can_sync = True
            else:
                new_can_sync = False
        # this is to avoid transient state when we turn wifi on and nm tell "is connected" by default until checking
        gobject.timeout_add_seconds(1, self._refresh_can_sync, new_can_sync)

    def _sso_login_result(self, sso_login, credential):
        self.credential = credential
        self._compute_can_sync()

    def _network_state_changed(self, netstate, connected):
        if connected:
            # refresh credential as we are interested (this will call _compute_can_sync)
            self._sso_login.get_credential()
        else:
            self._compute_can_sync()

    def _refresh_can_sync(self, new_can_sync):
        '''check if the state changed since last syncing process

        This is to avoid some transient state with nm flickering between connected and not connected'''
        if self._can_sync == new_can_sync:
            return

        self._can_sync = new_can_sync
        if self._can_sync:
            self._process_sync()
            # TODO: add regular sync there (and remove if not can sync)
            gobject.timeout_add_seconds(TIME_BEFORE_SYNCING, self.process_sync) 

    def _process_sync(self):
        '''start syncing what's needed if can sync'''

        # if no more connection, don't try syncing in the main loop
        if not self._can_sync:
            return False
        LOG.debug("Start processing sync")

        # 1. 

        # 9999.
        # If something changed, time to notify others!

        # continue syncing in the main loop
        return True

if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)

    sync_handler = SyncHandler()
    loop = gobject.MainLoop()

    loop.run()
