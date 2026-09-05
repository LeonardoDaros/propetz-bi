"""Contraprovas de CSV: dados sinteticos, sem abrir Excel, arquivos ou links."""
import ast
import csv
from datetime import date
import io
from pathlib import Path
import types
import unittest

import pandas as pd

import exportacao_csv as export


def read_rows(data):
    return list(csv.reader(io.StringIO(data.decode('utf-8-sig')), delimiter=';'))


class ExportacaoCSVTests(unittest.TestCase):
    def test_formula_prefixes_whitespace_controls_and_fullwidth(self):
        starts = '=+-@＝＋－＠'
        prefixes = ('', ' ', '\t', '\r', '\n', '\t \r\n', '\x00', '\x1f', '\u00a0', '\u200b', '\ufeff')
        values = [prefix + start + '1+1' for prefix in prefixes for start in starts]
        frame = pd.DataFrame({'Texto': values})
        rows = read_rows(export.csv_excel_bytes(frame))[1:]
        for original, row in zip(values, rows):
            with self.subTest(prefix=repr(original[:4])):
                self.assertEqual(row[0], original if original.startswith('\t') else '\t' + original)
                self.assertTrue(row[0].startswith('\t'))

    def test_formula_field_is_quoted_even_when_it_has_no_separator(self):
        data = export.csv_excel_bytes(pd.DataFrame({'Texto': ['=1+1', '\t+1+1']}))
        body = data.decode('utf-8-sig')
        self.assertIn('"\t=1+1"', body)
        self.assertIn('"\t+1+1"', body)

    def test_already_apostrophed_and_neutralized_text_are_idempotent(self):
        values = ["'=1+1", "  '+1+1", '\t=1+1', '=1+1', '\r@1+1']
        for value in values:
            once = export._texto_excel(value)
            self.assertEqual(export._texto_excel(once), once)
        self.assertEqual(export._texto_excel(values[0]), values[0])
        self.assertEqual(export._texto_excel(values[1]), values[1])

    def test_regular_text_unicode_blanks_and_dates_are_unchanged(self):
        values = ['Conversa normal', 'Ação combinada', '', '   ', 'Pedido - revisar',
                  'Nome@exemplo', '\ttexto', "O cliente disse 'sim'", 'R$ -4,50']
        rows = read_rows(export.csv_excel_bytes(pd.DataFrame({'Texto': values})))[1:]
        self.assertEqual([r[0] for r in rows], values)
        self.assertEqual(export._texto_excel(date(2026, 9, 4)), date(2026, 9, 4))
        self.assertIsNone(export._texto_excel(None))

    def test_typed_negative_numbers_stay_numeric_and_sources_unchanged(self):
        frame = pd.DataFrame({'Inteiro': [-2, 3], 'Decimal': [-4.5, 2.25],
                              'Misto': ['-2', -3], 'Booleano': [True, False]})
        before = frame.copy(deep=True)
        rows = read_rows(export.csv_excel_bytes(frame))
        self.assertEqual(rows[1], ['-2', '-4,5', '\t-2', 'True'])
        self.assertEqual(rows[2], ['3', '2,25', '-3', 'False'])
        pd.testing.assert_frame_equal(frame, before)

    def test_nullable_numbers_preserve_values_and_na(self):
        frame = pd.DataFrame({'Valor': pd.Series([-7, pd.NA], dtype='Int64')})
        before = frame.copy(deep=True)
        self.assertEqual(read_rows(export.csv_excel_bytes(frame)), [['Valor'], ['-7'], ['']])
        pd.testing.assert_frame_equal(frame, before)

    def test_categorical_text_and_duplicate_headers(self):
        frame = pd.DataFrame({'A': pd.Categorical(['=1+1', 'Normal']), 'B': ['+1+1', 'Outro']})
        frame.columns = ['=Cabecalho', '=Cabecalho']
        before = frame.copy(deep=True)
        rows = read_rows(export.csv_excel_bytes(frame))
        self.assertEqual(rows[0], ['\t=Cabecalho', '\t=Cabecalho'])
        self.assertEqual(rows[1], ['\t=1+1', '\t+1+1'])
        pd.testing.assert_frame_equal(frame, before)

    def test_quotes_separators_and_line_breaks_cannot_create_extra_cells(self):
        value = '=1+1";@1+1\r\ntexto;"fim"'
        frame = pd.DataFrame({'Observacao': [value], 'Quantidade': [2]})
        rows = read_rows(export.csv_excel_bytes(frame))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1], ['\t' + value, '2'])

    def test_headers_index_values_and_index_name_are_protected(self):
        frame = pd.DataFrame({'\r=Coluna': ['normal']}, index=pd.Index([' @Indice'], name='+Nome'))
        before = frame.copy(deep=True)
        rows = read_rows(export.csv_excel_bytes(frame, index=True))
        self.assertEqual(rows, [['\t+Nome', '\t\r=Coluna'], ['\t @Indice', 'normal']])
        pd.testing.assert_frame_equal(frame, before)

    def test_multiindex_header_and_exported_index(self):
        columns = pd.MultiIndex.from_tuples([('=Grupo', '+Campo')], names=['@Nivel', 'Subnivel'])
        index = pd.MultiIndex.from_tuples([('-Texto', -4)], names=['=Nome', '@Numero'])
        frame = pd.DataFrame([['normal']], columns=columns, index=index)
        before = frame.copy(deep=True)
        rows = read_rows(export.csv_excel_bytes(frame, index=True))
        self.assertEqual(rows[0][0], '\t@Nivel')
        self.assertEqual(rows[0][-1], '\t=Grupo')
        self.assertEqual(rows[1][-1], '\t+Campo')
        self.assertEqual(rows[2][:2], ['\t=Nome', '\t@Numero'])
        self.assertEqual(rows[3], ['\t-Texto', '-4', 'normal'])
        pd.testing.assert_frame_equal(frame, before)

    def test_empty_frame_retains_safe_header_and_bom(self):
        data = export.csv_excel_bytes(pd.DataFrame(columns=['=Cabecalho']))
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(read_rows(data), [['\t=Cabecalho']])

    def test_real_download_adapter_neutralizes_and_preserves_metadata(self):
        tree = ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8-sig'))
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_csv_download')
        captured = []
        namespace = {'csv_excel_bytes': export.csv_excel_bytes,
                     'st': types.SimpleNamespace(download_button=lambda *a, **kw: captured.append((a, kw)))}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<real-download-adapter>', 'exec'), namespace)
        frame = pd.DataFrame({'Observacao': ['=1+1'], 'Valor': [-4.5]})
        before = frame.copy(deep=True)
        namespace['_csv_download'](frame, 'Baixar teste', 'synthetic.csv', 'test-export')
        args, kwargs = captured[0]
        self.assertEqual(args[0], 'Baixar teste')
        self.assertEqual(read_rows(args[1]), [['Observacao', 'Valor'], ['\t=1+1', '-4,5']])
        self.assertEqual(kwargs, {'file_name': 'synthetic.csv', 'mime': 'text/csv', 'key': 'test-export'})
        pd.testing.assert_frame_equal(frame, before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
