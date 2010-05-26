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

from oneconf.distributor import Distro
import re


class Ubuntu(Distro):

    def get_distro_channel_name(self):
        """ The name in the Release file """
        return "Ubuntu"

    def get_additional_packages(self, packagesethandler, apt_cache):
        additional_packages = set(['flashplugin-nonfree', 'gnash',
            'gstreamer0.10-fluendo-mpegdemux', 'swfdec-gnome', 'swfdec-mozilla',
            'ubuntu-restricted-extras'])
        # complete the default set by ubuntu-restricted-extras deps
        packagesethandler._get_dep_rec_list(apt_cache['ubuntu-restricted-extras'],
                                   additional_packages, apt_cache, recursive=False)
        return additional_packages

    def is_recommends_as_dep(self):
        return True

    def get_blacklist_regexp(self):
        return re.compile('.*-dev')

    def get_false_defaults(self):
        return set(['p7zip-full', 'vim-gnome', 'vim'])

    def get_distribution_meta_packages(self):
        return set(['ubuntu-minimal', 'ubuntu-standard', 'ubuntu-desktop',
                    'ubuntu-netbook', 'xubuntu-desktop', 'lubuntu-desktop',
                    'mythbuntu-desktop'])



