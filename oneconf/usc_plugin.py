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

import gobject
import gtk
import logging
import os
import softwarecenter.plugin
import sys
from softwarecenter.view.widgets.animatedimage import AnimatedImage

import gettext
from gettext import gettext as _


# append directory to take oneconf module
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from oneconf.dbusconnect import DbusConnect
from oneconf.uscplugin import u1inventorydialog, oneconfeventhandler, oneconfpane

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

        # FIXME: workaround for imperfect apps.py
        #self.app.view_switcher.apps_filter = None

        # add menu item
        self.u1logindialog = None
        #self.menuitem_saveinventory = gtk.MenuItem(_("Save Inventory…"))
        self.menuitem_manageu1inventory = gtk.MenuItem(_("Inventory on Ubuntu One…"))
        self.menuitem_manageu1inventory.connect_object("activate", self.show_manageui1inventory, None)
        # maybe a placeholder for plugins would be better, isn't?
        pos = 0
        for menu in self.app.menu1.get_children():
            if menu == self.app.menuitem_close:        
                #self.app.menu1.insert(self.menuitem_saveinventory, pos)
                self.app.menu1.insert(self.menuitem_manageu1inventory, pos+1)
                self.app.menu1.insert(gtk.SeparatorMenuItem(), pos+2)
                break
            pos += 1
        # initialize dbus binding
        self.oneconf = DbusConnect()
        self.oneconfeventhandler = oneconfeventhandler.OneConfEventHandler(self.oneconf)
        # refresh host list
        self.oneconfeventhandler.connect('inventory-refreshed', self.refresh_hosts)
        self.oneconfeventhandler.check_inventory()
        self.view_switchers_oneconf_hostid = set()

    def show_manageui1inventory(self, menuitem):
        """build and show the u1 login window"""
        u1logindialog = u1inventorydialog.U1InventoryDialog(self.datadir, self.oneconfeventhandler, parent=self.app.window_main)
        u1logindialog.show()

    def refresh_hosts(self, loginhandler):
        """refresh hosts list in the panel view"""
        logging.debug('oneconf: refresh hosts')

        view_switcher = self.app.view_switcher
        model = view_switcher.get_model()
        icon = None
        parent_iter = None
        channel = None
        previous_iter = model.installed_iter

        new_elem = {}

        for hostid in self.oneconfeventhandler.u1hosts:
            current, name, show_inventory, show_others = self.oneconfeventhandler.u1hosts[hostid]
            if not current and show_inventory:
                new_elem[hostid] = name
            else:
                if not show_others:
                    return # TODO: need to unregister

        for current_hostid in new_elem:
            if current_hostid not in self.view_switchers_oneconf_hostid:
                current_pane = oneconfpane.OneConfPane(self.app.cache, None, self.app.db, 'Ubuntu', self.app.icons, self.app.datadir, self.oneconfeventhandler, current_hostid)
                self.app.view_manager.register(current_pane, current_hostid)
                icon = AnimatedImage(view_switcher.icons.load_icon("computer", model.ICON_SIZE, 0))
                current_iter = model.insert_after(None, previous_iter, [icon, new_elem[current_hostid], current_hostid, channel])
                previous_iter = current_iter
                self.view_switchers_oneconf_hostid.add(current_hostid)
                # show the pane and its content once it's added to the notebook
                current_pane.show_all()

