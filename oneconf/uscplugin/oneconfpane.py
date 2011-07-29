# -*- coding: utf-8 -*-
#
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
# this program.  If not, see <http://www.gnu.org/licenses/>.


import apt
import gobject
import gettext
import gtk
import logging
import os
import sys
from threading import Thread
import xapian

from gettext import gettext as _


from softwarecenter.enums import NavButtons, DEFAULT_SEARCH_LIMIT

from softwarecenter.ui.gtk.appview import AppView, AppStore, AppViewFilter
from softwarecenter.ui.gtk.models.appstore import AppStore
from softwarecenter.distro import get_distro
from softwarecenter.ui.gtk.widgets.spinner import SpinnerView
from softwarecenter.ui.gtk.softwarepane import SoftwarePane, wait_for_apt_cache_ready

# TODO:
# - change the way to count and search in OneConfFilter() (have benefits, like search refresh)

class OneConfPane(SoftwarePane):

    (ADDITIONAL_PKG, REMOVED_PKG) = range(2)

    (PAGE_APPLIST,
     PAGE_APP_DETAILS) = range(2)

    (PAGE_CHILD_APPLIST,
     PAGE_CHILD_SPINNER) = range(2)
     

    def __init__(self, 
                 cache,
                 history,
                 db, 
                 distro, 
                 icons, 
                 datadir,
                 oneconf,
                 hostid,
                 hostname):
        # parent
        SoftwarePane.__init__(self, cache, db, distro, icons, datadir)
        self.hostname = hostname
        self.pane_name = hostname
        self.search_terms = ""
        self.hostid = hostid
        self.current_appview_selection = None
        self.apps_filter = None
        self.nonapps_visible = AppStore.NONAPPS_NEVER_VISIBLE
        self.refreshing = False
        # OneConf stuff there
        self.oneconf = oneconf
        self.oneconf.hosts_dbus_object.connect_to_signal('packagelist_changed', self._on_store_packagelist_changed)

        # Backend installation
        self.backend.connect("transaction-finished", self._on_transaction_finished)

    def init_view(self):
        if not self.view_initialized:
            self.show_appview_spinner(spinner_text=_("Getting OneConf data"), init=True)
            
            while gtk.events_pending():
                gtk.main_iteration()

            # open the cache since we are initializing the UI for the first time    
            gobject.idle_add(self.cache.open)
            
            super(OneConfPane, self).init_view()
            self._build_ui()
            self.view_initialized = True
            #self.hide_appview_spinner(init=True)
            # dummy call to force async refresh
            self._on_transaction_finished(None, True, 0)

    def _build_ui(self):

        self.navigation_bar.set_size_request(26, -1)

        self.app_list_notebook = gtk.Notebook()
        self.app_list_notebook.set_show_tabs(False)
        self.app_list_notebook.set_show_border(False)

        self.main_app_list_page = gtk.VBox()
        self.app_list_notebook.append_page(self.box_app_list, gtk.Label("list"))
        self.child_spinner_view = SpinnerView()
        self.app_list_notebook.append_page(self.child_spinner_view, gtk.Label("child spinner"))
        self.child_spinner_view.show_all()
        
        self.notebook.append_page(self.main_app_list_page, gtk.Label("app list"))
        self.notebook.append_page(self.scroll_details, gtk.Label("details"))
        self.scroll_details.show()

        self.embeeded_title_bar = gtk.HBox()
        self.toolbar = gtk.Toolbar()
        self.toolbar.show()
        self.toolbar.set_style(gtk.TOOLBAR_TEXT)
                
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
        self.act_on_store_button = gtk.Button()
        self.embeeded_title_bar.pack_end(self.act_on_store_button, expand=False)
        self.act_on_store_button.connect('clicked', self._act_on_current_appstore)
        self.act_on_store_button.show()
        
        self.embeeded_title_bar.pack_start(self.toolbar, expand=True)
        self.main_app_list_page.pack_start(self.embeeded_title_bar, expand=False)
        self.main_app_list_page.pack_start(self.app_list_notebook, expand=True)
        
        self.main_app_list_page.show_all()

    def _act_on_current_appstore(self, widget):
        '''
        Function that installs or removes all applications displayed in the pane.
        '''
        pkgnames = []
        appnames = []
        iconnames = []
        appstore = self.app_view.get_model()
        for match in appstore.matches:
            pkgnames.append(self.db.get_pkgname(match.document))
            appnames.append(self.db.get_appname(match.document))
            iconnames.append(self.db.get_iconname(match.document))
        if self.apps_filter.current_mode == self.ADDITIONAL_PKG:
            self.backend.install_multiple(pkgnames, appnames, iconnames)
        else:
            self.backend.remove_multiple(pkgnames, appnames, iconnames)
            
    def _on_transaction_finished(self, backend, success, time=5):
        # refresh inventory with delay and threaded (to avoid waiting if an oneconf update is in progress)
        if success:
            gobject.timeout_add_seconds(time, Thread(target=self._on_inventory_change, args=()).start)

    def _on_store_packagelist_changed(self, hostid):
        '''trigger a packagelist inventory change signal if current hostid is concerned'''
        if hostid == self.hostid:
            self._on_inventory_change()

    def _on_inventory_change(self):
        
        # only make oneconf calls once initialized
        if not self.view_initialized:
            return

        # create first filter
        if not self.apps_filter:
            self.apps_filter = OneConfFilter(self.db, self.cache, set(), set(), self.nonapps_visible)
        (additional_pkg, missing_pkg) = self.oneconf.diff(self.hostid, '')
        self.apps_filter.additional_pkglist = set(additional_pkg)
        self.apps_filter.removed_pkglist = set(missing_pkg)
        self._append_refresh_apps()

    def _append_refresh_apps(self):
        """thread hammer protector for asking refresh of apps in pane"""
        gobject.timeout_add(0, self.refresh_apps)

    def refresh_selection_bar(self):
        if self.nonapps_visible == AppStore.NONAPPS_ALWAYS_VISIBLE:
            number_additional_pkg = len(self.apps_filter.additional_apps_pkg)
            number_removed_pkg = len(self.apps_filter.removed_apps_pkg)
        else:
            number_additional_pkg = len(self.apps_filter.additional_apps_pkg)
            number_removed_pkg = len(self.apps_filter.removed_apps_pkg)

        use_plural = (number_additional_pkg > 1) and number_additional_pkg or 1 # hack around ngettext considering 0 is plural
        msg_additional_pkg = gettext.ngettext("%(amount)s missing item",
                                    "%(amount)s missing items",
                                    use_plural) % { 'amount' : number_additional_pkg, }
        msg_add_act_on_store = gettext.ngettext("Install this item",
                                    "Install those %(amount)s items",
                                    use_plural) % { 'amount' : number_additional_pkg, }  
        use_plural = (number_removed_pkg > 1) and number_removed_pkg or 1 # hack around ngettext considering 0 is plural
        msg_removed_pkg =  gettext.ngettext("%(amount)s additional item",
                                    "%(amount)s additional items",
                                    use_plural) % { 'amount' : number_removed_pkg, }                                                
        msg_remove_act_on_store =  gettext.ngettext("Remove this item",
                                    "Remove those %(amount)s items",
                                    use_plural) % { 'amount' : number_removed_pkg, }            

        self.additional_pkg_action.set_label(msg_additional_pkg)
        self.removed_pkg_action.set_label(msg_removed_pkg)
        if self.apps_filter.current_mode == self.ADDITIONAL_PKG:
            self.act_on_store_button.set_label(msg_add_act_on_store)
            nb_pkg_to_act_on = number_additional_pkg
        else:
            self.act_on_store_button.set_label(msg_remove_act_on_store)
            nb_pkg_to_act_on = number_removed_pkg
        if nb_pkg_to_act_on > 0:
            self.act_on_store_button.set_sensitive(True)
        else:
            self.act_on_store_button.set_sensitive(False)


    def refresh_number_of_pkg(self):
        self.oneconf
        additional_pkg_action.set_label()

    def change_current_mode(self, action, current):
        if self.apps_filter:
            self.apps_filter.set_new_current_mode(action.get_current_value())
            self._append_refresh_apps()

    def _show_installed_overview(self):
        " helper that goes back to the overview page "
        self.navigation_bar.remove_id(NavButtons.DETAILS)
        self.notebook.set_current_page(self.PAGE_APPLIST)
        self.toolbar.show()
        self.searchentry.show()
        
    def _clear_search(self):
        # remove the details and clear the search
        self.searchentry.clear()
        self.apps_search_term = ""
        self.navigation_bar.remove_id(NavButtons.SEARCH)

    def show_appview_spinner(self, spinner_text=None, init=False):
        """ display the spinner in the appview panel """

        # We area really evil because we like it! There are two spinners:
        # the main one (the traditional software-center spinner view) for "building"
        # the ui, and a child one without removing the top toolbar
        if not self.apps_search_term:
            self.action_bar.clear()
        if init:            
            self.spinner_view.stop()
            if spinner_text:
                self.spinner_view.set_text(spinner_text)
            self.spinner_notebook.set_current_page(self.PAGE_SPINNER)
        else:
            self.child_spinner_view.stop()
            if spinner_text:
                self.child_spinner_view.set_text(spinner_text)
            self.app_list_notebook.set_current_page(self.PAGE_CHILD_SPINNER)
        # "mask" the spinner view momentarily to prevent it from flashing into
        # view in the case of short delays where it isn't actually needed
        gobject.timeout_add(100, self._unmask_appview_spinner, init)

    def _unmask_appview_spinner(self, init=False):
        if init:
            self.spinner_view.start()
        else:
            self.child_spinner_view.start()

    def hide_appview_spinner(self):
        """ hide the spinner and display the appview in the panel """
        if self.spinner_notebook.get_current_page() != self.PAGE_APPVIEW:
            self.spinner_view.stop()
            self.spinner_view.set_text()
            self.spinner_notebook.set_current_page(self.PAGE_APPVIEW)
        self.child_spinner_view.stop()
        self.child_spinner_view.set_text()
        self.app_list_notebook.set_current_page(self.PAGE_CHILD_APPLIST)

    @wait_for_apt_cache_ready
    def refresh_apps(self):
        """refresh the applist after search changes and update the 
           navigation bar
        """

        # seems like some part is done async, try to protect this by pane
        if self.refreshing:
            return False
        self.refreshing = True
        self.apps_filter.reset_counter()

        # call parent to do the real work
        super(OneConfPane, self).refresh_apps()
        
        # FIXME: his is fake just to see if the label shows up
        #self.app_view.get_model().nr_apps = 1
        #self.app_view.get_model().nr_pkgs = 9

        self.update_show_hide_nonapps()
        self.refresh_selection_bar()
        self.refreshing = False
        return False
        
    def on_search_terms_changed(self, widget, new_text):
        """callback when the search entry widget changes"""
        logging.debug("on_search_terms_changed: %s" % new_text)

        # we got the signal after we already switched to a details
        # page, ignore it
        if self.notebook.get_current_page() == self.PAGE_APP_DETAILS:
            return

        # DTRT if the search is reseted
        if not new_text:
            self._clear_search()
        else:
            self.apps_search_term = new_text
            self.apps_limit = DEFAULT_SEARCH_LIMIT
            # enter custom list mode if search has non-trailing
            # comma per custom list spec.
            self.custom_list_mode = "," in new_text.rstrip(',')
        self._append_refresh_apps()
        self.notebook.set_current_page(self.PAGE_APPLIST)        

    def on_db_reopen(self, db):
        self._append_refresh_apps()
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
        
    @wait_for_apt_cache_ready
    def on_application_activated(self, appview, app):
        super(OneConfPane, self).on_application_activated(appview, app)
        self.update_show_hide_nonapps()
        
    def display_search(self):
        self.navigation_bar.remove_id(NavButtons.DETAILS)
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
        
    def is_applist_view_showing(self):
        """Return True if we are in the applist view """
        return self.notebook.get_current_page() == self.PAGE_APPLIST
        
    def is_app_details_view_showing(self):
        """Return True if we are in the app_details view """
        return self.notebook.get_current_page() == self.PAGE_APP_DETAILS
        
    def _hide_nonapp_pkgs(self):
        # override to never show apps visible
        self.nonapps_visible = AppStore.NONAPPS_NEVER_VISIBLE
        self.apps_filter.set_non_apps_visible(self.nonapps_visible)
        self.refresh_apps()

    def _show_nonapp_pkgs(self):
        # override to never show apps visible
        self.nonapps_visible = AppStore.NONAPPS_ALWAYS_VISIBLE
        self.apps_filter.set_non_apps_visible(self.nonapps_visible)
        self.refresh_apps()

