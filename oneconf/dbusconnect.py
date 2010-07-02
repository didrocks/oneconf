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

from oneconf.hosts import Hosts, HostError
from oneconf.packagesethandler import PackageSetHandler

ONECONF_SERVICE_NAME = "com.ubuntu.OneConf"
HOSTS_OBJECT_NAME = "/com/ubuntu/oneconf/HostsHandler"
PACKAGE_SET_INTERFACE = "com.ubuntu.OneConf.HostsHandler.PackageSetHandler"
HOSTS_INTERFACE = "com.ubuntu.OneConf.HostsHandler.Hosts"

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
        self.hosts = Hosts()
        self.PackageSetHandler = PackageSetHandler(self.hosts)
        self.activity = False

    @dbus.service.method(HOSTS_INTERFACE)
    def get_current_host(self):
        self.activity = True
        return self.hosts.get_current_host()

    @dbus.service.method(HOSTS_INTERFACE)
    def get_all_hosts(self):
        self.activity = True
        return self.hosts.get_all_hosts()

    @dbus.service.method(PACKAGE_SET_INTERFACE)
    def get_selection(self, hostid, hostname):
        self.activity = True
        return self.PackageSetHandler.get_selection(hostid, hostname)

    @dbus.service.method(PACKAGE_SET_INTERFACE)
    def get_all(self, hostid, hostname):
        self.activity = True
        return self.PackageSetHandler.get_all(hostid, hostname)

    @dbus.service.method(PACKAGE_SET_INTERFACE)
    def diff(self, selection, hostid, hostname, use_cache):
        self.activity = True
        return self.PackageSetHandler.diff(selection, hostid, hostname,
                                           use_cache)

    @dbus.service.method(PACKAGE_SET_INTERFACE)
    def update(self):
        self.activity = True
        self.PackageSetHandler.update()

    @dbus.service.method(PACKAGE_SET_INTERFACE)
    def async_update(self):
        self.activity = True
        glib.timeout_add_seconds(1,self.PackageSetHandler.update)

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

    def get_current_host(self):
        '''get a dictionnary of the current host'''
        return self._get_hosts_dbusobject().get_current_host()

    def get_all_hosts(self):
        '''get a dictionnary of all available hosts'''
        return self._get_hosts_dbusobject().get_all_hosts()

    def get_all(self, hostid, hostname):
        '''trigger getall handling'''

        try:
            return self._get_package_handler_dbusobject().get_all(hostid,
                                                                  hostname)
        except dbus.exceptions.DBusException,e:
            print(e)
            sys.exit(1)

    def get_selection(self, hostid, hostname):
        '''trigger selection handling'''

        try:
            return self._get_package_handler_dbusobject().get_selection(hostid,
                                                                       hostname)
        except dbus.exceptions.DBusException,e:
            print(e)
            sys.exit(1)

    def diff_all(self, hostid, hostname, use_cache):
        '''trigger diff_all handling'''
        try:
            return self._get_package_handler_dbusobject().diff(False, hostid,
                                                            hostname, use_cache)
        except dbus.exceptions.DBusException,e:
            print(e)
            sys.exit(1)

    def diff_selection(self, hostid, hostname, use_cache):
        '''trigger diff_selection handling'''

        try:
            return self._get_package_handler_dbusobject().diff(True, hostid,
                                                            hostname, use_cache)
        except dbus.exceptions.DBusException,e:
            print(e)
            sys.exit(1)

    def update(self):
        '''trigger update handling'''
        self._get_package_handler_dbusobject().update()

    def async_update(self):
        '''trigger update handling'''
        self._get_package_handler_dbusobject().async_update()
    

