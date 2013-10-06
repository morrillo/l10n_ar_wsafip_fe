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
import logging
import sys

_logger = logging.getLogger(__name__)

def _update(pool, cr, uid, model_name, remote_list, can_create=True, domain=[]):
    model_obj = pool.get(model_name) 

    # Build set of AFIP codes
    rem_afip_code_set = set([ i['afip_code'] for i in remote_list ])

    # Take exists instances 
    sto_ids = model_obj.search(cr, uid, [('active','in',['f','t'])] + domain)
    sto_list = model_obj.read(cr, uid, sto_ids, ['afip_code'])
    sto_afip_code_set = set([ i['afip_code'] for i in sto_list ])

    # Append new afip_code
    to_append = rem_afip_code_set - sto_afip_code_set
    if to_append and can_create:
        for item in [ i for i in remote_list if i['afip_code'] in to_append ]:
            model_obj.create(cr, uid, item)
    elif to_append and not can_create:
        _logger.warning('New items of type %s in WS. I will not create them.' % model_name)

    # Update active document types
    to_update = rem_afip_code_set & sto_afip_code_set
    update_dict = { i['afip_code']:i['active'] for i in remote_list if i['afip_code'] in to_update }
    to_active = [ k for k,v in update_dict.items() if v ]
    if to_active:
        model_ids = model_obj.search(cr, uid, [('afip_code','in',to_active),('active','in',['f',False])])
        model_obj.write(cr, uid, model_ids, {'active':True})

    to_deactive = [ k for k,v in update_dict.items() if not v ]
    if to_deactive:
        model_ids = model_obj.search(cr, uid, [('afip_code','in',to_deactive),('active','in',['t',True])])
        model_obj.write(cr, uid, model_ids, {'active':False})

    # To disable exists local afip_code but not in remote
    to_inactive = sto_afip_code_set - rem_afip_code_set 
    if to_inactive:
        model_ids = model_obj.search(cr, uid, [('afip_code','in',list(to_inactive))])
        model_obj.write(cr, uid, model_ids, {'active':False})

    _logger.info('Updated %s items' % model_name)

    return True

