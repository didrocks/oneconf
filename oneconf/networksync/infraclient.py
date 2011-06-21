#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2011 Canonical
#
# Authors:
#  Didier Roche
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

import json

import logging
LOG = logging.getLogger(__name__)
import os

URL_INFRA = 'http://foo' + "/fake_user_id"

from paths import OTHER_HOST_FILENAME, HOST_DATA_FILENAME, PACKAGE_LIST_FILENAME

class InfraClient:

    '''Client for Online infrastructure'''
    
    
    def __init__(self):
        pass
    
    def _get_etag(self, url):
        '''rest request to get the etag for an url'''
        
    def _get_full_json_content(self, url):
        '''rest request to get the json content for an url'''
        
    def get_other_hosts(self, current_hostid, only_etag=False):
        '''get etag or file from other host'''
        
        url = '/'.join([URL_INFRA, current_hostid, OTHER_HOST_FILENAME])
        return self._get_url_content_handler(url, only_etag)

    def get_packages_for_host(self, hostid, only_etag=False):
        '''get etag or file for package list for hostid'''
        
        url = '/'.join([URL_INFRA, hostid, PACKAGE_LIST_FILENAME])
        return self._get_url_content_handler(url, only_etag)
        

    def _get_url_content_handler(self, url, only_etag):
        '''get the url content (etag or content)'''
        
        if only_etag:
            return self._get_etag(url)
        return self._get_full_json_content(url)

        
        
class MockInfraClient(InfraClient):
    '''Mock local client for the infra'''
            
    def __init__(self):
        InfraClient()    

        self.infra_dir = os.path.join(os.getcwd(), 'mocklocalinfra')
        
    def _url_to_file(self, url):
        '''reverse engineer, web url to local path for testing'''
        return os.path.join(self.infra_dir, os.path.sep.join(url.split("/")[-2:]))
    
    def _get_etag(self, url):
        '''get distant etag from local files'''

        # of course, this makes no sense to get the full content to check the ETag, but we are mocking server behavior
        file_content = self._get_full_json_content(url)
        if file_content:
            return file_content['ETag']
        return None
            
    def _get_full_json_content(self, url):
        '''get distant full file content from local file'''
        try:
            with open(self._url_to_file(url), 'r') as f:
                return json.load(f)
        except IOError:
            LOG.debug("No mock file found for %s", self._url_to_file(url))
            return None

