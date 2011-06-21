# Copyright (C) 2010 Canonical
#
# Authors:
#  Didier Roche <didrocks@ubuntu.com>
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
import dbus.service
import glib
import sys


ONECONF_SERVICE_NAME = "com.ubuntu.OneConf"
HOSTS_OBJECT_NAME = "/com/ubuntu/oneconf/HostsHandler"
PACKAGE_SET_INTERFACE = "com.ubuntu.OneConf.HostsHandler.PackageSetHandler"
HOSTS_INTERFACE = "com.ubuntu.OneConf.HostsHandler.Hosts"
timeout=ONE_CONF_DBUS_TIMEOUT = 300

def none_to_null(var):
    '''return var in dbus compatible format'''
    if not var:
        var = ''
    return var

class DbusHostsService(dbus.service.Object):

    """
    Dbus service, daemon side
    """

    def __init__(self):
        '''registration over dbus'''
        bus_name = dbus.service.BusName(ONECONF_SERVICE_NAME,
                                        bus=dbus.SessionBus())
        dbus.service.Object.__init__(self, bus_name, HOSTS_OBJECT_NAME)
        # Only import oneconf module now (and so load desktopcouch and such)
        # in the server side
        from oneconf.hosts import Hosts, HostError

        self.hosts = Hosts()
        self._packageSetHandler = None
        self.activity = False
        self.synchandler = None
        
    # TODO: can be a property
    def get_packageSetHandler(self):
        '''Ensure we load the package set handler at the right time'''
        if not self._packageSetHandler:
            from oneconf.packagesethandler import PackageSetHandler
            self._packageSetHandler = PackageSetHandler(self.hosts)
        return self._packageSetHandler

    @dbus.service.method(HOSTS_INTERFACE)
    def get_all_hosts(self):
        self.activity = True
        return self.hosts.get_all_hosts()

    @dbus.service.method(HOSTS_INTERFACE)
    def set_share_inventory(self, share_inventory):
        self.activity = True
        if share_inventory: # map to boolean to avoid difference in dbus call and direct
            share_inventory = True
        else:
            share_inventory = False
        return self.hosts.set_share_inventory(share_inventory)

    @dbus.service.method(PACKAGE_SET_INTERFACE)
    def get_packages(self, hostid, hostname, only_manual):
        self.activity = True
        return none_to_null(self.get_packageSetHandler().get_packages(hostid, hostname, only_manual))

    @dbus.service.method(PACKAGE_SET_INTERFACE)
    def diff(self, hostid, hostname):
        self.activity = True
        return self.get_packageSetHandler().diff(hostid, hostname)

    @dbus.service.method(PACKAGE_SET_INTERFACE)
    def update(self):
        self.activity = True
        self.get_packageSetHandler().update()

    @dbus.service.method(PACKAGE_SET_INTERFACE)
    def async_update(self):
        self.activity = True
        glib.timeout_add_seconds(1, self.get_packageSetHandler().update)

class DbusConnect(object):

    """
    Dbus request sender, daemon connection
    """

    def __init__(self):
        '''connect to the bus and get packagesethandler object'''
        self.bus = dbus.SessionBus()
        self.hosts_dbus_object = self.bus.get_object(ONECONF_SERVICE_NAME,
                                                     HOSTS_OBJECT_NAME) 

    def _get_package_handler_dbusobject(self):
        '''get package handler dbus object'''
        return dbus.Interface(self.hosts_dbus_object, PACKAGE_SET_INTERFACE)

    def _get_hosts_dbusobject(self):
        '''get hosts dbus object'''
        return dbus.Interface(self.hosts_dbus_object, HOSTS_INTERFACE)

    def get_all_hosts(self):
        '''get a dictionnary of all available hosts'''
        return self._get_hosts_dbusobject().get_all_hosts()

    def set_share_inventory(self, share_inventory):
        '''update if we share the current inventory on the server'''
        self._get_hosts_dbusobject().set_share_inventory(share_inventory)

    def get_packages(self, hostid, hostname, only_manual):
        '''trigger getpackages handling'''

        try:
            return self._get_package_handler_dbusobject().get_packages(hostid,
                                                           hostname, only_manual)
        except dbus.exceptions.DBusException,e:
            print(e)
            sys.exit(1)

    def diff(self, hostid, hostname):
        '''trigger diff handling'''

        try:
            return self._get_package_handler_dbusobject().diff(hostid,
                                                            hostname,
                                                            timeout=ONE_CONF_DBUS_TIMEOUT)
        except dbus.exceptions.DBusException,e:
            print(e)
            sys.exit(1)

    def update(self):
        '''trigger update handling'''
        self._get_package_handler_dbusobject().update(timeout=ONE_CONF_DBUS_TIMEOUT)

    def async_update(self):
        '''trigger update handling'''
        self._get_package_handler_dbusobject().async_update()
    

