# -*- coding: utf-8 -*-
"""Initialisation des données techniques de la paie intégrée."""


def post_init_hook(env):
    """Crée les précisions décimales sans dupliquer celles d'un ancien payroll."""
    precision_model = env['decimal.precision'].sudo()
    for name, digits in (('Payroll', 2), ('Payroll Rate', 4)):
        if not precision_model.search([('name', '=', name)], limit=1):
            precision_model.create({'name': name, 'digits': digits})

    # Lorsqu'une ancienne installation dispose encore de l'addon payroll,
    # son menu racine est masqué : les mêmes fonctions sont désormais sous RH.
    legacy_menu = env.ref('payroll.payroll_menu_root', raise_if_not_found=False)
    if legacy_menu:
        legacy_menu.write({'groups_id': [(6, 0, [env.ref('base.group_no_one').id])]})
