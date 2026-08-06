# -*- coding: utf-8 -*-
"""ROTINA HORÁRIA do banco silver — agendada no PC do Leonardo.

A cada rodada: (1) roda a sombra do churn (silver_churn_sombra.py), que gera o
silver_distribuicao.json (Fase 2: o app LÊ este json — última compra real);
(1b) roda o silver_mes_vivo.py (página "Mês ao Vivo": receita do mês corrente
+ metas), em MELHOR ESFORÇO — falha aqui não cancela o churn; (2) publica os
DOIS jsons num só commit no branch `state` pelo método seguro do projeto
(clone raso em %TEMP% — NUNCA git worktree, regra do CLAUDE.md); (3) registra
tudo em silver_diaria.log. DESLIGAR esta rotina congela o churn E o Mês ao
Vivo do app online.
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
LOG = os.path.join(BASE, "silver_diaria.log")
JSON_APP = os.path.join(BASE, "silver_distribuicao.json")
JSON_MV = os.path.join(BASE, "silver_mes_vivo.json")
# pasta de clone ÚNICA por execução (instâncias simultâneas não colidem);
# órfãs de execuções antigas são varridas no início, melhor esforço
CLONE_PREFIXO = os.path.join(os.environ.get("TEMP", "."), "_propetz_state_push")
CLONE = f"{CLONE_PREFIXO}_{os.getpid()}"
# identidade git EXPLÍCITA: o clone em %TEMP% não herda o config local do repo
# (auditoria 21/07: sem isso o commit morria mudo e o log mentia 'sucesso')
GIT_ID = ["-c", "user.name=Propetz BI (rotina diaria)",
          "-c", "user.email=leonardo@daroscorp.com.br"]


def log(msg):
    linha = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(linha)
    try:
        # rotação simples: acima de ~300 KB, mantém só a metade recente
        if os.path.exists(LOG) and os.path.getsize(LOG) > 300_000:
            with open(LOG, encoding="utf-8", errors="replace") as f:
                cauda = f.readlines()[-1500:]
            with open(LOG, "w", encoding="utf-8") as f:
                f.writelines(cauda)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def _apagar_dir(caminho):
    """Apaga diretório com .git (objetos somente-leitura no Windows)."""
    if not os.path.isdir(caminho):
        return True
    def _destrava(func, p, exc):
        try:
            os.chmod(p, 0o777)
            func(p)
        except OSError:
            pass
    try:
        shutil.rmtree(caminho, onexc=_destrava)
    except OSError:
        pass
    if os.path.isdir(caminho):
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", caminho],
                       capture_output=True, timeout=120)
    return not os.path.isdir(caminho)


def limpar_clone():
    """Apaga o clone desta execução + varre órfãos de execuções antigas."""
    import glob
    for orfao in glob.glob(CLONE_PREFIXO + "*"):
        if orfao != CLONE:
            _apagar_dir(orfao)  # melhor esforço
    return _apagar_dir(CLONE)


def run(cmd, cwd=None, timeout=600):
    # encoding explícito: o console Windows decodificaria em cp1252 e os acentos
    # da sombra estouravam o leitor de saída do subprocess
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    log("=== rotina silver: início ===")

    # 1. sombra (consulta o banco + gera relatório e json) — com RETRY:
    # às 07:30 o notebook pode ainda estar sem rede (aconteceu em 22/07)
    rc = 1
    for tentativa in (1, 2, 3):
        rc, out = run([PY, os.path.join(BASE, "silver_churn_sombra.py")],
                      cwd=BASE, timeout=900)
        if rc == 0:
            for linha in out.strip().splitlines()[-6:]:
                log(f"  sombra: {linha}")
            break
        log(f"sombra falhou (tentativa {tentativa}/3, rc={rc}): "
            f"{out.strip().splitlines()[-1][:160] if out.strip() else '?'}")
        if tentativa < 3:
            import time
            time.sleep(120)  # espera a rede/VPN subir
    if rc != 0 or not os.path.exists(JSON_APP):
        log("FALHA na sombra após 3 tentativas — publicação cancelada nesta rodada.")
        return 1

    # 1b. mês ao vivo (página do app) — MELHOR ESFORÇO de verdade: NENHUMA
    # exceção daqui (nem TimeoutExpired) pode cancelar a publicação do churn
    try:
        rc_mv, out_mv = run([PY, os.path.join(BASE, "silver_mes_vivo.py")],
                            cwd=BASE, timeout=900)
    except Exception as e:
        rc_mv, out_mv = 1, f"{type(e).__name__}: {e}"
    if rc_mv == 0:
        for linha in out_mv.strip().splitlines()[-1:]:
            log(f"  mes-vivo: {linha[:200]}")
    else:
        log(f"mes-vivo FALHOU (rc={rc_mv}) — publico só o churn nesta rodada: "
            f"{out_mv.strip().splitlines()[-1][:160] if out_mv.strip() else '?'}")

    # 2. publica no branch state (clone raso -> copia -> commit -> push c/ rebase)
    rc, remote = run(["git", "-C", BASE, "remote", "get-url", "origin"])
    remote = remote.strip()
    if rc != 0 or not remote:
        log("FALHA: remote origin não encontrado — json ficou só local.")
        return 1
    if not limpar_clone():
        log("FALHA: não consegui limpar o clone anterior em %TEMP% — tento amanhã.")
        return 1
    rc, out = run(["git", "clone", "--depth", "1", "--branch", "state", remote, CLONE],
                  timeout=300)
    if rc != 0:
        log(f"FALHA no clone do branch state: {out.strip()[:200]}")
        return 1
    shutil.copy2(JSON_APP, os.path.join(CLONE, "silver_distribuicao.json"))
    arquivos = ["silver_distribuicao.json"]
    if rc_mv == 0 and os.path.exists(JSON_MV):
        shutil.copy2(JSON_MV, os.path.join(CLONE, "silver_mes_vivo.json"))
        arquivos.append("silver_mes_vivo.json")
    rc, out = run(["git", "-C", CLONE, "add", *arquivos])
    if rc != 0:
        log(f"FALHA no git add (rc={rc}): {out.strip()[:200]}")
        limpar_clone()
        return 1
    rc, out = run(["git", "-C", CLONE, *GIT_ID, "commit", "-m",
                   f"Silver diária: {datetime.now():%Y-%m-%d %H:%M}"])
    if rc != 0:
        if "nothing to commit" in out.lower():
            log("sem mudança no json desde ontem — nada a publicar.")
            limpar_clone()
            return 0
        # auditoria 21/07: commit falhando MUDO (identidade ausente) fazia o
        # push vazio parecer sucesso — agora QUALQUER rc!=0 aqui é falha dura
        log(f"FALHA no git commit (rc={rc}): {out.strip()[:200]}")
        limpar_clone()
        return 1
    ok = False
    for tentativa in (1, 2):
        rc, out = run(["git", "-C", CLONE, "push", "origin", "state"], timeout=300)
        if rc == 0:
            ok = True
            break
        # o app pode ter gravado estado entre o clone e o push: rebase e repete
        log(f"push rejeitado (tentativa {tentativa}) — rebase e repito.")
        rc2, out2 = run(["git", "-C", CLONE, *GIT_ID, "pull", "--rebase",
                         "origin", "state"], timeout=300)
        if rc2 != 0:
            log(f"FALHA no rebase (rc={rc2}): {out2.strip()[:200]}")
            break
    if not ok:
        limpar_clone()
        log(f"FALHA no push: {out.strip()[:200]} — json ficou local, tento amanhã.")
        return 1
    # PROVA pós-push: o SHA remoto tem que ser o nosso HEAD (nunca mais
    # confiar em 'rc 0' de push — foi assim que o log mentiu 'sucesso')
    _, sha_local = run(["git", "-C", CLONE, "rev-parse", "HEAD"])
    rc, remoto_out = run(["git", "-C", CLONE, "ls-remote", "origin",
                          "refs/heads/state"], timeout=120)
    sha_remoto = remoto_out.split()[0] if rc == 0 and remoto_out.strip() else ""
    limpar_clone()
    if sha_local.strip() and sha_local.strip() == sha_remoto:
        log(f"publicado e CONFERIDO no branch state (sha {sha_remoto[:10]}).")
        log("=== rotina diária silver: FIM OK ===")
        return 0
    log(f"FALHA na conferência pós-push: local={sha_local.strip()[:10]} "
        f"remoto={sha_remoto[:10]} — investigar.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # nunca estourar sem registrar
        log(f"ERRO INESPERADO: {type(e).__name__}: {e}")
        sys.exit(1)
