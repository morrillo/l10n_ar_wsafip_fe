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

# Functions to list parents names.
def _get_parents(child, parents=[]):
    if child and not isinstance(child, osv.orm.browse_null):
        return parents + [ child.name ] + _get_parents(child.parent_id)
    else:
        return parents

def _calc_concept(product_types):
    if product_types == set(['consu']):
        concept = '1'
    elif product_types == set(['service']):
        concept = '2'
    elif product_types == set(['consu','service']):
        concept = '3'
    else:
        concept = False
    return concept

class invoice(osv.osv):
    def _get_concept(self, cr, uid, ids, name, args, context=None):
        r = {}
        for inv in self.browse(cr, uid, ids):
            concept = False
            product_types = set([ line.product_id.type for line in inv.invoice_line ])
            r[inv.id] = _calc_concept(product_types)
        return r

    _inherit = "account.invoice"
    _columns = {
        'afip_concept': fields.function(_get_concept,
                                        type="selection",
                                        selection=[('1','Consumible'),
                                                   ('2','Service'),
                                                   ('3','Mixted')],
                                        method=True,
                                        string="AFIP concept",
                                        readonly=1),
        'afip_result': fields.selection([
            ('', 'No CAE'),
            ('A', 'Accepted'),
            ('R', 'Rejected'),
        ], 'Status', help='This state is asigned by the AFIP. If * No CAE * state mean you have no generate this invoice by '),
        'afip_service_start': fields.date('Service Start Date'),
        'afip_service_end': fields.date('Service End Date'),
        'afip_batch_number': fields.integer('Batch Number', readonly=True),
        'afip_cae': fields.char('CAE number', size=24),
        'afip_cae_due': fields.date('CAE due'),
        'afip_error_id': fields.many2one('afip.wsfe_error', 'AFIP Status', readonly=True),
    }

    _defaults = {
        'afip_result': '',
    }

    def valid_batch(self, cr, uid, ids, *args):
        """
        Increment batch number groupping by afip connection server.
        """
        conns = []
        invoices = {}
        for inv in self.browse(cr, uid, ids):
            conn = inv.journal_id.afip_connection_id
            if not conn: continue
            if inv.journal_id.afip_items_generated + 1 != inv.journal_id.sequence_id.number_next:
                raise osv.except_osv(_(u'Syncronization Error'),
                                     _(u'La AFIP espera que el próximo número de secuencia sea %i, pero el sistema indica que será %i. Hable inmediatamente con su administrador del sistema para resolver este problema.') %
                                     (inv.journal_id.afip_items_generated + 1, inv.journal_id.sequence_id.number_next))
            conns.append(conn)
            invoices[conn.id] = invoices.get(conn.id, []) + [inv.id]

        for conn in conns:
            prefix = conn.batch_sequence_id.prefix or ''
            suffix = conn.batch_sequence_id.suffix or ''
            sid_re = re.compile('%s(\d*)%s' % (prefix, suffix))
            sid = conn.batch_sequence_id.get_id()
            self.write(cr, uid, invoices[conn.id], {
                'afip_batch_number': int(sid_re.search(sid).group(1)),
            })

        return True

    def get_related_invoices(self, cr, uid, ids, *args):
        """
        List related invoice information to fill CbtesAsoc
        """
        r = {}
        _ids = [ids] if isinstance(ids, int) else ids

        for inv in self.browse(cr, uid, _ids):
            r[inv.id] = []
            rel_inv_ids = self.search(cr, uid, [('number','=',inv.origin),
                                                ('state','not in',['draft','proforma','proforma2','cancel'])])
            for rel_inv in self.browse(cr, uid, rel_inv_ids):
                journal = rel_inv.journal_id
                r[inv.id].append({
                    'Tipo': journal.journal_class_id.afip_code,
                    'PtoVta': journal.point_of_sale,
                    'Nro': rel_inv.invoice_number,
                })

        return r[ids] if isinstance(ids, int) else r

    def get_taxes(self, cr, uid, ids, *args):
        r = {}
        _ids = [ids] if isinstance(ids, int) else ids

        for inv in self.browse(cr, uid, _ids):
            r[inv.id] = []

            for tax in inv.tax_line:
                if tax.account_id.name == 'IVA a pagar':
                    continue
                r[inv.id].append({
                    'Id': tax.tax_code_id.parent_afip_code,
                    'Desc': tax.tax_code_id.name,
                    'BaseImp': tax.base_amount,
                    'Alic': (tax.tax_amount / tax.base_amount),
                    'Importe': tax.tax_amount,
                })


        return r[ids] if isinstance(ids, int) else r

    def get_vat(self, cr, uid, ids, *args):
        r = {}
        _ids = [ids] if isinstance(ids, int) else ids

        for inv in self.browse(cr, uid, _ids):
            r[inv.id] = []

            for tax in inv.tax_line:
                if tax.account_id.name != 'IVA a pagar':
                    continue
                r[inv.id].append({
                    'Id': tax.tax_code_id.parent_afip_code,
                    'BaseImp': tax.base_amount,
                    'Importe': tax.tax_amount,
                })

        return r[ids] if isinstance(ids, int) else r

    def get_optionals(self, cr, uid, ids, *args):
        optional_type_obj = self.pool.get('afip.optional_type')

        r = {}
        _ids = [ids] if isinstance(ids, int) else ids
        optional_type_ids = optional_type_obj.search(cr, uid, [])

        for inv in self.browse(cr, uid, _ids):
            r[inv.id] = []
            for optional_type in optional_type_obj.browse(cr, uid, optional_type_ids):
                if optional_type.apply_rule and optional_type.value_computation:
                    """
                    Debería evaluar apply_rule para saber si esta opción se computa
                    para esta factura. Y si se computa, se evalua value_computation
                    sobre la factura y se obtiene el valor que le corresponda.
                    Luego se debe agregar al output r.
                    """
                    raise NotImplemented

        return r[ids] if isinstance(ids, int) else r

    def action_retrieve_cae(self, cr, uid, ids, context=None):
        """
        Contact to the AFIP to get a CAE number.
        """
        if context is None:
            context = {}
        #TODO: not correct fix but required a frech values before reading it.
        self.write(cr, uid, ids, {})

        wsfe_error_obj = self.pool.get('afip.wsfe_error')
        conn_obj = self.pool.get('wsafip.connection')
        serv_obj = self.pool.get('wsafip.server')
        currency_obj = self.pool.get('res.currency')

        Servers = {}
        Requests = {}
        Inv2id = {}
        for inv in self.browse(cr, uid, ids, context=context):
            journal = inv.journal_id
            conn = journal.afip_connection_id

            # Only process if set to connect to afip
            if not conn: continue
            
            # Ignore invoice if connection server is not type WSFE.
            if conn.server_id.code != 'wsfe': continue

            Servers[conn.id] = conn.server_id.id

            # Take the last number of the "number".
            # Could not work if your number have not 8 digits.
            invoice_number = int(re_number.search(inv.number).group())

            _f_date = lambda d: d and d.replace('-','')

            # Build request dictionary
            if conn.id not in Requests: Requests[conn.id] = {}
            Requests[conn.id][inv.id]=dict( (k,v) for k,v in {
                'CbteTipo': journal.journal_class_id.afip_code,
                'PtoVta': journal.point_of_sale,
                'Concepto': inv.afip_concept,
                'DocTipo': inv.partner_id.document_type_id.afip_code or '99',
                'DocNro': int(inv.partner_id.document_type_id.afip_code is not None and inv.partner_id.document_number),
                'CbteDesde': invoice_number,
                'CbteHasta': invoice_number,
                'CbteFch': _f_date(inv.date_invoice),
                'ImpTotal': inv.amount_total,
                'ImpTotConc': 0, # TODO: Averiguar como calcular el Importe Neto no Gravado
                'ImpNeto': inv.amount_untaxed,
                'ImpOpEx': inv.compute_all(line_filter=lambda line: len(line.invoice_line_tax_id)==0)['amount_total'],
                'ImpIVA': inv.compute_all(tax_filter=lambda tax: 'IVA' in _get_parents(tax.tax_code_id))['amount_tax'],
                'ImpTrib': inv.compute_all(tax_filter=lambda tax: 'IVA' not in _get_parents(tax.tax_code_id))['amount_tax'],
                'FchServDesde': _f_date(inv.afip_service_start) if inv.afip_concept != '1' else None,
                'FchServHasta': _f_date(inv.afip_service_end) if inv.afip_concept != '1' else None,
                'FchVtoPago': _f_date(inv.date_due) if inv.afip_concept != '1' else None,
                'MonId': inv.currency_id.afip_code,
                'MonCotiz': currency_obj.compute(cr, uid, inv.currency_id.id, inv.company_id.currency_id.id, 1.),
                'CbtesAsoc': [ {'CbteAsoc': c} for c in self.get_related_invoices(cr, uid, inv.id) ],
                'Tributos': [ {'Tributo': t} for t in self.get_taxes(cr, uid, inv.id) ],
                'Iva': [ {'AlicIva': a} for a in self.get_vat(cr, uid, inv.id) ],
                'Opcionales': [ {'Opcional': o} for o in self.get_optionals(cr, uid, inv.id) ],
            }.iteritems() if v is not None)
            Inv2id[invoice_number] = inv.id

        for c_id, req in Requests.iteritems():
            conn = conn_obj.browse(cr, uid, c_id)
            res = serv_obj.wsfe_get_cae(cr, uid, [conn.server_id.id], c_id, req)
            for k, v in res.iteritems():
                if 'CAE' in v:
                    self.write(cr, uid, Inv2id[k], {
                        'afip_cae': v['CAE'],
                        'afip_cae_due': v['CAEFchVto'],
                    })
                else:
                    # Muestra un mensaje de error por la factura con error.
                    # Se cancelan todas las facturas del batch!
                    msg = 'Factura %s:\n' % k + '\n'.join(
                        [ u'(%s) %s\n' % e for e in v['Errores']] +
                        [ u'(%s) %s\n' % e for e in v['Observaciones']]
                    )
                    raise osv.except_osv(_(u'AFIP Validation Error'), msg)

        return True


    def _do_request(self, request_dict):

        Details = {}
        Auths = {}
        Invoice = {}
        BatchNum = {}

        if False:
            # New invoice request, header and details
            Request = FECAESolicitarSoapIn().new_FeCAEReq()
            Header  = Request.new_FeCabReq()
            Details = Request.new_FeDetReq()
            Detail  = Details.new_FECAEDetRequest() # One for invoice

            # Create header
            Header.set_element_CantReg(1)
            Header.set_element_CbteTipo(journal.journal_class_id.afip_code)
            Header.set_element_PtoVta(journal.point_of_sale)

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
        is_electronic = bool(self.browse(cr, uid, ids[0]).journal_id.afip_connection_id)
        return {
            'type': 'ir.actions.report.xml',
            'report_name': 'account.invoice_fe' if is_electronic else 'account.invoice',
            'datas': datas,
            'nodestroy' : True
        }

    def afip_get_currency_code(self, cr, uid, ids, currency_id, context=None):
        """
        Take the AFIP currency code. If not set update database.
        """
        currency_obj = self.pool.get('res.currency')

        afip_code = currency_obj.read(cr, uid, currency_id, ['afip_code'], context=context)

        if not afip_code['afip_code']:
            self.afip_update_currency(cr, uid, ids, context=context)

            afip_code = currency_obj.read(cr, uid, currency_id, ['afip_code'], context=context)

        return afip_code['afip_code']

    def afip_update_currency(self, cr, uid, ids, context=None):
        """
        Update currency codes from AFIP database.
        """
        currency_obj = self.pool.get('res.currency')

        for inv in self.browse(cr, uid, ids[:1], context=context):
            journal = inv.journal_id
            auth = journal.afip_connection_id

            # Only process if set to connect to afip
            if not auth: continue
            
            # Ignore invoice if connection server is not type WSFE.
            if auth.server_id.code != 'wsfe': continue

            auth.login() # Login if nescesary.
            
            # Ignore if cant connect to server.
            if auth.state not in  [ 'connected', 'clockshifted' ]: continue

            # Build request
            request = FEParamGetTiposMonedasSoapIn()
            request = auth.set_auth_request(request)

            response = get_bind(auth.server_id).FEParamGetTiposMonedas(request)

        pass
    
    def onchange_invoice_line(self, cr, uid, ids, invoice_line):
        product_obj = self.pool.get('product.product')
        res = {}
        product_types = set()

        for act, opt, data in invoice_line:
            product_id = data.get('product_id', False)
            if product_id:
                product_types.add(product_obj.read(cr, uid, product_id, ['type'])['type'])
                
        res['value'] = { 'afip_concept': _calc_concept(product_types) }
        return res

invoice()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
