"""This module provides the WebCatalogAPI class for talking to the
webcatalog API, plus a few helper classes.
"""

from urllib import quote_plus
from piston_mini_client import (
    PistonAPI,
    PistonResponseObject,
    PistonSerializable,
    returns,
    returns_json
    )
from piston_mini_client.validators import validate_pattern, validate
from piston_mini_client.failhandlers import APIError

# These are factored out as constants for if you need to work against a
# server that doesn't support both schemes (like http-only dev servers)
PUBLIC_API_SCHEME = 'http'
AUTHENTICATED_API_SCHEME = 'https'

class WebCatalogAPI(PistonAPI):
    """A client for talking to the webcatalog API.

    If you pass no arguments into the constructor it will try to connect to
    localhost:8000 so you probably want to at least pass in the
    ``service_root`` constructor argument.
    """
    default_service_root = 'http://localhost:8000/cat/api/1.0'
    default_content_type = 'application/x-www-form-urlencoded'

    @returns_json
    def server_status(self):
        """Check the state of the server, to see if everything's ok."""
        return self._get('server-status/', scheme=PUBLIC_API_SCHEME)

    @returns_json
    def list_machines(self):
        """List all machine for the current user."""
        return self._get('list-machines/', scheme=PUBLIC_API_SCHEME)

    @validate_pattern('machine_uuid', r'[-\w+]+')
    @validate_pattern('hostname', r'[-\w+]+')
    @returns_json
    def update_machine(self, machine_uuid, hostname):
        """Register or update an existing machine with new name."""
        return self._get('update-machine/%s/%s/' % (machine_uuid, hostname), scheme=PUBLIC_API_SCHEME)

    @validate_pattern('machine_uuid', r'[-\w+]+')
    @returns_json
    def delete_machine(self, machine_uuid):
        """Delete an existing machine."""
        return self._get('delete-machine/%s/' % machine_uuid, scheme=PUBLIC_API_SCHEME)

    @validate_pattern('machine_uuid', r'[-\w+]+')
    def get_machine_logo(self, machine_uuid):
        """get the logo for a machine."""
        return self._get('machine-logo/%s/' % machine_uuid, scheme=PUBLIC_API_SCHEME)

    # FIXME: get [08/Jul/2011 15:34:51] "POST /cat/api/1.0/machine-logo/UUUUU/ooo/ HTTP/1.1" 400 11.
    # need autentification?
    @validate_pattern('machine_uuid', r'[-\w+]+')
    @validate_pattern('logo_checksum', r'[-\w+]+\.[-\w+]+')
    @returns_json
    def update_machine_logo(self, machine_uuid, logo_checksum, logo_content):
        """update the logo for a machine."""
        return self._post('machine-logo/%s/%s/' % (machine_uuid, logo_checksum), data=logo_content,
        content_type='image/png', scheme=PUBLIC_API_SCHEME)

    @validate_pattern('machine_uuid', r'[-\w+]+')
    @returns_json
    def list_packages(self, machine_uuid):
        """List all packages for that machine"""
        package_list = self._get('list-packages/%s/' % machine_uuid, scheme=PUBLIC_API_SCHEME)
        if not package_list:
            raise APIError('Package list invalid')
        return package_list

    @validate_pattern('machine_uuid', r'[-\w+]+')
    @validate_pattern('packages_checksum', r'[-\w+]+')
    @returns_json
    def update_packages(self, machine_uuid, packages_checksum, package_list):
        """update the package list for a machine."""
        return self._post('update-packages/%s/%s/' % (machine_uuid, packages_checksum), data=package_list,
        scheme=PUBLIC_API_SCHEME)

