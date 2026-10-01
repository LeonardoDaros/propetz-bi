"""Importação assistida do Tiny, reutilizando a Nova Garantia e sua persistência.

Este módulo não acessa o Silver nem grava protocolos. Conteúdo do ERP é exibido
em controles de texto/tabela; nenhuma descrição é interpretada como HTML.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Callable
from zoneinfo import ZoneInfo

import orcamentos_garantias as dominio


PAPEIS_IMPORTACAO = frozenset({"garantia", "garantia_master", "admin", "diretor"})
PAPEIS_CORRECAO_FECHADA = frozenset({"garantia_master", "admin"})
PAPEIS_CANCELADAS = frozenset({"garantia_master", "admin", "diretor"})
STATUS_FECHADOS = frozenset({"Concluída", "Concluida", "Cancelada", "Finalizada"})
PENDENCIAS_ORIGEM = {
    "CONTATO_AUSENTE": "O contato não veio nesta carga; confirme o cliente na ficha.",
    "TEXTOS_AUSENTES": "O relato não veio em campo de texto; complete o relato na ficha.",
    "ITENS_AUSENTES": "Os itens não vieram nesta carga; confira o equipamento físico.",
    "ITEM_QUANTIDADE_INVALIDO": "Há quantidade ausente ou inválida no orçamento; corrija no Tiny antes de importar.",
    "ITEM_SEM_IDENTIFICACAO": "Há item sem descrição ou SKU; confira o cadastro no Tiny.",
}


def _texto(value: Any, limite: int = 18000) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return dominio.texto_sem_html(value, limite=limite)
    return ""


def _papel(usuario: Any) -> str:
    if isinstance(usuario, str):
        return usuario
    return _texto(usuario.get("role")) if isinstance(usuario, Mapping) else ""


def pode_importar(usuario: Any) -> bool:
    return _papel(usuario) in PAPEIS_IMPORTACAO


def _data_carga(value: Any) -> str:
    try:
        dt = datetime.fromisoformat(_texto(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("Fuso ausente")
        return dt.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y às %H:%M (Brasília)")
    except (ValueError, TypeError):
        return "Data não disponível"


def _lista_dicts(value: Any) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _chave(orcamento: dict) -> str:
    return _texto(orcamento.get("chave_origem")) or (
        _texto(orcamento.get("unidade_negocio_id")) + ":" + _texto(orcamento.get("tiny_id"))
    )


def filtrar_orcamentos(orcamentos: Any, busca: str = "") -> list[dict]:
    """Busca local, sem procurar pessoas em outras bases ou inferir canal."""
    termos = _texto(busca, 120).casefold().split()
    encontrados = []
    for orcamento in _lista_dicts(orcamentos):
        partes = [_texto(orcamento.get(k)) for k in (
            "numero_proposta", "contato_nome", "nome_modelo", "introducao",
            "descricao_extra", "situacao", "unidade_negocio_nome",
        )]
        for item in _lista_dicts(orcamento.get("itens")):
            partes.extend(_texto(item.get(k)) for k in ("sku", "descricao", "nome"))
        marcadores = orcamento.get("marcadores")
        if isinstance(marcadores, list):
            partes.extend(_texto(x) for x in marcadores)
        alvo = " ".join(partes).casefold()
        if all(termo in alvo for termo in termos):
            encontrados.append(orcamento)
    return sorted(encontrados, key=lambda x: (
        _texto(x.get("data_orcamento")), _texto(x.get("numero_proposta")), _chave(x)
    ), reverse=True)


def _rotulo(orcamento: dict) -> str:
    numero = _texto(orcamento.get("numero_proposta"), 80) or "sem número"
    unidade = _texto(orcamento.get("unidade_negocio_nome"), 100) or "Unidade não informada"
    contato = _texto(orcamento.get("contato_nome"), 150) or "Contato não informado"
    return f"Orçamento {numero} · {unidade} · {contato}"


def registros_para_vincular(registros: Any, usuario: Any) -> list[dict]:
    papel = _papel(usuario)
    if papel not in PAPEIS_IMPORTACAO:
        return []
    return [x for x in _lista_dicts(registros) if _texto(x.get("id"))
            and (x.get("status") not in STATUS_FECHADOS
                 or papel in PAPEIS_CORRECAO_FECHADA)]


def _vinculos_visiveis(ligacao: dict, papel: str) -> tuple[list[dict], bool]:
    if ligacao.get("estado") not in {"livre", "vinculado", "ambiguo"} or not isinstance(ligacao.get("vinculos"), list):
        raise ValueError("Formato da conferência de vínculos inválido")
    if any(not isinstance(v, dict) for v in ligacao["vinculos"]):
        raise ValueError("Lista de vínculos inválida")
    visiveis = []
    restrito = False
    for vinculo in _lista_dicts(ligacao.get("vinculos")):
        status = _texto(vinculo.get("status"))
        if status == "restrito" or not _texto(vinculo.get("id")) or (
            status == "Cancelada" and papel not in PAPEIS_CANCELADAS
        ):
            restrito = True
        else:
            visiveis.append(vinculo)
    return visiveis, restrito


def _dados_tabela_itens(orcamento: dict) -> list[dict]:
    return [{"SKU": _texto(x.get("sku")),
             "Descrição no orçamento": _texto(x.get("descricao") or x.get("nome")),
             "Quantidade": _texto(x.get("quantidade")),
             "Tipo no Tiny": _texto(x.get("tipo")),
             "Unidade": _texto(x.get("unidade"))}
            for x in _lista_dicts(orcamento.get("itens"))[:500]]


def _referencias_pedidos(orcamento: dict) -> list[dict]:
    linhas = []
    for pedido in _lista_dicts(orcamento.get("pedidos"))[:500]:
        notas = _lista_dicts(pedido.get("notas_fiscais") or pedido.get("nfs"))
        base = {"Pedido": _texto(pedido.get("numero_pedido") or pedido.get("numero")),
                "ID do pedido no Silver": _texto(pedido.get("pedido_id")),
                "Tiny ID do pedido": _texto(pedido.get("tiny_id") or pedido.get("pedido_tiny_id")),
                "Unidade": _texto(pedido.get("unidade_negocio_nome")),
                "Regra do vínculo": _texto(pedido.get("regra_operacional") or pedido.get("regra_origem")),
                "Tipo do vínculo": _texto(pedido.get("tipo_vinculo")),
                "ID da NF no Silver": _texto(pedido.get("nota_fiscal_id"))}
        if notas:
            for nota in notas[:500]:
                linhas.append(dict(base,
                    **{"NF": _texto(nota.get("numero_nf") or nota.get("numero")),
                       "Série": _texto(nota.get("serie")),
                       "Papel fiscal": _texto(nota.get("tipo_faturamento") or nota.get("papel"))}))
        else:
            linhas.append(dict(base, **{"NF": "Não informada nesta carga", "Série": "", "Papel fiscal": ""}))
    # Algumas publicações trazem referências fiscais no nível do orçamento.
    for nota in _lista_dicts(orcamento.get("notas_fiscais"))[:500]:
        linhas.append({"Pedido": _texto(nota.get("numero_pedido")),
                       "Tiny ID do pedido": _texto(nota.get("pedido_tiny_id")),
                       "Unidade": _texto(nota.get("unidade_negocio_nome")),
                       "Regra do vínculo": _texto(nota.get("regra_operacional")),
                       "NF": _texto(nota.get("numero_nf") or nota.get("numero")),
                       "Série": _texto(nota.get("serie")),
                       "Papel fiscal": _texto(nota.get("tipo_faturamento") or nota.get("papel"))})
    return linhas


def _mostrar_dados(st: Any, orcamento: dict, preparado: dict, *, etapa: bool = True) -> None:
    st.subheader("2. Confira as informações do Tiny" if etapa else "Informações do orçamento")
    st.text(_rotulo(orcamento))
    st.text("Data do orçamento: " + (_texto(orcamento.get("data_orcamento")) or "Não informada"))
    st.text("Situação no Tiny: " + (_texto(orcamento.get("situacao")) or "Não informada"))
    st.caption("A situação comercial do orçamento não define a chegada, o reparo ou o encerramento da garantia.")
    st.caption("O contato do Tiny é uma referência. Na Nova Garantia, confirme quem é o cliente e, quando houver distribuidor, quem é o consumidor final.")
    sugestao = preparado.get("sugestao_equipamento")
    if isinstance(sugestao, dict):
        st.text("Equipamento informado no texto: " + (_texto(sugestao.get("texto")) or "Não identificado em campo próprio."))
    for aviso in preparado.get("alertas", []):
        st.text(_texto(aviso))
    pendencias = orcamento.get("pendencias_origem")
    if isinstance(pendencias, list) and pendencias:
        st.caption("Informações que precisam de conferência")
        for pendencia in pendencias[:100]:
            st.text(PENDENCIAS_ORIGEM.get(_texto(pendencia), "Há um detalhe do cadastro de origem que precisa de conferência."))
    if preparado.get("conflitos"):
        st.warning("Há divergência entre o texto e o item do orçamento. Confira o equipamento físico antes de continuar.")
        for conflito in preparado["conflitos"]:
            st.text(_texto(conflito))
    with st.container():
        st.caption("Texto original do atendimento")
        for titulo, campo in (("Introdução", "introducao_texto"), ("Descrição extra", "descricao_extra_texto")):
            st.caption(titulo)
            st.text(_texto(preparado.get(campo)) or "Não informado nesta carga.")
    with st.container():
        st.caption("Itens do orçamento")
        st.caption("Confira quais equipamentos vieram para atendimento. As linhas comerciais não comprovam quais peças foram usadas no reparo.")
        itens = _dados_tabela_itens(orcamento)
        if itens:
            st.dataframe(itens, hide_index=True, use_container_width=True)
        else:
            st.info("Itens não disponíveis nesta carga. Isso não confirma que o orçamento está sem itens.")
        st.caption("Peças utilizadas, quantidades e custos do reparo continuam sendo confirmados na Bancada. O valor comercial do orçamento não é custo de garantia.")
    marcadores = orcamento.get("marcadores")
    if isinstance(marcadores, list) and marcadores:
        st.caption("Marcadores do orçamento")
        for marcador in marcadores[:100]:
            st.text(_texto(marcador))
    with st.container():
        st.caption("Pedidos e notas ligados ao orçamento")
        referencias = _referencias_pedidos(orcamento)
        if referencias:
            st.dataframe(referencias, hide_index=True, use_container_width=True)
        else:
            st.info("Nenhuma referência de pedido ou NF foi disponibilizada nesta carga.")
        st.caption("A relação operacional considera a unidade de negócio, incluindo a regra da Filial Foz. Um orçamento pode ter vários pedidos e notas. Confirme o papel de cada NF; essas referências não preenchem automaticamente a nota do consumidor final ou as notas de entrada e saída do SAC.")


def render_importacao_tiny(
    st: Any,
    snapshot: Any,
    registros: Any,
    usuario: Any,
    *,
    catalogo: Any = None,
    abrir_nova: Callable[[dict], Any] | None = None,
    abrir_existente: Callable[[str], Any] | None = None,
    vincular_existente: Callable[[str, dict, Any], Any] | None = None,
    ligacao_origem: Callable[[dict], dict] | None = None,
    agora: datetime | None = None,
) -> dict:
    """Renderiza a seleção/conferência e devolve status; callbacks fazem a ação.

    ``registros`` deve ser o recorte visível ao usuário. Para bloquear duplicata
    também de protocolos restritos, ``ligacao_origem`` pode consultar o estado
    completo e devolver vínculos redigidos (id vazio, status ``restrito``).
    """
    papel = _papel(usuario)
    if papel not in PAPEIS_IMPORTACAO:
        return {"status": "sem_permissao"}
    st.subheader("Importar do Tiny")
    st.caption("Busque o orçamento, confira o atendimento e aproveite as informações na Nova Garantia. Se o caso já tem protocolo no BI, vincule os registros.")
    validacao = dominio.validar_snapshot(snapshot, agora=agora)
    if not validacao.get("valido") or not validacao.get("disponivel"):
        st.info("A lista de orçamentos está indisponível. A entrada manual de garantia continua disponível abaixo.")
        for aviso in validacao.get("erros", []) + validacao.get("avisos", []):
            st.text(_texto(aviso))
        return {"status": "indisponivel"}
    st.text("Última coleta do Silver: " + _data_carga(snapshot.get("atualizado_em")))
    if snapshot.get("status") == "parcial":
        st.warning("A carga está parcial. Alguns orçamentos ainda não têm todos os detalhes; não encontrar um atendimento aqui não prova que ele não existe no Tiny.")
    if not validacao.get("atualizado", True):
        st.warning("A carga está desatualizada. Confira no Tiny se houve alterações antes de reaproveitar os dados.")
    for aviso in validacao.get("avisos", []):
        st.text(_texto(aviso))
    cobertura = snapshot.get("cobertura")
    if isinstance(cobertura, dict) and papel in PAPEIS_CANCELADAS:
        total = cobertura.get("orcamentos_total")
        completos = cobertura.get("orcamentos_enriquecidos")
        if isinstance(total, int) and isinstance(completos, int):
            st.caption(f"Esta carga contém {total} orçamentos; {completos} têm detalhes do atendimento. Esses totais não são a quantidade de garantias.")
    # Verificar antes da busca e dos rótulos: um vínculo restrito não pode revelar
    # o contato nem os textos do orçamento por meio do seletor de importação.
    ligacoes = {}
    orcamentos_visiveis = []
    tem_restrito = False
    try:
        for candidato in validacao.get("orcamentos", []):
            ligacao_candidato = (ligacao_origem(candidato) if ligacao_origem
                                else dominio.status_ligacao(registros, candidato))
            if not isinstance(ligacao_candidato, dict):
                raise ValueError("Vínculos indisponíveis")
            _, candidato_restrito = _vinculos_visiveis(ligacao_candidato, papel)
            if candidato_restrito:
                tem_restrito = True
                continue
            ligacoes[_chave(candidato)] = ligacao_candidato
            orcamentos_visiveis.append(candidato)
    except (ValueError, TypeError):
        st.error("Não consegui conferir os vínculos existentes. Tente novamente antes de importar.")
        return {"status": "ligacao_indisponivel"}
    if tem_restrito:
        st.info("Alguns vínculos exigem o acesso do responsável da garantia e não aparecem nesta lista.")
    if not orcamentos_visiveis and tem_restrito:
        return {"status": "vinculo_restrito"}
    st.subheader("1. Encontre o orçamento")
    busca = st.text_input("Buscar por número, contato, equipamento ou SKU", key="tiny_gar_busca", max_chars=120)
    encontrados = filtrar_orcamentos(orcamentos_visiveis, busca)
    if not encontrados:
        st.info("Não encontrei orçamento nesta carga com essa busca. Confira o número e a disponibilidade dos detalhes no Tiny.")
        return {"status": "sem_resultados"}
    por_chave = {_chave(o): o for o in encontrados}
    if len(por_chave) != len(encontrados):
        st.error("A carga contém identidades repetidas. A importação está bloqueada até a próxima carga válida.")
        return {"status": "identidades_repetidas"}
    selecionado = st.selectbox("Escolha o orçamento que a equipe cadastrou no Tiny", list(por_chave),
        index=None, placeholder="Digite ou selecione o número do orçamento…", key="tiny_gar_orcamento",
        format_func=lambda chave: _rotulo(por_chave[chave]))
    if selecionado not in por_chave:
        return {"status": "aguardando_selecao"}
    orcamento = por_chave[selecionado]
    try:
        preparado = dominio.preparar_orcamento(orcamento, catalogo=catalogo)
    except (TypeError, ValueError):
        st.error("Os dados deste orçamento não puderam ser conferidos. Aguarde uma nova carga ou registre manualmente.")
        return {"status": "orcamento_invalido"}
    assinatura = json.dumps(preparado["dados_origem"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    prefixo = "tiny_gar_" + sha256((selecionado + assinatura).encode("utf-8")).hexdigest()[:16]
    ligacao = ligacoes.get(selecionado)
    if not isinstance(ligacao, dict):
        st.error("Não consegui conferir os vínculos existentes. Tente novamente antes de importar.")
        return {"status": "ligacao_indisponivel"}
    visiveis, restrito = _vinculos_visiveis(ligacao, papel)
    if restrito:
        st.warning("Este orçamento possui vínculo com um atendimento de acesso restrito. Peça ao responsável da garantia para conferir o vínculo antes de criar outro protocolo.")
        return {"status": "vinculo_restrito"}
    _mostrar_dados(st, orcamento, preparado)
    if visiveis:
        st.info("Este orçamento já está ligado a atendimento no BI. Abra a ficha existente para continuar o trabalho.")
        for vinculo in visiveis:
            st.text("Protocolo " + _texto(vinculo.get("id")) + " · " + _texto(vinculo.get("status")))
            st.text("Equipamento identificado como: " + _texto(vinculo.get("unidade_atendida")))
            if abrir_existente and st.button("Abrir protocolo " + _texto(vinculo.get("id")),
                key=prefixo + "_abrir_" + _texto(vinculo.get("id"))):
                abrir_existente(_texto(vinculo.get("id")))
                return {"status": "abrir_existente"}
    if ligacao.get("estado") == "ambiguo":
        st.error("Há vínculos duplicados para este orçamento e equipamento. Peça ao responsável para conferir os protocolos antes de continuar.")
        return {"status": "vinculo_ambiguo"}
    st.subheader("3. Identifique o equipamento atendido")
    serie = st.text_input("Número de série do equipamento (quando houver)", key=prefixo + "_serie",
                         max_chars=80, placeholder="Copie a série do equipamento físico")
    identificador = ""
    if not _texto(serie):
        identificador = st.text_input("Identificador do equipamento sem número de série", key=prefixo + "_slot",
            max_chars=80, placeholder="Ex.: ETIQUETA-SAC-104",
            help="Use um identificador fixo na etiqueta do equipamento e repita o mesmo em futuras conferências. Não use a posição da linha do orçamento.")
    confirmou_multiplo = False
    if visiveis or preparado.get("exige_confirmacao_multiplo"):
        confirmou_multiplo = st.checkbox("Confirmei que este orçamento atende mais de um equipamento e que estou identificando outra unidade física.",
            key=prefixo + "_multiplo")
        if visiveis and not confirmou_multiplo:
            return {"status": "ja_vinculado"}
    confirmou_conflito = True
    if preparado.get("conflitos"):
        confirmou_conflito = st.checkbox("Conferi a divergência entre o texto e o item; vou selecionar o equipamento correto na ficha.",
            key=prefixo + "_conflito")
    confirmou = st.checkbox("Conferi o texto original, o contato e o equipamento. Vou completar apenas os campos que faltarem na Nova Garantia.",
                           key=prefixo + "_conferiu")
    try:
        unidade_atendida = dominio.chave_unidade_atendida(serie=_texto(serie), slot_manual=_texto(identificador), confirmada=True)
    except (TypeError, ValueError):
        unidade_atendida = ""
    if unidade_atendida:
        exatos = [v for v in visiveis if v.get("unidade_atendida") == unidade_atendida]
        if exatos:
            st.info("Este equipamento já tem protocolo ligado a este orçamento. Use o botão Abrir protocolo acima.")
            return {"status": "equipamento_ja_vinculado"}
    pronto = bool(unidade_atendida and confirmou and confirmou_conflito
                  and validacao.get("pode_importar") and orcamento.get("enriquecido") is True
                  and (not preparado.get("exige_confirmacao_multiplo") or confirmou_multiplo))
    if orcamento.get("enriquecido") is not True:
        st.info("Este orçamento ainda não tem detalhe confirmado na carga. Aguarde a atualização para importar ou use a entrada manual.")
    acao = st.radio("Como deseja aproveitar este orçamento?",
        ["Levar para a Nova Garantia", "Vincular a um protocolo já existente"],
        key=prefixo + "_acao", horizontal=False)
    if acao == "Vincular a um protocolo já existente":
        candidatos = registros_para_vincular(registros, usuario)
        por_id = {_texto(x.get("id")): x for x in candidatos}
        if not por_id:
            st.info("Não há protocolo elegível para vínculo com seu acesso. Protocolos encerrados precisam do responsável da garantia.")
            return {"status": "sem_protocolo_elegivel"}
        gid = st.selectbox("Protocolo que corresponde a este mesmo atendimento", list(por_id), index=None,
            placeholder="Selecione um protocolo…", key=prefixo + "_protocolo",
            format_func=lambda codigo: codigo + " · " + _texto(por_id[codigo].get("cliente"), 150)
                + " · " + _texto(por_id[codigo].get("produto_nome"), 150))
        st.caption("O vínculo acrescenta a referência do Tiny. O diagnóstico, as peças, os custos e o histórico do protocolo continuam sendo os registrados pelo SAC.")
        confirma_vinculo = st.checkbox("Confirmei que este orçamento e este protocolo são do mesmo atendimento e do mesmo equipamento.",
                                      key=prefixo + "_confirma_vinculo")
        apto_vinculo = bool(pronto and gid in por_id and confirma_vinculo)
        if vincular_existente and st.button("Confirmar vínculo com o Tiny", type="primary",
            key=prefixo + "_vincular", disabled=not apto_vinculo) and apto_vinculo:
            contexto = _contexto(st, orcamento, unidade_atendida, snapshot, confirmou_multiplo, confirmou_conflito, agora)
            if contexto:
                vincular_existente(gid, contexto, por_id[gid].get("_version"))
                return {"status": "vincular_existente", "id": gid}
    elif abrir_nova and st.button("Conferir na Nova Garantia", type="primary", key=prefixo + "_nova", disabled=not pronto) and pronto:
        contexto = _contexto(st, orcamento, unidade_atendida, snapshot, confirmou_multiplo, confirmou_conflito, agora)
        if contexto:
            abrir_nova({"tiny_context": contexto, "campos_iniciais": preparado.get("campos_iniciais", {})})
            return {"status": "abrir_nova"}
    return {"status": "conferindo"}


def _contexto(st: Any, orcamento: dict, unidade: str, snapshot: dict,
              confirmou_multiplo: bool, confirmou_conflitos: bool,
              agora: datetime | None) -> dict | None:
    try:
        return dominio.preparar_contexto_importacao(orcamento, unidade_atendida=unidade,
            confirmado=True, atualizado_em=snapshot.get("atualizado_em"),
            confirmou_multiplo=confirmou_multiplo, confirmou_conflitos=confirmou_conflitos, agora=agora)
    except (TypeError, ValueError) as exc:
        st.error("A importação não pôde continuar. Confira a identificação e a disponibilidade dos detalhes.")
        st.text(_texto(str(exc)))
        return None


def render_origem_tiny(st: Any, registro: dict, snapshot: Any, usuario: Any, *,
                      atualizar_origem: Callable[[str, dict, Any], Any] | None = None,
                      agora: datetime | None = None) -> dict:
    """Mostra a origem vinculada e permite renovar somente a referência externa."""
    papel = _papel(usuario)
    if papel not in PAPEIS_IMPORTACAO or not isinstance(registro, dict):
        return {"status": "sem_permissao"}
    if registro.get("status") == "Cancelada" and papel not in PAPEIS_CANCELADAS:
        return {"status": "sem_permissao"}
    origem = registro.get("origem_tiny")
    if not isinstance(origem, dict) or origem.get("fonte") != "tiny_orcamento":
        return {"status": "sem_origem"}
    chave_consulta = "tiny_origem_consultar_" + sha256(_texto(registro.get("id")).encode("utf-8")).hexdigest()[:16]
    if not st.checkbox("Consultar origem do atendimento no Tiny", key=chave_consulta):
        return {"status": "origem_recolhida"}
    with st.container():
        st.subheader("Origem do atendimento no Tiny")
        st.text("Orçamento: " + _texto(origem.get("numero_proposta")))
        st.text("Equipamento identificado como: " + _texto(origem.get("unidade_atendida")))
        st.text("Referência conferida com a carga de: " + _data_carga(origem.get("atualizado_em")))
        st.caption("A referência do Tiny é mantida junto ao protocolo. O acompanhamento técnico é o registrado pelo SAC no BI.")
        dados_salvos = origem.get("dados")
        if isinstance(dados_salvos, dict):
            try:
                dados_consulta = dict(dados_salvos, enriquecido=True)
                preparado_salvo = dominio.preparar_orcamento(dados_consulta)
                _mostrar_dados(st, dados_consulta, preparado_salvo, etapa=False)
            except (ValueError, TypeError):
                st.info("A referência histórica não pôde ser exibida em detalhes. Confira a origem antes de atualizá-la.")
        validacao = dominio.validar_snapshot(snapshot, agora=agora)
        if not validacao.get("valido") or not validacao.get("disponivel"):
            st.info("A carga atual está indisponível. A referência salva no protocolo permanece disponível para consulta.")
            return {"status": "origem_salva"}
        atuais = [o for o in validacao.get("orcamentos", []) if
                  _texto(o.get("unidade_negocio_id")) == _texto(origem.get("unidade_negocio_id"))
                  and _texto(o.get("tiny_id")) == _texto(origem.get("tiny_id"))]
        if len(atuais) != 1:
            st.info("Este orçamento não está disponível com detalhes nesta carga. Isso não cancela nem exclui o atendimento no BI.")
            return {"status": "origem_sem_detalhe_atual"}
        atual = atuais[0]
        preparado = dominio.preparar_orcamento(atual)
        fingerprint = sha256(json.dumps(preparado["dados_origem"], ensure_ascii=False,
            sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if fingerprint == origem.get("fingerprint"):
            st.caption("A referência salva corresponde aos dados desta coleta do Silver.")
            return {"status": "origem_atual"}
        st.warning("O orçamento mudou no Tiny desde a última conferência. Confira a versão atual antes de atualizar a referência no protocolo.")
        _mostrar_dados(st, atual, preparado, etapa=False)
        st.caption("Atualizar a referência não altera status, diagnóstico, resultado, peças, fretes ou custos da garantia.")
        if registro.get("status") in STATUS_FECHADOS and papel not in PAPEIS_CORRECAO_FECHADA:
            st.info("Este protocolo está encerrado. O responsável da garantia pode conferir e atualizar a referência.")
            return {"status": "origem_alterada_somente_leitura"}
        if not validacao.get("pode_importar") or atual.get("enriquecido") is not True:
            st.info("A carga atual precisa estar completa para este orçamento e ter menos de 24 horas para atualizar o vínculo.")
            return {"status": "origem_alterada_indisponivel"}
        prefixo = "tiny_origem_" + sha256((_texto(registro.get("id")) + fingerprint).encode("utf-8")).hexdigest()[:16]
        multiplo = st.checkbox("Conferi qual unidade física deste orçamento pertence ao protocolo.",
                              key=prefixo + "_unidade")
        conflito = True
        if preparado.get("conflitos"):
            conflito = st.checkbox("Conferi a divergência entre o texto, os marcadores e os itens comerciais.",
                                   key=prefixo + "_conflito")
        confirma = st.checkbox("Confirmo a atualização apenas da referência do Tiny neste protocolo.",
                               key=prefixo + "_confirma")
        apto = bool(multiplo and conflito and confirma)
        if atualizar_origem and st.button("Atualizar referência do Tiny", key=prefixo + "_atualizar",
                                           disabled=not apto) and apto:
            contexto = _contexto(st, atual, _texto(origem.get("unidade_atendida")), snapshot, multiplo, conflito, agora)
            if contexto:
                atualizar_origem(_texto(registro.get("id")), contexto, registro.get("_version"))
                return {"status": "atualizar_origem"}
        return {"status": "origem_alterada"}
