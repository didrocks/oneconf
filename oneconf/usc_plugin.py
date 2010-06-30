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
import os
import softwarecenter.plugin

import gettext
from gettext import gettext as _

import imp
imp.load_package('uscplugin', os.path.dirname(os.path.realpath(__file__)) + '/uscplugin')
from uscplugin import *

ONECONF_DATADIR = '/usr/share/oneconf/data'

class OneConfPlugin(softwarecenter.plugin.Plugin):
    """OneConf plugin to get sync and package diff in USC"""

    def init_plugin(self):
        """take datadir, add menu items and get hosts"""

        # set datadir from trunk (and respect symlink)
        self.filename = os.path.realpath(__file__)
        self.datadir = os.path.join(os.path.dirname(os.path.dirname(self.filename)), "data")
        if not os.path.exists(self.datadir):
            self.datadir = ONECONF_DATADIR
        logging.debug("oneconf datadir: %s", self.datadir)

        # add menu item
        self.u1logindialog = None
        self.menuitem_saveinventory = gtk.MenuItem(_("Save Inventory…"))
        self.menuitem_manageu1inventory = gtk.MenuItem(_("Inventory on Ubuntu One…"))
        self.menuitem_manageu1inventory.connect_object("activate", self.show_manageui1inventory, None)
        # maybe a placeholder for plugins would be better, isn't?
        pos = 0
        for menu in self.app.menu1.get_children():
            if menu == self.app.menuitem_close:        
                self.app.menu1.insert(self.menuitem_saveinventory, pos)
                self.app.menu1.insert(self.menuitem_manageu1inventory, pos+1)
                self.app.menu1.insert(gtk.SeparatorMenuItem(), pos+2)
                break
            pos += 1

    def show_manageui1inventory(self, menuitem):
        """build and show the u1 login window"""

        if not self.u1logindialog:
            self.u1logindialog = u1inventorydialog.U1InventoryDialog(self.datadir, parent=self.app.window_main)
        self.u1logindialog.show()


