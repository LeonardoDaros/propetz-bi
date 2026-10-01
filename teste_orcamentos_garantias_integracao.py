"""Adaptadores reais por AST; estado sintético, sem banco, secrets ou rede."""
import ast
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import uuid

import orcamentos_garantias as dominio
_tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8-sig"))
_functions = [copy.deepcopy(n) for n in _tree.body if isinstance(n, ast.FunctionDef)]
for _node in _functions:
    _node.decorator_list = []
FUNCTION_CODE = compile(ast.Module(body=_functions, type_ignores=[]), "<app-functions-only>", "exec")


def budget():
    return {"unidade_negocio_id": "fc97d781-d6d4-433d-94c3-7ceabb1b425a",
            "tiny_id": "12345", "numero_proposta": "9999", "situacao": "Concluído",
            "data_orcamento": "2026-09-20", "contato_nome": "Contato fictício",
            "introducao": "PRODUTO: AURA\nRELATO: Não liga", "descricao_extra": "",
            "marcadores": ["GARANTIA", "AURA"], "enriquecido": True,
            "itens": [{"sku": "AURA-220", "descricao": "Secador Aura 220V", "quantidade": 1, "tipo": "P"}],
            "pedidos": []}


class AdaptadorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="propetz-tiny-sintetico-")
        self.path = Path(self.tmp.name) / "garantias.json"
        self.data = {"garantias": [], "metadado_preservado": "sim"}
        self.sha = "v1"
        self.puts = []
        self.before_put = None
        self.user = {"name": "Operador fictício", "role": "garantia"}
        self.snapshot = {"schema_version": 1, "status": "parcial",
                         "atualizado_em": datetime.now(timezone.utc).isoformat(), "orcamentos": [budget()]}
        self.context = dominio.preparar_contexto_importacao(budget(), unidade_atendida="manual:UNIDADE 1",
                    confirmado=True, atualizado_em=self.snapshot["atualizado_em"])
        self.st = types.SimpleNamespace(session_state={"authenticated": True, "role": "garantia", "username": "operador"})
        self.ns = {"os": os, "json": json, "hashlib": hashlib, "uuid": uuid,
                   "datetime": datetime, "threading": threading, "st": self.st,
                   "orcamentos_garantias": dominio, "GARANTIAS_FILE": str(self.path),
                   "_STATE_RAW_CACHE": {}, "_GH_WRITE_LOCK": threading.Lock(),
                   "_GH_STATE_BRANCH": "state", "STATUS_FINALIZADOS": ["Concluída", "Cancelada"],
                   "STATUS_GARANTIA": ["Aguardando chegada", "Em bancada", "Aguardando peça", "Confirmado — aguardando R$ frete", "Concluída", "Cancelada"],
                   "_STATUS_LEGADO": {"Aberta": "Aguardando chegada", "Devolvida ao cliente": "Concluída"},
                   "yaml": types.SimpleNamespace(YAMLError=ValueError)}
        exec(FUNCTION_CODE, self.ns)
        self.ns.update({"_gh_token": lambda: "synthetic", "_session_expired": lambda: False,
                        "load_users": lambda: {"users": {"operador": copy.deepcopy(self.user)}},
                        "_gh_get_file": lambda *a, **k: (json.dumps(self.data).encode(), self.sha),
                        "_gh_put_file_status": self.put,
                        "load_orcamentos_garantias": lambda: copy.deepcopy(self.snapshot)})

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, filename, body, message, branch, sha, token):
        self.puts.append(json.loads(body))
        if self.before_put:
            callback, self.before_put = self.before_put, None
            callback()
            return False, 409
        if sha != self.sha:
            return False, 409
        self.data = json.loads(body)
        self.sha += "x"
        return True, 200

    def create(self):
        return self.ns["add_garantia"]({"cliente": "Cliente confirmado", "produto_sku": "AURA-220",
            "defeito": "Não liga", "pecas": [], "custo_total": 0}, tiny_context=self.context)

    def record(self, gid="G-0005", **fields):
        return {"id": gid, "status": "Em bancada", "cliente": "Cliente confirmado", "historico": [{
            "em": "2026-09-20", "por": "Operador", "acao": "Diagnóstico"}], "pecas": [{
            "sku": "PECA", "qtd": 1, "custo": 15}], "diagnostico_obs": "Serviço preservado",
            "custo_total": 15, **fields}

    def test_importacao_idempotente_nao_altera_dados_tecnicos(self):
        gid, ok = self.create()
        self.assertTrue(ok)
        self.assertEqual(self.create(), (gid, True))
        self.assertEqual(len(self.puts), 1)
        self.assertEqual(len(self.data["garantias"]), 1)
        self.assertEqual(self.data["garantias"][0]["status"], "Aguardando chegada")
        self.assertEqual(self.data["garantias"][0]["pecas"], [])
        self.assertEqual(self.data["metadado_preservado"], "sim")

    def test_corrida_409_rele_vinculo_sem_criar_duplicata(self):
        def concorrente():
            self.data["garantias"] = [self.record(origem_tiny=self.context["origem_tiny"])]
            self.sha = "concorrente"
        self.before_put = concorrente
        self.assertEqual(self.create(), ("G-0005", True))
        self.assertEqual(len(self.data["garantias"]), 1)
        self.assertEqual(self.data["garantias"][0]["diagnostico_obs"], "Serviço preservado")
        self.assertEqual(len(self.puts), 1)

    def test_corrida_preserva_outro_atendimento(self):
        def concorrente():
            self.data["garantias"] = [self.record()]
            self.sha = "concorrente"
        self.before_put = concorrente
        self.assertEqual(self.create(), ("G-0006", True))
        self.assertEqual(len(self.data["garantias"]), 2)
        self.assertEqual(self.data["garantias"][0]["custo_total"], 15)

    def test_revogacao_de_perfil_durante_retry_bloqueia(self):
        self.before_put = lambda: self.user.update(role="vendedor", vendor_filter="Carteira")
        self.assertEqual(self.create(), (None, False))
        self.assertEqual(self.data["garantias"], [])

    def test_cancelada_invisivel_bloqueia_duplicata_sem_vazar_id(self):
        self.data["garantias"] = [self.record(gid="G-RESTRITO", status="Cancelada", origem_tiny=self.context["origem_tiny"])]
        self.assertEqual(self.create(), (None, False))
        self.assertNotIn("G-RESTRITO", self.st.session_state["_gar_save_error"])
        self.assertFalse(self.puts)

    def test_origem_modificada_apos_confirmacao_bloqueia(self):
        self.snapshot["orcamentos"][0]["introducao"] += "\nDados alterados"
        self.assertEqual(self.create(), (None, False))
        self.assertFalse(self.puts)

    def test_origem_ausente_ou_antiga_bloqueia(self):
        self.snapshot["orcamentos"] = []
        self.assertEqual(self.create(), (None, False))
        self.snapshot["orcamentos"] = [budget()]
        self.snapshot["atualizado_em"] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        self.assertEqual(self.create(), (None, False))
        self.assertFalse(self.puts)

    def test_vinculo_legado_preserva_todos_os_dados_e_acrescenta_historico(self):
        before = self.record()
        self.data["garantias"] = [copy.deepcopy(before)]
        version = self.ns["_garantia_versao"](before)
        self.assertTrue(self.ns["vincular_orcamento_garantia"]("G-0005", self.context, version))
        after = self.data["garantias"][0]
        self.assertEqual({k: after[k] for k in before if k != "historico"}, {k: v for k,v in before.items() if k != "historico"})
        self.assertEqual(after["historico"][:-1], before["historico"])
        self.assertTrue(self.ns["vincular_orcamento_garantia"]("G-0005", self.context, self.ns["_garantia_versao"](after)))
        self.assertEqual(len(self.puts), 1)

    def test_vinculo_finalizado_somente_master_admin(self):
        for role, allowed in [("garantia", False), ("diretor", False), ("garantia_master", True), ("admin", True)]:
            self.user["role"] = role
            self.data["garantias"] = [self.record(status="Concluída")]
            version = self.ns["_garantia_versao"](self.data["garantias"][0])
            self.assertEqual(self.ns["vincular_orcamento_garantia"]("G-0005", self.context, version), allowed)

    def test_versao_desatualizada_nao_sobrepoe_bancada(self):
        self.data["garantias"] = [self.record()]
        self.assertFalse(self.ns["vincular_orcamento_garantia"]("G-0005", self.context, "antiga"))
        self.assertFalse(self.puts)

    def test_update_generico_nao_substitui_vinculo(self):
        g = self.record()
        self.data["garantias"] = [g]
        self.assertFalse(self.ns["update_garantia"]("G-0005", {"origem_tiny": {}}, "Teste",
                     expected_version=self.ns["_garantia_versao"](g)))
        self.assertFalse(self.puts)

    def test_atualizacao_origem_preserva_tecnica_e_repeticao_sem_evento(self):
        before = self.record(origem_tiny=copy.deepcopy(self.context["origem_tiny"]))
        self.data["garantias"] = [copy.deepcopy(before)]
        self.snapshot["orcamentos"][0]["descricao_extra"] = "Serviço atualizado na origem para conferência"
        contexto = dominio.preparar_contexto_importacao(self.snapshot["orcamentos"][0],
            unidade_atendida="manual:UNIDADE 1", confirmado=True, atualizado_em=self.snapshot["atualizado_em"])
        self.assertTrue(self.ns["vincular_orcamento_garantia"]("G-0005", contexto,
            self.ns["_garantia_versao"](before), atualizar=True))
        after = copy.deepcopy(self.data["garantias"][0])
        for k in before:
            if k not in ("historico", "origem_tiny"):
                self.assertEqual(before[k], after[k])
        self.assertEqual(len(after["historico"]), len(before["historico"]) + 1)
        self.assertNotEqual(after["origem_tiny"]["fingerprint"], before["origem_tiny"]["fingerprint"])
        self.assertTrue(self.ns["vincular_orcamento_garantia"]("G-0005", contexto,
            self.ns["_garantia_versao"](after), atualizar=True))
        self.assertEqual(self.data["garantias"][0], after)
        self.assertEqual(len(self.puts), 1)

    def test_bancada_continua_sem_fonte_e_preserva_referencia(self):
        g = self.record(origem_tiny=copy.deepcopy(self.context["origem_tiny"]))
        self.data["garantias"] = [copy.deepcopy(g)]
        self.ns["load_orcamentos_garantias"] = lambda: self.fail("Salvar bancada não depende de origem")
        self.assertTrue(self.ns["update_garantia"]("G-0005", {"diagnostico_obs": "Novo diagnóstico"},
            "Serviço", expected_version=self.ns["_garantia_versao"](g)))
        self.assertEqual(self.data["garantias"][0]["origem_tiny"], g["origem_tiny"])
        self.assertEqual(self.data["garantias"][0]["diagnostico_obs"], "Novo diagnóstico")

    def test_409_vinculo_rejeita_versao_nova_sem_sobrepor_servico(self):
        self.data["garantias"] = [self.record()]
        version = self.ns["_garantia_versao"](self.data["garantias"][0])
        def concorrente():
            self.data["garantias"][0]["diagnostico_obs"] = "Serviço registrado por colega"
            self.sha = "outro-operador"
        self.before_put = concorrente
        self.assertFalse(self.ns["vincular_orcamento_garantia"]("G-0005", self.context, version))
        self.assertEqual(self.data["garantias"][0]["diagnostico_obs"], "Serviço registrado por colega")
        self.assertNotIn("origem_tiny", self.data["garantias"][0])
        self.assertEqual(len(self.puts), 1)

    def test_loader_nao_le_orcamentos_para_vendedor_ou_sessao_expirada(self):
        # Reinstala apenas o loader real removido pelo fixture de origem.
        functions = {}
        exec(FUNCTION_CODE, functions)
        self.ns["load_orcamentos_garantias"] = types.FunctionType(functions["load_orcamentos_garantias"].__code__, self.ns)
        self.ns["__file__"] = str(Path(__file__))
        self.ns["_read_state_json"] = lambda *a, **k: self.fail("Fonte SAC não deve ser lida")
        self.st.session_state["role"] = "vendedor"
        self.assertIsNone(self.ns["load_orcamentos_garantias"]())
        self.st.session_state["role"] = "garantia"
        self.ns["_session_expired"] = lambda: True
        self.assertIsNone(self.ns["load_orcamentos_garantias"]())


