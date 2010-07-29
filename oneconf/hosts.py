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


import logging
import platform

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

        self.database = CouchDatabase("oneconf_hosts", create=True)
        if not self.database.view_exists("get_hosts"):
            viewfn = 'function(doc) { emit(null, doc); }'
            self.database.add_view("get_hosts", viewfn, None, None)
        self._hosts = {}
        self.hostid = open('/var/lib/dbus/machine-id').read()[:-1]
        self.hostname = platform.node()
        # faking this id for testing purpose
        #self.hostid = 'BBBBBB'
        #self.hostname = "foomachine"

        results = self.database.execute_view("get_hosts")
        for rec in results:
            if (rec.id == self.hostid and
                rec.value['hostname'] != self.hostname):
                update = {'hostname': self.hostname}
                logging.debug("Update current hostname")
                self.database.update_fields(rec.id, update)
                self._hosts[self.hostid] = {'hostname': self.hostname,
                                            'show_inventory': rec.value['show_inventory'],
                                            'show_others': rec.value['show_others']}
            else:
                self._hosts[rec.id] = {'hostname': rec.value['hostname'],
                                       'show_inventory': rec.value['show_inventory'],
                                       'show_others': rec.value['show_others']}

        if self.hostid not in self._hosts:
            logging.debug("Adding this host to storage")
            record = CouchRecord({"hostname": self.hostname,
                                  "show_inventory": False,
                                  "show_others": True},
                                 record_id=self.hostid,
                                 record_type=ONECONF_HOSTS_RECORD_TYPE)
            self.database.put_record(record)
            self._hosts[self.hostid] = {'hostname': self.hostname,
                                        'show_inventory': False,
                                        'show_other': True}

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

        Return: hostid

        can trigger HostError exception unexisting hostname in the DB
        or multiple hostid for this hostname
        '''

        result_hostid = None
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

        result = {}
        for hostid in self._hosts:
            current = (hostid == self.hostid)
            curr_host = self._hosts[hostid]
            result[hostid] = (current, curr_host['hostname'],
                              curr_host.get('show_inventory', False),
                              curr_host.get('show_others', False))
        return result

    def set_show_inventory(self, show_inventory, others):
        '''Change if show current inventory to other hosts or other inventory to this host'''

        if others:
            logging.debug("Update show_others to %s" % show_inventory)
            self._hosts[self.hostid]['show_others'] = show_inventory
            update = {'show_others': show_inventory}
        else:
            logging.debug("Update current show_inventory to %s" % show_inventory)
            self._hosts[self.hostid]['show_inventory'] = show_inventory
            update = {'show_inventory': show_inventory}
        self.database.update_fields(self.hostid, update)


