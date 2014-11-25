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
from openerp import api
from openerp.osv import fields, osv
from openerp.tools.translate import _
import re
import logging

_logger = logging.getLogger(__name__)

# Number Filter
re_number = re.compile(r'\d{8}')

# Functions to list parents names.
def _get_parents(child, parents=[]):
    if child:
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
        seq_obj = self.pool.get('ir.sequence')

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
            sid = seq_obj.next_by_id(cr, uid, conn.batch_sequence_id.id)
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
                if tax.tax_code_id:
                    r[inv.id].append({
                        'Id': tax.tax_code_id.parent_afip_code,
                        'Desc': tax.tax_code_id.name,
                        'BaseImp': tax.base_amount,
                        'Alic': (tax.tax_amount / tax.base_amount),
                        'Importe': tax.tax_amount,
                    })
                else:
                    raise osv.except_osv(_(u'TAX without tax-code'),
                                         _(u'Please, check if you set tax code for invoice or refund to tax %s.') % tax.name)



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
            assert inv.currency_id.afip_code, 'Must defined afip_code for this invoice'
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

    def invoice_print(self, cr, uid, ids, context=None):
        '''
        This function prints the invoice and mark it as sent, so that we can see more easily the next step of the workflow
        Check if electronic invoice or normal invoice.
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



    @api.onchange('invoice_line')
    def update_product_type(self):
        product_types = set()
	if self.type == 'out_invoice':	
		if self.invoice_line:
		        for line in self.invoice_line:
				product_id = line.product_id
        			if product_id:
					product_type = self.env['product.product'].browse(product_id).type
					product_types.add(product_type)
        	        self.afip_concept = _calc_concept(product_types)
	

invoice()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
