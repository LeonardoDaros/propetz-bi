"""Contrato do catálogo na Bancada e na rotina, sem rede ou estado real."""
import copy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

import teste_etapa1_garantias as base


def catalogo():
    return {'schema_version': 1, 'fonte': 'silver.produto',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'produtos': [
                {'sku': 'PECA-110', 'nome': 'Motor exemplo 127V'},
                {'sku': 'PECA-220', 'nome': 'Motor exemplo 220V'}]}


class CatalogoNaBancadaTests(unittest.TestCase):
    def render(self, snapshot):
        record = base.caso(status='Em bancada', pecas=[
            {'sku': 'FORA-CATALOGO', 'nome': 'Peça histórica', 'qtd': 1, 'custo': 12.5}])
        with patch.dict(base.NS, {'load_catalogo_garantias': lambda: copy.deepcopy(snapshot)}):
            return base.render('garantia', [record])

    def test_peca_sem_venda_aparece_com_voltagens_separadas_e_preserva_legado(self):
        ui = self.render(catalogo())
        for slot in range(3):
            opts = ui.selectors[f'p{slot}_atv_G-1001']['options']
            self.assertIn('PECA-110 — Motor exemplo 127V', opts)
            self.assertIn('PECA-220 — Motor exemplo 220V', opts)
            self.assertIn('FORA-CATALOGO — Peça histórica', opts)
        self.assertIn('PECA-110 — Motor exemplo 127V', ui.selectors['gn_prod']['options'])

    def test_fonte_indisponivel_avisa_e_mantem_lista_legada(self):
        ui = self.render(None)
        self.assertTrue(any('Catálogo completo de peças indisponível' in m for m in ui.messages))
        self.assertIn('SKU-EXEMPLO — Produto fictício', ui.selectors['p0_atv_G-1001']['options'])

    def test_carga_antiga_fica_visivel_com_aviso(self):
        old = catalogo()
        old['generated_at'] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        ui = self.render(old)
        self.assertTrue(any('24 horas' in m for m in ui.messages))
        self.assertIn('PECA-110 — Motor exemplo 127V', ui.selectors['p0_atv_G-1001']['options'])


class PublicacaoCatalogoTests(unittest.TestCase):
    def executar(self, resultado):
        import silver_diaria as rotina
        commands, copied = [], []
        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            if any(str(arg).endswith('silver_catalogo_garantias.py') for arg in cmd):
                if isinstance(resultado, Exception):
                    raise resultado
                return resultado, ''
            if 'get-url' in cmd:
                return 0, 'https://example.invalid/repo.git'
            if 'commit' in cmd:
                return 1, 'nothing to commit'
            return 0, ''
        with patch.object(rotina, 'run', side_effect=fake_run), \
             patch.object(rotina, 'log'), patch.object(rotina, 'limpar_clone', return_value=True), \
             patch.object(rotina.os.path, 'exists', return_value=True), \
             patch.object(rotina.shutil, 'copy2', side_effect=lambda src, dst: copied.append(Path(src).name)):
            self.assertEqual(rotina.main(), 0)
        return next(c for c in commands if 'add' in c), copied

    def test_falha_catalogo_preserva_remoto_sem_impedir_pedidos_ou_faturamento(self):
        for failure in (1, TimeoutError('simulado')):
            with self.subTest(failure=type(failure).__name__):
                added, copied = self.executar(failure)
                self.assertNotIn('silver_catalogo_garantias.json', copied)
                self.assertNotIn('silver_catalogo_garantias.json', added)
                self.assertIn('silver_pedidos_distribuicao.json', copied)
                self.assertIn('silver_mes_vivo.json', copied)

    def test_sucesso_publica_catalogo_separado_sem_tocar_garantias(self):
        added, copied = self.executar(0)
        self.assertIn('silver_catalogo_garantias.json', copied)
        self.assertIn('silver_catalogo_garantias.json', added)
        self.assertNotIn('garantias.json', copied)
        self.assertNotIn('users.yaml', copied)


if __name__ == '__main__':
    unittest.main()