class wsafip_server(osv.osv):
    _name = "wsafip.server"
    _inherit = "wsafip.server"

    """
    TODO:
        AFIP Description: Método de obtención de CAEA (FECAEASolicitar)
        AFIP Description: Método de consulta de CAEA (FECAEAConsultar)
        AFIP Description: Método para informar CAEA sin movimiento (FECAEASinMovimientoInformar)
        AFIP Description: Método para informar comprobantes emitidos con CAEA (FECAEARegInformativo)
        AFIP Description: Método para consultar CAEA sin movimiento (FECAEASinMovimientoConsultar)
        AFIP Description: Recuperador de valores referenciales de códigos de Tipos de Alícuotas (FEParamGetTiposIva)
        AFIP Description: Recuperador de valores referenciales de códigos de Tipos de datos Opcionales (FEParamGetTiposOpcional)
        AFIP Description: Recuperador de valores referenciales de códigos de Tipos de Tributos (FEParamGetTiposTributos)
        AFIP Description: Recuperador de los puntos de venta asignados a Facturación Electrónica que soporten CAE y CAEA vía Web Services (FEParamGetPtosVenta)
        AFIP Description: Recuperador de cotización de moneda (FEParamGetCotizacion)
        AFIP Description: Método Dummy para verificación de funcionamiento de infraestructura (FEDummy)
        AFIP Description: Recuperador de cantidad máxima de registros FECAESolicitar / FECAEARegInformativo (FECompTotXRequest)
        AFIP Description: Método para consultar Comprobantes Emitidos y su código (FECompConsultar)
        """

    def wsfe_update_afip_concept_type(self, cr, uid, ids, conn_id, context=None):
        """
        Update concepts class.

        AFIP Description: Recuperador de valores referenciales de códigos de Tipos de Conceptos (FEParamGetTiposConcepto)
        """
        journal_obj = self.pool.get('afip.journal_class')
        conn_obj = self.pool.get('wsafip.connection')

        for srv in self.browse(cr, uid, ids, context=context):
            # Ignore servers without code WSFE.
            if srv.code != 'wsfe': continue

            # Take the connection, continue if connected or clockshifted
            conn = conn_obj.browse(cr, uid, conn_id, context=context) 
            conn.login() # Login if nescesary.
            if conn.state not in  [ 'connected', 'clockshifted' ]: continue

            # Build request
            request = FEParamGetTiposConceptoSoapIn()
            request = conn.set_auth_request(request, context=context)

            try:
                _logger.info('Updating concept class from AFIP Web service')
                response = get_bind(conn.server_id).FEParamGetTiposConcepto(request)

                # Take list of concept type
                concepttype_list = [
                    { 'afip_code': c.Id,
                      'name': c.Desc,
                      'active': c.FchHasta  in [None, 'NULL']}
                    for c in response.FEParamGetTiposConceptoResult.ResultGet.ConceptoTipo
                ]
            except:
                _logger.error('AFIP Web service error!')
                return False

            _update(self.pool, cr, uid,
                    'afip.concept_type',
                    concepttype_list,
                    can_create=True,
                    domain=[('afip_code','!=',0)]
                   )

        return


    def wsfe_update_journal_class(self, cr, uid, ids, conn_id, context=None):
        """
        Update journal class.

        AFIP Description: Recuperador de valores referenciales de códigos de Tipos de comprobante (FEParamGetTiposCbte)
        """
        journal_obj = self.pool.get('afip.journal_class')
        conn_obj = self.pool.get('wsafip.connection')

        for srv in self.browse(cr, uid, ids, context=context):
            # Ignore servers without code WSFE.
            if srv.code != 'wsfe': continue

            # Take the connection, continue if connected or clockshifted
            conn = conn_obj.browse(cr, uid, conn_id, context=context) 
            conn.login() # Login if nescesary.
            if conn.state not in  [ 'connected', 'clockshifted' ]: continue

            # Build request
            request = FEParamGetTiposCbteSoapIn()
            request = conn.set_auth_request(request, context=context)

            try:
                _logger.info('Updating journal class from AFIP Web service')
                response = get_bind(conn.server_id).FEParamGetTiposCbte(request)

                # Take list of journal class
                journalclass_list = [
                    { 'afip_code': c.Id,
                      'name': c.Desc,
                      'active': c.FchHasta  in [None, 'NULL']}
                    for c in response.FEParamGetTiposCbteResult.ResultGet.CbteTipo
                ]
            except:
                _logger.error('AFIP Web service error!')
                return False

            _update(self.pool, cr, uid,
                    'afip.journal_class',
                    journalclass_list,
                    can_create=False,
                    domain=[('afip_code','!=',0)]
                   )

        return

    def wsfe_update_document_type(self, cr, uid, ids, conn_id, context=None):
        """
        Update document type. This function must be called from connection model.

        AFIP Description: Recuperador de valores referenciales de códigos de Tipos de Documentos (FEParamGetTiposDoc)
        """
        doctype_obj = self.pool.get('afip.document_type')
        conn_obj = self.pool.get('wsafip.connection')

        for srv in self.browse(cr, uid, ids, context=context):
            # Ignore servers without code WSFE.
            if srv.code != 'wsfe': continue

            # Take the connection, continue if connected or clockshifted
            conn = conn_obj.browse(cr, uid, conn_id, context=context) 
            conn.login() # Login if nescesary.
            if conn.state not in  [ 'connected', 'clockshifted' ]: continue

            # Build request
            request = FEParamGetTiposDocSoapIn()
            request = conn.set_auth_request(request, context=context)

            try:
                _logger.info('Updating document types from AFIP Web service')
                response = get_bind(conn.server_id).FEParamGetTiposDoc(request)

                # Take list of document types
                doctype_list = [
                    { 'afip_code': c.Id,
                      'name': c.Desc,
                      'code': c.Desc,
                      'active': c.FchHasta in [None, 'NULL'] }
                    for c in response.FEParamGetTiposDocResult.ResultGet.DocTipo
                ]
            except:
                _logger.error('AFIP Web service error!')
                return False

            _update(self.pool, cr, uid,
                    'afip.document_type',
                    doctype_list,
                    can_create=True,
                    domain=[]
                   )

        return True
 
    def wsfe_update_currency(self, cr, uid, ids, conn_id, context=None):
        """
        Update currency. This function must be called from connection model.

        AFIP Description: Recuperador de valores referenciales de códigos de Tipos de Monedas (FEParamGetTiposMonedas) 
        """
        currency_obj = self.pool.get('res.currency')
        conn_obj = self.pool.get('wsafip.connection')

        for srv in self.browse(cr, uid, ids, context=context):
            # Ignore servers without code WSFE.
            if srv.code != 'wsfe': continue

            # Take the connection, continue if connected or clockshifted
            conn = conn_obj.browse(cr, uid, conn_id, context=context) 
            conn.login() # Login if nescesary.
            if conn.state not in  [ 'connected', 'clockshifted' ]: continue

            # Build request
            request = FEParamGetTiposMonedasSoapIn()
            request = conn.set_auth_request(request, context=context)

            try:
                _logger.info('Updating currency from AFIP Web service')
                response = get_bind(conn.server_id).FEParamGetTiposMonedas(request)

                # Take list of currency
                currency_list = [
                    { 'afip_code': c.Id,
                      'name': c.Desc,
                      'active': c.FchHasta in [None, 'NULL'] }
                    for c in response.FEParamGetTiposMonedasResult.ResultGet.Moneda
                ]
            except:
                _logger.error('AFIP Web service error!')
                return False

            _update(self.pool, cr, uid,
                    'res.currency',
                    currency_list,
                    can_create=False,
                    domain=[]
                   )
        return True

    def wsfe_get_last_invoice_number(self, cr, uid, ids, conn_id, ptoVta, cbteTipo, context=None):
        """
        Get last ID number from AFIP

        AFIP Description: Recuperador de ultimo valor de comprobante registrado (FECompUltimoAutorizado)
        """
        conn_obj = self.pool.get('wsafip.connection')

        for srv in self.browse(cr, uid, ids, context=context):
            # Ignore servers without code WSFE.
            if srv.code != 'wsfe': continue

            # Take the connection
            conn = conn_obj.browse(cr, uid, conn_id, context=context) 
            conn.login() # Login if nescesary.
            if conn.state not in  [ 'connected', 'clockshifted' ]: continue

            _logger.info('Get Last Invoice Number from AFIP Web service')

            request = FECompUltimoAutorizadoSoapIn()
            request = conn.set_auth_request(request, context=context)
            request.PtoVta = ptoVta
            request.CbteTipo =  cbteTipo

            try:
                _logger.info('Take last invoice number from AFIP Web service')
                response = get_bind(conn.server_id).FECompUltimoAutorizado(request)

                return int(response.FECompUltimoAutorizadoResult.CbteNro)
            except:
                _logger.error('AFIP Web service error!')
                return False

    def wsfe_get_cae(self, cr, uid, ids, conn_id, invoice_request, context=None):
        """
        Get CAE.

        AFIP Description: Método de autorización de comprobantes electrónicos por CAE (FECAESolicitar)
        """
        conn_obj = self.pool.get('wsafip.connection')

        for srv in self.browse(cr, uid, ids, context=context):
            # Ignore servers without code WSFE.
            if srv.code != 'wsfe': continue

            # Take the connection
            conn = conn_obj.browse(cr, uid, conn_id, context=context) 
            conn.login() # Login if nescesary.
            if conn.state not in  [ 'connected', 'clockshifted' ]: continue

            _logger.info('Get CAE from AFIP Web service')

            request = FECAESolicitarSoapIn()
            request = conn.set_auth_request(request, context=context)
            Request = request.new_FeCAEReq()

            # Set Request Header
            Header  = Request.new_FeCabReq()
            Header.set_element_CantReg(len(invoice_request))
            Header.set_element_CbteTipo(invoice_request[0]['CbteTipo'])
            Header.set_element_PtoVta(invoice_request[0]['PtoVta'])
            Request.FeCabReq = Header

            # Set Request Details
            Details = Request.new_FeDetReq()
            for invoice in invoice_request:
                Detail  = Details.new_FECAEDetRequest()
                Detail.set_element_Concepto(invoice['Concepto'])
                Detail.set_element_DocTipo(invoice['DocTipo'])
                Detail.set_element_DocNro(invoice['DocNro'])
                Detail.set_element_CbteDesde(invoice['CbteDesde'])
                Detail.set_element_CbteHasta(invoice['CbteHasta'])
                Detail.set_element_CbteFch(invoice.get('CbteFch', None))
                Detail.set_element_ImpTotal(invoice['ImpTotal'])
                Detail.set_element_ImpTotConc(invoice['ImpTotConc'])
                Detail.set_element_ImpNeto(invoice['ImpNeto'])
                Detail.set_element_ImpOpEx(invoice['ImpOpEx'])
                Detail.set_element_ImpIVA(invoice['ImpIVA'])
                Detail.set_element_ImpTrib(invoice['ImpTrib'])
                Detail.set_element_FchServDesde(invoice.get('FchServDesde', None))
                Detail.set_element_FchServHasta(invoice.get('FchServHasta', None))
                Detail.set_element_FchVtoPago(invoice.get('FchVtoPago', None))
                Detail.set_element_MonId(invoice['MonId'])
                Detail.set_element_MonCotiz(invoice['MonCotiz'])

                Associateds = Detail.new_CbtesAsoc()
                for associated in invoice.get('CbtesAsoc',[]):
                    Associated = Associateds.new_CbteAsoc()
                    Associated.set_element_Tipo(associated['Tipo'])
                    Associated.set_element_PtoVta(associated['PtoVta'])
                    Associated.set_element_Nro(associated['Nro'])
                    Associateds.CbteAssoc.append(Associated)
                Detail.CbtesAsoc = Associateds

                Taxes = Detail.new_Tributos()
                for tax in invoice.get('Tributos', []):
                    Tax = Taxes.new_Tributo()
                    Tax.set_element_Id(tax['Id'])
                    Tax.set_element_Desc(tax.get('Desc',None))
                    Tax.set_element_BaseImp(tax['BaseImp'])
                    Tax.set_element_Alic(tax['Alic'])
                    Tax.set_element_Importe(tax['Importe'])
                    Taxes.Tributo.append(Tax)
                Detail.Taxes = Taxes

                VAT = Detail.new_Iva()
                for vat in invoice.get('IVA', []):
                    Alic = VAT.new_AlicIva()
                    Alic.set_element_Id(vat['Id'])
                    Alic.set_element_BaseImp(vat['BaseImp'])
                    Alic.set_element_Importe(vat['Importe'])
                    VAT.AlicIva.append(Alic)
                Detail.IVA = VAT

                Optionals = Detail.new_Opcionales()
                for optional in invoice.get('Opcionales',[]):
                    Optional = Optionals.new_Optional()
                    Optional.set_element_Id(optional['Id'])
                    Optional.set_element_Valor(optional['Valor'])
                    Optionals.Opcional.append(Optional)
                Detail.Opcionales = Optionals

                Details.FECAEDetRequest.append(Detail)

            Request.FeDetReq = Details

            request.FeCAEReq = Request

            try:
                #Detail.set_element_CbtesAsoc(invoice['CbtesAsoc'])
                #response = get_bind(conn.server_id).FECAESolicitar(request)
                pass

            except:
                _logger.error('AFIP Web service error!')
                return False

        raise RuntimeError


wsafip_server()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