# TODO: find a way to replace that by a Xapian query ?
class OneConfFilter(xapian.MatchDecider):
    """
    Filter that can be hooked into xapian get_mset to filter for criteria that
    are based around the package details that are not listed in xapian
    (like installed_only) or archive section
    """
    
    (ADDITIONAL_PKG, REMOVED_PKG) = range(2)

    def __init__(self, db, cache, additional_pkglist, removed_pkglist, non_apps_visible):
        xapian.MatchDecider.__init__(self)
        self.distro = get_distro()
        self.db = db
        self.cache = cache
        self.supported_only = False
        self.installed_only = False
        self.not_installed_only = False
        self.additional_pkglist = additional_pkglist
        self.removed_pkglist = removed_pkglist
        self.current_mode = self.ADDITIONAL_PKG
        self._non_apps_visible = non_apps_visible
        self.reset_counter()
    @property
    def required(self):
        """ True if the filter is in a state that it should be part of a query """
        return True
    def set_new_current_mode(self, v):
        self.current_mode = v
    def get_current_mode(self):
        return self.current_mode
    def get_supported_only(self):
        return self.supported_only
    def set_non_apps_visible(self, non_apps_visible):
        self._non_apps_visible = non_apps_visible
    def __eq__(self, other):
        #if self is None and other is not None: 
        #    return True
        #if self is None or other is None: 
        #    return False
        #return (self.current_mode == other.current_mode and
        #        self.additional_pkglist == other.additional_pkglist and
        #        self.removed_pkglist == other.removed_pkglist)
        # FIXME: EVILHACK
        # let be evil for now and reforce all the reference. This bad hack can be removed once
        # __call__ doesn't need the filtering to be performed again for counting the number of package both side (so a one-only tree will be needed)
        # Note: evil here mean "as in maverick-natty-oneiric" case as there was not this kind of filter :)
        return False
    def __ne__(self, other):
        return not self.__eq__(other)
    def reset_counter(self):
        self.additional_apps_pkg = set()
        self.removed_apps_pkg = set()
    def _current_package_is_app(self, pkgname):
        if not self._package_cache_is_app:
            self._package_name_is_app = (self._non_apps_visible == AppStore.NONAPPS_ALWAYS_VISIBLE or
                                         len(self.db.get_apps_for_pkgname(pkgname)) == 1)
        return self._package_name_is_app
    def __call__(self, doc):
        """return True if the package should be displayed"""
        pkgname =  self.db.get_pkgname(doc)
        self._package_cache_is_app = None
        
        if self.current_mode == self.ADDITIONAL_PKG:
            pkg_list_to_compare = self.additional_pkglist
            other_list = self.removed_pkglist
        else:
            pkg_list_to_compare = self.removed_pkglist
            other_list = self.additional_pkglist

        # TODO: that's ugly, but if we could have a direct Xapian request
        # for that (OneConf doesn't know which packages are applications)
        # it would be better.

        if pkgname in other_list and self._current_package_is_app(pkgname): 
            if self.current_mode == self.ADDITIONAL_PKG:
                self.removed_apps_pkg.add(pkgname)
            else:
                self.additional_apps_pkg.add(pkgname)
                                    
        if pkgname in pkg_list_to_compare:
            if self._current_package_is_app(pkgname):
                if self.current_mode == self.ADDITIONAL_PKG:
                    self.additional_apps_pkg.add(pkgname)
                else:
                    self.removed_apps_pkg.add(pkgname)
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

    w = OneConfPane(cache, None, db, 'Ubuntu', icons, datadir, oneconfeventhandler, 'BBBBBB')
    w.show()

    window = gtk.Window()
    window.add(w)
    window.set_size_request(600, 500)
    window.set_position(gtk.WIN_POS_CENTER)
    window.show_all()
    window.connect('destroy', gtk.main_quit)

    gtk.main()

