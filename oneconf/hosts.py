# Copyright (C) 2010 Canonical
#
# Authors:
#  Didier Roche <didrocks@ubuntu.com>
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


import hashlib
import json
import logging
import os
import platform

import gettext
from gettext import gettext as _

#FIXME: where should the cache go? Ideally /var/cache/oneconf, but owned by root (not root when just updating the list)
# home: in addition to the duplication, it's not nice as on new install dpkg -> no update to every user account
ONECONF_CACHE_DIR = "%s/.cache/oneconf" % os.path.expanduser('~')
ONECONF_HOST_DATA = "host_data"

class HostError(Exception):
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)

class Hosts(object):
    """
    Class to get hostid <-> hostname 
    """

    def __init__(self):
        '''initialize database

        This will register/update this host if not already done.
        '''

        # create cache dir if doesn't exist
        if not os.path.isdir(ONECONF_CACHE_DIR):
            os.mkdir(ONECONF_CACHE_DIR)

        self.hostid = open('/var/lib/dbus/machine-id').read()[:-1]
        self.hostname = platform.node()
        # faking this id for testing purpose
        #self.hostid = 'BBBBBB'
        #self.hostname = "foomachine"

        self._host_file_dir = os.path.join(ONECONF_CACHE_DIR, self.hostid)
        try:
            with open(os.path.join(self._host_file_dir, ONECONF_HOST_DATA), 'r') as f:
                self.share_inventory = json.load(f)['host']['share_inventory']
        except IOError:
            self.share_inventory = False
            self._save_host()

        (self._other_hosts_etag, self._other_hosts) = self._load_other_hosts()

    def _load_other_hosts(self, previous_etag = None):
        '''Load all other hosts from cache, eventually refreshed from the server (only available online)'''

        other_hosts = {}
        etag = previous_etag

        # try a first load on cache, in particular to get the ETag
        if not etag:
            try:
                with open("%s/other_hosts" % ONECONF_CACHE_DIR, 'r') as f:
                    file_content = json.load(f)
                    other_hosts = file_content['hosts']
                    etag  = file_content['ETag']
            except IOError:
                pass
        
        #TODO: FAKE for now, we will get the agregated list from the server (we need to check if we are offline first)
        # check cache with ETag (file is {ETag: etag, hosts: {}}
        
        
        # TODO: if cache is not valid, rewrite it

        return (etag, other_hosts)

    def _save_host(self):
        '''Save host on disk'''
        
        logging.debug("Save current host to disk")

        json_elem = {'hostid': self.hostid, 'hostname': self.hostname, 'share_inventory': self.share_inventory}
        etag = hashlib.sha224(str(json_elem)).hexdigest()
        
        if not os.path.isdir(self._host_file_dir):
            os.mkdir(self._host_file_dir)
        with open(os.path.join(self._host_file_dir, ONECONF_HOST_DATA), 'w') as f:
            json.dump({'ETag': etag, 'host': json_elem}, f)

    def gethostname_by_id(self, hostid):
        '''Get hostname by id

        Return: hostname

        can trigger HostError excpetion if no hostname found for this id
        '''
        
        logging.debug("Get a hostname by id")
        
        if hostid == self.hostid:
            return self.hostname

        try:
            return self._other_hosts[hostid]
        except KeyError:
            raise HostError(_("No hostname registered for this id"))

    def gethostid_by_name(self, hostname):
        '''Get hostid by hostname

        Return: hostid

        can trigger HostError exception unexisting hostname
        or multiple hostid for this hostname
        '''
        
        logging.debug("Get a hostid by name")

        result_hostid = None
        if hostname == self.hostname:
            result_hostid = self.hostid
        for hostid in self._hosts:
            if hostname == self._hosts[hostid]:
                if not result_hostid:
                    result_hostid = hostid
                else:
                    raise HostError(_("Multiple hostid registered for this "\
                        "hostname. Use --list --host to get the hostid and "\
                        "use the --hostid option."))
        if not result_hostid:
            raise HostError(_("No hostid registered for this hostname"))
        return result_hostid

    def get_all_hosts(self):
        '''Return a dictionnary of all hosts

        put in them as dict -> tuple for dbus connection'''

        logging.debug("Request to compute an list of all hosts")
        result = {self.hostid: (True, self.hostname, self.share_inventory)}
        for hostid in self._other_hosts:
            result[hostid] = (False, self._other_hosts[hostid]['hostname'], True)
        return result

    def set_share_inventory(self, share_inventory):
        '''Change if we share the current inventory to other hosts'''

        logging.debug("Update current share_inventory state to %s" % share_inventory)
        self.share_inventory = share_inventory
        self._save_host()
        # TODO: update, and take the case into account once offline


