# -*- coding: utf-8 -*-
# Copyright (C) 2010 Canonical
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

import logging

class LoginHandler(object):

    """"U1 login status and binding"""

    def __init__(self, u1inventorydialog):
        """Try to login with credentials"""

        self._u1inventorydialog = u1inventorydialog
        self.login = None


    # logged property
    def _get_login(self):
        return self._login
    def _set_login(self, newlogin):
        logging.debug("changed login to %s" % newlogin)
        self._login = newlogin
        self._u1inventorydialog.refresh(self)

    login = property(_get_login, _set_login)


