# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Canonical
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
# this program.  If not, see <http://www.gnu.org/licenses/>.


import apt
import gobject
import gettext
import gtk
import logging
import os
import sys
import xapian

from gettext import gettext as _

from softwarecenter.enums import *

from softwarecenter.view.appview import AppView, AppStore, AppViewFilter

from softwarecenter.view.softwarepane import SoftwarePane, wait_for_apt_cache_ready

# TODO:
# - add hide/show apps
# - add install all/remove all
# - add correct refresh once an app is installed/removed (on this view or another) -> look at the code, with the notification stuff
# - change the way to count and search in OneConfFilter()
# - check focus/selection behavior when switching from one mode to another

class OneConfPane(SoftwarePane):

    (ADDITIONAL_PKG, REMOVED_PKG) = range(2)

    (PAGE_APPLIST,
     PAGE_APP_DETAILS) = range(2)

    def __init__(self, 
                 cache,
                 history,
                 db, 
                 distro, 
                 icons, 
                 datadir,
                 oneconfeventhandler,
                 compared_with_hostid):
        # parent
        SoftwarePane.__init__(self, cache, history, db, distro, icons, datadir)
        self.hostname = ''
        self.search_terms = ""
        self.compared_with_hostid = compared_with_hostid
        self.current_appview_selection = None
        self.apps_filter = None
        self.nonapps_visible = False

        # OneConf stuff there
        self.oneconfeventhandler = oneconfeventhandler
        oneconfeventhandler.connect('inventory-refreshed', self._on_inventory_change)

        # Backend installation
        self.backend.connect("transaction-finished", self._on_transaction_finished)

        # UI
        self._build_ui()

    def _build_ui(self):

        self.navigation_bar.set_size_request(26, -1)
        self.notebook.append_page(self.scroll_app_list, gtk.Label("app list"))
        # details
        self.notebook.append_page(self.scroll_details, gtk.Label("details"))

        self.toolbar = gtk.Toolbar()
        self.toolbar.show()
        self.toolbar.set_style(gtk.TOOLBAR_TEXT)
        self.pack_start(self.toolbar, expand=False)
        self.reorder_child(self.toolbar, 1)

        additional_pkg_action = gtk.RadioAction('additional_pkg', None, None, None, self.ADDITIONAL_PKG)
        additional_pkg_action.connect('changed', self.change_current_mode)
        additional_pkg_button = additional_pkg_action.create_tool_item()
        self.toolbar.insert(additional_pkg_button, 0)
        removed_pkg_action = gtk.RadioAction('removed_pkg', None, None, None, self.REMOVED_PKG)
        removed_pkg_action.set_group(additional_pkg_action)
        removed_pkg_button = removed_pkg_action.create_tool_item()
        self.toolbar.insert(removed_pkg_button, 1)
        additional_pkg_action.set_active(True)
        self.additional_pkg_action = additional_pkg_action
        self.removed_pkg_action = removed_pkg_action

        # initial refresh
        self._on_inventory_change(self.oneconfeventhandler)

    def _on_transaction_finished(self, backend, success):
        # refresh inventory
        if success:
            print 'plop'
            gobject.timeout_add_seconds(10, self._on_inventory_change, self.oneconfeventhandler)

    def _on_inventory_change(self, oneconfeventhandler):
        try:
            current, hostname, show_inventory, show_others = oneconfeventhandler.u1hosts[self.compared_with_hostid]
        except KeyError:
            logging.critical("Host not registered")
            return
        self.hostname = hostname
        (additional_pkg, missing_pkg) = oneconfeventhandler.oneconf.diff_selection(self.compared_with_hostid, '', True)
        self.apps_filter = OneConfFilter(db, cache, set(additional_pkg), set(missing_pkg))
        self.refresh_apps()

    def refresh_selection_bar(self):
        if self.nonapps_visible:
            number_additional_pkg = len(self.apps_filter.additional_pkg)
            number_removed_pkg = len(self.apps_filter.removed_pkg)
        else:
            number_additional_pkg = self.apps_filter.additional_apps_pkg
            number_removed_pkg = self.apps_filter.removed_apps_pkg
        if number_additional_pkg > 1:
            msg_additional_pkg = _('%s items that aren\'t on that computer') % number_additional_pkg
        else:
            msg_additional_pkg = _('%s item that isn\'t on that computer') % number_additional_pkg
        if number_removed_pkg > 1:
            msg_removed_pkg = _('%s items that aren\'t on the remote computer') % number_removed_pkg
        else:
            msg_removed_pkg = _('%s item that isn\'t on the remote computer') % number_removed_pkg
        self.additional_pkg_action.set_label(msg_additional_pkg)
        self.removed_pkg_action.set_label(msg_removed_pkg)

    def refresh_number_of_pkg(self):
        self.oneconf
        additional_pkg_action.set_label()

    def change_current_mode(self, action, current):
        if self.apps_filter:
            self.apps_filter.set_new_current_mode(action.get_current_value())
            self.refresh_apps()

    def _show_installed_overview(self):
        " helper that goes back to the overview page "
        self.navigation_bar.remove_id("details")
        self.notebook.set_current_page(self.PAGE_APPLIST)
        self.toolbar.show()
        self.searchentry.show()
        
    def _clear_search(self):
        # remove the details and clear the search
        self.searchentry.clear()
        self.navigation_bar.remove_id("search")

    @wait_for_apt_cache_ready
    def refresh_apps(self):
        """refresh the applist after search changes and update the 
           navigation bar
        """
        self.apps_filter.reset_counter()
        if self.search_terms:
            query = self.db.get_query_list_from_search_entry(self.search_terms)
            self.navigation_bar.add_with_id(_("Search Results"),
                                            self.on_navigation_search, 
                                            "search")
        else:
            query = None
        self.navigation_bar.add_with_id(self.hostname, 
                                        self.on_navigation_list,
                                        "list",
                                        animate=False)
        # *ugh* deactivate the old model because otherwise it keeps
        # getting progress_changed events and eats CPU time until it's
        # garbage collected
        old_model = self.app_view.get_model()
        if old_model is not None:
            old_model.active = False
        # get a new store and attach it to the view
        new_model = AppStore(self.cache,
                             self.db, 
                             self.icons, 
                             query,
                             nonapps_visible = self.nonapps_visible,
                             filter=self.apps_filter)
        self.app_view.set_model(new_model)
        self.emit("app-list-changed", len(new_model))
        self.refresh_selection_bar()
        return False

    def on_search_terms_changed(self, searchentry, terms):
        """callback when the search entry widget changes"""
        logging.debug("on_search_terms_changed: '%s'" % terms)
        self.search_terms = terms
        if not self.search_terms:
            self._clear_search()
        self.refresh_apps()
        self.notebook.set_current_page(self.PAGE_APPLIST)

    def on_db_reopen(self, db):
        self.refresh_apps()
        self._show_installed_overview()
        
    def on_navigation_search(self, pathbar, part):
        """ callback when the navigation button with id 'search' is clicked"""
        self.display_search()
        
    def on_navigation_list(self, pathbar, part):
        """callback when the navigation button with id 'list' is clicked"""
        if not pathbar.get_active():
            return
        self._clear_search()
        self._show_installed_overview()
        # only emit something if the model is there
        model = self.app_view.get_model()
        if model:
            self.emit("app-list-changed", len(model))

    def on_navigation_details(self, pathbar, part):
        """callback when the navigation button with id 'details' is clicked"""
        if not pathbar.get_active():
            return
        self.toolbar.hide()
        self.notebook.set_current_page(self.PAGE_APP_DETAILS)
        self.searchentry.hide()
        
    def on_application_selected(self, appview, app):
        """callback when an app is selected"""
        logging.debug("on_application_selected: '%s'" % app)
        self.current_appview_selection = app

    def display_search(self):
        self.navigation_bar.remove_id("details")
        self.notebook.set_current_page(self.PAGE_APPLIST)
        model = self.app_view.get_model()
        if model:
            self.emit("app-list-changed", len(model))
        self.searchentry.show()
    
    def get_status_text(self):
        """return user readable status text suitable for a status bar"""
        # no status text in the details page
        if self.notebook.get_current_page() == self.PAGE_APP_DETAILS:
            return ""
        # otherwise, show status based on search or not
        model = self.app_view.get_model()
        if not model:
            return ""
        length = len(model)
        if len(self.searchentry.get_text()) > 0:
            return gettext.ngettext("%(amount)s matching item",
                                    "%(amount)s matching items",
                                    length) % { 'amount' : length, }
        else:
            return gettext.ngettext("%(amount)s item installed",
                                    "%(amount)s items installed",
                                    length) % { 'amount' : length, }
                                    
    def get_current_app(self):
        """return the current active application object applicable
           to the context"""
        return self.current_appview_selection
        
    def is_category_view_showing(self):
        # there is no category view in the OneConf pane
        return False

