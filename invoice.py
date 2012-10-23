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
        'afip_result': fields.selection([
            ('', 'No CAE'),
            ('A', 'Accepted'),
            ('R', 'Rejected'),
        ], 'Status', help='This status is asigned by the AFIP. If * No CAE * status mean you have no generate this invoice by '),
        'afip_service_start': fields.date(u'Service Start Date'),
        'afip_service_end': fields.date(u'Service End Date'),
        'afip_batch_number': fields.integer('Batch Number'),
        'afip_cae': fields.char(u'Código de Autorización Electrónico', size=24, readonly=True),
        'afip_motive': fields.text('Error motive'), # Hay una tabla con texto para cargar.
    }

    _defaults = {
        'afip_result': '',
    }

    def action_retrieve_cae(self, cr, uid, ids, *args):
        """
        Contact to the AFIP to get a CAE number.
        """
        Details = {}
        Auths = {}
        Invoice = {}
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

            # Take the last number of the "number".
            # Could not work if you dont use '/' as delimiter or if the number is not a postfix.
            invoice_number = int(inv.number.split('/')[-1])

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
            # Invoice number. Could not work if you print more than one page for an invoice.
            Detalle.set_element_cbt_desde(invoice_number)
            Detalle.set_element_cbt_hasta(invoice_number)
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
            Invoice[invoice_number] = inv

        # Now work for authority entities and send request.
        req_id = 0
        for name in Details:
            auth = Auths[name]
            details = Details[name]

            seq_id = self.pool.get('ir.sequence').get_id(cr, uid, auth.batch_sequence_id.id)
            batch_id = int(seq_id)

            request = FEAutRequestSoapIn()
            request = auth.set_auth_request(request)

            Fer = request.new_Fer()
            Fecr = Fer.new_Fecr()
            Fecr.set_element_id(batch_id) # Request id
            Fecr.set_element_cantidadreg(len(details))
            Fecr.set_element_presta_serv(1 if name[-3:] == '>_!' else 0)
            Fer.Fecr = Fecr

            Fedr = Fer.new_Fedr()
            Fedr.FEDetalleRequest = details
            Fer.Fedr = Fedr

            request.Fer = Fer

            response = get_bind(auth.server_id).FEAutRequest(request)

            if response._FEAutRequestResult._RError._percode == 0:
                # Not error
                for i in range(response._FEAutRequestResult._FecResp._cantidadreg):
                    response_id = response._FEAutRequestResult._FecResp._id # ID de lote.
                    r = response._FEAutRequestResult._FedResp._FEDetalleResponse[i]
                    self.write(cr, uid, Invoice[r._cbt_desde].id, 
                               {'afip_cae': int(r._cae),
                                'afip_batch_number':response_id,
                                'afip_result': r._resultado,
                                'afip_motive': r._motivo,
                               })
            else:
                # Error
                response_id = response._FEAutRequestResult._FecResp._id # ID de lote.
                response_cuit = response._FEAutRequestResult._FecResp._cuit
                response_fecha_cae = response._FEAutRequestResult._FecResp._fecha_cae
                response_cant_reg = response._FEAutRequestResult._FecResp._cantidadreg
                response_resultado = response._FEAutRequestResult._FecResp._resultado
                response_motivo = response._FEAutRequestResult._FecResp._motivo
                response_reproceso = response._FEAutRequestResult._FecResp._reproceso
                for i in range(response._FEAutRequestResult._FecResp._cantidadreg):
                    r = response._FEAutRequestResult._FedResp._FEDetalleResponse[i]
                    self.write(cr, uid, Invoice[r._cbt_desde].id, 
                               {'afip_batch_number':response_id,
                                'status': 'invalid',
                                'afip_result': r._resultado,
                                'afip_motive': r._motivo,
                               })
        pass

invoice()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
