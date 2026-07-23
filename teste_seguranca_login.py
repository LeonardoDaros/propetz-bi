# -*- coding: utf-8 -*-
"""Barreira de segurança: URL nunca autentica; só a sessão do servidor loga.
Regressão do fix de 2026-07-23 (remoção do login por ?u=&t=)."""
import warnings, io
warnings.filterwarnings("ignore")
import app

falhas = 0
def chk(cond, desc):
    global falhas
    print(("OK   " if cond else "FALHA ") + desc)
    if not cond:
        falhas += 1

# 1) o mecanismo inseguro NÃO existe mais no código
chk(not hasattr(app, "_auto_login_from_params"), "auto-login por URL removido")
chk(not hasattr(app, "_set_login_params"), "gravação de token na URL removida")
src = io.open(app.__file__, encoding="utf-8").read()
chk('hashlib.sha256(f"{u}' not in src and ":propetz\".encode()" not in src,
    "derivação de token por hash+pepper apagada do código")
chk("st.query_params[\"u\"]" not in src and "st.query_params['u']" not in src,
    "app não escreve mais usuário/token na URL")

# 2) params de URL (token forjado ou antigo) NÃO concedem sessão
app.st.session_state.clear()
app.st.query_params.clear()
app.st.query_params["u"] = "leonardo"
app.st.query_params["t"] = "ac0f014818d91747"   # token exposto no teste do Leonardo
app._strip_stale_auth_params()
chk(not app.st.session_state.get("authenticated"),
    "token exposto na URL NÃO autentica (sessão continua deslogada)")
chk("u" not in app.st.query_params and "t" not in app.st.query_params,
    "params de auth são apagados da URL (não ficam visíveis/logados)")

# 3) login de verdade continua funcionando e exige senha correta
app.st.session_state.clear()
u = app.verify_login("leonardo", "senha_errada_qualquer")
chk(u is None, "senha errada é rejeitada")
# (não testo a senha real aqui: o hash está no users.yaml, fora do teste)

print("\n" + ("SEGURANÇA OK — URL não loga, sessão exige senha"
              if falhas == 0 else f"{falhas} FALHAS"))
