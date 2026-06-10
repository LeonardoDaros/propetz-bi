# -*- coding: utf-8 -*-
"""Gera abc_valor.json — faturamento por SKU do canal Propetz Distribuição
(últimos 12 meses) a partir da Base Mãe. O app usa esse arquivo para calcular
a curva ABC por VALOR (Pareto 80/15/5). Rodado automaticamente pelo deploy.bat;
também pode ser executado manualmente."""
import json
import os
from datetime import datetime
from collections import defaultdict

import openpyxl

BASE_MAE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                        'Demanda Curva abc', 'Demanda Curva Abc - Pet',
                        'Base_Mae_Propetz.xlsx')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'abc_valor.json')

if not os.path.exists(BASE_MAE):
    raise SystemExit(f"[ERRO] Base Mae nao encontrada em: {BASE_MAE}")

wb = openpyxl.load_workbook(BASE_MAE, data_only=True, read_only=True)
ws = wb['TRANSACOES']

# Colunas TRANSACOES: 1 ano | 2 mes | 4 bu | 6 sku | 12 quantidade | 14 valor_total | 17 tipo_dado
trans = []
meses = set()
for row in ws.iter_rows(min_row=2, values_only=True):
    ano, mes, bu, sku, vt, tipo = row[0], row[1], row[3], row[5], row[13], row[16]
    if not ano or str(tipo).strip() != 'real':
        continue
    if 'Distribui' not in str(bu):
        continue
    try:
        vt = float(vt or 0)
    except Exception:
        vt = 0
    trans.append((int(ano), int(mes), str(sku).strip(), vt))
    meses.add((int(ano), int(mes)))

ult12 = sorted(meses)[-12:]
ult12_set = set(ult12)
fat = defaultdict(float)
for ano, mes, sku, vt in trans:
    if (ano, mes) in ult12_set:
        fat[sku] += vt
fat = {k: round(v, 2) for k, v in fat.items() if v > 0}

MESES_PT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
periodo = (f"{MESES_PT[ult12[0][1]-1]}/{ult12[0][0]} a "
           f"{MESES_PT[ult12[-1][1]-1]}/{ult12[-1][0]}")

data = {
    "gerado_em": datetime.now().strftime('%Y-%m-%d %H:%M'),
    "periodo": periodo,
    "criterio": "Faturamento do canal Propetz Distribuição, últimos 12 meses (Base Mãe)",
    "faturamento": fat,
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=1)

print(f"abc_valor.json gerado: {len(fat)} SKUs | periodo {periodo} | "
      f"total R$ {sum(fat.values()):,.0f}")
