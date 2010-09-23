# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005-2009 Async Open Source <http://www.async.com.br>
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
## Author(s):   Ronaldo Maia                <romaia@async.com.br>
##
##
""" Stock Decrease wizard definition """

import datetime
from decimal import Decimal
import sys

import gtk

from kiwi.datatypes import currency, ValidationError
from kiwi.ui.widgets.list import Column

from stoqlib.database.runtime import (get_current_branch, new_transaction,
                                      finish_transaction, get_current_user)
from stoqlib.domain.interfaces import (IBranch, ITransporter, ISupplier,
                                       IStorable, IEmployee)
from stoqlib.domain.payment.group import PaymentGroup
from stoqlib.domain.payment.method import PaymentMethod
from stoqlib.domain.payment.operation import register_payment_operations
from stoqlib.domain.person import Person
from stoqlib.domain.product import ProductSupplierInfo
from stoqlib.domain.receiving import (ReceivingOrder, ReceivingOrderItem,
                                      get_receiving_items_by_purchase_order)
from stoqlib.domain.sellable import Sellable
from stoqlib.domain.stockdecrease import StockDecrease, StockDecreaseItem
from stoqlib.lib.translation import stoqlib_gettext
from stoqlib.lib.parameters import sysparam
from stoqlib.lib.validators import format_quantity, get_formatted_cost
from stoqlib.gui.base.wizards import WizardEditorStep, BaseWizard
from stoqlib.gui.editors.purchaseeditor import PurchaseItemEditor
from stoqlib.gui.printing import print_report
from stoqlib.gui.wizards.personwizard import run_person_role_dialog
from stoqlib.gui.wizards.receivingwizard import ReceivingInvoiceStep
from stoqlib.gui.wizards.abstractwizard import SellableItemStep
from stoqlib.gui.editors.personeditor import SupplierEditor, TransporterEditor
from stoqlib.gui.slaves.paymentslave import (CheckMethodSlave,
                                             BillMethodSlave, MoneyMethodSlave)

_ = stoqlib_gettext


#
# Wizard Steps
#


class StartStockDecreaseStep(WizardEditorStep):
    gladefile = 'StartStockDecreaseStep'
    model_type = StockDecrease
    proxy_widgets = ('confirm_date',
                     'branch',
                     'reason',
                     'removed_by',
                     )


    def _fill_employee_combo(self):
        employees = [(e.person.name, e)
                     for e in Person.iselect(IEmployee,
                                             connection=self.conn)]
        self.removed_by.prefill(sorted(employees))


    def _fill_branch_combo(self):
        table = Person.getAdapterClass(IBranch)
        branches = table.get_active_branches(self.conn)
        items = [(s.person.name, s) for s in branches]
        self.branch.prefill(sorted(items))

    def _setup_widgets(self):
        self.confirm_date.set_sensitive(False)
        self._fill_employee_combo()
        self._fill_branch_combo()

    #
    # WizardStep hooks
    #

    def post_init(self):
        self.confirm_date.grab_focus()
        self.table1.set_focus_chain([self.confirm_date, self.branch,
                                     self.removed_by, self.reason])
        self.register_validate_function(self.wizard.refresh_next)
        self.force_validation()

    def next_step(self):
        return DecreaseItemStep(self.wizard, self, self.conn, self.model)

    def has_previous_step(self):
        return False

    def setup_proxies(self):
        self._setup_widgets()
        self.proxy = self.add_proxy(self.model,
                                    self.proxy_widgets)




class DecreaseItemStep(SellableItemStep):
    """ Wizard step for purchase order's items selection """
    model_type = StockDecrease
    item_table = StockDecreaseItem
    summary_label_text = "<b>%s</b>" % _('Total Ordered:')
    summary_label_column = None
    sellable_editable = False

    #
    # Helper methods
    #

    def get_sellable_view_query(self):
        return Sellable.get_available_sellables_query(
            self.conn,
            )

    def setup_slaves(self):
        SellableItemStep.setup_slaves(self)
        self.hide_add_button()

        self.cost_label.set_visible(False)
        self.cost.set_visible(False)
        self.quantity.connect('validate', self._on_quantity__validate)

    #
    # SellableItemStep virtual methods
    #

    def validate(self, value):
        SellableItemStep.validate(self, value)
        can_decrease = self.model.get_items().count()
        self.wizard.refresh_next(can_decrease)

    def get_order_item(self, sellable, cost, quantity):
        item = self.model.add_sellable(sellable, quantity)
        return item

    def get_saved_items(self):
        return list(self.model.get_items())

    def get_columns(self):
        return [
            Column('sellable.code', title=_('Code'), width=100, data_type=str),
            Column('sellable.description', title=_('Description'),
                   data_type=str, expand=True, searchable=True),
            Column('sellable.category_description', title=_('Category'),
                   data_type=str, expand=True, searchable=True),
            Column('quantity', title=_('Quantity'), data_type=float, width=90,
                   format_func=format_quantity),
            Column('sellable.unit_description',title=_('Unit'), data_type=str,
                   width=70),
            ]

    #
    # WizardStep hooks
    #

    def post_init(self):
        SellableItemStep.post_init(self)
        self.slave.set_editor(PurchaseItemEditor)
        self._refresh_next()

    def has_next_step(self):
        return False

    def next_step(self):
        return None

    #
    # Callbacks
    #

    def _on_quantity__validate(self, widget, value):
        if not value or value <= Decimal(0):
            return ValidationError(_(u'Quantity must be greater than zero'))

        sellable = self.proxy.model.sellable
        storable = IStorable(sellable.product, None)
        assert storable
        balance = storable.get_stock_item(self.model.branch).quantity
        for i in self.slave.klist:
            if i.sellable == sellable:
                balance -= i.quantity

        if value > balance:
            return ValidationError(
                _(u'Quantity is greater than the quantity in stock.'))





#
# Main wizard
#


class StockDecreaseWizard(BaseWizard):
    size = (775, 400)
    title = _('Manual Stock Decrease')

    def __init__(self, conn):
        model = self._create_model(conn)

        first_step = StartStockDecreaseStep(conn, self, model)
        BaseWizard.__init__(self, conn, first_step, model)

    def _create_model(self, conn):
        branch = get_current_branch(conn)
        user = get_current_user(conn)
        employee = IEmployee(user.person, None)
        return StockDecrease(responsible=user,
                             removed_by=employee,
                             branch=branch,
                             status=StockDecrease.STATUS_INITIAL,
                             connection=conn)

    #
    # WizardStep hooks
    #

    def finish(self):
        self.retval = self.model
        self.model.confirm()
        self.close()
