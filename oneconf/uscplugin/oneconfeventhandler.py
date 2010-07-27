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

import gnomekeyring
import gobject
import logging
from oauth import oauth
from threading import Thread
from ubuntuone.api.restclient import RestClient
from urllib2 import URLError

import gettext
from gettext import gettext as _

from oneconf.desktopcouchstate import get_last_sync_date

CHECK_CONNECT_STATE_DELAY = 60*3

class OneConfEventHandler(gobject.GObject):

    """"U1 login status and binding"""

    __gsignals__ = {
        "inventory-refreshed" : (gobject.SIGNAL_RUN_LAST,
                             gobject.TYPE_NONE, 
                             (),
                            ),
    }

    def __init__(self, oneconf, keyring=gnomekeyring):
        """Try to login with credentials"""
        gobject.GObject.__init__(self)
        self.oneconf = oneconf
        self.keyring = keyring
        self.u1hosts = {}
        self.login = None
        # update account info in the GUI in async mode
        gobject.threads_init()
        gobject.timeout_add_seconds(CHECK_CONNECT_STATE_DELAY, self.check_connect_state)

    # login property
    def _get_login(self):
        return self._login
    def _set_login(self, newlogin):
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
                               keyring=self.keyring,
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

    def make_rest_request(self, url=None, method='GET',
                          callback=None, keyring=None):
        """Helper that makes an oauth-wrapped REST request."""
        token = self.get_access_token(keyring)

        rest_client = RestClient(url)
        Thread(target=self.do_rest_request, args=(rest_client, url, method, token, callback)).start()

    def get_access_token(self, keyring):
        """Get the access token from the keyring."""
        items = []
        try:
            items = keyring.find_items_sync(
                keyring.ITEM_GENERIC_SECRET,
                {'ubuntuone-realm': "https://ubuntuone.com",
                 'oauth-consumer-key': 'ubuntuone'})
            secret = items[0].secret
            return oauth.OAuthToken.from_string(secret)
        except (gnomekeyring.NoMatchError, gnomekeyring.DeniedError):
            return None

    def do_rest_request(self, rest_client, url, method, token, callback):
        """Helper that handles the REST response."""
        try:
            consumer = oauth.OAuthConsumer('ubuntuone', 'hammertime')
            result = rest_client.call(url, method, consumer, token)
        except URLError, e:
            result = None
        callback(result)


