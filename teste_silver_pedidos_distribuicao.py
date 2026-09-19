"""Coletor em isolamento: dados fictícios, sem banco/rede/publicação."""
import copy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import silver_pedidos_distribuicao as coleta


class ColetorPedidosTests(unittest.TestCase):
    def setUp(self):
        self.p = dict(id=100, unidade_negocio_id='u1', numero=10,
                      data_pedido='2026-01-02', data_prevista=None, data_faturamento=None,
                      data_envio=None, cliente_nome='Empresa Exemplo LTDA', vendedor_nome='Carteira A',
                      situacao='aberto', valor_total='123.45', nota_fiscal_id=0, id_pedido_origem=None)
        self.depara = {'Empresa Exemplo LTDA': {'codigo': '001'}}

    def build(self, pedidos=None, itens=None, notas=None, marcadores=None, depara=None):
        return coleta.montar_snapshot(pedidos or [self.p], itens or [], notas or [], marcadores or [],
              self.depara if depara is None else depara, {'u1': 'Unidade Exemplo'},
              generated_at=datetime.now(timezone.utc).isoformat(),
              coverage_start='2026-01-01', coverage_end=date.today().isoformat())

    def test_codigo_tiny_nao_substitui_identidade_bi(self):
        self.p['cliente_codigo'] = 'OUTRA-CARTEIRA'
        row = self.build()['pedidos'][0]
        self.assertEqual(row['cliente_id'], '001')
        self.assertNotIn('cliente_codigo', row)
        self.assertEqual(row['cliente_nome'], '')

    def test_normalizado_unico_e_ambiguo(self):
        self.p['cliente_nome'] = 'Empresa Exemplo'
        self.assertEqual(self.build()['pedidos'][0]['cliente_id'], '001')
        dp = {**self.depara, 'Empresa Exemplo ME': {'codigo': '002'}}
        self.assertEqual(self.build(depara=dp)['pedidos'][0]['cliente_id'], '')

    def test_sem_fuzzy_ou_valor_inventado(self):
        self.p['cliente_nome'] = 'Emp Exem'
        self.assertEqual(self.build()['pedidos'][0]['cliente_id'], '')
        self.p['valor_total'] = None
        with self.assertRaises(ValueError): self.build()

    def test_vinculo_reverso_encontra_nf_mesmo_sem_data(self):
        note = dict(id=999, unidade_negocio_id='u1', venda_id=100,
                    situacao_descricao='Autorizada', data_emissao=None)
        self.assertEqual(self.build(notas=[note])['pedidos'][0]['fiscal_status'], 'revisar')

    def test_nota_de_outra_unidade_nao_contamina(self):
        note = dict(id=999, unidade_negocio_id='u2', venda_id=100, situacao_descricao='Autorizada')
        self.assertEqual(self.build(notas=[note])['pedidos'][0]['fiscal_status'], 'sem_nf')

    def test_nf_pendente_nao_vira_faturado_ou_sem_nf(self):
        self.p['nota_fiscal_id'] = 999
        note = dict(id=999, unidade_negocio_id='u1', venda_id=None, situacao_descricao='Pendente')
        self.assertEqual(self.build(notas=[note])['pedidos'][0]['fiscal_status'], 'nf_pendente')

    def test_nf_pendente_com_outra_autorizada_exige_revisao(self):
        notes = [dict(id=i, unidade_negocio_id='u1', venda_id=100, situacao_descricao=s)
                 for i,s in [(999,'Pendente'),(998,'Autorizada')]]
        self.assertEqual(self.build(notas=notes)['pedidos'][0]['fiscal_status'], 'revisar')

    def test_id_nf_nao_encontrado_e_data_movimento_nao_sao_sem_nf(self):
        for field,value in [('nota_fiscal_id',999),('data_faturamento','2026-01-03'),('data_envio','2026-01-03')]:
            p=copy.deepcopy(self.p);p[field]=value
            self.assertEqual(self.build(pedidos=[p])['pedidos'][0]['fiscal_status'], 'revisar')

    def test_origem_transferencia_e_operacao_especial_excluem_soma(self):
        for label in ['multiempresa','GARATIA','BONIFICAÇÃO','Amostra']:
            marker=dict(id_unidade_negocio='u1',id_pedido=100,descricao=label)
            self.assertEqual(self.build(marcadores=[marker])['pedidos'][0]['fiscal_status'],'revisar')
        self.p['id_pedido_origem']=200
        self.assertEqual(self.build()['pedidos'][0]['fiscal_status'],'revisar')

    def test_itens_e_marcadores_nao_multiplicam_valor(self):
        items=[dict(unidade_negocio_id='u1',pedido_id=100,codigo=f'S{i}',descricao='Produto',quantidade=2) for i in range(3)]
        markers=[dict(id_unidade_negocio='u1',id_pedido=100,descricao='Conferido')]*4
        result=self.build(itens=items,marcadores=markers)
        self.assertEqual(len(result['pedidos']),1)
        self.assertEqual(result['pedidos'][0]['valor_total'],123.45)
        self.assertEqual(len(result['pedidos'][0]['itens']),3)

    def test_quantidade_ausente_nao_vira_zero(self):
        items=[dict(unidade_negocio_id='u1',pedido_id=100,codigo='S1',descricao='Produto',quantidade=None)]
        with self.assertRaises(ValueError): self.build(itens=items)

    def test_duplicidade_de_cabecalho_aborta(self):
        with self.assertRaises(ValueError): self.build(pedidos=[self.p,self.p])

    def test_sem_dados_pessoais_e_tecnicos_no_snapshot(self):
        self.p.update(cliente_cpf_cnpj='SEGREDO',cliente_email='SEGREDO',obs='SEGREDO',obs_interna='SEGREDO')
        self.assertNotIn('SEGREDO',json.dumps(self.build()))

    def test_gravacao_atomica_preserva_arquivo_em_erro(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'snapshot.json';original=self.build()
            coleta.salvar_atomico(original,target)
            before=target.read_bytes();new=copy.deepcopy(original);new['pedidos'][0]['valor_total']=400
            with patch.object(coleta.os,'replace',side_effect=OSError('Falha simulada')):
                with self.assertRaises(OSError): coleta.salvar_atomico(new,target)
            self.assertEqual(target.read_bytes(),before)
            self.assertEqual(list(Path(folder).glob('*.tmp')),[])

    def test_carteira_esvaziada_exige_conferencia_e_preserva_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'snapshot.json';original=self.build()
            coleta.salvar_atomico(original,target)
            before=target.read_bytes();empty={**original,'pedidos':[]}
            with self.assertRaises(ValueError):coleta.salvar_atomico(empty,target)
            self.assertEqual(target.read_bytes(),before)
            coleta.salvar_atomico(empty,target,aceitar_reducao=True)
            self.assertEqual(json.loads(target.read_text())['pedidos'],[])


class RotinaPedidosTests(unittest.TestCase):
    def executar_rotina(self, collector_rc):
        import silver_diaria as rotina
        commands, copied = [], []
        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            if any(str(arg).endswith('silver_pedidos_distribuicao.py') for arg in cmd):
                if isinstance(collector_rc, Exception):raise collector_rc
                return collector_rc, ''
            if 'get-url' in cmd:return 0,'https://example.invalid/repo.git'
            if 'commit' in cmd:return 1,'nothing to commit'
            return 0,''
        with patch.object(rotina,'run',side_effect=fake_run), patch.object(rotina,'log'), \
             patch.object(rotina,'limpar_clone',return_value=True), \
             patch.object(rotina.os.path,'exists',return_value=True), \
             patch.object(rotina.shutil,'copy2',side_effect=lambda src,dst:copied.append(Path(src).name)):
            self.assertEqual(rotina.main(),0)
        return commands,copied

    def test_falha_ou_timeout_nao_publica_snapshot_velho_como_novo(self):
        for error in (1,TimeoutError('simulado')):
            commands,copied=self.executar_rotina(error)
            self.assertIn('silver_distribuicao.json',copied)
            self.assertIn('silver_mes_vivo.json',copied)
            self.assertNotIn('silver_pedidos_distribuicao.json',copied)
            added=next(c for c in commands if 'add' in c)
            self.assertNotIn('silver_pedidos_distribuicao.json',added)

    def test_sucesso_prepara_somente_snapshot_comercial_separado(self):
        commands,copied=self.executar_rotina(0)
        self.assertEqual(set(copied),{'silver_distribuicao.json','silver_mes_vivo.json','silver_pedidos_distribuicao.json'})
        added=next(c for c in commands if 'add' in c)
        self.assertNotIn('garantias.json',added)
        self.assertNotIn('agenda_comercial.json',added)


if __name__=='__main__':unittest.main(verbosity=2)
