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

from oneconf.packagesethandler import PackageSetHandler
from oneconf.hosts import Hosts, HostError

import sys

class DirectConnect(object):

    """
    Dummy backend handling exit and exception directly
    """

    def get_hosts(self):
        '''get a list of all available hosts'''
        return Hosts().get_all_hosts()

    def get_all(self, hostid, hostname):
        '''trigger getall handling'''

        try:
            return PackageSetHandler().get_all(hostid, hostname)
        except HostError, e:
            print(e)
            sys.exit(1)

    def get_appscodec(self, hostid, hostname):
        '''trigger appscodec handling'''

        try:
            return PackageSetHandler().get_appscodec(hostid, hostname)
        except HostError, e:
            print(e)
            sys.exit(1)

    def diff_all(self, hostid, hostname):
        '''trigger diff_all handling'''
        try:
            return PackageSetHandler().diff(False, hostid, hostname)
        except HostError, e:
            print(e)
            sys.exit(1)

    def diff_appscodec(self, hostid, hostname):
        '''trigger diff_appscodec handling'''

        try:
            return PackageSetHandler().diff(True, hostid, hostname)
        except HostError, e:
            print(e)
            sys.exit(1)

    def update(self):
        '''trigger update handling'''
        PackageSetHandler().update()

