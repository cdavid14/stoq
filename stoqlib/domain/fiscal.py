# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2006-2007 Async Open Source <http://www.async.com.br>
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
##
##  Author(s): Stoq Team <stoq-devel@async.com.br>
##
""" Domain classes to manage fiscal informations.

Note that this whole module is Brazil-specific.
"""

import datetime

from zope.interface import implements

from stoqlib.database.orm import (UnicodeCol, DateTimeCol, ForeignKey, IntCol,
                                  BoolCol)
from stoqlib.database.orm import LeftJoin, Join, const
from stoqlib.database.orm import Viewable
from stoqlib.database.orm import PriceCol
from stoqlib.database.runtime import get_current_branch
from stoqlib.domain.base import Domain
from stoqlib.domain.interfaces import IDescribable, IReversal
from stoqlib.domain.person import Person
from stoqlib.lib.parameters import sysparam


class CfopData(Domain):
    """A Brazil-specific class wich defines a fiscal code of operations.
    In Brazil it means 'Codigo fiscal de operacoes e prestacoes'
    """
    implements(IDescribable)

    code = UnicodeCol()
    description = UnicodeCol()

    def get_description(self):
        return u"%s %s" % (self.code, self.description)


class FiscalBookEntry(Domain):
    implements(IReversal)

    (TYPE_PRODUCT,
     TYPE_SERVICE,
     TYPE_INVENTORY) = range(3)

    date = DateTimeCol(default_factory=datetime.datetime.now)
    is_reversal = BoolCol(default=False)
    invoice_number = IntCol()
    cfop = ForeignKey("CfopData")
    branch = ForeignKey("Branch")
    drawee = ForeignKey("Person", default=None)
    payment_group = ForeignKey("PaymentGroup", default=None)
    iss_value = PriceCol(default=None)
    icms_value = PriceCol(default=None)
    ipi_value = PriceCol(default=None)
    entry_type = IntCol(default=None)

    @classmethod
    def has_entry_by_payment_group(cls, store, payment_group, entry_type):
        return bool(cls.get_entry_by_payment_group(
            store, payment_group, entry_type))

    @classmethod
    def get_entry_by_payment_group(cls, store, payment_group, entry_type):
        return store.find(cls, payment_group=payment_group,
                          is_reversal=False,
                          entry_type=entry_type).one()

    @classmethod
    def _create_fiscal_entry(cls, store, entry_type, group, cfop, invoice_number,
                             iss_value=0, icms_value=0, ipi_value=0):
        return FiscalBookEntry(
            entry_type=entry_type,
            iss_value=iss_value,
            ipi_value=ipi_value,
            icms_value=icms_value,
            invoice_number=invoice_number,
            cfop=cfop,
            drawee=group.recipient,
            branch=get_current_branch(store),
            date=const.NOW(),
            payment_group=group,
            store=store)

    @classmethod
    def create_product_entry(cls, store, group, cfop, invoice_number, value,
                             ipi_value=0):
        """Creates a new product entry in the fiscal book
        :param store: a store
        :param group: payment group
        :type  group: :class:`PaymentGroup`
        :param cfop: cfop for the entry
        :type  cfop: :class:`CfopData`
        :param invoice_number: payment invoice number
        :param value: value of the payment
        :param ipi_value: ipi value of the payment
        :returns: a fiscal book entry
        :rtype: :class:`FiscalBookEntry`
        """
        return cls._create_fiscal_entry(
            store,
            FiscalBookEntry.TYPE_PRODUCT,
            group, cfop, invoice_number,
            icms_value=value, ipi_value=ipi_value,
            )

    @classmethod
    def create_service_entry(cls, store, group, cfop, invoice_number, value):
        """Creates a new service entry in the fiscal book
        :param store: a store
        :param group: payment group
        :type  group: :class:`PaymentGroup`
        :param cfop: cfop for the entry
        :type  cfop: :class:`CfopData`
        :param invoice_number: payment invoice number
        :param value: value of the payment
        :returns: a fiscal book entry
        :rtype: :class:`FiscalBookEntry`
        """
        return cls._create_fiscal_entry(
            store,
            FiscalBookEntry.TYPE_SERVICE,
            group, cfop, invoice_number,
            iss_value=value,
            )

    def reverse_entry(self, invoice_number,
                      iss_value=None, icms_value=None, ipi_value=None):
        store = self.get_store()
        icms_value = icms_value if icms_value is not None else self.icms_value
        iss_value = iss_value if iss_value is not None else self.iss_value
        ipi_value = ipi_value if ipi_value is not None else self.ipi_value

        return FiscalBookEntry(
            entry_type=self.entry_type,
            iss_value=iss_value,
            icms_value=icms_value,
            ipi_value=ipi_value,
            cfop=sysparam(store).DEFAULT_RETURN_SALES_CFOP,
            branch=self.branch,
            invoice_number=invoice_number,
            drawee=self.drawee,
            is_reversal=True,
            payment_group=self.payment_group,
            store=store)


class _FiscalBookEntryView(Viewable):

    columns = dict(
        id=FiscalBookEntry.q.id,
        date=const.DATE(FiscalBookEntry.q.date),
        invoice_number=FiscalBookEntry.q.invoice_number,
        cfop_id=FiscalBookEntry.q.cfop_id,
        branch_id=FiscalBookEntry.q.branch_id,
        drawee_id=FiscalBookEntry.q.drawee_id,
        payment_group_id=FiscalBookEntry.q.payment_group_id,
        cfop_code=CfopData.q.code,
        drawee_name=Person.q.name,
        )

    joins = [
        LeftJoin(Person,
                   Person.q.id == FiscalBookEntry.q.drawee_id),
        Join(CfopData,
                    CfopData.q.id == FiscalBookEntry.q.cfop_id)
        ]

    @property
    def book_entry(self):
        return FiscalBookEntry.get(self.id,
                                   store=self.get_store())


class IcmsIpiView(_FiscalBookEntryView):
    """
    Stores information about the taxes (ICMS and IPI) related to a
    certain product.
    This view is used to query the product tax information.

    :param id: the id of the fiscal_book_entry
    :param icms_value: the total value of icms
    :param ipi_value: the total value of ipi
    :param date: the date when the entry was created
    :param invoice_number: the invoice number
    :param cfop_data_id: the cfop
    :param cfop_code: the code of the cfop
    :param drawee_name: the drawee name
    :param drawee_id: the person
    :param branch_id: the branch
    :param payment_group_id: the payment group
    """

    columns = _FiscalBookEntryView.columns.copy()
    columns['icms_value'] = FiscalBookEntry.q.icms_value
    columns['ipi_value'] = FiscalBookEntry.q.ipi_value

    clause = FiscalBookEntry.q.entry_type == FiscalBookEntry.TYPE_PRODUCT


class IssView(_FiscalBookEntryView):
    """
    Stores information related to a service tax (ISS).
    This view is used to query the service tax information.

    :param id: the id of the fiscal_book_entry
    :param iss_value: the total value of ipi
    :param date: the date when the entry was created
    :param invoice_number: the invoice number
    :param cfop_data_id: the if of the cfop_data table
    :param cfop_code: the code of the cfop
    :param drawee_name: the drawee name
    :param drawee_id: the person
    :param branch_id: the branch
    :param payment_group_id: the payment group
    """

    columns = _FiscalBookEntryView.columns.copy()
    columns['iss_value'] = FiscalBookEntry.q.iss_value

    clause = FiscalBookEntry.q.entry_type == FiscalBookEntry.TYPE_SERVICE
