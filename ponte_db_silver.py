# -*- coding: utf-8 -*-
"""Ponte para o banco PostgreSQL "silver" da DarosCorp.

SEGURO PARA VERSIONAR: este arquivo NAO contem credencial nenhuma — ele so
importa o cliente do projeto vizinho (Demanda Curva ABC), onde as credenciais
vivem FORA de qualquer repositorio. Leia o Manual_Integracao_Banco_Silver.md
antes de escrever consultas (regras de negocio validadas + armadilhas).

Uso:
    from ponte_db_silver import consultar
    linhas = consultar("SELECT ... FROM silver.faturamento WHERE ano = %s", [2026])

ATENCAO: so funciona rodando no PC do Leonardo (o app publicado no Streamlit
Cloud nao tem acesso ao projeto vizinho — para isso seria st.secrets, decisao
que exige conversa previa com o Leonardo e a DarosCorp).
"""
import os
import sys

_TOOLS_VIZINHO = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "Demanda Curva abc", "Demanda Curva Abc - Pet", "tools"))

if not os.path.isdir(_TOOLS_VIZINHO):
    raise ImportError(
        "Projeto vizinho (Demanda Curva ABC) nao encontrado em %s — esta ponte "
        "so funciona no PC do Leonardo, nao no app publicado." % _TOOLS_VIZINHO)

sys.path.insert(0, _TOOLS_VIZINHO)
from db_cloud import consultar, conectar  # noqa: E402,F401
