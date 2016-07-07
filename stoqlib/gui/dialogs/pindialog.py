# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2016 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
## Author(s): Stoq Team <stoq-devel@async.com.br>
##

import logging

from kiwi.python import Settable

from stoqlib.api import api
from stoqlib.gui.editors.baseeditor import BaseEditor
from stoqlib.lib.message import warning, info
from stoqlib.lib.translation import stoqlib_gettext as _
from stoqlib.net.server import ServerProxy, ServerError

log = logging.getLogger(__name__)


class PinDialog(BaseEditor):
    gladefile = 'PinDialog'
    model_type = Settable
    title = _("Connect to Stoq.link")
    size = (400, 200)
    proxy_widgets = ['pin']
    confirm_widgets = proxy_widgets

    def __init__(self, store):
        super(PinDialog, self).__init__(store)
        self._processing = False
        self._done = False
        self._set_processing(False)

    #
    #   BaseEditor
    #

    def create_model(self, store):
        return Settable(pin=None)

    def setup_proxies(self):
        self.add_proxy(self.model, self.proxy_widgets)
        self._proxy = ServerProxy()

    def validate_confirm(self):
        if self._done:
            return True

        self._set_processing(True)
        self._register_link()
        return False

    def refresh_ok(self, validation_value):
        super(PinDialog, self).refresh_ok(
            validation_value and not self._processing)

    #
    #   Private
    #

    def _set_processing(self, processing):
        self._processing = processing
        self.main_dialog.ok_button.set_sensitive(self.is_valid and not processing)
        self.main_dialog.cancel_button.set_sensitive(not processing)
        if processing:
            self.reply_lbl.set_text(
                _("Setting up the connection. This may take a while..."))
        else:
            self.reply_lbl.set_text("")
        self.spinner.set_visible(processing)

    @api.async
    def _register_link(self):
        running = yield self._proxy.check_running()
        if running:
            pin = self.pin.read()
            try:
                rv = yield self._proxy.call('register_link', pin)
            except ServerError as e:
                warning(_("An error happened when trying to register "
                          "to Stoq.Link"), str(e))
            else:
                log.info("register_link succedded. Retval: %s", rv)
                # If no exception happened, that mens that the registration
                # has succeeded.
                # XXX: Better text here
                info(_("Stoq.Link registration successful! You may "
                       "manage your installation from there now"))
                self._done = True
                self.confirm()
        else:
            # TODO: Maybe we should add a link pointing to instructions
            # on how to get and install the stoq-server package?
            warning(_("Could not find an instance of Stoq Server running."))

        self._set_processing(False)