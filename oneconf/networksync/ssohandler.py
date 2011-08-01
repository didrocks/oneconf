#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2010-2011 Canonical
#
# Authors:
#  Michael Vogt
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

import dbus
import gettext
import gobject
import logging

from gettext import gettext as _

gettext.textdomain("software-center")

NO_OP = lambda *args, **kwargs: None

LOG = logging.getLogger(__name__)

class LoginBackendDbusSSO(gobject.GObject):


    __gsignals__ = {
        "login-result" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_PYOBJECT,),
                         ),
        }

    def __init__(self):
        super(LoginBackendDbusSSO, self).__init__()
        
        # use USC credential
        #self.appname = _("Ubuntu Software Center Store")
        self.appname = "Ubuntu Software Center"
        bus = dbus.SessionBus()
        self.proxy = bus.get_object('com.ubuntu.sso', '/com/ubuntu/sso/credentials')
        self.proxy.connect_to_signal("CredentialsFound",
                                     self._on_credentials_found)
        self.proxy.connect_to_signal("CredentialsNotFound",
                                     self._on_credentials_not_found)
        self.proxy.connect_to_signal("CredentialsError",
                                     self._on_credentials_error)

    def get_credential(self):
        LOG.debug("look for credential")
        self.proxy.find_credentials(self.appname, '', reply_handler=NO_OP, error_handler=NO_OP)

    def _on_credentials_found(self, app_name, credentials):
        if app_name != self.appname:
            return
        LOG.debug("credential found")
        self.emit("login-result", credentials)

    def _on_credentials_not_found(self, app_name):
        if app_name != self.appname:
            return
        LOG.debug("credential not found")
        self.emit("login-result", None)
    
    def _on_credentials_error(self, app_name, error):
        if app_name != self.appname:
            return
        LOG.error("credential error")
        self.emit("login-result", None)


        
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)

    login = LoginBackendDbusSSO()

    loop = gobject.MainLoop()
    login.get_credential()
    
    def print_result(obj, foo):
        print foo
    
    login.connect("login-result", print_result)
    
    gobject.timeout_add_seconds(5, login.get_credential)

    loop.run()



