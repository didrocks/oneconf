#!/usr/bin/python
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
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import ConfigParser
from oneconf.paths import ONECONF_OVERRIDE_FILE

config = ConfigParser.RawConfigParser()
try:
    config.read(ONECONF_OVERRIDE_FILE)
    MIN_TIME_WITHOUT_ACTIVITY = config.getint('TestSuite', 'MIN_TIME_WITHOUT_ACTIVITY')
except ConfigParser.NoSectionError:
    MIN_TIME_WITHOUT_ACTIVITY = 60*5
ONECONF_SERVICE_NAME = "com.ubuntu.OneConf"

