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

class PackageSetHandler(object):
    """
    Direct access to database for getting and updating the list
    """

    def __init__(self):
        # Connect to CouchDB and create the database  
        self.database = CouchDatabase("oneconf_pkg", create=True)
        self.hostid = "AZERTYFTW"
        self.current_time = time.time()

        if not self.database.view_exists("get_pkg_by_hostid"):  
            viewfn = 'function(doc) { emit(doc.hostid, doc); }'
            self.database.add_view("get_pkg_by_hostid", viewfn, None, None)
        if not self.database.view_exists("get_app_codec_by_hostid"):  
            viewfn = 'function(doc) { if (doc.app_codec) { emit(doc.hostid, doc) }; }'
            self.database.add_view("get_app_codec_by_hostid", viewfn, None, None)
        if not self.database.view_exists("get_pkg_by_hostid_name"):  
            viewfn = 'function(doc) { emit([doc.hostid,doc.name], doc); }'  
            self.database.add_view("get_pkg_by_hostid_name", viewfn, None, None)


    def update(self):
        '''update the database'''

        this_computer_stored_pkg = self._load_pkg_on_hostid(self.hostid)
        logging.debug("Initial set: %s" % this_computer_stored_pkg)

        # get the list of update to do
        logging.debug("computing list of update to do")
        (this_computer_stored_pkg, pkg_to_create, pkg_to_update) = \
                            self._computepackagelist(this_computer_stored_pkg)

        # update minimal set of records
        logging.debug("CouchDB update")
        for pkg in pkg_to_create:
            self._new_record(pkg)
        for pkg in pkg_to_update:
            self._update_record(pkg)
        logging.debug("End of CouchDB update")


    def getall(self, hostid=None):
        '''get all auto installed packages in two lists

        Return: a dictionnary of installed packages, with last modification time
                a dictionnary of removed packages, with last modification time
        '''
        return(self._get_packages_on_view("get_pkg_by_hostid", hostid))

    def getappscodec(self, hostid=None):
        '''get apps/codecs in two lists

        Return: a dictionnary of installed apps/codecs, with last modification time
                a dictionnary of removed apps/codecs, with last modification time
        '''
        return(self._get_packages_on_view("get_app_codec_by_hostid", hostid))
    
    def _get_packages_on_view(self, view_name, hostid=None):
        '''Internal function to be called by getall and getappscodec'''
        if not hostid:
            hostid = self.hostid
        installed_pkg = {}
        removed_pkg = {}
        results = self.database.execute_view(view_name)
        for rec in results[hostid]:
            pkg_name = rec.value["name"]
            if rec.value["manually_installed"]:
                installed_pkg[pkg_name] = rec.value["last_modification"]
            else:
                removed_pkg[pkg_name] = rec.value["last_modification"]
        return(installed_pkg, removed_pkg)

    def _load_pkg_on_hostid(self, hostid):
        '''load records from CouchDB

        Return: initial dictionnary of Package with:
                {(hostid, pkg_name) : Package}
        '''
        results = self.database.execute_view("get_pkg_by_hostid")
        stored_pkg_for_hostid = {}
        for rec in results[hostid]:
            pkg_name = rec.value["name"]
            stored_pkg_for_hostid[pkg_name] = Package(hostid, pkg_name,
                rec.value["installed"], rec.value["auto_installed"],
                rec.value["app_codec"], rec.value["last_modification"])
        return stored_pkg_for_hostid

    def _update_record(self, pkg):
        '''Update an existing record matching (hostid, package)'''

        rec = None
        update = {}
        results = self.database.execute_view("get_pkg_by_hostid_name")
        for rec in results[[pkg.hostid, pkg.name]]:
            update["installed"] = pkg.installed
            update["auto_installed"] = pkg.auto_installed
            update["app_codec"] = pkg.app_codec
            update["last_modification"] = pkg.last_modification
            self.database.update_fields(rec.id, update)
        if not rec:
            logging.warning("Try to update a non existing record: %s, %s",
                            pkg.hostid, pkg.name)

    def _new_record(self, pkg):
        '''Insert a new record for a new package never stored in CouchDB'''

        record = CouchRecord({"hostid": pkg.hostid,
                              "name": pkg.name,
                              "installed": pkg.installed,
                              "auto_installed": pkg.auto_installed,
                              "app_codec": pkg.app_codec,
                              "last_modification": pkg.last_modification,
                               }, ONECONF_PACKAGE_RECORD_TYPE)
        self.database.put_record(record)
        

    def _get_dep_rec_list(self, root_package, default_packages, apt_cache,
                          recursive=True):
            '''Get list of dep of package_root, add them to default_packages'''

            for relations in (root_package.candidate.dependencies,
                              root_package.candidate.recommends):
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

    def _get_default_package_list(self, meta_package, apt_cache):
        '''Get default package installed in the distribution

        Return: set of default packages from the meta_package
        '''

        default_packages = set()
        # these are false default package as alternatives deps are taken
        # into account by the algorithm like file-roller depends zip | p7zip-full
        # -> p7zip-full won't be listed as it will be in "default"
        false_defaults = set(['p7zip-full', 'vim-gnome', 'vim'])
        self._get_dep_rec_list(apt_cache[meta_package], default_packages,
                               apt_cache)
        self._get_dep_rec_list(apt_cache['ubuntu-minimal'], default_packages,
                               apt_cache)
        self._get_dep_rec_list(apt_cache['ubuntu-standard'], default_packages,
                               apt_cache)
        default_packages -= false_defaults
        return default_packages


    def _computepackagelist(self, stored_pkg=None):
        '''Introspect what's installed on this hostid

        Return: stored_pkg of all package states for this hostid
                set of package to create if in update mode (empty otherwise)
                set of package to update if in update mode (empty otherwise)
        '''

        apt_cache = apt.Cache()

        # additional_packages, completed then by ubuntu-restricted-extras deps
        additional_packages = set(['flashplugin-nonfree', 'gnash',
                             'gstreamer0.10-fluendo-mpegdemux', 'swfdec-gnome',
                             'swfdec-mozilla', 'ubuntu-restricted-extras'])
        self._get_dep_rec_list(apt_cache['ubuntu-restricted-extras'],
                               additional_packages, apt_cache, recursive=False)

        # determine wether an app is an app_codec package or not
        blacklist_pkg_regexp = re.compile('.*-dev')
        desktop_pkg_file_pattern = re.compile('/usr/share/applications/.*\.desktop')
        executable_file_pattern = re.compile('^(/usr)?/s?bin/.*')

        # TODO: detect all meta_package installed on that hostid (ubuntu-netbook)
        default_packages = self._get_default_package_list('ubuntu-desktop',
                                                          apt_cache)

        # speedup first batch package insertion and
        # when computing list in read mode for diff between hostA and this host
        updating = False
        if stored_pkg:
            updating = True

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
                           auto_installed, app_codec, self.current_time):
                        pkg_to_update.add(stored_pkg[pkg.name])
                except KeyError:
                    # new package, we are only interested in installed and not
                    # autoinstalled for initial storage
                    if installed and not auto_installed:
                        stored_pkg[pkg.name] = Package(self.hostid, pkg.name,
                            True, False, app_codec, self.current_time)
                        pkg_to_create.add(stored_pkg[pkg.name])
            else:
                # for making a diff, we are only interested in packages
                # installed and not autoinstalled for this host
                if installed and not auto_installed:
                    stored_pkg[pkg.name] = Package(self.hostid, pkg.name,
                        True, False, app_codec, self.current_time)
                    # this is only for first load on an host in update mode:
                    # don't lost time to get keyid. Otherwise, pkg_to_create
                    # isn't relevant for read mode
                    pkg_to_create.add(stored_pkg[pkg.name])

        return stored_pkg, pkg_to_create, pkg_to_update

