"""Regressão do catálogo técnico: sem depender de vendas ou de banco real."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import MagicMock, patch

from garantias_catalogo import FONTE_CUSTO_CONSOLIDADO, UNIDADES_CUSTO, catalogo_opcoes, custo_referencia_consolidado, validate_snapshot
import silver_catalogo_garantias as coletor


NOW = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)


def snapshot(n=2):
    return {"schema_version": 1, "fonte": "silver.produto", "generated_at": NOW.isoformat(),
            "produtos": [{"sku": f"PECA-{i}", "nome": f"Peça {i} Propetz"} for i in range(n)]}


class ValidacaoTests(unittest.TestCase):
    def test_valido_minimizado_sem_alterar_entrada(self):
        raw = snapshot()
        raw["credencial"] = "não transportar"
        raw["produtos"][0]["custo"] = 33
        before = deepcopy(raw)
        result = validate_snapshot(raw, NOW)
        self.assertEqual(raw, before)
        self.assertNotIn("credencial", result)
        self.assertEqual(set(result["produtos"][0]), {"sku", "nome"})

    def test_malformados_vazios_e_limite_fecham_fonte(self):
        cases = [None, [], {}, snapshot(0), snapshot(10001)]
        for field, value in [("schema_version", True), ("schema_version", 2),
                             ("fonte", "outra"), ("generated_at", "2026-09-21"),
                             ("generated_at", (NOW + timedelta(minutes=6)).isoformat()),
                             ("produtos", {}), ("produtos", [None])]:
            raw = snapshot(); raw[field] = value; cases.append(raw)
        for raw in cases:
            with self.subTest(raw_type=type(raw).__name__):
                self.assertIsNone(validate_snapshot(raw, NOW))

    def test_identidade_invalida_duplicada_nao_e_ignorada(self):
        for key, value in [("sku", ""), ("sku", 123), ("sku", "A — B"),
                           ("nome", None), ("nome", "x\ny"), ("sku", "PECA-1")]:
            raw = snapshot(); raw["produtos"][0][key] = value
            self.assertIsNone(validate_snapshot(raw, NOW))

    def test_union_prioriza_cadastro_mantem_legado_e_variantes(self):
        raw = snapshot()
        raw["produtos"] = [{"sku": s, "nome": "Motor Aura Propetz"}
                           for s in ("SEP1-MOA-110", "SEP1-MOA-220", "X-100", "X-200")]
        legacy = [{"code": "SEP1-MOA-110", "name": "Antigo"},
                  {"code": "LEGADO", "name": "Produto antigo"}]
        options = catalogo_opcoes(raw, legacy)
        self.assertEqual(len(options), 5)
        self.assertIn("SEP1-MOA-110 — Motor Aura Propetz", options)
        self.assertIn("LEGADO — Produto antigo", options)
        self.assertNotIn("SEP1-MOA-110 — Antigo", options)

    def test_fonte_invalida_preserva_legado_e_ignora_linha_ruim(self):
        self.assertEqual(catalogo_opcoes({}, [None, {"code": "A", "name": "Legado"}]),
                         ["A — Legado"])


class TransformacaoTests(unittest.TestCase):
    def test_dedup_deterministico_prefere_nome_legivel(self):
        rows = [{"codigo": "A", "nome": "Motor \ufffd Aura Propetz"},
                {"codigo": "A", "nome": "Motor Aura Propetz 110V"},
                {"codigo": "B", "nome": "Motor Aura Propetz 110V"}]
        first = coletor.montar_snapshot(rows, generated_at=NOW.isoformat())
        self.assertEqual(first, coletor.montar_snapshot(rows[::-1], generated_at=NOW.isoformat()))
        self.assertEqual(len(first["produtos"]), 2)
        self.assertEqual(first["produtos"][0]["nome"], "Motor Aura Propetz 110V")

    def test_cadastro_sem_venda_saldo_data_custo_e_suficiente(self):
        raw = coletor.montar_snapshot([{"codigo": "NOVO", "nome": "PCB Aura Propetz"}])
        self.assertEqual(raw["produtos"], [{"sku": "NOVO", "nome": "PCB Aura Propetz"}])

    def test_linhas_invalidas_abortam(self):
        for rows in ([], [None], [{"codigo": "A", "nome": ""}],
                     [{"codigo": None, "nome": "Nome"}]):
            with self.assertRaises(ValueError):
                coletor.montar_snapshot(rows)


class CustoConsolidadoTests(unittest.TestCase):
    def _raw(self):
        raw = snapshot()
        raw.update({"fonte_custo_consolidado": FONTE_CUSTO_CONSOLIDADO,
                    "custos_consolidados": [{"sku": "PECA-0", "custo": 12.35,
                    "atualizado_em": NOW.isoformat(), "unidades": list(UNIDADES_CUSTO),
                    "criterio": "maior_custo_medio_sem_saldo"}]})
        return raw

    def _linha(self, **values):
        row = {"codigo": "PECA-0", "nome": "Peça Propetz", "unidade": "Matriz",
               "saldo_estoque": "0", "preco_custo": "10", "preco_custo_medio": "12.345",
               "xdata_atualizacao": NOW}
        row.update(values)
        return row

    def _montar(self, rows):
        return coletor.montar_snapshot([{"codigo": "PECA-0", "nome": "Peça Propetz"}],
                                     linhas_custo=rows, generated_at=NOW.isoformat())

    def test_helper_por_sku_e_sem_dado_de_unidade(self):
        value = custo_referencia_consolidado(self._raw(), "PECA-0", NOW)
        self.assertEqual(value["custo"], 12.35)
        self.assertEqual(value["fonte"], FONTE_CUSTO_CONSOLIDADO)
        self.assertEqual(value["unidades"], ["Matriz", "Filial", "TradeCorp"])
        self.assertIsNone(custo_referencia_consolidado(self._raw(), "PECA-1", NOW))
        self.assertNotIn("unidade_id", value)

    def test_sem_custo_antigo_continua_valido(self):
        self.assertIsNotNone(validate_snapshot(snapshot(), NOW))
        self.assertIsNone(custo_referencia_consolidado(snapshot(), "PECA-0", NOW))

    def test_so_whitelist_custo_e_proveniencia(self):
        raw = self._raw()
        raw["custos_consolidados"][0].update({"saldo_estoque": 20, "preco_custo_medio": 99})
        valid = validate_snapshot(raw, NOW)
        self.assertEqual(set(valid["custos_consolidados"][0]),
                         {"sku", "custo", "atualizado_em", "criterio", "unidades"})

    def test_valores_invalidos_nao_sao_custo_gratis(self):
        for value in (0, -1, float("nan"), float("inf"), True, "12.34", 10 ** 1000):
            raw = self._raw(); raw["custos_consolidados"][0]["custo"] = value
            self.assertIsNone(validate_snapshot(raw, NOW))

    def test_timestamp_escopo_metodo_duplicidade_invalidos(self):
        for key, value in [("atualizado_em", "2026-09-21"),
                           ("atualizado_em", (NOW + timedelta(minutes=6)).isoformat()),
                           ("sku", "FORA"), ("criterio", "arbitrario"),
                           ("unidades", ["FilialFoz"])]:
            raw = self._raw(); raw["custos_consolidados"][0][key] = value
            self.assertIsNone(validate_snapshot(raw, NOW))
        raw = self._raw(); raw["custos_consolidados"].append(deepcopy(raw["custos_consolidados"][0]))
        self.assertIsNone(validate_snapshot(raw, NOW))

    def test_validade_pela_coleta_nao_pela_ultima_alteracao_do_cadastro(self):
        raw = self._raw(); old = (NOW - timedelta(days=10)).isoformat()
        raw["custos_consolidados"][0]["atualizado_em"] = old
        self.assertIsNotNone(custo_referencia_consolidado(raw, "PECA-0", NOW))
        raw["generated_at"] = (NOW - timedelta(hours=25)).isoformat()
        self.assertIsNone(custo_referencia_consolidado(raw, "PECA-0", NOW))

    def test_sem_saldo_usa_maior_medio_sem_incluir_foz_gerencial(self):
        rows = [self._linha(preco_custo_medio="12"),
                self._linha(unidade="Filial", preco_custo_medio="15.123"),
                self._linha(unidade="TradeCorp", preco_custo_medio="13"),
                self._linha(unidade="FilialFoz", preco_custo_medio="999"),
                self._linha(unidade="Gerencial", preco_custo_medio="999")]
        raw = self._montar(rows)
        value = raw["custos_consolidados"][0]
        self.assertEqual(value["custo"], 15.12)
        self.assertEqual(value["criterio"], "maior_custo_medio_sem_saldo")
        self.assertNotIn("999", json.dumps(raw))
        self.assertNotIn("saldo_estoque", json.dumps(raw))

    def test_ponderacao_usa_preco_custo_saldo_fisico_assinado_sem_reserva(self):
        rows = [self._linha(saldo_estoque="10", preco_custo="10", preco_custo_medio="99", saldo_estoque_reservado=9),
                self._linha(unidade="Filial", saldo_estoque="-2", preco_custo="20", preco_custo_medio="99"),
                self._linha(unidade="TradeCorp", saldo_estoque="2", preco_custo="30", preco_custo_medio="99")]
        value = self._montar(rows)["custos_consolidados"][0]
        self.assertEqual(value["custo"], 12.0)  # (100 - 40 + 60) / (10 - 2 + 2)
        self.assertEqual(value["criterio"], "media_ponderada_saldo_fisico")

    def test_duplicados_concordantes_nao_duplicam_peso(self):
        first = self._linha(saldo_estoque="1", preco_custo="10")
        rows = [first, dict(first, id=2), self._linha(unidade="Filial", saldo_estoque="1", preco_custo="20")]
        self.assertEqual(self._montar(rows)["custos_consolidados"][0]["custo"], 15.0)

    def test_conflito_omite_custo_preserva_produto(self):
        raw = self._montar([self._linha(preco_custo_medio="12"), self._linha(preco_custo_medio="15")])
        self.assertEqual(raw["custos_consolidados"], [])
        self.assertEqual(len(raw["custos_consolidados_ambiguos"]), 1)
        self.assertEqual(len(raw["produtos"]), 1)

    def test_invalido_custo_em_estoque_positivo_omite_referencia(self):
        for value in (None, "0", "NaN", "-1"):
            raw = self._montar([self._linha(preco_custo=value, saldo_estoque="2")])
            self.assertEqual(raw["custos_consolidados"], [])
            self.assertEqual(len(raw["produtos"]), 1)

    def test_sem_qualquer_custo_nao_inventa_gratuidade(self):
        raw = self._montar([self._linha(preco_custo=None, preco_custo_medio=None)])
        self.assertEqual(raw["custos_consolidados"], [])
        self.assertIsNone(custo_referencia_consolidado(raw, "PECA-0", NOW))

    def test_ambiguo_nao_coexiste_com_custo_do_sku(self):
        raw = self._raw()
        raw["custos_consolidados_ambiguos"] = [{"sku": "PECA-0", "motivo": "Divergente"}]
        self.assertIsNone(validate_snapshot(raw, NOW))


class ArquivoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "catalogo.json"
        coletor.salvar_atomico(snapshot(10), self.path)
        self.previous = self.path.read_bytes()

    def test_reducao_maior_30_preserva_conteudo_e_timestamp(self):
        mtime = self.path.stat().st_mtime_ns
        with self.assertRaises(ValueError):
            coletor.salvar_atomico(snapshot(6), self.path)
        self.assertEqual(self.path.read_bytes(), self.previous)
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)
        coletor.salvar_atomico(snapshot(7), self.path)
        self.assertEqual(len(json.loads(self.path.read_text())["produtos"]), 7)

    def test_override_explicito_nao_permite_catalogo_vazio(self):
        coletor.salvar_atomico(snapshot(1), self.path, aceitar_reducao=True)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            coletor.salvar_atomico(snapshot(0), self.path, aceitar_reducao=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_falha_replace_preserva_e_limpa_temporario(self):
        with patch.object(coletor.os, "replace", side_effect=OSError("falha simulada")):
            with self.assertRaises(OSError):
                coletor.salvar_atomico(snapshot(11), self.path)
        self.assertEqual(self.path.read_bytes(), self.previous)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [self.path])

    def test_falha_coleta_nao_publica_nem_muda_outros_estados(self):
        other = Path(self.temp.name) / "garantias.json"
        other.write_text('{"imutavel":true}')
        stdout = io.StringIO()
        with patch.object(coletor, "consultar_fonte", side_effect=RuntimeError("segredo SQL")), redirect_stdout(stdout):
            self.assertEqual(coletor.main(["--saida", str(self.path)]), 1)
        self.assertEqual(self.path.read_bytes(), self.previous)
        self.assertEqual(other.read_text(), '{"imutavel":true}')
        self.assertNotIn("segredo", stdout.getvalue())

    def test_cli_so_escreve_snapshot_de_catalogo(self):
        rows = [{"codigo": f"PECA-{i}", "nome": "Peça Propetz"} for i in range(12)]
        with patch.object(coletor, "consultar_fonte", return_value=(rows, [])), redirect_stdout(io.StringIO()):
            self.assertEqual(coletor.main(["--saida", str(self.path)]), 0)
        self.assertEqual(len(json.loads(self.path.read_text())["produtos"]), 12)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [self.path])


class BancoSimuladoTests(unittest.TestCase):
    def _executar(self, *, count=2, distinct=2, readonly="on"):
        bridge = ModuleType("ponte_db_silver")
        extra = ModuleType("psycopg2.extras")
        extra.RealDictCursor = object()
        cx, cursor = MagicMock(), MagicMock()
        bridge.conectar = MagicMock(return_value=cx)
        cx.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [{"transaction_read_only": readonly}, {"n": count, "skus": distinct}, {"n": 1}]
        cursor.fetchall.side_effect = [
            [{"codigo": "A-110", "nome": "Motor Aura Propetz 110V", "id_unidade_negocio": "filial-id"},
             {"codigo": "A-220", "nome": "Motor Aura Propetz 220V", "id_unidade_negocio": "filial-id"}],
            [{"id": "filial-id", "nome": "Filial"}, {"id": "matriz-id", "nome": "Matriz"},
             {"id": "trade-id", "nome": "TradeCorp"}],
            [{"codigo": "A-110", "id_unidade_negocio": "filial-id", "saldo_estoque": 0,
              "preco_custo": 10, "preco_custo_medio": 12, "xdata_atualizacao": NOW}]]
        with patch.dict(sys.modules, {"ponte_db_silver": bridge, "psycopg2.extras": extra}):
            result = coletor.consultar_fonte()
        return result, cx, cursor

    def test_transacao_readonly_contagem_independente_e_limites(self):
        result, cx, cur = self._executar()
        produtos, custos = result
        self.assertEqual(len(produtos), 2)
        self.assertEqual(len(custos), 1)
        cx.set_session.assert_called_once_with(readonly=True, autocommit=False, isolation_level="REPEATABLE READ")
        cx.rollback.assert_called_once(); cx.close.assert_called_once()
        sql = "\n".join(call.args[0] for call in cur.execute.call_args_list)
        self.assertIn("statement_timeout = 45000", sql)
        self.assertIn("lock_timeout = 3000", sql)
        self.assertIn("count(DISTINCT btrim(p.codigo))", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertNotIn("faturamento", sql)
        self.assertNotIn("xdata_criacao", sql)
        limited = next(call for call in cur.execute.call_args_list if "LIMIT %s" in call.args[0])
        self.assertEqual(limited.args[1][-1], 10001)
        self.assertEqual(custos[0]["unidade"], "Filial")
        self.assertIn("p.preco_custo", sql)
        custo_sql = next(call.args[0] for call in cur.execute.call_args_list if "p.saldo_estoque" in call.args[0])
        self.assertNotIn("ILIKE", custo_sql)
        self.assertNotIn("p.nome", custo_sql)
        self.assertIn("btrim(p.codigo)=ANY(%s)", custo_sql)

    def test_sem_marca_nome_propetz_entra_e_gerencial_fica_fora(self):
        self.assertIn("p.marca ILIKE %s OR p.nome ILIKE %s", coletor.FILTRO)
        self.assertEqual(coletor.PARAMETROS, ("A", "%propetz%", "%propetz%", "Gerencial"))

    def test_contagem_divergente_vazia_excessiva_ou_sessao_escrita_aborta(self):
        for args in ({"count": 3}, {"distinct": 1}, {"count": 0},
                     {"count": 10001}, {"readonly": "off"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self._executar(**args)


if __name__ == "__main__":
    unittest.main()
