# Copyright (C) 2010 Canonical
# Author: Didier Roche <didrocks@ubuntu.com>
# This program is free software: you can redistribute it and/or modify it 
# under the terms of the GNU General Public License version 3, as published 
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but 
# WITHOUT ANY WARRANTY; without even the implied warranties of 
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR 
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along 
# with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import platform
import uuid

from desktopcouch.records.server import CouchDatabase  
from desktopcouch.records.record import Record as CouchRecord  
ONECONF_HOSTS_RECORD_TYPE = "http://wiki.ubuntu.com/OneConf/Record/Hosts"

import gettext
from gettext import gettext as _

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

        database = CouchDatabase("oneconf_hosts", create=True)
        if not database.view_exists("get_hosts"):
            viewfn = 'function(doc) { emit(null, doc); }'
            database.add_view("get_hosts", viewfn, None, None)
        self._hosts = {}
        self.hostid = str(uuid.getnode())
        self.hostname = platform.node()

        results = database.execute_view("get_hosts")
        for rec in results:
            if (rec.id == self.hostid and
                rec.value['hostname'] != self.hostname):
                update = {'hostname': self.hostname}
                logging.debug("Update current hostname")
                database.update_fields(rec.id, update)
                self._hosts[self.hostid] = self.hostname
            else:
                self._hosts[rec.id] = rec.value['hostname']
        if self.hostid not in self._hosts:
            logging.debug("Adding new hosts")
            record = CouchRecord({"hostname": self.hostname},
                                 record_id=self.hostid,
                                 record_type=ONECONF_HOSTS_RECORD_TYPE)
            database.put_record(record)
            self._hosts[self.hostid] = self.hostname

    def gethostname_by_id(self, hostid):
        '''Get hostname by id

        Return: hostname

        can trigger HostError excpetion if no hostname found for this id
        '''
        try:
            return self._hosts[hostid]
        except KeyError:
            raise HostError(_("No hostname registered for this id"))

    def gethostid_by_name(self, hostname):
        '''Get hostid by hostname

        Return: tuple of hostid

        can trigger HostError exception unexisting hostname in the DB
        '''

        result_hostid = []
        for hostid in self._hosts:
            if hostname == self._hosts[hostid]:
                result_hostid.append(hostid)

        if not result_hostid:
            raise HostError(_("No hostid registered for this hostname"))
        return result_hostid

    def get_all_hosts(self):
        '''Return a dictionnary of all hosts'''

        return self._hosts

