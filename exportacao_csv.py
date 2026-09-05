"""CSV para leitura no Excel, sem executar formulas vindas de campos de texto.

Valores de texto com gatilhos de formula recebem TAB dentro de campo citado.
O TAB faz parte do arquivo exportado; dados de origem e numeros tipados ficam
intactos. Esta copia e voltada a planilhas humanas, nao a reimportacao como base.
Referencia: https://owasp.org/www-community/attacks/CSV_Injection
"""
import csv
import unicodedata

import pandas as pd


_FORMULA_STARTS = frozenset('=+-@＝＋－＠')


def _texto_excel(value):
    """Neutraliza texto; numero negativo tipado continua numerico.

    Reconhece espacos e controles antes do gatilho. O TAB inicial permanece
    estavel ao reaplicar a conversao; csv_excel_bytes SEMPRE cita esse campo.
    Um texto ja apostrofado nao comeca por gatilho e permanece inalterado.
    """
    if not isinstance(value, str):
        return value
    position = 0
    while position < len(value):
        char = value[position]
        if not (char.isspace() or unicodedata.category(char) in ('Cc', 'Cf')):
            break
        position += 1
    if position < len(value) and value[position] in _FORMULA_STARTS:
        return value if value.startswith('\t') else '\t' + value
    return value


def _indice_excel(index):
    if isinstance(index, pd.MultiIndex):
        return pd.MultiIndex.from_tuples(
            [tuple(_texto_excel(value) for value in key) for key in index],
            names=[_texto_excel(name) for name in index.names])
    return pd.Index([_texto_excel(value) for value in index],
                    name=_texto_excel(index.name), tupleize_cols=False)


def csv_excel_bytes(frame, *, index=False):
    """Retorna UTF-8 com BOM, separador ; e virgula decimal, sobre copia segura.

    Cabecalhos sao protegidos, assim como valores/nomes do indice se exportado.
    QUOTE_ALL e escape padrao de aspas impedem quebra de campos por ; ou aspas
    inseridos no texto. Nao altera frame nem converte numeros em texto seguro.
    """
    safe = frame.copy(deep=True)
    for position in range(safe.shape[1]):
        column = safe.iloc[:, position]
        if not pd.api.types.is_numeric_dtype(column.dtype):
            safe.isetitem(position, column.map(_texto_excel))
    safe.columns = _indice_excel(safe.columns)
    if index:
        safe.index = _indice_excel(safe.index)
    return safe.to_csv(index=index, sep=';', decimal=',', quoting=csv.QUOTE_ALL,
                       doublequote=True).encode('utf-8-sig')
