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

import datetime

import gettext
from gettext import gettext as _

from softwarecenter.backend.login_sso import get_sso_backend
from softwarecenter.backend.restfulclient import get_ubuntu_sso_backend
from softwarecenter.utils import clear_token_from_ubuntu_sso

class OneConfInventoryDialog(object):
    """Dialog to manage OneConf inventory"""

    def __init__(self, datadir, oneconf, parent=None):

        logging.debug("creating inventory manager dialog")

        self.builder = gtk.Builder()
        self.builder.add_from_file(datadir + "/ui/oneconfinventorydialog.ui")
        self.builder.connect_signals(self)
        for o in self.builder.get_objects():
            if issubclass(type(o), gtk.Buildable):
                name = gtk.Buildable.get_name(o)
                setattr(self, name, o)
            else:
                print >> sys.stderr, "WARNING: can not get name for '%s'" % o
        
        self.token = None
        self.appname = "Ubuntu Software Center"
        self.user_display_name = None
        self.nb_other_hosts = 0
        
        #oneconfeventhandler.connect('inventory-refreshed', self.refresh)
        #if oneconfeventhandler and not oneconfeventhandler.login:
        #    oneconfeventhandler.check_connect_state()
        if parent:
            self.dialog_oneconflogin.set_transient_for(parent)
        self.parent = parent
        self.oneconf = oneconf
        
    def try_login(self, widget):
        logging.debug("OneConf login()")
        login_text = _("To share your content with others computer you own you need to "
                       "sign in to a Ubuntu Single Sign-On account.")
        self.sso = get_sso_backend(self.dialog_oneconflogin.window.xid,
                                   self.appname, login_text)
        self.sso.connect("login-successful", self._maybe_login_successful)
        self.sso.connect("login-canceled", self._login_canceled)
        self.sso.login_or_register()
 
    def _login_canceled(self, sso):
        self.user_display_name = None
        self.refresh_user()
        
    def _maybe_login_successful(self, sso, oauth_result):
        """ called after we have the token, then we go and figure out our name """
        logging.debug("_maybe_login_successful")
        self.token = oauth_result
        self.ssoapi = get_ubuntu_sso_backend(self.token)
        self.ssoapi.connect("whoami", self._whoami_done)
        self.ssoapi.connect("error", self._whoami_error)
        self.ssoapi.whoami()

    def _whoami_done(self, ssologin, result):
        logging.debug("_whoami_done")
        self.user_display_name = result["displayname"]
        self.refresh_user()

    def _whoami_error(self, ssologin, e):
        logging.error("whoami error '%s'" % e)
        # HACK: clear the token from the keyring assuming that it expired
        #       or got deauthorized by the user on the website
        # this really should be done by ubuntu-sso-client itself
        import lazr.restfulclient.errors
        errortype = lazr.restfulclient.errors.HTTPError
        if (type(e) == errortype):
            logging.warn("authentication error, reseting token and retrying")
            clear_token_from_ubuntu_sso(self.appname)
            self.refresh_user()
            return

        #self.label_latest_sync_date.set_label("heeeehe" or _("unknown"))

    def show(self):
        self.dialog_oneconflogin.show()
        self.refresh_user()
        self.try_login(None)

    def on_button_close_clicked(self, button):
        self.dialog_oneconflogin.hide()

    def refresh_user(self):
        logging.debug("refresh user name")
        if self.user_display_name:
            logging.debug("ask for refreshing login state with login as %s" % self.user_display_name)
            self.check_share_inventory.set_sensitive(True)
            self.label_sso_status.set_text(_("Signed in as %s") % self.user_display_name)
            self.button_sign_in.hide()
        else:
            self.label_sso_status.set_text(_("You are not signed in."))
            self.check_share_inventory.set_sensitive(False)
            self.button_sign_in.set_label(_("Sign in or join Ubuntu sso…"))
            self.button_sign_in.connect("clicked", self.try_login)
            self.button_sign_in.show()
            
    def register_nb_hosts(self, registered_hostids, is_current_registered):
        logging.debug("register a new number of hosts")
        nb_hosts = len(registered_hostids)
        self.nb_other_hosts = nb_hosts
        if is_current_registered:
            nb_hosts += 1
        self.check_share_inventory.set_active(is_current_registered)
        self.refresh_nb_hosts(nb_hosts)
        
    def refresh_nb_hosts(self, nb_hosts):
        if nb_hosts:
            msg = gettext.ngettext("%(amount)s host registered",
                                   "%(amount)s hosts registered",
                                   nb_hosts) % { 'amount' : nb_hosts, }
        else:
            msg = _("No host registered")
        self.label_nb_host.set_label(msg)
        self.label_nb_host.show()

    def share_inventory_toogle(self, widget):
        logging.debug("change share inventory state")
        self.oneconf.set_share_inventory(widget.get_active())
        self.refresh_nb_hosts(self.nb_other_hosts + widget.get_active())
        
    def set_latest_oneconf_sync(self, timestamp):
        logging.debug("refresh latest sync date")
        
        try:
            last_sync = datetime.datetime.fromtimestamp(float(timestamp))
            today = datetime.datetime.strptime(str(datetime.date.today()), '%Y-%m-%d')
            the_daybefore = today - datetime.timedelta(days=1)

            if last_sync > today:
                msg = _("Last sync %s") % last_sync.strftime('%H:%M')
            elif last_sync < today and last_sync > the_daybefore:
                msg = _("Last sync yesterday %s") % last_sync.strftime('%H:%M')
            else:
                msg = _("Last sync %s") % last_sync.strftime('%Y-%m-%d  %H:%M')                    
        except TypeError:
            msg = _("Was never synced successfully")
        self.label_latest_sync_date.set_label(msg)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # import oneconf dir
    import os
    import sys
    
    oneconf_root_path =  os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
    sys.path.append(oneconf_root_path)

    # oneconf handler
    from oneconf.dbusconnect import DbusConnect
    oneconf = DbusConnect()

    # gui
    oneconflogindialog = OneConfInventoryDialog('%s/data' % oneconf_root_path, oneconf, parent=None)
    oneconflogindialog.register_nb_hosts(["foo", "bar", "baz"], True)
    oneconflogindialog.set_latest_oneconf_sync("123456")
    oneconflogindialog.show()

    gtk.main()
