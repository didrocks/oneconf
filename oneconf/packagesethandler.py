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

from oneconf.package import Package
from oneconf.hosts import Hosts, HostError
from oneconf.distributor import get_distro

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

        # create cache for local package list (two keys: True/False, see diff())
        self.cache_this_computer_target_pkg_name = {}

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

        # check that host enabling storing inventory
        if not self.hosts.get_current_store_inventory_status():
            raise HostError(_("Current host doesn't allow saving the inventory, use --allow-store-inventory first"))

        this_computer_stored_pkg = self._get_packages_on_view_for_hostid(
                                    "get_all_pkg_by_hostid", self.hosts.hostid)
        logging.debug("Initial set: %s" % this_computer_stored_pkg)

        # get the list of update to do
        logging.debug("computing list of update to do")
        (this_computer_stored_pkg, pkg_to_create, pkg_to_update) = \
                            self._computepackagelist(this_computer_stored_pkg)
        # invalidate cache for others queries on the daemon
        self.cache_this_computer_target_pkg_name = {}
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

    def get_all(self, hostid=None, hostname=None):
        '''get all manually installed packages from the storage

        Return: * a double dictionnary, first indexed by hostid and then
                  by installed package name, with Package
                * a double dictionnary, first indexed by hostid and then
                  by removed package name, with Package
        '''

        hostid = self._get_hostid_from_context(hostid, hostname)
        installed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid \
                                 ("get_manuallyinstalled_pkg_by_hostid", hostid)
        removed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid \
                                 ("get_removed_pkg_by_hostid", hostid)
        # convert for dbus empty dict to ''
        if not installed_pkg_for_host:
            installed_pkg_for_host = ''
        if not removed_pkg_for_host:
            removed_pkg_for_host = ''
        return(installed_pkg_for_host, removed_pkg_for_host)

    def get_selection(self, hostid=None, hostname=None):
        '''get the package selection from the storage

        Selection is manually installed packages not part of default

        Return: * a double dictionnary, first indexed by hostid and then
                  by installed package name, with Package
        '''

        hostid = self._get_hostid_from_context(hostid, hostname)
        selection_for_host = self._get_simplified_packages_on_view_for_hostid \
                                        ("get_selection_pkg_by_hostid", hostid)
        # convert for dbus empty dict to ''
        if not selection_for_host:
            selection_for_host = ''
        return selection_for_host

    def diff(self, selection=True, hostid=None, hostname=None, use_cache=True):
        '''get a diff from current package state from another host

        This function can be use to make a diff for selection or for
        all packages.

        Return: * a double dictionnary, first indexed by hostid and then
                  by additionnal packages not present here, with
                  (time_added_on_hostid)
                * a double dictionnary, first indexed by hostid and then
                  by missing packages present on hostid, with
                  time_removed_on_hostid (=None if never present)
        '''

        logging.debug("Collecting every manually installed package on the system")
        try:
            if use_cache:
                this_computer_target_pkg_name = \
                            self.cache_this_computer_target_pkg_name[selection]
                logging.debug("Use local cache for selection to %s" % selection)
        except KeyError:
            use_cache = False
        if not use_cache:
            logging.debug("Compute the list of local cache for selection to %s"
                           % selection)
            (this_computer_pkg, pkg_to_create, pkg_to_update) = \
                                self._computepackagelist()
            if selection:
                logging.debug("Taking only selection")
            else:
                logging.debug("Taking all apps")
            this_computer_target_pkg_name = set()
            for pkg_name in this_computer_pkg:
                pkg = this_computer_pkg[pkg_name]
                if ((selection and pkg.selection) or
                    not (selection or pkg.auto_installed)):
                    this_computer_target_pkg_name.add(pkg_name)
            # cache the result
            self.cache_this_computer_target_pkg_name[selection] = \
                                                   this_computer_target_pkg_name
        
        logging.debug("Comparing to others hostid")
        installed_pkg_for_host = {}
        selection_for_host = {}
        removed_pkg_for_host = {}
        hostid = self._get_hostid_from_context(hostid, hostname)
        logging.debug("Comparing to %s", hostid)
        installed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid \
                                    ("get_installed_pkg_by_hostid", hostid)
        removed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid \
                                    ("get_removed_pkg_by_hostid", hostid)
        if selection:
            selection_for_host = \
                self._get_simplified_packages_on_view_for_hostid \
                                    ("get_selection_pkg_by_hostid", hostid)
        # additionally installed selection on hostid not present locally
        additional_target_pkg_for_host = {}
        if selection:
            target_reference_list = selection_for_host
        else:
            target_reference_list = installed_pkg_for_host
        for pkg_name in target_reference_list:
            if not pkg_name in this_computer_target_pkg_name:
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

    def _get_simplified_packages_on_view_for_hostid(self, view_name, hostid):
        '''load records from CouchDB and return a simplified view

        Contrary to _get_packages_on_view_for_hostid, this function doesn't
        Build package object (to be compatible with dbus interface)
        Return: get dictionnary of all packages in the DB respecting the view
                with: {pkg_name : (last_modification, distro_channel)}
        '''
        results = self.database.execute_view(view_name)
        pkg_for_hostid = {}
        for rec in results[hostid]:
            pkg_for_hostid[rec.value["name"]] = (rec.value["last_modification"],
                                                 rec.value["distro_channel"])
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
        

    def _get_dep_rec_list(self, root_package, default_packages, apt_cache,
                          recursive=True):
            '''Get list of dep of package_root, add them to default_packages'''

            # if no candidate package available, give up
            if not root_package.candidate:
		return

            if self.distro.is_recommends_as_dep():
                relations_list = (root_package.candidate.dependencies,
                                  root_package.candidate.recommends)
            else:
                relations_list = (root_package.candidate.dependencies)

            for relations in relations_list:
                for dep in relations:
                    for or_dep in dep.or_dependencies:
                        # don't introspect same package twice (or more)
                        if or_dep.name not in default_packages:
                            default_packages.add(or_dep.name)
                            try:
                                if recursive:
                                    self._get_dep_rec_list \
                                        (apt_cache[or_dep.name],
                                         default_packages, apt_cache)
                            except KeyError:
                                pass

    def _get_default_package_list(self, apt_cache):
        '''Get default package installed in the distribution

        Return: set of default packages from the meta_package
        '''

        default_packages = set()
        # these are false default package as alternatives deps are taken
        # into account by the algorithm like file-roller depends zip | p7zip-full
        # -> p7zip-full won't be listed as it will be in "default" on ubuntu
        false_defaults = self.distro.get_false_defaults()
        meta_package_list = self.distro.get_distribution_meta_packages()

        for meta_package in meta_package_list:
            if apt_cache[meta_package].is_installed:
                self._get_dep_rec_list(apt_cache[meta_package],
                                       default_packages, apt_cache)
        default_packages -= false_defaults
        return default_packages

    def _computepackagelist(self, stored_pkg=None):
        '''Introspect what's installed on this hostid

        Return: stored_pkg of all package states for this hostid
                set of package to create if in update mode (empty otherwise)
                set of package to update if in update mode (empty otherwise)
        '''

        apt_cache = apt.Cache()

        default_packages = self._get_default_package_list(apt_cache)

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
            selection = False
            origin = ''
            if pkg.candidate:
                origin = pkg.candidate.origins[0]
            if pkg.is_installed:
                installed = True
                if not pkg.is_auto_installed:
                    auto_installed = False
                    if not pkg.priority in ('required', 'important'):
                        if not pkg.name in default_packages:
                            selection = True
            # check if update/creation is needed for that package
            if updating:
                try:
                    if stored_pkg[pkg.name].update_needed(installed,
                           auto_installed, selection, self.current_time,
                           str(origin)):
                        pkg_to_update.add(stored_pkg[pkg.name])
                except KeyError:
                    # new package, we are only interested in installed and not
                    # auto_installed for initial storage
                    if installed and not auto_installed:
                        stored_pkg[pkg.name] = Package(self.hosts.hostid, pkg.name,
                            True, False, selection, self.current_time,
                            str(origin))
                        pkg_to_create.add(stored_pkg[pkg.name])
            else:
                # for making a diff, we are only interested in packages
                # installed and not auto_installed for this host
                if installed and not auto_installed:
                    stored_pkg[pkg.name] = Package(self.hosts.hostid, pkg.name,
                        True, False, selection, self.current_time,
                        str(origin))
                    # this is only for first load on an host in update mode:
                    # don't lost time to get KeyError on stored_pkg[pkg.name].
                    # pkg_to_create isn't relevant for read mode
                    pkg_to_create.add(stored_pkg[pkg.name])

        return stored_pkg, pkg_to_create, pkg_to_update