class RotinaTests(unittest.TestCase):
    def executar(self, resultado):
        import silver_diaria as rotina
        commands, copied = [], []
        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            if any(str(arg).endswith("silver_orcamentos_garantias.py") for arg in cmd):
                if isinstance(resultado, Exception):
                    raise resultado
                return resultado, ""
            if "get-url" in cmd:
                return 0, "https://example.invalid/repo.git"
            if "commit" in cmd:
                return 1, "nothing to commit"
            return 0, ""
        with patch.object(rotina, "run", side_effect=fake_run), patch.object(rotina, "log"), \
             patch.object(rotina, "limpar_clone", return_value=True), patch.object(rotina.os.path, "exists", return_value=True), \
             patch.object(rotina.shutil, "copy2", side_effect=lambda src,dst: copied.append(Path(src).name)):
            self.assertEqual(rotina.main(), 0)
        return next(c for c in commands if "add" in c), copied

    def test_falha_nova_fonte_preserva_as_demais_publicacoes(self):
        for failure in (1, TimeoutError("sintético")):
            added, copied = self.executar(failure)
            self.assertNotIn("silver_orcamentos_garantias.json", added)
            self.assertIn("silver_catalogo_garantias.json", copied)
            self.assertIn("silver_mes_vivo.json", copied)

    def test_sucesso_publica_apenas_snapshot_sem_mutar_protocolos(self):
        added, copied = self.executar(0)
        self.assertIn("silver_orcamentos_garantias.json", added)
        self.assertIn("silver_orcamentos_garantias.json", copied)
        self.assertNotIn("garantias.json", copied)
        self.assertNotIn("users.yaml", copied)


if __name__ == "__main__":
    unittest.main(verbosity=2)
