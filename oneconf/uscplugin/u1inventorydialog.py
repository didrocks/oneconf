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

import oneconfeventhandler
import os
import subprocess

NEW_ACCOUNT_URL = "https://one.ubuntu.com/plans/"

class U1InventoryDialog(object):
    """Dialog to manage OneConf U1 inventory"""

    def __init__(self, datadir, oneconfeventhandler, parent=None):

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
        # bind login handler to window
        self.oneconfeventhandler = oneconfeventhandler
        self.refresh() # force first refresh (can speedup if already oneconfeventhandler)
        oneconfeventhandler.connect('inventory-refreshed', self.refresh)
        if oneconfeventhandler and not oneconfeventhandler.login:
            print "there"
            oneconfeventhandler.check_connect_state()
        if parent:
            self.dialog_u1login.set_transient_for(parent)
        self.parent = parent

    def show(self):
        self.dialog_u1login.show()

    def on_button_close_clicked(self, button):
        self.dialog_u1login.hide()

    def refresh(self, logger=None):
        """switched connected mode on/off"""
        if not logger:
            logger = self.oneconfeventhandler
        if logger.login:
            logging.debug("ask for refreshing login state with login as %s" % logger.login)
            self.button_sign_in.hide()
            self.label_u1_status.set_text(_("Signed in as %s") % logger.login)
            self.button_manage_u1.set_label(_("Ubuntu One Settings…"))
            self.button_manage_u1.connect("clicked", self.setting)
            self.label_sync_u1_date.set_label(logger.last_sync)
            self.label_sync_u1_date.show()
        else:
            self.button_sign_in.show()
            self.label_u1_status.set_text(_("You are not signed in."))
            self.check_show_inventory.set_sensitive(False)
            self.check_show_others.set_sensitive(False)
            self.button_manage_u1.set_label(_("Join Ubuntu one…"))
            self.button_manage_u1.connect("clicked", self.register)
            self.label_sync_u1_date.hide()

        if logger.u1hosts:
            nb_hosts = 0
            for hostid in logger.u1hosts:
                current, name, show_inventory, show_others = logger.u1hosts[hostid]
                if current:
                    self.check_show_inventory.set_active(show_inventory)
                    self.check_show_others.set_active(show_others)
                if show_inventory:
                    nb_hosts += 1
            if nb_hosts:
                msg = _("%s registered") % nb_hosts
            else:
                msg = _("None registered")
            self.check_show_inventory.set_sensitive(True)
            self.check_show_others.set_sensitive(True)
            self.label_nb_host.set_label(msg)
            self.label_nb_host.show()

    def sign_in(self, widget):
        subprocess.Popen(['ubuntuone-preferences'])

    def register(self, widget):
        subprocess.call(["xdg-open", NEW_ACCOUNT_URL])

    def setting(self, widget):
        subprocess.Popen(['ubuntuone-preferences'])

    def show_others_toogle(self, widget):
        self.oneconfeventhandler.oneconf.set_show_inventory(widget.get_active(), others=True)
        self.oneconfeventhandler.check_connect_state() # refresh hostid list        

    def show_inventory_toogle(self, widget):
        self.oneconfeventhandler.oneconf.set_show_inventory(widget.get_active(), others=False)
        self.oneconfeventhandler.check_connect_state() # refresh hostid list

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # import oneconf dir
    import sys
    sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))))

    # oneconf handler
    from oneconf.dbusconnect import DbusConnect
    oneconf = DbusConnect()
    oneconfeventhandler = oneconfeventhandler.OneConfEventHandler(oneconf)

    # gui
    u1logindialog = U1InventoryDialog('../../data', oneconfeventhandler, parent=None)
    u1logindialog.show()

    gtk.main()
