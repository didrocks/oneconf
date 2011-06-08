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

LOG = logging.getLogger(__name__)

from oneconf.paths import ONECONF_CACHE_DIR, OTHER_HOST_FILENAME, HOST_DATA_FILENAME

class HostError(Exception):
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)

class Hosts(object):
    """
    Class to get hosts
    """

    def __init__(self):
        '''initialize database

        This will register/update this host if not already done.
        '''

        # create cache dir if doesn't exist
        if not os.path.isdir(ONECONF_CACHE_DIR):
            os.mkdir(ONECONF_CACHE_DIR)

        hostid = open('/var/lib/dbus/machine-id').read()[:-1]
        hostname = platform.node()
        # faking this id for testing purpose
        #hostid = 'BBBBBB'
        #hostname = "foomachine"

        self._host_file_dir = os.path.join(ONECONF_CACHE_DIR, hostid)
        try:
            with open(os.path.join(self._host_file_dir, HOST_DATA_FILENAME), 'r') as f:
                self.current_host = json.load(f)['host']
                if hostname != self.current_host['hostname']:
                    self.current_host['hostname'] = hostname
                    self._save_current_host()
        except IOError:
            self.current_host = {'hostid': hostid, 'hostname': hostname, 'share_inventory': False}
            self._save_current_host()

        (self._other_hosts_etag, self._other_hosts) = self._load_other_hosts()

    def _load_other_hosts(self, previous_etag = None):
        '''Load all other hosts from cache, eventually refreshed from the server (only available online)'''

        other_hosts = {}
        etag = previous_etag

        # try a first load on cache, in particular to get the ETag
        if not etag:
            try:
                with open(os.path.join(self._host_file_dir, OTHER_HOST_FILENAME), 'r') as f:
                    file_content = json.load(f)
                    other_hosts = file_content['hosts']
                    etag  = file_content['ETag']
            except IOError:
                pass
        
        #TODO: FAKE for now, we will get the agregated list from the server (we need to check if we are offline first)
        # check cache with ETag (file is {ETag: etag, hosts: {}}
        
        
        # TODO: if cache is not valid, rewrite it

        return (etag, other_hosts)

    def _save_current_host(self):
        '''Save current host on disk'''
        
        LOG.debug("Save current host to disk")

        etag = hashlib.sha224(str(self.current_host)).hexdigest()
        
        if not os.path.isdir(self._host_file_dir):
            os.mkdir(self._host_file_dir)
        with open(os.path.join(self._host_file_dir, HOST_DATA_FILENAME), 'w') as f:
            json.dump({'ETag': etag, 'host': self.current_host}, f)
    
    
    def gethost_by_id(self, hostid):
        '''Get host dictionnary by id

        Return: hostname

        can trigger HostError exception if no hostname found for this id
        '''
        
        if hostid == self.current_host['hostid']:
            return self.current_host

        try:
            return self._other_hosts[hostid]
        except KeyError:
            raise HostError(_("No hostname registered for this id"))

    def gethostname_by_id(self, hostid):
        '''Get hostname by id

        Return: hostname

        can trigger HostError excpetion if no hostname found for this id
        '''
        
        LOG.debug("Get a hostname for %s", hostid)
        return self.gethost_by_id(hostid)['hostname']
        

    def gethostid_by_name(self, hostname):
        '''Get hostid by hostname

        Return: hostid

        can trigger HostError exception unexisting hostname
        or multiple hostid for this hostname
        '''
        
        LOG.debug("Get a hostid for %s", hostname)

        result_hostid = None
        if hostname == self.current_host['hostname']:
            result_hostid = self.current_host['hostid']
        for hostid in self._other_hosts:
            if hostname == self._other_hosts[hostid]['hostname']:
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

        LOG.debug("Request to compute an list of all hosts")
        result = {self.current_host['hostid']: (True, self.current_host['hostname'], self.current_host['share_inventory'])}
        for hostid in self._other_hosts:
            result[hostid] = (False, self._other_hosts[hostid]['hostname'], True)
        return result

    def set_share_inventory(self, share_inventory):
        '''Change if we share the current inventory to other hosts'''

        LOG.debug("Update current share_inventory state to %s" % share_inventory)
        self.current_host['share_inventory'] = share_inventory
        self._save_current_host()
        # TODO: update, and take the case into account once offline


