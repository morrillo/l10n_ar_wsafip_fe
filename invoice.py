# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright (C) 2012 OpenERP - Team de Localización Argentina.
# https://launchpad.net/~openerp-l10n-ar-localization
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from osv import fields, osv
from cache_bind import get_bind
from stub.Service_client import *
from stub.Service_types import *
import netsvc

class invoice(osv.osv):
    # Class members to send messages to the logger system.
    _logger = netsvc.Logger()

    def logger(self, log, msg):
        self._logger.notifyChannel('addons.'+self._name, log, msg)

    _inherit = "account.invoice"
    _columns = {
        'afip_status': fields.selection([
            ('nocae', 'No CAE'),
            ('valid', 'Valid'),
            ('invalid', 'Invalid'),
        ], 'Status', help='This status is asigned by the AFIP. If * No CAE * status mean you have no generate this invoice by '),
        'afip_service_start': fields.date(u'Service Start Date'),
        'afip_service_end': fields.date(u'Service End Date'),
        'cae': fields.char(u'Código de Autorización Electrónico', size=24, readonly=True),
    }

    def action_retrieve_cae(self, cr, uid, ids, *args):
        """
        Contact to the AFIP to get a CAE number.
        """
        Details = {}
        Auths = {}
        for inv in self.browse(cr, uid, ids):
            journal = inv.journal_id
            auth = journal.afip_authorization_id

            # Only process if set to connect to afip
            if not auth: continue
            
            # Ignore invoice if connection server is not type WSFE.
            if auth.server_id.code != 'wsfe': continue

            auth.login() # Login if nescesary.
            
            # Ignore if cant connect to server.
            if auth.status not in  [ 'Connected', 'Shifted Clock' ]: continue

            # New invoice detail
            Detalle = FEAutRequestSoapIn().new_Fer().new_Fedr().new_FEDetalleRequest()

            # Partner data
            if inv.partner_id.vat and inv.partner_id.vat[:2] == 'ar':
                # CUIT
                Detalle.set_element_tipo_doc(80)
                Detalle.set_element_nro_doc(int(inv.parter_id.vat[2:]))
            elif inv.partner_id.vat and inv.partner_id.vat[:2] != 'ar':
                # CUIT for country
                raise NotImplemented
            else:
                # Consumidor final. No lleno estos datos.
                Detalle.set_element_tipo_doc(80)
                Detalle.set_element_nro_doc(99999999999)

            # Document information
            Detalle.set_element_tipo_cbte(journal.afip_document_class_id.code)
            Detalle.set_element_punto_vta(journal.afip_point_of_sale)
            # Comprobantes???
            Detalle.set_element_cbt_desde(1)
            Detalle.set_element_cbt_hasta(1)
            # Values: REVISAR!!!
            Detalle.set_element_imp_total(inv.amount_total)
            Detalle.set_element_imp_tot_conc(0)
            Detalle.set_element_imp_neto(inv.amount_untaxed)
            Detalle.set_element_impto_liq(inv.amount_tax)
            Detalle.set_element_impto_liq_rni(0)
            Detalle.set_element_imp_op_ex(0)
            # Dates
            Detalle.set_element_fecha_cbte(inv.date_invoice.replace('-',''))
            if inv.date_due:
                Detalle.set_element_fecha_venc_pago(inv.date_due.replace('-',''))
            # For service type
            if inv.afip_service_start:
                Detalle.set_element_fecha_serv_desde(inv.afip_service_start)
                Detalle.set_element_fecha_serv_hasta(inv.afip_service_end)
                is_service = True
            else:
                is_service = False

            # Store detail
            name = ("<%s>_!" if is_service else "<%s>") % auth.name
            if not auth in Details:
                Details[name] = []
                Auths[name] = auth
            Details[name].append(Detalle)

        # Now work for authority entities and send request.
        req_id = 0
        for name in Details:
            auth = Auths[name]
            details = Details[name]

            request = FEAutRequestSoapIn()
            request = auth.set_auth_request(request)

            Fer = request.new_Fer()
            Fecr = Fer.new_Fecr()
            Fecr.set_element_id(req_id) # Request id
            Fecr.set_element_cantidadreg(len(details))
            Fecr.set_element_presta_serv(1 if name[-3:] == '>_!' else 0)
            Fer.Fecr = Fecr

            Fedr = Fer.new_Fedr()
            Fedr.FEDetalleRequest = details
            Fer.Fedr = Fedr

            request.Fer = Fer

            import pdb; pdb.set_trace()

            response = get_bind(auth.server_id).FEAutRequest(request)

            if response._FEAutRequestResult._RError._percode == 0:
                import pdb; pdb.set_trace()
            else:
                import pdb; pdb.set_trace()

        pass

invoice()



# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
