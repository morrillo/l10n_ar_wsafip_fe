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
from stub.Service_client import *
from stub.Service_types import *
from openerp.tools.translate import _
from cache_bind import get_bind
import logging

_logger = logging.getLogger(__name__)
_schema = logging.getLogger(__name__ + '.schema')

class account_journal(osv.osv):
    def _get_afip_state(self, cr, uid, ids, fields_name, arg, context=None):
        if context is None:
            context={}
        r={}
        for journal in self.browse(cr, uid, ids):
            auth = journal.afip_authorization_id
            if not auth:
                r[journal.id] = 'not available'
            elif auth.server_id.code != 'wsfe':
                r[journal.id] = 'authorization_service_error'
            else:
                # Try to login just one time.
                try:
                    auth.login()
                    if auth.state not in  [ 'connected', 'clockshifted' ]:
                        r[journal.id] = 'connection_error'
                    else:
                        request = FEDummySoapIn()
                        response = get_bind(auth.server_id).FEDummy(request)
                        if response._FEDummyResult._authserver == 'OK':
                            r[journal.id] = 'connected'
                        else:
                            if response._FEDummyResult._appserver != 'OK':
                                r[journal.id] = 'connected_but_appserver_error'
                            elif response._FEDummyResult._dbserver != 'OK':
                                r[journal.id] = 'connected_but_dbserver_error'
                            else:
                                r[journal.id] = 'connected_but_servers_error'
                except:
                    pass
        return r

    def _get_afip_items_available(self, cr, uid, ids, fields_name, arg, context=None):
        if context is None:
            context={}
        r={}
        for journal in self.browse(cr, uid, ids):
            r[journal.id] = False
            auth = journal.afip_authorization_id
            if auth and auth.server_id.code == 'wsfe':
                try:
                    auth.login()
                    if auth.state in  [ 'connected', 'clockshifted' ]:
                        request = FERecuperaQTYRequestSoapIn()
                        request = auth.set_auth_request(request)
                        response = get_bind(auth.server_id).FERecuperaQTYRequest(request)
                        if response._FERecuperaQTYRequestResult._RError._percode == 0:
                            r[journal.id] = response._FERecuperaQTYRequestResult._qty._value
                        else:
                            _logger.error('RESPONSE:afip_items_available:%i:\n%s' % (
                                response._FERecuperaQTYRequestResult._RError._percode,
                                response._FERecuperaQTYRequestResult._RError._perrmsg
                            ))
                            raise osv.except_osv(_('Error in Response'), _('Following error back from server: (%i) %s') % (
                                response._FERecuperaQTYRequestResult._RError._percode,
                                response._FERecuperaQTYRequestResult._RError._perrmsg
                            ))
                except:
                    pass
        return r

    def _get_afip_items_generated(self, cr, uid, ids, fields_name, arg, context=None):
        if context is None:
            context={}
        r={}
        for journal in self.browse(cr, uid, ids):
            r[journal.id] = False
            auth = journal.afip_authorization_id
            if auth and auth.server_id.code == 'wsfe':
                try:
                    auth.login()
                    if auth.state in  [ 'connected', 'clockshifted' ]:
                        request = FERecuperaLastCMPRequestSoapIn()
                        request = auth.set_auth_request(request)
                        argTCMP = request.new_argTCMP()
                        argTCMP.set_element_PtoVta(journal.point_of_sale)
                        argTCMP.set_element_TipoCbte(journal.journal_class_id.afip_code)
                        request.ArgTCMP = argTCMP
                        response = get_bind(auth.server_id).FERecuperaLastCMPRequest(request)
                        if response._FERecuperaLastCMPRequestResult._RError._percode == 0:
                            r[journal.id] = response._FERecuperaLastCMPRequestResult._cbte_nro
                        else:
                            _logger.error('RESPONSE:afip_items_available:%i:\n%s' %  (
                                response._FERecuperaQTYRequestResult._RError._percode,
                                response._FERecuperaQTYRequestResult._RError._perrmsg
                            ))
                            raise osv.except_osv(_('Error in Response'), _('Following error back from server: (%i) %s') % (
                                response._FERecuperaQTYRequestResult._RError._percode,
                                response._FERecuperaQTYRequestResult._RError._perrmsg
                            ))
                except:
                    pass
        return r

    _inherit = "account.journal"
    _columns = {
        'afip_authorization_id': fields.many2one('wsafip.authorization', 'Web Service AFIP Authorization',
                            help="Which service authorization must be used to connecto to AFIP."),
        'afip_state': fields.function(_get_afip_state, type='char', string='AFIP State',method=True, 
                            help="Connect to the AFIP and check is service is avilable."),
        'afip_items_available': fields.function(_get_afip_items_available, type='integer', string='Number of Invoices Available',method=True, 
                            help="Connect to the AFIP and check how many invoices are avaible to print."),
        'afip_items_generated': fields.function(_get_afip_items_generated, type='integer', string='Number of Invoices Generated',method=True, 
                            help="Connect to the AFIP and check how many invoices was generated."),
    }
account_journal()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
