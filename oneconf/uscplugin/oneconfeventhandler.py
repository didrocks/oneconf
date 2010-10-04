# -*- coding: utf-8 -*-
# Copyright (C) 2010 Canonical
#
# Authors:
#  Rodney Dawes <rodney.dawes@canonical.com>
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

import dbus.service
import gobject
import gtk
import logging
from multiprocessing import Pipe, Process
from oauth import oauth
import os
from threading import Thread
from ubuntu_sso import DBUS_BUS_NAME, DBUS_IFACE_CRED_NAME, DBUS_CRED_PATH
from ubuntuone import clientdefs
from urllib2 import URLError

oauth_consumer = None
oauth_token = None

import gettext
from gettext import gettext as _

from oneconf.desktopcouchstate import get_last_sync_date

CHECK_CONNECT_STATE_DELAY = 60*3

class OneConfEventHandler(gobject.GObject):

    """"U1 login status and binding"""

    # TODO:
    # We need to be smarter there and handle more signals:
    # inventory-changed (new OneConf syncing and so, new potential value)
    # inventory-refreshed (or others): just adding/removing something when new host
    __gsignals__ = {
        "inventory-refreshed" : (gobject.SIGNAL_RUN_LAST,
                                 gobject.TYPE_NONE, 
                                 (),
                              ),
    }

    def __init__(self, oneconf):
        """Try to login with credentials"""
        gobject.GObject.__init__(self)
        self.oneconf = oneconf
        self.u1hosts = {}
        self.bus = dbus.SessionBus()
        self._login = None
        # update account info in the GUI in async mode
        gobject.threads_init()
        self.register_u1_signal_handlers()
        gobject.timeout_add_seconds(1, self.do_login_request, self.bus)
        gobject.timeout_add_seconds(CHECK_CONNECT_STATE_DELAY, self.check_connect_state)

    # login property
    def _get_login(self):
        return self._login
    def _set_login(self, newlogin):
        if newlogin != self._login:
            logging.debug("changed login to %s" % newlogin)
            self._login = newlogin
            self.emit('inventory-refreshed')
    login = property(_get_login, _set_login)

    def check_inventory(self):
        Thread(target=self.check_async_inventory).start()

    def check_async_inventory(self):
        """check for available computers in a dedicated thread"""

        self.u1hosts = self.oneconf.get_all_hosts()
        self.emit('inventory-refreshed')

    def check_connect_state(self):
        """executed every CHECK_CONNECT_STATE_DELAY to check connectivity and update info"""

        self.check_inventory()
        self.update_u1info()
        return True

    def update_u1info(self):
        """Request account info from server, and update display."""
        self.make_rest_request(url='https://one.ubuntu.com/api/account/',
                               callback=self.got_account_info)

    def got_account_info(self, user):
        """Handle the result from the account REST call."""
        if user:
            # using name rather than email can be interesting
            #self.name_label.set_text(user.get('nickname', _("Unknown")))
            login = user.get('email', None)
            if login:
                logging.debug("logged in, check hosts and last sync state")
                self.last_sync = get_last_sync_date()
            # this will trigger updating the login GUI                
            self.login = login

    def make_rest_request(self, url=None, method='GET', callback=None):
        """Helper that makes an oauth-wrapped REST request."""
        conn1, conn2 = Pipe(False)
        p = Process(target=really_do_rest_request, args=(url, method, conn2))
        p.start()
        Thread(target=do_rest_request, args=(p, conn1, callback)).start()

    def register_u1_signal_handlers(self):
        """Register the dbus signal handlers."""
        self.bus.add_signal_receiver(
            handler_function=self.got_newcredentials,
            signal_name='CredentialsFound',
            dbus_interface=DBUS_IFACE_CRED_NAME)
        self.bus.add_signal_receiver(
            handler_function=self.got_credentialserror,
            signal_name='CredentialsError',
            dbus_interface=DBUS_IFACE_CRED_NAME)
        self.bus.add_signal_receiver(
            handler_function=self.got_authdenied,
            signal_name='AuthorizationDenied',
            dbus_interface=DBUS_IFACE_CRED_NAME)

    def got_newcredentials(self, app_name, credentials):
        """Show our dialog, since we can do stuff now."""
        global oauth_consumer
        global oauth_token

        if app_name == clientdefs.APP_NAME:
            oauth_consumer = oauth.OAuthConsumer(credentials['consumer_key'],
                                                 credentials['consumer_secret'])
            oauth_token = oauth.OAuthToken(credentials['token'],
                                           credentials['token_secret'])
            logging.info("Got credentials for %s", app_name)

    def got_credentialserror(self, app_name, message, detailed_error):
        """Got an error during authentication."""
        if app_name == clientdefs.APP_NAME:
            logging.error("Credentials error for %s: %s - %s" %
                         (app_name, message, detailed_error))

    def got_authdenied(self, app_name):
        """User denied access."""
        if app_name == clientdefs.APP_NAME:
            logging.error("Authorization was denied for %s" % app_name)

    def dbus_async(self, *args, **kwargs):
        """Simple handler to make dbus do stuff async."""
    	pass

    def got_dbus_error(self, error):
        """Got a DBusError."""
        logging.error(error)

    def do_login_request(self, bus):
        """Make a login request to the login handling daemon."""
        try:
            client = bus.get_object(DBUS_BUS_NAME,
					                DBUS_CRED_PATH,
					                follow_name_owner_changes=True)
            iface = dbus.Interface(client, DBUS_IFACE_CRED_NAME)
            iface.login_or_register_to_get_credentials(
                clientdefs.APP_NAME,
                clientdefs.TC_URL,
                clientdefs.DESCRIPTION,
                0,
                reply_handler=self.dbus_async,
                error_handler=self.got_dbus_error)
        except DBusException, e:
            error_handler(e)


def really_do_rest_request(url, method, conn):
    """Second-order helper that does the REST request.

    Necessary because of libproxy's orneriness WRT threads: LP:633241.
    """
    from ubuntuone.api.restclient import RestClient
    rest_client = RestClient(url)
    try:
        result = rest_client.call(url, method, oauth_consumer, oauth_token)
    except (AttributeError, URLError):
        # to finish the stack call, otherwise freeze the ui
        result = None
    conn.send(result)

def do_rest_request(proc, conn, callback):
    """Helper that handles the REST response."""
    pid = os.getpid()
    proc.join()

    result = conn.recv()
    if callback is not None:
        with gtk.gdk.lock:
            callback(result)