# TODO: find a way to replace that by a Xapian query ?
class OneConfFilter(object):
    """
    Filter that can be hooked into AppStore to filter for pkg name criteria
    """
    (ADDITIONAL_PKG, REMOVED_PKG) = range(2)

    def __init__(self, db, cache, additional_pkglist, removed_pkglist):
        self.db = db
        self.cache = cache
        self.additional_pkglist = additional_pkglist
        self.removed_pkglist = removed_pkglist
        self.only_packages_without_applications = False
        self.current_mode = self.ADDITIONAL_PKG
        self.reset_counter()
    def set_only_packages_without_applications(self, v):
        """
        only show packages that are not displayed as applications

        e.g. abiword (the package document) will not be displayed
             because there is a abiword application already
        """
        self.only_packages_without_applications = v
    def get_only_packages_without_applications(self, v):
        return self.only_packages_without_applications
    def set_new_current_mode(self, v):
        self.current_mode = v
    def get_current_mode(self):
        return self.current_mode
    def reset_counter(self):
        self.additional_apps_pkg = 0
        self.removed_apps_pkg = 0
    def filter(self, doc, pkgname):
        """return True if the package should be displayed"""
        if self.current_mode == self.ADDITIONAL_PKG:
            pkg_list_to_compare = self.additional_pkglist
            other_list = self.removed_pkglist
        else:
            pkg_list_to_compare = self.removed_pkglist
            other_list = self.additional_pkglist

        # TODO: that's ugly, but if we could have a direct Xapian request
        # for that (OneConf doesn't know what are applications)
        if pkgname in other_list:
            if self.current_mode == self.ADDITIONAL_PKG:
                self.removed_apps_pkg += 1
            else:
                self.additional_apps_pkg += 1
                                    

        if pkgname in pkg_list_to_compare:
            if self.current_mode == self.ADDITIONAL_PKG:
                self.additional_apps_pkg += 1
            else:
                self.removed_apps_pkg += 1
            return True
        return False

