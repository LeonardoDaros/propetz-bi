# -*- coding: utf-8 -*-
"""Utilitários compartilhados do projeto (app + scripts locais).
Regra global nº 6 (22/07): reutilizar em vez de duplicar — as três funções
abaixo existiam copiadas em app.py, silver_churn_sombra.py e nos scripts da
Tabela de Pedido; agora vivem só aqui."""
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime

MESES_PT = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
            "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}

STOP_CLIENTE = {"LTDA", "ME", "MEI", "EIRELI", "EPP", "CIA", "LT", "SA",
                # conectores: sem identidade p/ casamento de nomes
                "E", "DE", "DA", "DO", "DAS", "DOS", "PARA"}


def parse_label_ym(label):
    """Rótulo de mês -> (ano, mês) ou None. Aceita 'jun/26' E datetime/ISO —
    a MESMA dualidade da pegadinha conhecida do process_excel (jul/26)."""
    s = str(label or "").strip().lower()
    if "/" in s:
        p = s.split("/")
        if len(p) == 2 and p[0][:3] in MESES_PT:
            try:
                return (2000 + int(p[1]), MESES_PT[p[0][:3]])
            except ValueError:
                return None
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d")
        return (d.year, d.month)
    except ValueError:
        return None


def norm_cliente(nome):
    """Normalização de nome de cliente p/ casar com o CÓDIGO (sombra silver):
    sem acento/pontuação, sem sufixo de regime ('| SN'/'- RN'), sem CNPJ/CPF
    embutido, sem stopwords societárias. NÃO alterar sem re-rodar a sombra —
    o de-para inteiro depende desta função ser estável."""
    s = str(nome or "").strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    s = re.sub(r"[\|\-/]+\s*(SN|RN)\s*$", " ", s)
    s = re.sub(r"[\|]+\s*$", " ", s)
    s = s.replace("S/A", " SA ").replace("S.A", " SA ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    toks = [t for t in s.split()
            if not (t.isdigit() and len(t) >= 4) and t not in STOP_CLIENTE]
    return " ".join(toks)


# Unificação de carteiras de vendedores — FONTE ÚNICA (app e coletores
# importam daqui; mudou carteira? editar SÓ este dicionário).
VENDOR_MERGE = {
    "Ellen Propetz Distribuição": "Emanuel Propetz Distribuição",
}
# o banco silver usa nomes completos próprios; o casamento entre fontes é pelo
# 1º nome (critério da sombra) — o merge também precisa valer nesse plano
VENDOR_MERGE_1O_NOME = {k.split(" ")[0].lower(): v.split(" ")[0].lower()
                        for k, v in VENDOR_MERGE.items()}


def normalize_vendor(name):
    """Normaliza nome do vendedor aplicando o mapeamento de carteiras."""
    if not name:
        return ""
    name = str(name).strip()
    return VENDOR_MERGE.get(name, name)


def primeiro_nome_vendedor(name):
    """1º nome minúsculo, já com o merge de carteiras aplicado."""
    pn = str(name or "").strip().split(" ")[0].lower()
    return VENDOR_MERGE_1O_NOME.get(pn, pn)


def copiar_para_temp(caminho, apelido):
    """Copia p/ %TEMP% e devolve o caminho da cópia — leitura segura de
    planilha aberta no Excel/OneDrive (que trava a leitura direta)."""
    destino = os.path.join(tempfile.gettempdir(), apelido)
    shutil.copy2(caminho, destino)
    return destino


def abrir_ou_copiar(caminho, apelido):
    """O próprio caminho se legível; senão, uma cópia em %TEMP%."""
    try:
        with open(caminho, "rb"):
            return caminho
    except PermissionError:
        return copiar_para_temp(caminho, apelido)
