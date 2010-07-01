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

import gtk
import logging

import gettext
from gettext import gettext as _

import u1loginhandler
import os
import subprocess

NEW_ACCOUNT_URL = "https://one.ubuntu.com/plans/"

class U1InventoryDialog(object):
    """Dialog to manage OneConf U1 inventory"""

    def __init__(self, datadir, parent=None):

        logging.debug("creating inventory manager dialog")
        # ui
        self.builder = gtk.Builder()
        self.builder.add_from_file(datadir+"/ui/u1inventorydialog.ui")
        self.builder.connect_signals(self)
        for o in self.builder.get_objects():
            if issubclass(type(o), gtk.Buildable):
                name = gtk.Buildable.get_name(o)
                setattr(self, name, o)
            else:
                print >> sys.stderr, "WARNING: can not get name for '%s'" % o
        # logger
        self.logger = u1loginhandler.LoginHandler(self)

        # parent
        if parent:
            self.dialog_u1login.set_transient_for(parent)
        self.parent = parent

    def show(self):
        self.dialog_u1login.show()

    def refresh(self, logger=None):
        """switched connected mode on/off"""
        logging.debug("ask for refreshing login state with login as %s" % logger.login)
        if not logger:
            logger = self.logger
        if logger.login:
            self.button_sign_in.hide()
            self.label_u1_status.set_text(_("Signed in as %s") % logger.login)
            self.check_share_inventory.set_sensitive(True)
            self.check_show_inventories.set_sensitive(True)
            self.button_manage_u1.set_label(_("Ubuntu One Settings…"))
            self.button_manage_u1.connect("clicked", self.setting)
        else:
            self.button_sign_in.show()
            self.label_u1_status.set_text(_("You are not signed in."))
            self.check_share_inventory.set_sensitive(False)
            self.check_show_inventories.set_sensitive(False)
            self.button_manage_u1.set_label(_("Join Ubuntu one…"))
            self.button_manage_u1.connect("clicked", self.register)

    def sign_in(self, widget):
        subprocess.Popen(['ubuntuone-preferences'])

    def register(self, widget):
        subprocess.call(["xdg-open", NEW_ACCOUNT_URL])

    def setting(self, widget):
        subprocess.Popen(['ubuntuone-preferences'])

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # gui
    u1logindialog = U1InventoryDialog('../../data', parent=None)
    u1logindialog.show()

    gtk.main()
