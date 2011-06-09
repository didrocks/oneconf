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

LOG = logging.getLogger(__name__)

from oneconf.hosts import Hosts, HostError
from oneconf.distributor import get_distro
from oneconf.paths import ONECONF_CACHE_DIR, PACKAGE_LIST_FILENAME

class PackageSetHandler(object):
    """
    Direct access to database for getting and updating the list
    """

    def __init__(self, hosts=None):

        self.hosts = hosts
        if not hosts:
            self.hosts = Hosts()
        self.distro = get_distro()
        self.last_storage_sync = None

        # create cache for storage package list, indexed by hostid
        self.package_list = {}
    

    def update(self):
        '''update the database with package list'''

        hostid = self.hosts.current_host['hostid']
        
        LOG.debug("Updating package list")
        newpkg_list = self.distro.compute_local_packagelist()
        
        LOG.debug("Creating the etag")
        etag = hashlib.sha224(str(newpkg_list)).hexdigest()
        
        if not hostid in self.package_list:
            self.package_list[hostid] = {}
            (self.package_list[hostid]['ETag'], self.package_list[hostid]['package_list']) = self._get_installed_packages_etag(hostid)
        
        if etag != self.package_list[hostid]['ETag']:
            LOG.debug("Package list need refresh")
            self.package_list[hostid]['ETag'] = etag
            self.package_list[hostid]['package_list'] = newpkg_list
            with open(os.path.join(ONECONF_CACHE_DIR, hostid, PACKAGE_LIST_FILENAME), 'w') as f:
                json.dump(self.package_list[hostid], f)
            LOG.debug("Update done")
        else:
            LOG.debug("No refresh needed")
    
    def get_packages(self, hostid=None, hostname=None, only_manual=False):        
        '''get all installed packages from the storage'''
        
        hostid = self._get_hostid_from_context(hostid, hostname)
        LOG.debug ("Request for package list for %s with only manual packages reduced scope to: %s", hostid, only_manual)
        package_list = self._get_installed_packages_etag(hostid)[1]
        if only_manual:
            package_list = [package_elem for package_elem in package_list if package_list[package_elem]["auto"] == False]
        return package_list
        
    
    def _get_installed_packages_etag(self, hostid):
        '''get all etag, installed packages from the storage
        
        Return: (etag, package_list)'''
        
        try:
            etag = self.package_list[hostid]['ETag']
            package_list = self.package_list[hostid]['package_list']
            LOG.debug("Hit cache for package list")
        except KeyError:
            self.package_list[hostid] = self._get_packagelist_from_store(hostid)
            etag = self.package_list[hostid]['ETag']
            package_list = self.package_list[hostid]['package_list']
        return (etag, package_list)
        

    def diff(self, distant_hostid=None, distant_hostname=None):
        '''get a diff from current package state from another host

        This function can be use to make a diff between all packages installed on both computer
, use_cache
        Return: (packages_to_install (packages in distant_hostid not in local_hostid),
                 packages_to_remove (packages in local hostid not in distant_hostid))
        '''
        
        distant_hostid = self._get_hostid_from_context(distant_hostid, distant_hostname)
        
        LOG.debug("Collecting all installed packages on this system")
        local_package_list = set(self.get_packages(self.hosts.current_host['hostid'], False))
        
        LOG.debug("Collecting all installed packages on the other system")
        distant_package_list = set(self.get_packages(distant_hostid, False))

        LOG.debug("Comparing")
        packages_to_install = [x for x in local_package_list if x not in distant_package_list]
        packages_to_remove = [x for x in distant_package_list if x not in local_package_list]
        
        # for Dbus which doesn't like empty list
        if not packages_to_install:
            packages_to_install = ''
        if not packages_to_remove:
            packages_to_remove = ''
        
        return(packages_to_install, packages_to_remove)

    def check_if_storage_refreshed(self):
        '''check if server storage has refreshed, invalidate caches if so'''
        new_sync = get_last_sync_date()
        if self.last_storage_sync != new_sync:
            LOG.debug('Invalide cache as storage has been synced')
            self.cache_pkg_storage = {}
            self.last_storage_sync = new_sync
        LOG.debug('same sync')

    def _get_hostid_from_context(self, hostid=None, hostname=None):
        '''get and check hostid

        if hostid and hostname are none, hostid is the current one
        Return: the corresponding hostid, raise an error if multiple hostid
                for an hostname
        '''

        if not hostid and not hostname:
            hostid = self.hosts.current_host['hostid']
        if hostid:
            # just checking it exists
            self.hosts.gethost_by_id(hostid)
            hostid = hostid
        else:
            hostid = self.hosts.gethostid_by_name(hostname) 
        return hostid
        
        
    def _get_packagelist_from_store(self, hostid):
        '''load package list for every computer in cache'''
        
        LOG.debug('get package list from store for hostid: %s' % hostid)
        pkg_list = {'ETag': None, "package_list": set ()}

        # try a first load on cache, in particular to get the ETag
        try:
            with open(os.path.join(ONECONF_CACHE_DIR, hostid, PACKAGE_LIST_FILENAME), 'r') as f:
                pkg_list = json.load(f)
                etag = pkg_list['ETag']
        except IOError:
            etag = None
        
        #TODO: FAKE for now, we will get the agregated list from the server (we need to check if we are offline first)
        # check cache with ETag (file is {ETag: etag, packages: {}}
        
        
        # TODO: if cache is not valid, rewrite it
        
        return pkg_list
        


