# -*- coding: utf-8 -*-
"""Barreira de segurança da autenticação — regressão dos fixes de 2026-07-23.
Cobre: URL nunca loga; hashing scrypt + migração; comparação tempo constante;
rate limit por usuário/IP; timeout de sessão; escape de XSS."""
import warnings, io, os, sys, tempfile
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import app

falhas = 0
def chk(cond, desc):
    global falhas
    print(("OK   " if cond else "FALHA ") + desc)
    if not cond:
        falhas += 1

src = io.open(app.__file__, encoding="utf-8").read()

# ---- 1) login por URL continua morto ----
chk(not hasattr(app, "_auto_login_from_params"), "auto-login por URL removido")
app.st.session_state.clear(); app.st.query_params.clear()
app.st.query_params["u"] = "leonardo"; app.st.query_params["t"] = "ac0f014818d91747"
app._strip_stale_auth_params()
chk(not app.st.session_state.get("authenticated"), "token na URL nao autentica")

# ---- 2) hashing scrypt + sem sha256 puro no fluxo ----
h = app.hash_password("segredo123")
chk(h.startswith("scrypt$"), "hash_password gera scrypt (com salt)")
h2 = app.hash_password("segredo123")
chk(h != h2, "salt por chamada: mesmo texto gera hashes diferentes")
ok, legacy = app._verify_password("segredo123", h)
chk(ok and not legacy, "verifica scrypt correto")
chk(not app._verify_password("errado", h)[0], "rejeita senha errada no scrypt")

# ---- 6) comparacao em tempo constante ----
chk("hmac.compare_digest" in src, "usa hmac.compare_digest (timing-safe)")
chk('user["password"] == hash_password' not in src, "sem comparacao == de hash")

# ---- migracao: hash legado sha256 vira scrypt no login ----
tmp = tempfile.mkdtemp()
app.USERS_FILE = os.path.join(tmp, "users.yaml")
app._gh_token = lambda: None
import yaml
legado = app.hashlib.sha256("velha123".encode()).hexdigest()
yaml.dump({"users": {"teste": {"name": "T", "role": "vendedor",
          "vendor_filter": None, "password": legado}}},
          open(app.USERS_FILE, "w", encoding="utf-8"))
u = app.verify_login("teste", "velha123")
chk(u is not None, "login com hash legado (sha256) funciona")
novo = yaml.safe_load(open(app.USERS_FILE, encoding="utf-8"))["users"]["teste"]["password"]
chk(novo.startswith("scrypt$"), "hash legado foi MIGRADO para scrypt no login")
chk(app.verify_login("teste", "velha123") is not None, "apos migracao, login segue ok")
chk(app.verify_login("teste", "outra") is None, "apos migracao, senha errada rejeitada")

# ---- 5) rate limit: chaves por usuario e IP, e bloqueio ----
app.LOGIN_ATTEMPTS_FILE = os.path.join(tmp, "login_attempts.json")
app._bf_ultimo_push[0] = 9e18  # trava push assincrono durante o teste
for _ in range(app._BF_MAX):
    app.record_failed_attempt("alvo", ip="1.2.3.4")
blk, _ = app.check_rate_limit("alvo", ip="1.2.3.4")
chk(blk, "bloqueia o USUARIO apos _BF_MAX falhas")
# adivinhacao distribuida do MESMO IP: bloqueia ao atingir o limiar (alto) de IP
for i in range(app._BF_MAX_IP):
    app.record_failed_attempt(f"conta{i}", ip="9.9.9.9")
chk(app.check_rate_limit("conta_nova", ip="9.9.9.9")[0],
    "mesmo IP bloqueia adivinhacao distribuida ao atingir o limiar de IP")
chk("login_attempts.json" in app._STATE_FILES, "tentativas persistidas no estado (state branch)")
app.clear_failed_attempts("alvo", ip="1.2.3.4")
chk(not app.check_rate_limit("alvo", ip="1.2.3.4")[0], "clear libera o usuario")

# ---- 7) timeout de sessao ----
app.st.session_state.clear()
app._touch_session()
chk(not app._session_expired(), "sessao recem-criada nao expira")
app.st.session_state["_last_seen"] = app.datetime.now().timestamp() - (app._SESSION_INATIVIDADE + 10)
chk(app._session_expired(), "expira por inatividade")
app.st.session_state["_last_seen"] = app.datetime.now().timestamp()
app.st.session_state["_login_ts"] = app.datetime.now().timestamp() - (app._SESSION_MAX + 10)
chk(app._session_expired(), "expira por tempo maximo de vida")

# ---- robustez: hash corrompido/None NAO derruba (achado auditoria) ----
for veneno in ("senhac_com_acento_ç", "\U0001f511abc", "á"*64, "scrypt$16384$8", "", None):
    try:
        r = app._verify_password("x", veneno)
        chk(r == (False, False) or r[0] is False, f"hash corrompido nao crasha: {str(veneno)[:12]}")
    except Exception as e:
        chk(False, f"CRASHOU com {str(veneno)[:12]}: {e}")
chk(app._verify_password(None, "a"*64) == (False, False), "pwd None nao crasha")

# ---- 5b) limiar de IP mais alto (NAT do escritorio) + sem GitHub no caminho ----
app.LOGIN_ATTEMPTS_FILE = os.path.join(tmp, "la2.json")
app._bf_ultimo_push[0] = 9e18  # trava o push assincrono durante o teste
for i in range(6):
    app.record_failed_attempt(f"pessoa{i}", ip="200.1.1.1")  # 6 contas distintas, 1 IP
chk(not app.check_rate_limit("pessoa_nova", ip="200.1.1.1")[0],
    "6 erros de contas diferentes no MESMO IP nao travam o escritorio (limiar IP alto)")
chk("_gh_mutate_json" not in src.split("def record_failed_attempt")[1].split("def clear_failed")[0],
    "record_failed_attempt NAO faz escrita sincrona no GitHub (anti-DoS)")
chk(app._BF_MAX_IP > app._BF_MAX, "limiar por IP maior que por usuario")

# ---- 8) escape de XSS ----
chk(app.esc("<script>x</script>") == "&lt;script&gt;x&lt;/script&gt;", "esc() escapa HTML")
chk("&lt;b&gt;" in app.status_badge("<b>hack</b>"), "status_badge escapa status externo")
ins = app.insight_html("warning", "L", "vendedor <img src=x>", "acao")
chk("&lt;img" in ins, "insight_html escapa texto externo (nome de vendedor)")
chk("{esc(st.session_state['user_name'])}" in src, "nome do usuario escapado no cabecalho")
chk("{esc(months[0])}" in src, "rotulos de mes escapados no banner (achado auditoria)")

print("\n" + ("SEGURANCA OK — 8 frentes cobertas" if falhas == 0 else f"{falhas} FALHAS"))
