from odoo import models

class TrialBalanceXlsx(models.AbstractModel):
    _name = 'report.primetech_reporting_center.trial_balance_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizard):
        sheet = workbook.add_worksheet('Balance OHADA')
        sheet.set_zoom(90)
        sheet.set_column('A:A', 15)
        sheet.set_column('B:B', 40)
        sheet.set_column('C:H', 18)
        title = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter'})
        header_dark = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#334155', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        header_blue = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1E40AF', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        header_cyan = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#0369A1', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        header_green = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#047857', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        sub_blue = workbook.add_format({'bold': True, 'bg_color': '#DBEAFE', 'font_color': '#1E3A8A', 'border': 1, 'align': 'center'})
        debit_blue = workbook.add_format({'bold': True, 'bg_color': '#EFF6FF', 'font_color': '#1E40AF', 'border': 1, 'align': 'center'})
        debit_cyan = workbook.add_format({'bold': True, 'bg_color': '#F0F9FF', 'font_color': '#0369A1', 'border': 1, 'align': 'center'})
        debit_green = workbook.add_format({'bold': True, 'bg_color': '#F0FDF4', 'font_color': '#047857', 'border': 1, 'align': 'center'})
        amount = workbook.add_format({'num_format': '#,##0', 'border': 1, 'align': 'right'})
        level1 = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#374151', 'border': 1})
        level1_amount = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#374151', 'border': 1, 'num_format': '#,##0', 'align': 'right'})
        level2 = workbook.add_format({'bold': True, 'bg_color': '#F3F4F6', 'border': 1})
        level2_amount = workbook.add_format({'bold': True, 'bg_color': '#F3F4F6', 'border': 1, 'num_format': '#,##0', 'align': 'right'})
        level3 = workbook.add_format({'bold': True, 'bg_color': '#EEF6FF', 'border': 1})
        level3_amount = workbook.add_format({'bold': True, 'bg_color': '#EEF6FF', 'border': 1, 'num_format': '#,##0', 'align': 'right'})
        total_bilan = workbook.add_format({'bold': True, 'bg_color': '#E5E7EB', 'border': 1, 'num_format': '#,##0'})
        total_gestion = workbook.add_format({'bold': True, 'bg_color': '#DBEAFE', 'border': 1, 'num_format': '#,##0'})
        total_balance = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#16A34A', 'border': 1, 'num_format': '#,##0'})
        result = self.env['primetech.trial.balance'].get_trial_balance(date_from=data.get('date_from'), date_to=data.get('date_to'), level=data.get('level'), posted_only=data.get('posted_only'))
        previous_year = int(str(data.get('date_from'))[:4]) - 1
        sheet.merge_range('A1:H1', 'BALANCE GENERALE DES COMPTES', title)
        sheet.merge_range('A2:H2', f'Période du {data.get('date_from')} au {data.get('date_to')}', workbook.add_format({'align': 'center'}))
        row = 4
        sheet.merge_range(row, 0, row + 2, 0, 'Compte', header_dark)
        sheet.merge_range(row, 1, row + 2, 1, 'Intitulé des comptes', header_dark)
        sheet.merge_range(row, 2, row, 3, f'Soldes Initiaux\nExercice {previous_year}', header_blue)
        sheet.merge_range(row, 4, row + 1, 5, 'Mouvements', header_cyan)
        sheet.merge_range(row, 6, row + 1, 7, 'Soldes Cumulés', header_green)
        sheet.merge_range(row + 1, 2, row + 1, 3, "Situation d'ouverture", sub_blue)
        row += 2
        sheet.write(row, 2, 'Débit', debit_blue)
        sheet.write(row, 3, 'Crédit', debit_blue)
        sheet.write(row, 4, 'Débit', debit_cyan)
        sheet.write(row, 5, 'Crédit', debit_cyan)
        sheet.write(row, 6, 'Débit', debit_green)
        sheet.write(row, 7, 'Crédit', debit_green)
        row += 1
        for line in result['lines']:
            if not any([line['opening_debit'], line['opening_credit'], line['period_debit'], line['period_credit'], line['closing_debit'], line['closing_credit']]):
                continue
            if line['level'] == 1:
                txt_fmt = level1
                amt_fmt = level1_amount
            elif line['level'] == 2:
                txt_fmt = level2
                amt_fmt = level2_amount
            elif line['level'] == 3:
                txt_fmt = level3
                amt_fmt = level3_amount
            else:
                txt_fmt = None
                amt_fmt = amount
            sheet.write(row, 0, line['code'], txt_fmt)
            sheet.write(row, 1, line['name'], txt_fmt)
            sheet.write_number(row, 2, line['opening_debit'], amt_fmt)
            sheet.write_number(row, 3, line['opening_credit'], amt_fmt)
            sheet.write_number(row, 4, line['period_debit'], amt_fmt)
            sheet.write_number(row, 5, line['period_credit'], amt_fmt)
            sheet.write_number(row, 6, line['closing_debit'], amt_fmt)
            sheet.write_number(row, 7, line['closing_credit'], amt_fmt)
            row += 1
