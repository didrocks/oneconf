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


class Package(object):
    """
    Data holder for package property we are interested in
    """

    def __init__(self, hostid, name, installed, auto_installed,
                 app_codec, last_modification, repo="Ubuntu"):
        '''initalize Package values'''

        self.hostid = hostid
        self.name = name
        self.installed = installed
        self.auto_installed = auto_installed
        self.app_codec = app_codec
        self.last_modification = last_modification
        self.repo = repo

    def update_needed(self, installed, auto_installed, app_codec, current_time,
                      repo="Ubuntu"):
        '''Compare new values to old and return if update is needed

        Return: bool meaning if an update is needed or not
        '''

        need_update = False
        if self.installed != installed:
            self.installed = installed
            need_update = True
        if self.auto_installed != auto_installed:
            self.auto_installed = auto_installed
            need_update = True
        if self.app_codec != app_codec:
            self.app_codec = app_codec
            need_update = True
        if self.repo != repo:
            self.repo = repo
            need_update = True
        if need_update:
            self.last_modification = current_time
        return need_update
