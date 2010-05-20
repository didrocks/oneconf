#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (C) 2010 Canonical
# Author: Didier Roche <didrocks@ubuntu.com>
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

from oneconf.packagesethandler import PackageSetHandler
from oneconf.hosts import Hosts, HostError

import sys


class DirectConnect(object):

    """
    Dummy backend handling exit and exception directly
    """

    def get_all(self, hostid=None, hostname=None):
        '''trigger getall handling'''

        try:
            return PackageSetHandler().get_all(hostid, hostname)
        except HostError, e:
            print(e)
            sys.exit(1)

    def get_appscodec(self, hostid=None, hostname=None):
        '''trigger appscodec handling'''

        try:
            return PackageSetHandler().get_appscodec(hostid, hostname)
        except HostError, e:
            print(e)
            sys.exit(1)

    def diff(self, hostid=None, hostname=None):
        '''trigger diff handling'''

        try:
            return PackageSetHandler().diff(hostid, hostname)
        except HostError, e:
            print(e)
            sys.exit(1)

    def update(self):
        '''trigger update handling'''
        PackageSetHandler().update()

