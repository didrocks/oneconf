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


import apt
import logging
import time
import re

import gettext
from gettext import gettext as _

from desktopcouch.records.server import CouchDatabase  
from desktopcouch.records.record import Record as CouchRecord  
ONECONF_PACKAGE_RECORD_TYPE = "http://wiki.ubuntu.com/OneConf/Record/Package"

from oneconf.hosts import Hosts, HostError
from oneconf.distributor import get_distro
from oneconf.desktopcouchstate import get_last_sync_date

class PackageSetHandler(object):
    """
    Direct access to database for getting and updating the list
    """

    def __init__(self, hosts=None):
        # Connect to CouchDB and create the database  
        self.database = CouchDatabase("oneconf_pkg", create=True)
        self.hosts = hosts
        if not hosts:
            self.hosts = Hosts()
        self.distro = get_distro()
        self.current_time = time.time()
        self.last_desktopcouch_sync = get_last_sync_date()

        # create cache for storage package list (two keys: view_name, hostid)
        self.cache_pkg_storage = {}

        # Be careful get_manuallyinstalled_pkg_for_hostid + get_removed_pkg_for_hostid
        # != storage for hostid. There are manually installed packages, which
        # have been marked as automatic then
        # listing them doesn't seem relevant as of today
        if not self.database.view_exists("get_all_pkg_by_hostid"):  
            viewfn = 'function(doc) { emit(doc.hostid, doc); }'
            self.database.add_view("get_all_pkg_by_hostid", viewfn, None, None)
        if not self.database.view_exists("get_installed_pkg_by_hostid"):  
            viewfn = 'function(doc) { if (doc.installed) { emit(doc.hostid, doc) }; }'
            self.database.add_view("get_installed_pkg_by_hostid", viewfn, None, None)
        if not self.database.view_exists("get_manuallyinstalled_pkg_by_hostid"):  
            viewfn = 'function(doc) { if (doc.installed && !doc.auto_installed) { emit(doc.hostid, doc) }; }'
            self.database.add_view("get_manuallyinstalled_pkg_by_hostid", viewfn, None, None)
        if not self.database.view_exists("get_selection_pkg_by_hostid"):  
            viewfn = 'function(doc) { if (doc.installed && !doc.auto_installed && doc.selection) { emit(doc.hostid, doc) }; }'
            self.database.add_view("get_selection_pkg_by_hostid", viewfn, None, None)
        if not self.database.view_exists("get_removed_pkg_by_hostid"):  
            viewfn = 'function(doc) { if (!doc.installed) { emit(doc.name, doc) }; }'
            self.database.add_view("get_removed_pkg_by_hostid", viewfn, None, None)
        if not self.database.view_exists("get_all_pkg_by_hostid_and_name"):  
            viewfn = 'function(doc) { emit([doc.hostid,doc.name], doc); }'  
            self.database.add_view("get_all_pkg_by_hostid_and_name", viewfn, None, None)

    def update(self):
        '''update the database'''

        this_computer_stored_pkg = self._get_packages_on_view_for_hostid(
                                    "get_all_pkg_by_hostid", self.hosts.hostid)
        logging.debug("Initial set: %s" % this_computer_stored_pkg)

        # get the list of update to do
        logging.debug("computing list of update to do")
        (this_computer_stored_pkg, pkg_to_create, pkg_to_update) = \
                            self._computepackagelist(this_computer_stored_pkg)
        # invalidate cache for others queries on the daemon
        self.cache_pkg_storage = {}
        logging.debug("After update, it will be: %s" % this_computer_stored_pkg)

        # update minimal set of records
        logging.debug("creating new package objects")
        new_records = []
        for pkg in pkg_to_create:
            new_records.append(self._new_record(pkg))
        logging.debug("pushing new object to couchdb")
        self.database.put_records_batch(new_records)
        logging.debug("creating new update objects")
        for pkg in pkg_to_update:
            self._update_record(pkg)

    def get_all(self, hostid=None, hostname=None, use_cache=True):
        '''get all manually installed packages from the storage

        Return: * a double dictionnary, first indexed by hostid and then
                  by installed package name, with Package
                * a double dictionnary, first indexed by hostid and then
                  by removed package name, with Package
        '''

        hostid = self._get_hostid_from_context(hostid, hostname)
        installed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid \
                                 ("get_manuallyinstalled_pkg_by_hostid", hostid, use_cache)
        removed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid \
                                 ("get_removed_pkg_by_hostid", hostid, use_cache)
        # convert for dbus empty dict to ''
        if not installed_pkg_for_host:
            installed_pkg_for_host = ''
        if not removed_pkg_for_host:
            removed_pkg_for_host = ''
        return(installed_pkg_for_host, removed_pkg_for_host)

    def get_selection(self, hostid=None, hostname=None, use_cache=True):
        '''get the package selection from the storage

        Selection is manually installed packages not part of default

        Return: * a double dictionnary, first indexed by hostid and then
                  by installed package name, with Package
        '''

        hostid = self._get_hostid_from_context(hostid, hostname)
        selection_for_host = self._get_simplified_packages_on_view_for_hostid \
                                        ("get_selection_pkg_by_hostid", hostid, use_cache)
        # convert for dbus empty dict to ''
        if not selection_for_host:
            selection_for_host = ''
        return selection_for_host

    def diff(self, selection=True, hostid=None, hostname=None, use_cache=True):
        '''get a diff from current package state from another host

        This function can be use to make a diff for selection or for
        all packages.
, use_cache
        Return: * a double dictionnary, first indexed by hostid and then
                  by additionnal packages not present here, with
                  (time_added_on_hostid)
                * a double dictionnary, first indexed by hostid and then
                  by missing packages present on hostid, with
                  time_removed_on_hostid (=None if never present)
        '''

        logging.debug("Collecting all manually installed packages on this system")
        all_this_computer_pkg_name = \
            self._get_simplified_packages_on_view_for_hostid \
                                ("get_manuallyinstalled_pkg_by_hostid", self.hosts.hostid, use_cache)
        if selection:
            logging.debug("Collecting installed selection on this system")
            this_computer_target_pkg_name = \
                self._get_simplified_packages_on_view_for_hostid \
                                    ("get_selection_pkg_by_hostid", self.hosts.hostid, use_cache)
        else:
            this_computer_target_pkg_name = all_this_computer_pkg_name
        
        logging.debug("Comparing to others hostid")
        installed_pkg_for_host = {}
        selection_for_host = {}
        removed_pkg_for_host = {}
        hostid = self._get_hostid_from_context(hostid, hostname)
        logging.debug("Comparing to %s", hostid)
        installed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid \
                                    ("get_installed_pkg_by_hostid", hostid, use_cache)
        removed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid \
                                    ("get_removed_pkg_by_hostid", hostid, use_cache)
        if selection:
            selection_for_host = \
                self._get_simplified_packages_on_view_for_hostid \
                                    ("get_selection_pkg_by_hostid", hostid, use_cache)
        # additionally installed selection on hostid not present locally
        additional_target_pkg_for_host = {}
        if selection:
            target_reference_list = selection_for_host
        else:
            target_reference_list = installed_pkg_for_host
        for pkg_name in target_reference_list:
            # comparing to all_this_computer_pkg_name and not to this_computer_target_pkg_name
            # to avoid some fanzy cases (like app coming in
            # default will be shown as deleted otherwise, same for
            # manually installed -> auto installed)
            if not pkg_name in all_this_computer_pkg_name:
                added_str_pkg_on_hostid = target_reference_list[pkg_name]
                additional_target_pkg_for_host[pkg_name] = \
                                                        added_str_pkg_on_hostid
        #  missing selection on hostid present locally
        removed_target_pkg_for_host = {}
        for pkg_name in this_computer_target_pkg_name:
            # comparing to installed_pkg_for_host and not to selection_for_host
            # to avoid some fanzy cases (like app coming in
            # default will be shown as deleted otherwise, same for
            # manually installed -> auto installed)
            if not pkg_name in installed_pkg_for_host:
                try:
                    removed_str_pkg_on_hostid = removed_pkg_for_host[pkg_name]
                except KeyError:
                    removed_str_pkg_on_hostid = ('', '')
                removed_target_pkg_for_host[pkg_name] = removed_str_pkg_on_hostid
        # convert for dbus empty dict to ''
        if not additional_target_pkg_for_host:
            additional_target_pkg_for_host = ''
        if not removed_target_pkg_for_host:
            removed_target_pkg_for_host = ''
        logging.debug(additional_target_pkg_for_host)
        logging.debug(removed_target_pkg_for_host)
        return(additional_target_pkg_for_host, removed_target_pkg_for_host)

    def check_if_desktopcouch_refreshed(self):
        '''check if desktopcouch has refreshed, invalidate caches if so'''
        new_sync = get_last_sync_date()
        if self.last_desktopcouch_sync != new_sync:
            logging.debug('Invalide cache as desktopcouch has been synced')
            self.cache_pkg_storage = {}
            self.last_desktopcouch_sync = new_sync
        logging.debug('same sync')

    def _get_packages_on_view_for_hostid(self, view_name, hostid):
        '''load records from CouchDB

        Return: get dictionnary of all packages in the DB respecting the view
                with: {pkg_name : Package}
        '''
        results = self.database.execute_view(view_name)
        pkg_for_hostid = {}
        for rec in results[hostid]:
            pkg_name = rec.value["name"]
            pkg_for_hostid[pkg_name] = Package(hostid, pkg_name,
                rec.value["installed"], rec.value["auto_installed"],
                rec.value["selection"], rec.value["last_modification"],
                rec.value["distro_channel"])
        return pkg_for_hostid

    def _get_simplified_packages_on_view_for_hostid(self, view_name, hostid, use_cache):
        '''load records from CouchDB and return a simplified view

        Contrary to _get_packages_on_view_for_hostid, this function doesn't
        Build package object (to be compatible with dbus interface)
        Return: get dictionnary of all packages in the DB respecting the view
                with: {pkg_name : (last_modification, distro_channel)}
        '''

        try:
            if use_cache:
                pkg_for_hostid = \
                            self.cache_pkg_storage[view_name][hostid]
                logging.debug("Use local cache for %s view to %s hostid" % (view_name, hostid))
        except KeyError:
            use_cache = False
        if not use_cache:
            results = self.database.execute_view(view_name)
            pkg_for_hostid = {}
            for rec in results[hostid]:
                pkg_for_hostid[rec.value["name"]] = (rec.value["last_modification"],
                                                     rec.value["distro_channel"])
        # cache the result
        if not view_name in self.cache_pkg_storage:
            self.cache_pkg_storage[view_name] = {}
        self.cache_pkg_storage[view_name][hostid] = pkg_for_hostid
        return pkg_for_hostid

    def _get_hostid_from_context(self, hostid=None, hostname=None):
        '''get and check hostid

        if hostid and hostname are none, hostid is the current one
        Return: the corresponding hostid, raise an error if multiple hostid
                for an hostname
        '''

        if not hostid and not hostname:
            hostid = self.hosts.hostid
        if hostid:
            # just checking it exists
            self.hosts.gethostname_by_id(hostid)
            hostid = hostid
        else:
            hostid = self.hosts.gethostid_by_name(hostname) 
        return hostid

    def _update_record(self, pkg):
        '''Update an existing record matching (hostid, package)'''

        rec = None
        update = {}
        results = self.database.execute_view("get_all_pkg_by_hostid_and_name")
        for rec in results[[pkg.hostid, pkg.name]]:
            update["installed"] = pkg.installed
            update["auto_installed"] = pkg.auto_installed
            update["selection"] = pkg.selection
            update["last_modification"] = pkg.last_modification
            update["distro_channel"] = pkg.distro_channel
            self.database.update_fields(rec.id, update)
        if not rec:
            logging.warning("Try to update a non existing record: %s, %s",
                            pkg.hostid, pkg.name)

    def _new_record(self, pkg):
        '''Create a new record for a new package never stored in CouchDB

        Return: new record ready to be pushed in CouchDB
        '''

        return CouchRecord({"hostid": pkg.hostid,
                              "name": pkg.name,
                              "installed": pkg.installed,
                              "auto_installed": pkg.auto_installed,
                              "selection": pkg.selection,
                              "last_modification": pkg.last_modification,
                              "distro_channel": pkg.distro_channel
                               }, ONECONF_PACKAGE_RECORD_TYPE)
        

    def _computepackagelist(self, stored_pkg=None):
        '''Introspect what's installed on this hostid

        Return: stored_pkg of all package states for this hostid
                set of package to create if in update mode (empty otherwise)
                set of package to update if in update mode (empty otherwise)
        '''

        apt_cache = apt.Cache()

        # speedup first batch package insertion and
        # when computing list in read mode for diff between hostA and this host
        if stored_pkg:
            updating = True
        else:
            stored_pkg = {}
            updating = False            

        # get list of all apps installed
        installed_packages = {}
        pkg_to_update = set()
        pkg_to_create = set()
        for pkg in apt_cache:
            installed = False
            auto_installed = False
            origin = ''
            if pkg.candidate:
                origin = pkg.candidate.origins[0]
            if pkg.is_installed:
                installed = True
                if not pkg.is_auto_installed:
                    auto_installed = False
            # check if update/creation is needed for that package
            if updating:
                try:
                    if stored_pkg[pkg.name].update_needed(installed,
                           auto_installed, self.current_time,
                           str(origin)):
                        pkg_to_update.add(stored_pkg[pkg.name])
                except KeyError:
                    # new package, we are only interested in installed and not
                    # auto_installed for initial storage
                    if installed and not auto_installed:
                        stored_pkg[pkg.name] = Package(self.hosts.hostid, pkg.name,
                            True, False, self.current_time,
                            str(origin))
                        pkg_to_create.add(stored_pkg[pkg.name])
            else:
                # for making a diff, we are only interested in packages
                # installed and not auto_installed for this host
                if installed and not auto_installed:
                    stored_pkg[pkg.name] = Package(self.hosts.hostid, pkg.name,
                        True, False, self.current_time,
                        str(origin))
                    # this is only for first load on an host in update mode:
                    # don't lost time to get KeyError on stored_pkg[pkg.name].
                    # pkg_to_create isn't relevant for read mode
                    pkg_to_create.add(stored_pkg[pkg.name])

        return stored_pkg, pkg_to_create, pkg_to_update

