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


class PackageSetHandler(object):
    """
    Direct access to database for getting and updating the list
    """

    def __init__(self):
        # Connect to CouchDB and create the database  
        self.database = CouchDatabase("oneconf_pkg", create=True)
        self.machine = "moimoimoi"

        if not self.database.view_exists("get_pkg_by_machine"):  
            viewfn = 'function(doc) { emit(doc.machine, doc); }'
            self.database.add_view("get_pkg_by_machine", viewfn, None, None)
        if not self.database.view_exists("get_app_codec_by_machine"):  
            viewfn = 'function(doc) { if (doc.app_codec) { emit(doc.machine, doc) }; }'
            self.database.add_view("get_app_codec_by_machine", viewfn, None, None)
        if not self.database.view_exists("get_pkg_by_machine_name"):  
            viewfn = 'function(doc) { emit([doc.machine,doc.name], doc); }'  
            self.database.add_view("get_pkg_by_machine_name", viewfn, None, None)


    def update(self):
        '''update the database'''

        current_time = time.time()
        (stored_manuallyinstalled_pkg, stored_installed_app_codec_pkg,
         stored_deleted_pkg) =  self._load_pkg_on_machine(self.machine)

        # get the list of update to do
        (manuallyinstalled_pkg, installed_app_codec_pkg) = self._computepackagelist()
        removed_packages = stored_manuallyinstalled_pkg - manuallyinstalled_pkg
        new_packages = manuallyinstalled_pkg - stored_manuallyinstalled_pkg
        changed_status_app_codec = stored_installed_app_codec_pkg - installed_app_codec_pkg
        changed_status_app_codec.union(installed_app_codec_pkg - stored_installed_app_codec_pkg)
        changed_status_app_codec -= new_packages
        changed_status_app_codec -= removed_packages

        logging.debug("Initial set: %s" % stored_manuallyinstalled_pkg)
        logging.debug("Manually installed packages: %s" % manuallyinstalled_pkg)
        logging.debug("Apps/codec packages: %s" % installed_app_codec_pkg)
        logging.debug("New packages: %s" % new_packages)
        logging.debug("Deleted packages: %s" % removed_packages)
        logging.debug("Packages with apps/codec changed status %s" % changed_status_app_codec)

        # update minimal set of records
        for pkg_name in new_packages:
            app_codec = False
            if pkg_name in installed_app_codec_pkg:
                app_codec = True
            if pkg_name in stored_deleted_pkg:
                self._update_record(self.machine, pkg_name, current_time, True,
                                    app_codec)
            else: # speedup for insert: don't query if already exists
                self._new_record(self.machine, pkg_name, current_time, app_codec)
        for pkg_name in removed_packages:
            app_codec = False
            if pkg_name in installed_app_codec_pkg:
                app_codec = True
            self._update_record(self.machine, pkg_name, current_time,
                                is_manually_installed=False)

        # update changed status for app_codec
        for pkg_name in changed_status_app_codec:
            app_codec = False
            if pkg_name in installed_app_codec_pkg:
                app_codec = True
                self._update_record(self.machine, pkg_name, current_time,
                                    is_app_codec=app_codec)

    def getall(self, machine=None):
        '''get all auto installed packages in two lists

        Return: a dictionnary of installed packages, with last modification time
                a dictionnary of removed packages, with last modification time
        '''
        return(self._get_packages_on_view("get_pkg_by_machine", machine))

    def getappscodec(self, machine=None):
        '''get apps/codecs in two lists

        Return: a dictionnary of installed apps/codecs, with last modification time
                a dictionnary of removed apps/codecs, with last modification time
        '''
        return(self._get_packages_on_view("get_app_codec_by_machine", machine))
    
    def _get_packages_on_view(self, view_name, machine=None):
        '''Internal function to be called by getall and getappscodec'''
        if not machine:
            machine = self.machine
        installed_pkg = {}
        removed_pkg = {}
        results = self.database.execute_view(view_name)
        for rec in results[machine]:
            pkg_name = rec.value["name"]
            if rec.value["manually_installed"]:
                installed_pkg[pkg_name] = rec.value["last_modification"]
            else:
                removed_pkg[pkg_name] = rec.value["last_modification"]
        return(installed_pkg, removed_pkg)

    def _load_pkg_on_machine(self, machine):
        '''load records from CouchDB

        Return: initial set of manually installed packages
                intial set of filtered apps and codec manually installed
                intial set of deleted packages
        '''
        results = self.database.execute_view("get_pkg_by_machine")
        stored_manuallyinstalled_pkg = set()
        stored_installed_app_codec_pkg = set()
        stored_deleted_pkg = set()
        for rec in results[machine]:
            if rec.value["manually_installed"]:
                stored_manuallyinstalled_pkg.add(rec.value["name"])
                if rec.value["app_codec"]:
                    stored_installed_app_codec_pkg.add(rec.value["name"])
            else:
                stored_deleted_pkg.add(rec.value["name"])
        return(stored_manuallyinstalled_pkg, stored_installed_app_codec_pkg,
               stored_deleted_pkg)

    def _update_record(self, machine, pkg_name, last_modification,
                       is_manually_installed=None, is_app_codec=None):
        '''Update an existing record matching (machine, package)'''

        # check if it already exist (can happen even for a "new" package if
        # was previously removed)  
        rec = None
        update = {}

        results = self.database.execute_view("get_pkg_by_machine_name")
        for rec in results[[machine, pkg_name]]:
            if (is_manually_installed is not None
                and is_manually_installed != rec.value["manually_installed"]):
                update["manually_installed"] = is_manually_installed
            if (is_app_codec is not None
                and is_app_codec != rec.value["app_codec"]):
                update["app_codec"] = is_app_codec
            if update:
                logging.debug("Update %s, %s", machine, pkg_name)
                update["last_modification"] = last_modification
                self.database.update_fields(rec.id, update)
        if not rec:
            logging.debug("Try to update a non existing record: %s, %s",
                           machine, pkg_name)

    def _new_record(self, machine, pkg_name, current_time, is_app_codec):
        '''Insert a new record'''

        logging.debug("Insert new record: %s", machine, pkg_name)
        record = CouchRecord({"machine": machine,
                              "name": pkg_name, 
                              "manually_installed": True,
                              "app_codec": is_app_codec,
                              "last_modification": current_time,
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


    def _computepackagelist(self):
        '''Introspect what's installed on the owner machine

        Return: set of manually installed packages
                set of filtered apps and codec manually installed
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

        # TODO: detect all meta_package installed on that machine (ubuntu-netbook)
        default_packages = self._get_default_package_list('ubuntu-desktop',
                                                          apt_cache)

        # get list of all apps installed
        installed_app_codec_pkg = set()
        manuallyinstalled_pkg = set()
        for pkg in apt_cache:
            if (pkg.is_installed and not pkg.is_auto_installed):
                manuallyinstalled_pkg.add(pkg.name)
                if not pkg.priority in ('required', 'important'):
                    if pkg.name in additional_packages:
                        installed_app_codec_pkg.add(pkg.name)
                    elif (pkg.name in default_packages or
                          blacklist_pkg_regexp.match(pkg.name)):
                        continue
                    else:
                        for pkg_file in pkg.installed_files:
                            if (desktop_pkg_file_pattern.match(pkg_file) or
                                executable_file_pattern.match(pkg_file)):
                                installed_app_codec_pkg.add(pkg.name)
                                break
        return manuallyinstalled_pkg, installed_app_codec_pkg

