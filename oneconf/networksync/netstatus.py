#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2011 Canonical
#
# Authors:
#   Matthew McGowan
#   Michael Vogt
#   Didier Roche
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


import dbus
import gobject
import logging
import os

LOG = logging.getLogger(__name__)


class NetworkStatusWatcher(gobject.GObject):
    """ simple watcher which notifys subscribers to network events..."""
    
    # enums for network manager status
    # Old enum values are for NM 0.7

    # The NetworkManager daemon is in an unknown state. 
    NM_STATE_UNKNOWN            = 0
    NM_STATE_UNKNOWN_LIST       = [NM_STATE_UNKNOWN]
    # The NetworkManager daemon is asleep and all interfaces managed by it are inactive. 
    NM_STATE_ASLEEP_OLD         = 1
    NM_STATE_ASLEEP             = 10
    NM_STATE_ASLEEP_LIST        = [NM_STATE_ASLEEP_OLD,
                                   NM_STATE_ASLEEP]
    # The NetworkManager daemon is connecting a device.
    NM_STATE_CONNECTING_OLD     = 2
    NM_STATE_CONNECTING         = 40
    NM_STATE_CONNECTING_LIST    = [NM_STATE_CONNECTING_OLD,
                                   NM_STATE_CONNECTING]
    # The NetworkManager daemon is connected. 
    NM_STATE_CONNECTED_OLD      = 3
    NM_STATE_CONNECTED_LOCAL    = 50
    NM_STATE_CONNECTED_SITE     = 60
    NM_STATE_CONNECTED_GLOBAL   = 70
    NM_STATE_CONNECTED_LIST     = [NM_STATE_CONNECTED_OLD,
                                   NM_STATE_CONNECTED_LOCAL,
                                   NM_STATE_CONNECTED_SITE,
                                   NM_STATE_CONNECTED_GLOBAL]
    # The NetworkManager daemon is disconnecting.
    NM_STATE_DISCONNECTING      = 30
    NM_STATE_DISCONNECTING_LIST = [NM_STATE_DISCONNECTING]
    # The NetworkManager daemon is disconnected.
    NM_STATE_DISCONNECTED_OLD   = 4
    NM_STATE_DISCONNECTED       = 20
    NM_STATE_DISCONNECTED_LIST  = [NM_STATE_DISCONNECTED_OLD,
                                   NM_STATE_DISCONNECTED]
    
    __gsignals__ = {'changed':(gobject.SIGNAL_RUN_FIRST,
                               gobject.TYPE_NONE,
                               (int,)),
                   }

    def __init__(self):
        gobject.GObject.__init__(self)
        self.network_state = 0
        
        
        # check is ONECONF_NET_DISCONNECTED is in the environment variables
        # if so force the network status to be disconnected
        if "ONECONF_NET_DISCONNECTED" in os.environ and \
            os.environ["ONECONF_NET_DISCONNECTED"] is not None:
            NETWORK_STATE = self.NM_STATE_DISCONNECTED
            LOG.warn('forced netstate into disconnected mode...')
            return
        try:
            bus = dbus.SystemBus()
            nm = bus.get_object('org.freedesktop.NetworkManager',
                                '/org/freedesktop/NetworkManager')
            self.network_state = nm.state(dbus_interface='org.freedesktop.NetworkManager')
            nm.connect_to_signal("StateChanged", self._on_connection_state_changed)

        except Exception as e:
            LOG.warn("failed to init network state watcher '%s'" % e)
            self.network_state = self.NM_STATE_UNKNOWN


    def _on_connection_state_changed(self, state):
        LOG.debug("network status changed to %i", state)

        self.network_state = int(state)
        self.emit("changed", self.network_state)
        return


    def is_connected(self):
        """ get bool if we are connected """
        
        # unkown because in doubt, just assume we have network
        result = self.network_state in self.NM_STATE_UNKNOWN_LIST + self.NM_STATE_CONNECTED_LIST
        
        LOG.debug("check if we are connected: %s", result)
        return result

        
if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)
    
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    network = NetworkStatusWatcher()
    loop = gobject.MainLoop()

    def print_state(new_network, new_state):
        print "New state received is: %s" % new_state
        print "Consequently, it is connected: %s" % new_network.is_connected()
    print "initial connection state: %s" % network.is_connected()
    
    network.connect("changed", print_state)
    
    loop.run()



