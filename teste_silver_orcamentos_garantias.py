"""Testes sem banco, publicação, Tiny ou registros reais."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import silver_orcamentos_garantias as coletor

FOZ = coletor.FILIAL_FOZ
OUTRA = "4159b594-dba8-45e2-9f90-1c3aaf5c5739"
HORARIO = "2026-10-01T17:00:00+00:00"


def dados(numero=1, unidade=FOZ, operacional=True):
    header = {"id": numero, "unidade_negocio_id": unidade, "tiny_id": 1000 + numero,
              "numero_proposta": str(3000 + numero), "situacao": "Concluído",
              "data_orcamento": "2026-09-28", "data_proximo_contato": None,
              "contato_tiny_id": 2000 + numero, "contato_nome": "Contato de teste",
              "nome_modelo": "", "valor_total": "99.50",
              "introducao": "<p>Equipamento em análise.</p>",
              "descricao_extra": "<div>Relato original. Conferir bancada.</div>"}
    pai = {"orcamento_id": numero, "unidade_negocio_id": unidade,
           "orcamento_tiny_id": 1000 + numero, "numero_proposta": str(3000 + numero)}
    item = {**pai, "id": 90 + numero, "item": 1, "produto_tiny_id": 3000 + numero,
            "sku": "MP5-510P-100", "descricao": "Máquina Pro7", "tipo": "P", "unidade": "UN",
            "quantidade": "1", "valor_unitario": "99.50", "desconto": "0", "valor_total": "99.50"}
    marker = {**pai, "descricao": "GARANTIA" if operacional else "PROPETZ"}
    pedido = {**pai, "pedido_id": 4000 + numero, "numero_pedido": str(5000 + numero),
              "data_pedido": "2026-09-29", "situacao_pedido": "faturado", "nota_fiscal_id": 6000 + numero,
              "tipo_vinculo": "REGRA_NEGOCIO", "regra_origem": "OS_ESTRITA"}
    return header, item, marker, pedido


def snapshot(quantidade=1, *, horario=HORARIO):
    conjuntos = [[], [], [], []]
    for n in range(1, quantidade + 1):
        for destino, linha in zip(conjuntos, dados(n)):
            destino.append(linha)
    return coletor.montar_snapshot(*conjuntos, generated_at=horario,
                                  coverage_start="2026-01-01", coverage_end="2026-10-01")


class TesteColetor(unittest.TestCase):
    def test_dados_comerciais_nao_viram_pecas_custo_ou_status_sac(self):
        snap = snapshot()
        row = snap["orcamentos"][0]
        self.assertEqual(row["situacao"], "Concluído")
        self.assertEqual(row["itens"][0]["quantidade"], 1)
        self.assertEqual(row["valor_total"], 99.5)
        self.assertTrue(row["enriquecido"])
        for key in ("pecas", "custo", "status", "frete", "equipamento_sku", "diagnostico"):
            self.assertNotIn(key, row)
        self.assertFalse(snap["origem"]["frescor_tiny_comprovado"])

    def test_html_nao_executavel_e_identificadores_pessoais_fora(self):
        original = ('<p>Relato: não liga</p><script>alert("SEGREDO")</script>'
                    '<style>.algo { segredo:sim }</style><iframe src="https://evil.invalid">OCULTO</iframe>'
                    '<div onclick="roubar()">Troca em análise.</div><p>E-mail: teste@example.com</p>'
                    '<p>CPF 123.456.789-00; CNPJ 12.345.678/0001-90</p>'
                    '<p>Telefone: (45) 99999-8888</p><p>Endereço: Rua Exemplo, 10</p>'
                    '<p>CEP 85800-000</p>')
        texto = coletor.texto_seguro(original)
        for proibido in ("SEGREDO", "OCULTO", "<p>", "onclick", "example.com", "123.456", "12.345", "99999", "Rua Exemplo", "85800"):
            self.assertNotIn(proibido, texto)
        self.assertIn("não liga", texto)
        self.assertIn("Troca em análise", texto)

    def test_snapshot_nao_carrega_campos_sensiveis_ou_vendedor(self):
        h, i, m, p = dados()
        h.update(cpf="12345678900", cnpj="12345678000190", telefone="45999998888",
                 email="teste@example.com", endereco="Rua Secreta", vendedor_nome="Vendedor reservado")
        snap = coletor.montar_snapshot([h], [i], [m], [p], generated_at=HORARIO)
        serializado = json.dumps(snap)
        for segredo in ("12345678900", "12345678000190", "45999998888", "teste@example.com", "Rua Secreta", "Vendedor reservado"):
            self.assertNotIn(segredo, serializado)

    def test_somente_marcador_exato_operacional(self):
        h, i, m, _ = dados()
        for marca in ("PROPETZ", "SECADOR AURA", "SEM GARANTIA", "GARATIA", "garantia", "GARANTIA EXTRA"):
            m["descricao"] = marca
            snap = coletor.montar_snapshot([h], [i], [m], [], generated_at=HORARIO)
            self.assertEqual(snap["orcamentos"], [])
        for marca in coletor.MARCADORES_OPERACIONAIS:
            m["descricao"] = marca
            self.assertEqual(len(coletor.montar_snapshot([h], [i], [m], [], generated_at=HORARIO)["orcamentos"]), 1)

    def test_duplicacao_unidade_tiny_aborta(self):
        h, i, m, p = dados()
        h2 = {**h, "id": 999}
        with self.assertRaises(ValueError):
            coletor.montar_snapshot([h, h2], [i], [m], [p], generated_at=HORARIO)

    def test_mesmo_tiny_em_unidades_diferentes_e_distinto(self):
        a, b = dados(), dados(unidade=OUTRA)
        snap = coletor.montar_snapshot([a[0], b[0]], [a[1], b[1]], [a[2], b[2]], [a[3]], generated_at=HORARIO)
        self.assertEqual(len({r["chave_origem"] for r in snap["orcamentos"]}), 2)
        self.assertEqual(sum(len(r["pedidos"]) for r in snap["orcamentos"]), 1)

    def test_detalhe_com_unidade_tiny_ou_lake_divergente_aborta(self):
        h, i, m, p = dados()
        for campo, valor in (("unidade_negocio_id", OUTRA), ("orcamento_tiny_id", 1234), ("orcamento_id", 9876), ("numero_proposta", "OUTRO")):
            ruim = {**i, campo: valor}
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                coletor.montar_snapshot([h], [ruim], [m], [p], generated_at=HORARIO)

    def test_reordenar_linhas_e_posicao_nao_altera_fingerprint(self):
        h, i, m, p = dados()
        outro = {**i, "sku": "SEP1-100X-200", "descricao": "Secador Aura", "produto_tiny_id": 9001, "item": 2}
        primeiro = coletor.montar_snapshot([h], [i, outro], [m], [p], generated_at=HORARIO)
        segundo = coletor.montar_snapshot([h], [{**outro, "id": 777, "item": 1}, {**i, "id": 888, "item": 2}], [m, copy.deepcopy(m)], [p], generated_at="2026-10-01T18:00:00+00:00")
        self.assertEqual(primeiro["orcamentos"][0]["fingerprint"], segundo["orcamentos"][0]["fingerprint"])
        self.assertEqual(primeiro["orcamentos"][0]["itens"], segundo["orcamentos"][0]["itens"])

    def test_itens_iguais_preservados_e_pedidos_um_para_muitos(self):
        h, i, m, p = dados()
        segundo = {**p, "pedido_id": 999, "numero_pedido": "999", "nota_fiscal_id": 888}
        snap = coletor.montar_snapshot([h], [i, copy.deepcopy(i)], [m], [p, segundo], generated_at=HORARIO)
        row = snap["orcamentos"][0]
        self.assertEqual(len(row["itens"]), 2)
        self.assertEqual(len(row["pedidos"]), 2)
        self.assertEqual(row["valor_total"], 99.5)

    def test_vinculo_operacional_outro_escopo_ou_tipo_aborta(self):
        h, i, m, p = dados(unidade=OUTRA)
        with self.assertRaises(ValueError):
            coletor.montar_snapshot([h], [i], [m], [p], generated_at=HORARIO)
        h, i, m, p = dados()
        for campo, valor in (("tipo_vinculo", "FK_OFICIAL"), ("regra_origem", "OS_INFERIDA")):
            with self.assertRaises(ValueError):
                coletor.montar_snapshot([h], [i], [m], [{**p, campo: valor}], generated_at=HORARIO)

    def test_quantidade_invalida_bloqueia_candidato_sem_fabricar_zero(self):
        h, i, m, p = dados()
        for valor in (None, -1, 0, True, "NaN", "Infinity", "abc", "1e500"):
            snap = coletor.montar_snapshot([h], [{**i, "quantidade": valor}], [m], [p], generated_at=HORARIO)
            row = snap["orcamentos"][0]
            self.assertFalse(row["enriquecido"])
            self.assertIsNone(row["itens"][0]["quantidade"])
            self.assertIn("ITEM_QUANTIDADE_INVALIDO", row["pendencias_origem"])
            self.assertEqual(snap["status"], "parcial")

    def test_coleta_parcial_explica_cobertura_sem_ocultar_candidato(self):
        completo, incompleto = dados(), dados(2)
        incompleto[0].update(contato_nome=None, introducao=None, descricao_extra=None)
        snap = coletor.montar_snapshot([completo[0], incompleto[0]], [completo[1]], [completo[2], incompleto[2]], [], generated_at=HORARIO)
        self.assertEqual(snap["cobertura"]["orcamentos_total"], 2)
        self.assertEqual(snap["cobertura"]["orcamentos_enriquecidos"], 1)
        self.assertEqual(snap["cobertura"]["percentual_enriquecido"], 50)
        self.assertEqual(len(snap["orcamentos"]), 2)
        self.assertFalse(snap["orcamentos"][1]["enriquecido"])

    def test_proximo_contato_invalido_nao_vira_compromisso(self):
        h, i, m, p = dados()
        for valor in ("2024-01-01", "SEM DATA"):
            snap = coletor.montar_snapshot([{**h, "data_proximo_contato": valor}], [i], [m], [p], generated_at=HORARIO)
            row = snap["orcamentos"][0]
            self.assertIsNone(row["data_proximo_contato"])
            self.assertTrue(row["pendencias_origem"])

    def test_fonte_pre2026_ou_futura_aborta(self):
        h, i, m, p = dados()
        for valor in ("2025-12-31", "2026-10-02", None):
            with self.assertRaises(ValueError):
                coletor.montar_snapshot([{**h, "data_orcamento": valor}], [i], [m], [p], generated_at=HORARIO)

    def test_snapshot_venenoso_rejeitado(self):
        for veneno in (None, [], {}, {"schema_version": True}, {"schema_version": 1, "status": "erro"}):
            with self.assertRaises(ValueError):
                coletor.validar_snapshot(veneno)
        bom = snapshot()
        booleano = copy.deepcopy(bom)
        booleano["schema_version"] = True
        with self.assertRaises(ValueError):
            coletor.validar_snapshot(booleano)
        for alteracao in ({"tiny_id": "123 OR 1=1"}, {"fingerprint": "falso"}, {"chave_origem": "outra"}):
            ruim = copy.deepcopy(bom)
            ruim["orcamentos"][0].update(alteracao)
            with self.assertRaises(ValueError):
                coletor.validar_snapshot(ruim)

    def test_endereco_sem_rotulo_na_mesma_linha_e_suprimido(self):
        texto = coletor.texto_seguro("Relato: não liga. Cliente na Rua Exemplo, 123, bairro Centro")
        self.assertIn("não liga", texto)
        self.assertNotIn("Exemplo", texto)
        self.assertNotIn("123", texto)

    def test_reducao_preserva_bytes_e_timestamp_anterior(self):
        with tempfile.TemporaryDirectory() as pasta:
            path = Path(pasta) / "snapshot.json"
            coletor.salvar_atomico(snapshot(10), path)
            antes = path.read_bytes()
            for menor in (snapshot(0), snapshot(6)):
                with self.assertRaises(ValueError):
                    coletor.salvar_atomico(menor, path)
                self.assertEqual(path.read_bytes(), antes)
            coletor.salvar_atomico(snapshot(6), path, aceitar_reducao=True)
            self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["orcamentos"]), 6)

    def test_mesma_contagem_com_desaparecimento_suspeito_exige_revisao(self):
        original = snapshot(10)
        conjuntos = [[], [], [], []]
        for n in range(101, 111):
            for destino, linha in zip(conjuntos, dados(n)):
                destino.append(linha)
        novo = coletor.montar_snapshot(*conjuntos, generated_at=HORARIO)
        with tempfile.TemporaryDirectory() as pasta:
            path = Path(pasta) / "snapshot.json"
            coletor.salvar_atomico(original, path)
            with self.assertRaises(ValueError):
                coletor.salvar_atomico(novo, path)

    def test_escrita_atomica_falha_preserva_anterior(self):
        with tempfile.TemporaryDirectory() as pasta:
            path = Path(pasta) / "snapshot.json"
            coletor.salvar_atomico(snapshot(), path)
            antes = path.read_bytes()
            with patch.object(coletor.os, "replace", side_effect=OSError("falha simulada")):
                with self.assertRaises(OSError):
                    coletor.salvar_atomico(snapshot(horario="2026-10-01T18:00:00+00:00"), path)
            self.assertEqual(path.read_bytes(), antes)
            self.assertEqual(len(list(Path(pasta).iterdir())), 1)

    def test_anterior_corrompido_nao_e_sobrescrito_mesmo_com_flag(self):
        with tempfile.TemporaryDirectory() as pasta:
            path = Path(pasta) / "snapshot.json"
            path.write_text('{"sem":"estrutura"}', encoding="utf-8")
            antes = path.read_bytes()
            with self.assertRaises(ValueError):
                coletor.salvar_atomico(snapshot(), path, aceitar_reducao=True)
            self.assertEqual(path.read_bytes(), antes)

    def test_cli_falha_nao_publica_nem_toca_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            path = Path(pasta) / "snapshot.json"
            coletor.salvar_atomico(snapshot(), path)
            antes = path.read_bytes()
            with patch.object(coletor, "consultar_fonte", side_effect=RuntimeError("senha NUNCA imprimir")), patch("builtins.print") as output:
                self.assertEqual(coletor.main(["--saida", str(path)]), 1)
            self.assertNotIn("senha", str(output.call_args))
            self.assertEqual(path.read_bytes(), antes)


if __name__ == "__main__":
    unittest.main()
