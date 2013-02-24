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
from openerp.osv import fields, osv
from cache_bind import get_bind
from stub.Service_client import *
from stub.Service_types import *
from openerp.tools.translate import _
import re
import logging

_logger = logging.getLogger(__name__)
_schema = logging.getLogger(__name__ + '.schema')

# Tabla de Codigo de Documentos por tipo de Facturas
_FACT_A = [ 1, 2, 3, 4, 5, ]
_FACT_B = [ 6, 7, 8, 9, 10, ]
_FACT_C = [ 11, 12, 13, 15, 16, ]
_FACT_E = [ 19, 20, 21, 22, ]
_FACT_M = [ 51, 52, 53, 54, 55, ]
_TIQU_A = [ 81 ]
_TIQU_B = [ 82 ]
_TIQU_X = [ 83 ]

# Number Filter
re_number = re.compile(r'\d{8}')


class invoice(osv.osv):
    _inherit = "account.invoice"
    _columns = {
        'afip_result': fields.selection([
            ('', 'No CAE'),
            ('A', 'Accepted'),
            ('R', 'Rejected'),
        ], 'Status', help='This state is asigned by the AFIP. If * No CAE * state mean you have no generate this invoice by '),
        'afip_service_start': fields.date(u'Service Start Date'),
        'afip_service_end': fields.date(u'Service End Date'),
        'afip_batch_number': fields.integer('Batch Number', readonly=True),
        'afip_cae': fields.char(u'CAE number', size=24, readonly=True),
        'afip_cae_due': fields.date(u'CAE due', readonly=True),
        'afip_error_id': fields.many2one('afip.wsfe_error', 'AFIP Status', readonly=True),
    }

    _defaults = {
        'afip_result': '',
    }

    def valid_batch(self, cr, uid, ids, *args):
        """
        Increment batch number groupping by afip authority server.
        """
        auths = []
        invoices = {}
        for inv in self.browse(cr, uid, ids):
            auth = inv.journal_id.afip_authorization_id
            if not auth: continue
            if inv.journal_id.afip_items_generated + 1 != inv.journal_id.sequence_id.number_next:
                raise osv.except_osv(_(u'Syncronization Error'),
                                     _(u'La AFIP espera que el próximo número de secuencia sea %i, pero el sistema indica que será %i. Hable inmediatamente con su administrador del sistema para resolver este problema.') %
                                     (inv.journal_id.afip_items_generated + 1, inv.journal_id.sequence_id.number_next))
            auths.append(auth)
            invoices[auth.id] = invoices.get(auth.id, []) + [inv.id]

        for auth in auths:
            self.write(cr, uid, invoices[auth.id], { 'afip_batch_number': int(auth.batch_sequence_id.get_id()) })

        return True

    def action_retrieve_cae(self, cr, uid, ids, *args):
        """
        Contact to the AFIP to get a CAE number.
        """
        wsfe_error_obj = self.pool.get('afip.wsfe_error')

        Details = {}
        Auths = {}
        Invoice = {}
        BatchNum = {}
        for inv in self.browse(cr, uid, ids):
            journal = inv.journal_id
            auth = journal.afip_authorization_id

            # Only process if set to connect to afip
            if not auth: continue
            
            # Ignore invoice if connection server is not type WSFE.
            if auth.server_id.code != 'wsfe': continue

            auth.login() # Login if nescesary.
            
            # Ignore if cant connect to server.
            if auth.state not in  [ 'connected', 'clockshifted' ]: continue

            # New invoice detail
            Detalle = FEAutRequestSoapIn().new_Fer().new_Fedr().new_FEDetalleRequest()

            # Take the last number of the "number".
            # Could not work if your number have not 8 digits.
            invoice_number = int(re_number.search(inv.number).group())

            # Partner data
            if inv.partner_id.document_type and inv.partner_id.document_number:
                # CUIT
                Detalle.set_element_tipo_doc(inv.partner_id.document_type.afip_code)
                Detalle.set_element_nro_doc(int(inv.partner_id.document_number))
            else:
                raise osv.except_osv(_(u'Invoice error'),
                                     _(u'The customer needs to identify with a document to billing.'))

            # Document information
            Detalle.set_element_tipo_cbte(journal.journal_class_id.afip_code)
            Detalle.set_element_punto_vta(journal.point_of_sale)
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
                Detalle.set_element_fecha_serv_desde(inv.afip_service_start.replace('-',''))
                Detalle.set_element_fecha_serv_hasta(inv.afip_service_end.replace('-',''))
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
            BatchNum[name] = inv.afip_batch_number

        # Now work for authority entities and send request.
        req_id = 0
        for name in Details:
            auth = Auths[name]
            details = Details[name]

            seq_id = BatchNum[name]
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

            if response._FEAutRequestResult._RError._percode == 0 and response._FEAutRequestResult._FecResp._resultado in [ 'P', 'A' ]:
                # Not error
                error_message = []
                for i in range(response._FEAutRequestResult._FecResp._cantidadreg):
                    response_id = response._FEAutRequestResult._FecResp._id # ID de lote.
                    r = response._FEAutRequestResult._FedResp._FEDetalleResponse[i]

                    afip_error_ids = wsfe_error_obj.search(cr, uid, [('code','in',r._motivo.split(';'))])
                    afip_error = wsfe_error_obj.browse(cr, uid, afip_error_ids)
                    afip_message = '; '.join([ err.description for err in afip_error ])
                    error_message.append(_('Invoice %s: %s.') % (r._cbt_desde, afip_message))

                    _logger.error(_('Processed document %s-%s. AFIP message: %s.') % (r._cbt_desde, r._cbt_hasta, afip_message))

                    if r._cbt_desde not in Invoice:
                        _logger.error(_('Document sequence is not syncronized with AFIP. Afip return %i as valid.') % r._cbt_desde)
                        _logger.error(_('Expected sequences: %s.') % repr(Invoice.keys()))
                        continue

                    if r._cae is None:
                        _logger.error(_('Document have not CAE assigned.'))
                        return False 

                    self.write(cr, uid, Invoice[r._cbt_desde].id, 
                               {'afip_cae': r._cae,
                                'afip_cae_due': r._fecha_vto,
                                'afip_batch_number':response_id,
                                'afip_result': r._resultado,
                                'afip_error_id': afip_error_ids[0],
                               })
            elif response._FEAutRequestResult._FecResp is None:
                raise osv.except_osv(_('AFIP error'),
                                     _(u'Ocurrió un error en el AFIP (%i): %s') % 
                                     (response._FEAutRequestResult._RError._percode,
                                      response._FEAutRequestResult._RError._perrmsg,
                                     ))
            elif response._FEAutRequestResult._FecResp is not None:
                response_id = response._FEAutRequestResult._FecResp._id # ID de lote.
                response_cuit = response._FEAutRequestResult._FecResp._cuit
                response_fecha_cae = response._FEAutRequestResult._FecResp._fecha_cae
                response_cant_reg = response._FEAutRequestResult._FecResp._cantidadreg
                response_resultado = response._FEAutRequestResult._FecResp._resultado
                response_motivo = response._FEAutRequestResult._FecResp._motivo
                response_reproceso = response._FEAutRequestResult._FecResp._reproceso

                _logger.error(_('AFIP dont approve some document. Global Reason: %s') % response_motivo)

                error_message = []
                for i in range(response._FEAutRequestResult._FecResp._cantidadreg):
                    r = response._FEAutRequestResult._FedResp._FEDetalleResponse[i]

                    afip_error_ids = wsfe_error_obj.search(cr, uid, [('code','in',r._motivo.split(';'))])
                    afip_error = wsfe_error_obj.browse(cr, uid, afip_error_ids)
                    afip_message = '; '.join([ err.description for err in afip_error ])
                    error_message.append(_('Invoice %s: %s.') % (r._cbt_desde, afip_message))

                    _logger.error(_('AFIP dont approve the document %s-%s. Reason: %s.') % (r._cbt_desde, r._cbt_hasta, afip_message))

                    if r._cbt_desde not in Invoice:
                        _logger.error(_('Document sequence is not syncronized with AFIP. Afip return %i as valid.') % r._cbt_desde)
                        _logger.error(_('Expected sequences: %s.') % repr(Invoice.keys()))
                        return False

                # Esto deberia ser un mensaje al usuario, asi termina de procesar todas las facturas.
                raise osv.except_osv(_('AFIP error'),
                                     _(u'Ocurriró un error en el AFIP (%i: %s).<br/>\n %s.\n') % 
                                     (response._FEAutRequestResult._RError._percode,
                                      response._FEAutRequestResult._RError._perrmsg,
                                      '<br/>\n'.join(error_message),
                                     ))
        pass

    def invoice_print(self, cr, uid, ids, context=None):
        '''
        This function prints the invoice and mark it as sent, so that we can see more easily the next step of the workflow
        '''
        assert len(ids) == 1, 'This option should only be used for a single id at a time.'
        self.write(cr, uid, ids, {'sent': True}, context=context)
        datas = {
            'ids': ids,
            'model': 'account.invoice',
            'form': self.read(cr, uid, ids[0], context=context)
        }
        is_electronic = bool(self.browse(cr, uid, ids[0]).journal_id.afip_authorization_id)
        return {
            'type': 'ir.actions.report.xml',
            'report_name': 'account.invoice_fe' if is_electronic else 'account.invoice',
            'datas': datas,
            'nodestroy' : True
        }

invoice()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