if __name__ == '__main__':
    from softwarecenter.apt.apthistory import get_apt_history
    from softwarecenter.db.database import StoreDatabase

    #logging.basicConfig(level=logging.DEBUG)

    if len(sys.argv) > 1:
        datadir = sys.argv[1]
    elif os.path.exists("./data"):
        datadir = "./data"
    else:
        datadir = "/usr/share/software-center"

    # additional icons come from app-install-data
    icons = gtk.icon_theme_get_default()
    icons.append_search_path(ICON_PATH)
    icons.append_search_path(os.path.join(datadir,"icons"))
    icons.append_search_path(os.path.join(datadir,"emblems"))
    # HACK: make it more friendly for local installs (for mpt)
    icons.append_search_path(datadir+"/icons/32x32/status")
    gtk.window_set_default_icon_name("softwarecenter")
    cache = apt.Cache(apt.progress.text.OpProgress())
    cache.ready = True

    #apt history
    history = get_apt_history()
    # xapian
    xapian_base_path = XAPIAN_BASE_PATH
    pathname = os.path.join(xapian_base_path, "xapian")
    try:
        db = StoreDatabase(pathname, cache)
        db.open()
    except xapian.DatabaseOpeningError:
        # Couldn't use that folder as a database
        # This may be because we are in a bzr checkout and that
        #   folder is empty. If the folder is empty, and we can find the
        # script that does population, populate a database in it.
        if os.path.isdir(pathname) and not os.listdir(pathname):
            from softwarecenter.db.update import rebuild_database
            logging.info("building local database")
            rebuild_database(pathname)
            db = StoreDatabase(pathname, cache)
            db.open()
    except xapian.DatabaseCorruptError, e:
        logging.exception("xapian open failed")
        view.dialogs.error(None, 
                           _("Sorry, can not open the software database"),
                           _("Please re-install the 'software-center' "
                             "package."))
        # FIXME: force rebuild by providing a dbus service for this
        sys.exit(1)

    from oneconf.dbusconnect import DbusConnect
    from oneconf.uscplugin import oneconfeventhandler
    oneconf = DbusConnect()
    oneconfeventhandler = oneconfeventhandler.OneConfEventHandler(oneconf)

    w = OneConfPane(cache, None, db, 'Ubuntu', icons, datadir, oneconfeventhandler, 'AAAAA')
    w.show()

    window = gtk.Window()
    window.add(w)
    window.set_size_request(600, 500)
    window.set_position(gtk.WIN_POS_CENTER)
    window.show_all()
    window.connect('destroy', gtk.main_quit)

    gtk.main()
