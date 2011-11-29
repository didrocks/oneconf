# -*- coding: utf-8 -*-
# Copyright (C) 2011 Canonical
#
# Authors:
#  Didier Roche <didrocks@ubuntu.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUTa
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import ConfigParser
import os
from xdg import BaseDirectory as xdg

ONECONF_OVERRIDE_FILE = "/tmp/oneconf.override"

ONECONF_DATADIR = '/usr/share/oneconf/data'
ONECONF_CACHE_DIR = os.path.join(xdg.xdg_cache_home, "oneconf")
PACKAGE_LIST_PREFIX = "package_list"
OTHER_HOST_FILENAME = "other_hosts"
PENDING_UPLOAD_FILENAME = "pending_upload"
HOST_DATA_FILENAME = "host"
LOGO_PREFIX = "logo"
LAST_SYNC_DATE_FILENAME = "last_sync"

_datadir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
if not os.path.exists(_datadir): # take the paths file if loaded from networksync module
    _datadir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
if not os.path.exists(_datadir):  
    _datadir = ONECONF_DATADIR
LOGO_BASE_FILENAME = os.path.join(_datadir, 'images', 'computer.png')
WEBCATALOG_SILO_DIR = "/tmp"
FAKE_WALLPAPER = None # Fake wallpaper for tests

config = ConfigParser.RawConfigParser()
try:
    config.read(ONECONF_OVERRIDE_FILE)
    ONECONF_CACHE_DIR = config.get('TestSuite', 'ONECONF_CACHE_DIR')
    WEBCATALOG_SILO_DIR = config.get('TestSuite', 'WEBCATALOG_SILO_DIR')
    FAKE_WALLPAPER = os.path.join(os.path.dirname(_datadir), config.get('TestSuite', 'FAKE_WALLPAPER'))
except ConfigParser.NoSectionError:
    pass
WEBCATALOG_SILO_SOURCE = os.path.join(WEBCATALOG_SILO_DIR, "source")
WEBCATALOG_SILO_RESULT = os.path.join(WEBCATALOG_SILO_DIR, "result")
