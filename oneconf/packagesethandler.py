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
        if not self.database.view_exists("get_app_codec_pkg_by_hostid"):  
            viewfn = 'function(doc) { if (doc.installed && !doc.auto_installed && doc.app_codec) { emit(doc.hostid, doc) }; }'
            self.database.add_view("get_app_codec_pkg_by_hostid", viewfn, None, None)
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
            self._get_simplified_packages_on_view_for_hostid("get_manuallyinstalled_pkg_by_hostid", hostid)
        remove_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid("get_removed_pkg_by_hostid", hostid)
        # convert for dbus empty dict to ''
        if not installed_pkg_for_host:
            installed_pkg_for_host = ''
        if not remove_pkg_for_host:
            remove_pkg_for_host = ''
        return(installed_pkg_for_host, remove_pkg_for_host)

    def get_appscodec(self, hostid=None, hostname=None):
        '''get all apps codecs installed packages from the storage

        Return: * a double dictionnary, first indexed by hostid and then
                  by installed package name, with Package
        '''

        hostid = self._get_hostid_from_context(hostid, hostname)
        apps_codec_for_host = \
            self._get_simplified_packages_on_view_for_hostid("get_app_codec_pkg_by_hostid", hostid)
        # convert for dbus empty dict to ''
        if not apps_codec_for_host:
            apps_codec_for_host = ''
        return apps_codec_for_host

    def diff(self, only_appscodec=True, hostid=None, hostname=None):
        '''get a diff from current package state from another host

        This function can be use to make a diff for only apps_codec or for
        all packages.

        Return: * a double dictionnary, first indexed by hostid and then
                  by additionnal packages not present here, with
                  (time_added_on_hostid)
                * a double dictionnary, first indexed by hostid and then
                  by missing packages present on hostid, with
                  time_removed_on_hostid (=None if never present)
        '''

        logging.debug("Collecting every manually installed package on the system")
        (this_computer_pkg, pkg_to_create, pkg_to_update) = \
                            self._computepackagelist()
        if only_appscodec:
            logging.debug("Taking only apps_codecs")
        else:
            logging.debug("Taking all apps")
        this_computer_target_pkg_name = set()
        for pkg_name in this_computer_pkg:
            pkg = this_computer_pkg[pkg_name]
            if (only_appscodec and pkg.app_codec) or not (only_appscodec or pkg.auto_installed):
                this_computer_target_pkg_name.add(pkg_name)
        
        logging.debug("Comparing to others hostid")
        installed_pkg_for_host = {}
        app_codec_for_host = {}
        removed_pkg_for_host = {}
        additional_target_pkg_for_host = {}
        removed_target_pkg_for_host = {}
        hostid = self._get_hostid_from_context(hostid, hostname)
        logging.debug("Comparing to %s", hostid)
        installed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid("get_installed_pkg_by_hostid", hostid)
        removed_pkg_for_host = \
            self._get_simplified_packages_on_view_for_hostid("get_removed_pkg_by_hostid", hostid)
        if only_appscodec:
            app_codec_for_host = \
                self._get_simplified_packages_on_view_for_hostid("get_app_codec_pkg_by_hostid", hostid)
        # additionally installed apps/codec on hostid not present locally
        additional_target_pkg_for_host = {}
        if only_appscodec:
            target_reference_list = app_codec_for_host
        else:
            target_reference_list = installed_pkg_for_host
        for pkg_name in target_reference_list:
            if not pkg_name in this_computer_target_pkg_name:
                time_added_on_hostid = target_reference_list[pkg_name]
                additional_target_pkg_for_host[pkg_name] = \
                                                        time_added_on_hostid
        #  missing apps/codec on hostid present locally
        removed_target_pkg_for_host = {}
        for pkg_name in this_computer_target_pkg_name:
            # comparing to installed_pkg_for_host because and not app_codec_for_host
            # in any case to avoid some fanzy cases (like app coming in
            # default will be shown as deleted otherwise, same for
            # manually installed -> auto installed)
            if not pkg_name in installed_pkg_for_host:
                try:
                    time_removed_on_hostid = removed_pkg_for_host[pkg_name]
                except KeyError:
                    time_removed_on_hostid = None
                removed_target_pkg_for_host[pkg_name] = time_removed_on_hostid
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
                rec.value["app_codec"], rec.value["last_modification"],
                rec.value["distro_channel"])
        return pkg_for_hostid

    def _get_simplified_packages_on_view_for_hostid(self, view_name, hostid):
        '''load records from CouchDB and return a simplified view

        Contrary to _get_packages_on_view_for_hostid, this function doesn't
        Build package object (to be compatible with dbus interface)
        Return: get dictionnary of all packages in the DB respecting the view
                with: {pkg_name : last_modification}
        '''
        results = self.database.execute_view(view_name)
        pkg_for_hostid = {}
        for rec in results[hostid]:
            pkg_for_hostid[rec.value["name"]] = rec.value["last_modification"]
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
            update["app_codec"] = pkg.app_codec
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
                              "app_codec": pkg.app_codec,
                              "last_modification": pkg.last_modification,
                              "distro_channel": pkg.distro_channel
                               }, ONECONF_PACKAGE_RECORD_TYPE)
        

    def _get_dep_rec_list(self, root_package, default_packages, apt_cache,
                          recursive=True):
            '''Get list of dep of package_root, add them to default_packages'''

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
                                    self._get_dep_rec_list(apt_cache[or_dep.name],
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

        # additional_packages to take by default
        additional_packages = self.distro.get_additional_packages(self, apt_cache)
        default_packages = self._get_default_package_list(apt_cache)

        # determine wether an app is an app_codec package or not
        blacklist_pkg_regexp = self.distro.get_blacklist_regexp()
        desktop_pkg_file_pattern = re.compile('/usr/share/applications/.*\.desktop')
        executable_file_pattern = re.compile('^(/usr)?/s?bin/.*')

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
            app_codec = False
            if pkg.is_installed:
                installed = True
                if not pkg.is_auto_installed:
                    auto_installed = False
                    if not pkg.priority in ('required', 'important'):
                        if pkg.name in additional_packages:
                            app_codec = True
                        elif (pkg.name in default_packages or
                              blacklist_pkg_regexp.match(pkg.name)):
                            pass
                        else:
                            for pkg_file in pkg.installed_files:
                                if (desktop_pkg_file_pattern.match(pkg_file) or
                                    executable_file_pattern.match(pkg_file)):
                                    app_codec = True
                                    break
                else:
                    auto_installed = True
            # discover if update/creation is needed for that package
            if updating:
                try:
                    if stored_pkg[pkg.name].update_needed(installed,
                           auto_installed, app_codec, self.current_time,
                           self.distro.get_distro_channel_name()):
                        pkg_to_update.add(stored_pkg[pkg.name])
                except KeyError:
                    # new package, we are only interested in installed and not
                    # auto_installed for initial storage
                    if installed and not auto_installed:
                        stored_pkg[pkg.name] = Package(self.hosts.hostid, pkg.name,
                            True, False, app_codec, self.current_time,
                            self.distro.get_distro_channel_name())
                        pkg_to_create.add(stored_pkg[pkg.name])
            else:
                # for making a diff, we are only interested in packages
                # installed and not auto_installed for this host
                if installed and not auto_installed:
                    stored_pkg[pkg.name] = Package(self.hosts.hostid, pkg.name,
                        True, False, app_codec, self.current_time,
                        self.distro.get_distro_channel_name())
                    # this is only for first load on an host in update mode:
                    # don't lost time to get KeyError on stored_pkg[pkg.name].
                    # pkg_to_create isn't relevant for read mode
                    pkg_to_create.add(stored_pkg[pkg.name])

        return stored_pkg, pkg_to_create, pkg_to_update

