# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
from odoo import SUPERUSER_ID
import logging
LOGGER = logging.getLogger(__name__)

TYPE = {
    'cdd' : 'CDD', 
    'cdi' : 'CDI', 
    'consultant': 'Consultant',
    'academic' : 'Academic internship',
    'professional' : 'Professional internship'
    }

class Contract(models.Model):

    _inherit = "hr.contract" 

    type = fields.Selection([('cdd', 'CDD'),
                             ('cdi', 'CDI'),
                             ('consultant', 'Consultant'),
                             ('academic', 'Academic internship'),
                             ('professional', 'Professional internship')], string="Contract Type", required=True, default='cdd')

    def write(self, vals):
        """
        This function write an entry in the openchatter whenever we change important information
        on the contract like the model, the drive, the state of the contract or its license plate
        """
        for contract in self:
            changes = []
            if 'date_start' in vals and contract.date_start != vals['date_start']:
                changes.append(_("Start date: from '%s' to '%s'") % (contract.date_start, vals['date_start']))
            if 'date_end' in vals and contract.date_end != vals['date_end']:
                changes.append(_("End date: from '%s' to '%s'") % (contract.date_start, vals['date_end']))
            if 'trial_date_end' in vals and contract.trial_date_end != vals['trial_date_end']:
                changes.append(_("End trial date: from '%s' to '%s'") % (contract.trial_date_end, vals['trial_date_end']))

            if len(changes) > 0:
                self.message_post(body=", ".join(changes))

            return super(Contract, self).write(vals)


    def name_get(self):
        res = []
        for contract in self:
            if contract.type:
                if contract.type == 'cdi':
                    res.append((contract.id, _("%s : CDI from %s %s") % (contract.employee_id and contract.employee_id.matricule or ' ', contract.date_start, contract.date_end and _('to ' + contract.date_end) or '')))
                else:
                    res.append((contract.id, _("%s : %s from %s to %s") % (contract.employee_id and contract.employee_id.matricule or ' ', TYPE[contract.type], contract.date_start, contract.date_end and contract.date_end or '')))
        return res