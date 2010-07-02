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

import datetime
import gnomekeyring
import gobject
import logging
from oauth import oauth
import os
from threading import Thread
from ubuntuone.api.restclient import RestClient
from urllib2 import URLError

import gettext
from gettext import gettext as _


DESKTOPCOUCH_LOG = os.path.expanduser('~/.cache/desktop-couch/log/desktop-couch-replication.log')
CHECK_CONNECT_STATE_DELAY = 60*5


class LoginHandler(object):

    """"U1 login status and binding"""

    def __init__(self, oneconf, keyring=gnomekeyring):
        """Try to login with credentials"""

        self.oneconf = oneconf
        self.keyring = keyring
        self._u1inventorydialog = None
        self.u1hosts = {}
        self.login = None
        # update account info in the GUI in async mode
        gobject.threads_init()
        self.update_u1info()
        gobject.timeout_add_seconds(CHECK_CONNECT_STATE_DELAY, self.check_connect_state)

    # login property
    def _get_login(self):
        return self._login
    def _set_login(self, newlogin):
        logging.debug("changed login to %s" % newlogin)
        self._login = newlogin
        if self._u1inventorydialog:
            self._u1inventorydialog.refresh(self)
    login = property(_get_login, _set_login)

    def set_new_u1inventorydialog(self, u1inventorydialog):
        """set current inventory window has the one handled by logger and refresh it"""
        self._u1inventorydialog = u1inventorydialog
        u1inventorydialog.refresh(self)

    def check_connect_state(self):
        """executed every CHECK_CONNECT_STATE_DELAY to check connectivity and update info"""
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
            self.u1hosts = self.oneconf.get_all_hosts()
            login = user.get('email', None)
            if login:
                logging.debug("logged in, check hosts and last sync state")
                self.last_sync = self.get_last_sync_date()
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
            # as the callback won't be called, update the host list here
            self.u1hosts = self.oneconf.get_all_hosts()
        callback(result)

    def get_last_sync_date(self):
        """Check desktopcouch sync status"""
        if not os.path.exists(DESKTOPCOUCH_LOG):
            # no sync yet
            return None
        for line in self.BackwardsReader(file(DESKTOPCOUCH_LOG)):
            # started replicating seems to take ages, so "now syncing" can't be done right now
            if "finished replicating" in line:
                try:
                    last_sync = datetime.datetime.strptime(line[:19], '%Y-%m-%d %H:%M:%S')
                    today = datetime.datetime.strptime(str(datetime.date.today()), '%Y-%m-%d')
                    the_daybefore = today - datetime.timedelta(days=1)
                    if last_sync > today:
                        return _("Last sync %s") % last_sync.strftime('%H:%M')
                    elif last_sync < today and last_sync > the_daybefore:
                        return _("Last sync yesterday %s") % last_sync.strftime('%H:%M')
                    else:
                        return _("Last sync %s") % last_sync.strftime('%Y-%m-%d  %H:%M')                    
                except ValueError, e:
                    logging.warning("can't convert desktopcouch sync date to %s", e)
                break
        return None

    def BackwardsReader(self, fileread, BLKSIZE = 4096):
        """Read desktopcouch log file line by line, backwards"""
        buf = ""
        fileread.seek(-1, 2)
        lastchar = fileread.read(1)
        trailing_newline = (lastchar == "\n")

        while 1:
            newline_pos = buf.rfind("\n")
            pos = fileread.tell()
            if newline_pos != -1:
                # Found a newline
                line = buf[newline_pos+1:]
                buf = buf[:newline_pos]
                if pos or newline_pos or trailing_newline:
                    line += "\n"
                yield line
            elif pos:
                # Need to fill buffer
                toread = min(BLKSIZE, pos)
                fileread.seek(-toread, 1)
                buf = fileread.read(toread) + buf
                fileread.seek(-toread, 1)
                if pos == toread:
                    buf = "\n" + buf
            else:
                # Start-of-file
                return

