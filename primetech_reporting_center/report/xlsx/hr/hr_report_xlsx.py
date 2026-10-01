# -*- coding: utf-8 -*-
from odoo import models


class HRReportXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.hr_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizards):
        for wizard in wizards:
            values = wizard.get_report_values()
            sheet = workbook.add_worksheet(values['title'][:31])
            title_fmt = workbook.add_format({'bold': True, 'font_size': 16, 'font_color': '#0f172a'})
            head_fmt = workbook.add_format({'bold': True, 'bg_color': '#0D9488', 'font_color': '#FFFFFF', 'border': 1})
            cell_fmt = workbook.add_format({'border': 1})
            num_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
            sheet.merge_range(0, 0, 0, 4, 'Ressources Humaines - %s' % values['title'], title_fmt)
            sheet.write(1, 0, 'Période')
            sheet.write(1, 1, '%s - %s' % (values['filters']['date_from'], values['filters']['date_to']))
            headers = ['Employé', 'Département', 'Référence', 'Statut', 'Valeur']
            for col, header in enumerate(headers):
                sheet.write(3, col, header, head_fmt)
            row = 4
            for line in values['lines']:
                sheet.write(row, 0, line['name'], cell_fmt)
                sheet.write(row, 1, line['department'], cell_fmt)
                sheet.write(row, 2, line['job'], cell_fmt)
                sheet.write(row, 3, line['metric'], cell_fmt)
                sheet.write(row, 4, line.get('amount') or 0, num_fmt)
                row += 1
            sheet.set_column(0, 0, 24)
            sheet.set_column(1, 3, 22)
            sheet.set_column(4, 4, 14)
