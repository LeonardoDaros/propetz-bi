"""Regressao do deploy: apenas repos/remotos temporarios locais, sem rede ou dados reais.

Executa o helper PowerShell sem -AtualizarAbc. Nunca chama deploy.bat nem usa o
Git do projeto real. Saida nao zero sinaliza falha, adequada a uma futura CI.
"""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


HELPER = Path(__file__).resolve().with_name("deploy_seguro.ps1")
GIT = shutil.which("git")
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


@unittest.skipUnless(GIT and POWERSHELL, "Git e PowerShell sao necessarios")
class SafeDeployTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="propetz-deploy-tests-")).resolve()
        self.remote = self.root / "remote.git"
        self.local = self.root / "local"
        # Nao herdar GIT_DIR/WORK_TREE/INDEX_FILE/config global ou hooks do usuario.
        self.env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        self.env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                         "GIT_TERMINAL_PROMPT": "0"})
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.root, "clone", str(self.remote), str(self.local))
        self.git(self.local, "config", "user.name", "Teste local")
        self.git(self.local, "config", "user.email", "teste@example.invalid")
        self.write("app.py", "initial = True\n")
        self.write("users.yaml", "users: {}\n")
        self.write("access_log.json", "[]\n")
        self.write("Relatorio Distribuidores Mensal.xlsx", "synthetic spreadsheet v1\n")
        self.write(".gitignore", "CREDENCIAIS-LOCAL.md\nBackups/\n")
        self.git(self.local, "add", ".")
        self.git(self.local, "commit", "-m", "Synthetic initial state")
        self.git(self.local, "push", "origin", "main")
        self.initial = self.git(self.remote, "rev-parse", "main").stdout.strip()

    def tearDown(self):
        # Remocao confinada a raiz temporaria criada neste teste.
        assert self.root.parent == Path(tempfile.gettempdir()).resolve()
        assert self.root.name.startswith("propetz-deploy-tests-")

        def clear_readonly(func, path, exc):
            if not isinstance(exc, PermissionError):
                raise exc
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)

        shutil.rmtree(self.root, onexc=clear_readonly)

    def git(self, repo, *args):
        return subprocess.run([GIT, "-C", str(repo), *args], env=self.env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", check=True, timeout=30)

    def write(self, name, content):
        target = self.local / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def deploy(self, expect_ok=False):
        result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                                 "-File", str(HELPER), "-RepositoryPath", str(self.local),
                                 "-GitExecutable", GIT], env=self.env,
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=60)
        if expect_ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPLOY CONFIRMADO", result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("DEPLOY CONFIRMADO", result.stdout)
        return result

    def remote_unchanged(self):
        self.assertEqual(self.initial, self.git(self.remote, "rev-parse", "main").stdout.strip())

    def remote_upload(self):
        other = self.root / "site"
        self.git(self.root, "clone", str(self.remote), str(other))
        self.git(other, "config", "user.name", "Site sintetico")
        self.git(other, "config", "user.email", "site@example.invalid")
        (other / "Relatorio Distribuidores Mensal.xlsx").write_text("upload synthetic v2\n", encoding="utf-8")
        self.git(other, "add", ".")
        self.git(other, "commit", "-m", "Synthetic site upload")
        self.git(other, "push", "origin", "main")
        return self.git(self.remote, "rev-parse", "main").stdout.strip()

    def test_publishes_only_manifest_and_verifies_sha(self):
        self.write("app.py", "changed = True\n")
        self.write("users.yaml", "synthetic local users change\n")
        self.write("access_log.json", '["synthetic local state"]\n')
        self.write("CREDENCIAIS-LOCAL.md", "synthetic local file\n")
        self.write("Analise_local.md", "not for publication\n")
        self.write("Backups/internal.xlsx", "synthetic internal file\n")
        self.write("teste_etapa1_fixture.py", "assert True\n")
        self.write("teste_etapa2_fixture.py", "assert True\n")
        self.write("agenda_comercial.py", "MODULE = 'agenda'\n")
        self.write("ui_propetz.py", "MODULE = 'visual'\n")
        self.write("ficha_cliente_dados.py", "MODULE = 'client_metrics'\n")
        self.write("ficha_cliente_ui.py", "MODULE = 'client_view'\n")
        self.write("teste_ficha_cliente_dados.py", "assert True\n")
        self.write("teste_ficha_cliente_interface.py", "assert True\n")
        self.write("painel_garantias.py", "MODULE = 'warranty_view'\n")
        self.write("garantia_analytics.py", "MODULE = 'warranty_metrics'\n")
        self.write("teste_painel_garantias.py", "assert True\n")
        self.write("exportacao_csv.py", "MODULE = 'safe_csv'\n")
        self.write("teste_exportacao_csv.py", "assert True\n")
        self.write("agenda_comercial.json", '{"clientes": {"ficticio": {}}}\n')
        self.write("garantias.json", '{"garantias": [{"id": "SYNTHETIC"}]}\n')
        self.write(".streamlit/secrets.toml", "# Synthetic local-only configuration\n")
        shutil.copy2(HELPER, self.local / HELPER.name)
        self.deploy(expect_ok=True)
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD").stdout,
                         self.git(self.remote, "rev-parse", "main").stdout)
        self.assertEqual(self.git(self.remote, "show", "main:users.yaml").stdout, "users: {}\n")
        self.assertEqual(self.git(self.remote, "show", "main:access_log.json").stdout, "[]\n")
        files = self.git(self.remote, "ls-tree", "-r", "--name-only", "main").stdout.splitlines()
        self.assertIn("teste_etapa1_fixture.py", files)
        for included in ("teste_etapa2_fixture.py", "agenda_comercial.py", "ui_propetz.py",
                         "ficha_cliente_dados.py", "ficha_cliente_ui.py",
                         "teste_ficha_cliente_dados.py", "teste_ficha_cliente_interface.py",
                         "painel_garantias.py", "garantia_analytics.py", "teste_painel_garantias.py",
                         "exportacao_csv.py", "teste_exportacao_csv.py"):
            self.assertIn(included, files)
        self.assertIn(HELPER.name, files)
        for excluded in ("CREDENCIAIS-LOCAL.md", "Analise_local.md", "Backups/internal.xlsx",
                         "agenda_comercial.json", "garantias.json", ".streamlit/secrets.toml"):
            self.assertNotIn(excluded, files)
            self.assertTrue((self.local / excluded).exists())

    def test_remote_upload_aborts_before_commit_and_preserves_both(self):
        self.write("app.py", "unsaved local work\n")
        uploaded = self.remote_upload()
        result = self.deploy()
        self.assertIn("atualizacoes ainda nao integradas", result.stdout)
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD").stdout.strip(), self.initial)
        self.assertEqual(self.git(self.remote, "rev-parse", "main").stdout.strip(), uploaded)
        self.assertEqual((self.local / "app.py").read_text(), "unsaved local work\n")
        self.assertEqual(self.git(self.local, "diff", "--cached", "--name-only").stdout, "")

    def test_divergent_commits_are_preserved(self):
        self.write("app.py", "local commit\n")
        self.git(self.local, "add", "app.py")
        self.git(self.local, "commit", "-m", "Local code")
        local_sha = self.git(self.local, "rev-parse", "HEAD").stdout.strip()
        uploaded = self.remote_upload()
        self.deploy()
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD").stdout.strip(), local_sha)
        self.assertEqual(self.git(self.remote, "rev-parse", "main").stdout.strip(), uploaded)

    def test_existing_staging_is_preserved(self):
        self.write("Analise_local.md", "synthetic staging\n")
        self.git(self.local, "add", "Analise_local.md")
        self.deploy()
        self.remote_unchanged()
        self.assertIn("Analise_local.md", self.git(self.local, "diff", "--cached", "--name-only").stdout)

    def test_commit_failure_never_pushes(self):
        hook = self.local / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        self.write("app.py", "new code\n")
        self.deploy()
        self.remote_unchanged()
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD").stdout.strip(), self.initial)
        self.assertIn("app.py", self.git(self.local, "diff", "--cached", "--name-only").stdout)

    def test_rejected_push_is_not_success(self):
        (self.remote / "hooks" / "pre-receive").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        self.write("app.py", "new code\n")
        self.deploy()
        self.remote_unchanged()
        self.assertNotEqual(self.git(self.local, "rev-parse", "HEAD").stdout.strip(), self.initial)
        # Nova tentativa publica o commit preservado, sem reescrever historico.
        (self.remote / "hooks" / "pre-receive").unlink()
        self.deploy(expect_ok=True)
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD").stdout,
                         self.git(self.remote, "rev-parse", "main").stdout)

    def test_remote_sha_changed_after_push_is_not_success(self):
        # Simula outra escrita no remoto entre a recepcao e a confirmacao.
        (self.remote / "hooks" / "post-receive").write_text(
            '#!/bin/sh\nwhile read old new ref; do git update-ref "$ref" "$old"; done\n',
            encoding="utf-8")
        self.write("app.py", "new code\n")
        result = self.deploy()
        self.assertIn("SHA remoto", result.stdout)
        self.remote_unchanged()

    def test_wrong_branch_is_preserved(self):
        self.git(self.local, "checkout", "-b", "draft")
        self.write("app.py", "draft changes\n")
        self.deploy()
        self.assertEqual(self.git(self.local, "branch", "--show-current").stdout.strip(), "draft")
        self.assertEqual((self.local / "app.py").read_text(), "draft changes\n")
        self.remote_unchanged()

    def test_pending_secret_then_deleted_still_aborts(self):
        self.write("internal.txt", "synthetic file must never publish\n")
        self.git(self.local, "add", "internal.txt")
        self.git(self.local, "commit", "-m", "Unwanted synthetic file")
        self.git(self.local, "rm", "internal.txt")
        self.git(self.local, "commit", "-m", "Remove synthetic file")
        result = self.deploy()
        self.assertIn("fora da lista", result.stdout)
        self.remote_unchanged()

    def test_index_lock_preserved(self):
        lock = self.local / ".git" / "index.lock"
        lock.write_text("synthetic lock\n", encoding="utf-8")
        self.deploy()
        self.assertEqual(lock.read_text(), "synthetic lock\n")
        self.remote_unchanged()

    def test_external_gitdir_pointer_preserved(self):
        separate = self.root / "separate-git"
        self.git(self.local, "init", "--separate-git-dir", str(separate))
        gitfile = self.local / ".git"
        pointer = gitfile.read_bytes()
        self.write("app.py", "new code\n")
        self.deploy(expect_ok=True)
        self.assertEqual(gitfile.read_bytes(), pointer)
        self.assertTrue(separate.is_dir())

    def test_no_changes_confirms_existing_sha(self):
        self.deploy(expect_ok=True)
        self.remote_unchanged()


if __name__ == "__main__":
    unittest.main(verbosity=2)
