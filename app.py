import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import openpyxl
import yaml
import os
import hashlib
import json
import base64
import threading
import requests
from datetime import datetime, timedelta

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="Propetz BI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# CUSTOM CSS
# ============================================================
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
    /* ---- PROPETZ LIGHT THEME (matching TV Dashboard) ---- */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif !important; }
    .block-container { padding-top: 0.5rem; padding-bottom: 1rem; max-width: 1400px; }

    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
    [data-testid="stSidebar"] [data-testid="stMarkdown"] { color: #1e293b; }

    /* Header banner */
    .propetz-header {
        background: linear-gradient(135deg, #1e3a5f, #2563eb);
        padding: 20px 28px 14px; color: #fff; border-radius: 0 0 16px 16px;
        margin: -1rem -1rem 1.5rem -1rem;
    }
    .propetz-header h1 { font-size: 26px; font-weight: 800; margin: 0; color: #fff; }
    .propetz-header .sub { font-size: 13px; opacity: 0.8; margin-top: 2px; }

    /* KPI cards */
    div[data-testid="stMetric"] {
        background: #ffffff; border: none; border-radius: 12px; padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08); border-left: 4px solid #3b82f6;
    }
    div[data-testid="stMetric"] label { color: #64748b !important; font-size: 12px; font-weight: 500; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #1e293b !important; font-size: 22px; font-weight: 700; }
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] { font-size: 11px; font-weight: 600; }

    /* Insight cards */
    .insight-card {
        background: #ffffff; border: none; border-radius: 12px;
        padding: 14px 16px; margin-bottom: 10px; border-left: 4px solid #3b82f6;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .insight-danger { border-left-color: #ef4444; }
    .insight-warning { border-left-color: #f59e0b; }
    .insight-success { border-left-color: #10b981; }
    .insight-type { font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #64748b; margin-bottom: 4px; font-weight: 700; }
    .insight-text { font-size: 13.5px; line-height: 1.5; color: #1e293b; }
    .insight-action { font-size: 12px; color: #3b82f6; margin-top: 6px; font-weight: 600; }

    /* Badges */
    .badge { padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; display: inline-block; }
    .badge-green { color: #10b981; background: rgba(16,185,129,0.12); }
    .badge-yellow { color: #f59e0b; background: rgba(245,158,11,0.12); }
    .badge-red { color: #ef4444; background: rgba(239,68,68,0.12); }
    .badge-blue { color: #3b82f6; background: rgba(59,130,246,0.12); }

    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        padding: 7px 18px; border-radius: 8px; font-size: 13px; font-weight: 600;
        color: #64748b; background: #f1f5f9; border: none;
    }
    .stTabs [aria-selected="true"] { background: #3b82f6 !important; color: #fff !important; }

    /* Dataframes */
    [data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }

    /* Expander */
    [data-testid="stExpander"] { background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; }

    /* Selectbox, multiselect */
    .stSelectbox > div > div, .stMultiSelect > div > div {
        background: #ffffff; border-color: #e2e8f0; border-radius: 8px;
    }

    /* Divider */
    hr { border-color: #e2e8f0 !important; }

    /* Headers */
    h1, h2, h3 { color: #1e3a5f !important; }

    /* Login */
    .login-box {
        max-width: 400px; margin: 100px auto; background: #ffffff;
        border: 1px solid #e2e8f0; border-radius: 16px; padding: 40px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .login-title { text-align: center; font-size: 28px; font-weight: 800; margin-bottom: 8px; color: #1e3a5f; }
    .login-sub { text-align: center; font-size: 14px; color: #64748b; margin-bottom: 24px; }

    /* Plotly chart containers */
    .stPlotlyChart { background: #ffffff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); padding: 8px; }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #f1f5f9; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# USER DATABASE (stored in YAML - editable)
# ============================================================
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.yaml")

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    # Default users
    return {
        "users": {
            "leonardo": {
                "name": "Leonardo Daros",
                "password": hash_password("propetz2026"),
                "role": "admin",
                "vendor_filter": None  # sees everything
            },
            "emanuel": {
                "name": "Emanuel",
                "password": hash_password("emanuel2026"),
                "role": "vendedor",
                "vendor_filter": "Emanuel Propetz Distribuição"
            },
            "yasmin": {
                "name": "Yasmin",
                "password": hash_password("yasmin2026"),
                "role": "vendedor",
                "vendor_filter": "Yasmin Propetz Distribuição"
            },
            "cristiane": {
                "name": "Cristiane",
                "password": hash_password("cristiane2026"),
                "role": "vendedor",
                "vendor_filter": "Cristiane La Maison Propetz"
            },
            "grasiele": {
                "name": "Grasiele",
                "password": hash_password("grasiele2026"),
                "role": "diretor",
                "vendor_filter": None
            }
        }
    }

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def save_users(users_data):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(users_data, f, default_flow_style=False, allow_unicode=True)
    _push_state_file("users.yaml")

def verify_login(username, password):
    users = load_users()
    # Normaliza: celular capitaliza a 1ª letra e pode incluir espaço no autocomplete
    user = users["users"].get(str(username).strip().lower())
    if user and user["password"] == hash_password(password):
        return user
    return None

# ============================================================
# BRUTE FORCE PROTECTION
# ============================================================
LOGIN_ATTEMPTS_FILE = os.path.join(os.path.dirname(__file__), "login_attempts.json")

def _load_login_attempts():
    if os.path.exists(LOGIN_ATTEMPTS_FILE):
        try:
            with open(LOGIN_ATTEMPTS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_login_attempts(data):
    with open(LOGIN_ATTEMPTS_FILE, 'w') as f:
        json.dump(data, f)

def check_rate_limit(username):
    """Returns (is_blocked, seconds_remaining). Blocks after 5 failed attempts for 5 minutes."""
    attempts = _load_login_attempts()
    key = username.lower().strip()
    if key not in attempts:
        return False, 0
    info = attempts[key]
    fail_count = info.get("count", 0)
    last_fail = info.get("last_fail", 0)
    now = datetime.now().timestamp()
    # Reset after 5 minutes
    if now - last_fail > 300:
        del attempts[key]
        _save_login_attempts(attempts)
        return False, 0
    if fail_count >= 5:
        remaining = int(300 - (now - last_fail))
        return True, max(remaining, 0)
    return False, 0

def record_failed_attempt(username):
    attempts = _load_login_attempts()
    key = username.lower().strip()
    now = datetime.now().timestamp()
    if key not in attempts:
        attempts[key] = {"count": 1, "last_fail": now}
    else:
        # Reset if last attempt was over 5 min ago
        if now - attempts[key].get("last_fail", 0) > 300:
            attempts[key] = {"count": 1, "last_fail": now}
        else:
            attempts[key]["count"] = attempts[key].get("count", 0) + 1
            attempts[key]["last_fail"] = now
    _save_login_attempts(attempts)

def clear_failed_attempts(username):
    attempts = _load_login_attempts()
    key = username.lower().strip()
    if key in attempts:
        del attempts[key]
        _save_login_attempts(attempts)

# ============================================================
# ACCESS LOG (tracks who, when, where, duration)
# ============================================================
ACCESS_LOG_FILE = os.path.join(os.path.dirname(__file__), "access_log.json")

def _load_access_log():
    if os.path.exists(ACCESS_LOG_FILE):
        try:
            with open(ACCESS_LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def _save_access_log(log):
    # Keep last 5000 entries to avoid file bloat
    log = log[-5000:]
    with open(ACCESS_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    _push_state_file("access_log.json")

def log_access(username, user_name, action="login"):
    """Log a user access event."""
    log = _load_access_log()
    log.append({
        "user": username,
        "name": user_name,
        "action": action,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
    })
    _save_access_log(log)

def log_page_view(username, page_name):
    """Log a page view event."""
    log = _load_access_log()
    log.append({
        "user": username,
        "name": st.session_state.get("user_name", username),
        "action": "page_view",
        "page": page_name,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
    })
    _save_access_log(log)

def has_full_data_access():
    """Returns True for admin and diretor roles (see all data, no vendor filter)."""
    return st.session_state.get('role') in ('admin', 'diretor')

def can_approve_inactivations():
    """Somente admin aprova/inativa/reativa direto. Diretor e vendedor SOLICITAM
    (a diretora conhece a carteira de todos, então sugere; o admin decide)."""
    return st.session_state.get('role') == 'admin'

# ============================================================
# INACTIVE CLIENTS DATABASE (stored in JSON - persists across sessions)
# ============================================================
INACTIVE_FILE = os.path.join(os.path.dirname(__file__), "inactive_clients.json")

def load_inactive_clients():
    """Load set of inactive client IDs from JSON file."""
    if os.path.exists(INACTIVE_FILE):
        try:
            with open(INACTIVE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get("inactive_ids", []))
        except Exception:
            return set()
    return set()

def save_inactive_clients(inactive_set):
    """Save set of inactive client IDs to JSON file."""
    with open(INACTIVE_FILE, 'w', encoding='utf-8') as f:
        json.dump({"inactive_ids": sorted(list(inactive_set))}, f, ensure_ascii=False, indent=2)
    _push_state_file("inactive_clients.json")
    return None

# ============================================================
# SOLICITAÇÕES DE INATIVAÇÃO (vendedor solicita → admin aprova)
# ============================================================
INACTIVE_REQUESTS_FILE = os.path.join(os.path.dirname(__file__), "inactive_requests.json")

def load_inactive_requests():
    """Lista de solicitações de inativação (pendentes e decididas)."""
    if os.path.exists(INACTIVE_REQUESTS_FILE):
        try:
            with open(INACTIVE_REQUESTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get("requests", [])
        except Exception:
            return []
    return []

def save_inactive_requests(reqs):
    with open(INACTIVE_REQUESTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({"requests": reqs[-500:]}, f, ensure_ascii=False, indent=1)
    _push_state_file("inactive_requests.json")

def add_inactivation_request(client_id, client_name, vendor):
    """Registra uma solicitação pendente. Retorna False se já existe pendente."""
    reqs = load_inactive_requests()
    cid = str(client_id).strip()
    for r in reqs:
        if r.get("client_id") == cid and r.get("status") == "pendente":
            return False
    reqs.append({
        "client_id": cid,
        "client_name": str(client_name),
        "vendor": str(vendor or ""),
        "requested_by": st.session_state.get("username", ""),
        "requested_by_name": st.session_state.get("user_name", ""),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "pendente",
    })
    save_inactive_requests(reqs)
    return True

def pending_inactivation_requests():
    return [r for r in load_inactive_requests() if r.get("status") == "pendente"]

# ============================================================
# PERSISTÊNCIA REMOTA (GitHub) — o disco do Streamlit Cloud é
# temporário: tudo que não está no repositório some quando o
# container reinicia. Arquivos de ESTADO (usuários, inativados,
# log de acesso) são salvos no branch 'state' do repo via API;
# a planilha enviada pelo Admin é commitada no branch 'main'.
# Requer GITHUB_TOKEN nos secrets do Streamlit Cloud. Sem token,
# tudo continua funcionando apenas localmente (sem persistência).
# ============================================================
_GH_API = "https://api.github.com"
_GH_REPO = "LeonardoDaros/propetz-bi"
_GH_STATE_BRANCH = "state"
_STATE_FILES = ["users.yaml", "inactive_clients.json", "access_log.json", "inactive_requests.json"]
_GH_WRITE_LOCK = threading.Lock()  # serializa escritas de estado: evita corrida read-SHA/PUT entre threads

def _gh_token():
    """Lê o GITHUB_TOKEN dos secrets, limpando espaços e aspas acidentais
    (erro de colagem comum). Token real não tem aspas/espaços, então isso é
    seguro e evita 401 por causa de um caractere sobrando."""
    try:
        raw = st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        return None
    if not raw:
        return None
    t = str(raw).strip().strip('"').strip("'").strip()
    return t or None

def _gh_headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

def _gh_get_file(path, branch, token=None):
    """Lê um arquivo do repo. Retorna (bytes, sha) ou (None, None)."""
    token = token or _gh_token()
    if not token:
        return None, None
    try:
        r = requests.get(f"{_GH_API}/repos/{_GH_REPO}/contents/{path}",
                         params={"ref": branch}, headers=_gh_headers(token), timeout=15)
        if r.status_code == 200:
            data = r.json()
            return base64.b64decode(data["content"]), data["sha"]
    except Exception:
        pass
    return None, None

def _gh_ensure_state_branch(token=None):
    """Cria o branch 'state' a partir do main, se ainda não existir."""
    token = token or _gh_token()
    if not token:
        return False
    try:
        r = requests.get(f"{_GH_API}/repos/{_GH_REPO}/git/ref/heads/{_GH_STATE_BRANCH}",
                         headers=_gh_headers(token), timeout=15)
        if r.status_code == 200:
            return True
        r_main = requests.get(f"{_GH_API}/repos/{_GH_REPO}/git/ref/heads/main",
                              headers=_gh_headers(token), timeout=15)
        if r_main.status_code != 200:
            return False
        sha = r_main.json()["object"]["sha"]
        r_new = requests.post(f"{_GH_API}/repos/{_GH_REPO}/git/refs",
                              json={"ref": f"refs/heads/{_GH_STATE_BRANCH}", "sha": sha},
                              headers=_gh_headers(token), timeout=15)
        return r_new.status_code in (200, 201)
    except Exception:
        return False

def _gh_put_file(path, content_bytes, message, branch, token=None):
    """Cria/atualiza um arquivo no repo. Retorna True se salvou."""
    token = token or _gh_token()
    if not token:
        return False
    try:
        if branch == _GH_STATE_BRANCH and not _gh_ensure_state_branch(token=token):
            return False
        _, sha = _gh_get_file(path, branch, token=token)
        payload = {"message": message,
                   "content": base64.b64encode(content_bytes).decode(),
                   "branch": branch}
        if sha:
            payload["sha"] = sha
        r = requests.put(f"{_GH_API}/repos/{_GH_REPO}/contents/{path}",
                         json=payload, headers=_gh_headers(token), timeout=60)
        return r.status_code in (200, 201)
    except Exception:
        return False

def _push_state_file(filename):
    """Envia um arquivo de estado para o branch 'state' em segundo plano
    (thread) para não travar a interface. Melhor esforço: falha silenciosa.
    O token é capturado AQUI (thread principal) e passado para a thread —
    ler st.secrets de dentro da thread pode falhar fora do contexto Streamlit."""
    token = _gh_token()
    if not token:
        return
    local = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(local):
        return
    with open(local, "rb") as f:
        content = f.read()

    def _send():
        # Lock serializa as escritas: sem ele, dois logins simultâneos podem ler o
        # mesmo SHA e a 2ª gravação é rejeitada (409) e perdida em silêncio.
        with _GH_WRITE_LOCK:
            _gh_put_file(filename, content, f"Estado: {filename}", _GH_STATE_BRANCH, token=token)

    threading.Thread(target=_send, daemon=True).start()

def _gh_diagnose():
    """Diagnóstico SÍNCRONO da persistência. Retorna lista de
    (ok: bool, título: str, detalhe: str) para exibir na página Admin.
    Para no primeiro erro fatal — o último item indica onde quebrou."""
    out = []
    # 1) Ler secrets
    try:
        raw = st.secrets.get("GITHUB_TOKEN", None)
    except Exception as e:
        out.append((False, "Ler o campo Secrets",
                    f"Falhou ao ler os secrets ({e}). Quase sempre é erro de formato (TOML): "
                    "use aspas RETAS (\") e confira se não há outra linha quebrada no campo."))
        return out
    if not raw:
        out.append((False, "Token presente nos Secrets",
                    "GITHUB_TOKEN não foi encontrado. Confira: o nome é exatamente GITHUB_TOKEN; "
                    "o valor está entre aspas retas (\"); e nenhuma outra linha do campo Secrets "
                    "tem erro de formato (um erro em qualquer linha derruba TODOS os secrets)."))
        return out
    token = _gh_token()  # versão limpa (sem aspas/espaços)
    raw_str = str(raw)
    avisos = []
    if raw_str != raw_str.strip():
        avisos.append("tinha espaços/quebras de linha sobrando (removidos)")
    if raw_str.strip() != token:
        avisos.append("tinha aspas dentro do valor (removidas)")
    forma = "ghp_/github_pat_" if token.startswith(("ghp_", "github_pat_")) else f"'{token[:4]}…'"
    out.append((True, "Token presente",
                f"{len(token)} caracteres, formato {forma}." +
                (" ⚠️ Corrigido: " + "; ".join(avisos) if avisos else "")))
    # 2) Token válido?
    try:
        r = requests.get(f"{_GH_API}/user", headers=_gh_headers(token), timeout=15)
    except Exception as e:
        out.append((False, "Conexão com o GitHub", f"Não consegui falar com a API do GitHub: {e}"))
        return out
    if r.status_code == 401:
        out.append((False, "Token válido",
                    "GitHub recusou (401): token inválido, expirado ou copiado pela metade. "
                    "Gere um novo em github.com/settings/tokens e cole de novo."))
        return out
    if r.status_code != 200:
        out.append((False, "Token válido", f"Resposta inesperada {r.status_code}: {r.text[:120]}"))
        return out
    out.append((True, "Token válido", f"Autenticado como '{r.json().get('login', '?')}'."))
    # 3) Acesso ao repositório
    r = requests.get(f"{_GH_API}/repos/{_GH_REPO}", headers=_gh_headers(token), timeout=15)
    if r.status_code == 404:
        out.append((False, "Acesso ao repositório",
                    f"{_GH_REPO} não encontrado por este token. Em token clássico, marque o escopo "
                    "'repo'. Em token fine-grained, dê acesso a ESTE repositório com permissão "
                    "Contents: Read and write."))
        return out
    if r.status_code == 403:
        out.append((False, "Acesso ao repositório", "Proibido (403): falta o escopo 'repo' no token."))
        return out
    if r.status_code != 200:
        out.append((False, "Acesso ao repositório", f"Resposta {r.status_code}: {r.text[:120]}"))
        return out
    out.append((True, "Acesso ao repositório", f"{_GH_REPO} acessível."))
    # 4) Branch 'state'
    ok_branch = _gh_ensure_state_branch(token=token)
    out.append((ok_branch, "Branch 'state'",
                "Pronto." if ok_branch else "Não foi possível criar/verificar o branch 'state'."))
    if not ok_branch:
        return out
    # 5) Escrita real no branch 'state' (MESMO caminho do salvamento de inativações/
    #    usuários/log). Captura o status HTTP para dizer a causa exata se falhar.
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        _, sha = _gh_get_file("_diagnostico.txt", _GH_STATE_BRANCH, token=token)
        payload = {"message": "Teste de persistência",
                   "content": base64.b64encode(f"teste de escrita {stamp}".encode()).decode(),
                   "branch": _GH_STATE_BRANCH}
        if sha:
            payload["sha"] = sha
        rw = requests.put(f"{_GH_API}/repos/{_GH_REPO}/contents/_diagnostico.txt",
                          json=payload, headers=_gh_headers(token), timeout=30)
        if rw.status_code in (200, 201):
            out.append((True, "Escrita de teste (branch 'state')",
                        "Gravado com sucesso. ✅ A persistência de inativações, usuários e log "
                        "de acesso está FUNCIONANDO. (A planilha é salva no branch 'main' com o "
                        "mesmo token e deve funcionar igual.)"))
        else:
            out.append((False, "Escrita de teste (branch 'state')",
                        f"O token é válido e enxerga o repo, mas a GRAVAÇÃO falhou: "
                        f"HTTP {rw.status_code} — {rw.text[:160]}"))
    except Exception as e:
        out.append((False, "Escrita de teste (branch 'state')", f"Falha na gravação: {e}"))
    return out

@st.cache_resource
def _sync_state_from_github():
    """Roda 1x por processo (boot do container): restaura os arquivos de
    estado a partir do branch 'state', se existirem lá."""
    for filename in _STATE_FILES:
        content, _ = _gh_get_file(filename, _GH_STATE_BRANCH)
        if content:
            try:
                with open(os.path.join(os.path.dirname(__file__), filename), "wb") as f:
                    f.write(content)
            except Exception:
                pass
    return True

# ============================================================
# SESSION PERSISTENCE (via query params — native Streamlit, no extra libs)
# ============================================================
def _auto_login_from_params():
    """Try to restore session from URL query params. Returns True if restored."""
    try:
        u = st.query_params.get("u", "")
        t = st.query_params.get("t", "")
        if not u or not t:
            return False
        # Validate token
        users = load_users()
        user = users["users"].get(u)
        if not user:
            return False
        expected_token = hashlib.sha256(f"{u}:{user['password']}:propetz".encode()).hexdigest()[:16]
        if t != expected_token:
            return False
        st.session_state["authenticated"] = True
        st.session_state["username"] = u
        st.session_state["user_name"] = user["name"]
        st.session_state["role"] = user["role"]
        st.session_state["vendor_filter"] = user.get("vendor_filter")
        return True
    except Exception:
        return False

def _set_login_params(username, user):
    """Save login to URL query params so it survives page refresh."""
    token = hashlib.sha256(f"{username}:{user['password']}:propetz".encode()).hexdigest()[:16]
    st.query_params["u"] = username
    st.query_params["t"] = token

def _clear_login_params():
    """Clear login params from URL."""
    try:
        st.query_params.clear()
    except Exception:
        pass

# ============================================================
# AUTHENTICATION
# ============================================================
def login_page():
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">Propetz BI</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-sub">Dashboard Comercial</div>', unsafe_allow_html=True)

    # st.form: digitar + clicar Entrar (ou pressionar Enter) vira UMA ação só.
    # Sem o form, o 1º clique apenas confirmava o campo de senha e o usuário
    # achava que o login não funcionava.
    with st.form("login_form"):
        username = st.text_input("Usuário", key="login_user")
        password = st.text_input("Senha", type="password", key="login_pass")
        submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")

    if submitted:
        username = str(username).strip().lower()
        if not username or not password:
            st.error("Preencha usuário e senha.")
        else:
            # Check rate limit (brute force protection)
            is_blocked, seconds_left = check_rate_limit(username)
            if is_blocked:
                minutes = seconds_left // 60
                secs = seconds_left % 60
                st.error(f"🔒 Conta temporariamente bloqueada. Muitas tentativas incorretas. Tente novamente em {minutes}m{secs}s.")
            else:
                user = verify_login(username, password)
                if user:
                    clear_failed_attempts(username)
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = username
                    st.session_state["user_name"] = user["name"]
                    st.session_state["role"] = user["role"]
                    st.session_state["vendor_filter"] = user.get("vendor_filter")
                    _set_login_params(username, user)
                    log_access(username, user["name"], "login")
                    st.rerun()
                else:
                    record_failed_attempt(username)
                    attempts = _load_login_attempts()
                    key = username.lower().strip()
                    remaining = 5 - attempts.get(key, {}).get("count", 0)
                    if remaining > 0:
                        st.error(f"Usuário ou senha incorretos. ({remaining} tentativas restantes)")
                    else:
                        st.error("🔒 Conta bloqueada por 5 minutos após muitas tentativas incorretas.")

    st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# DATA LOADING
# ============================================================
@st.cache_data(ttl=3600)
def load_data():
    """Load and process data from the Excel file."""
    # Try to find the Excel file
    # Search for any .xlsx file in the app directory
    app_dir = os.path.dirname(__file__)
    possible_names = [
        "RELATORIOS ESTADO-CLIENTES - ATUALIZADO.xlsx",
        "Relatorio Distribuidores Mensal.xlsx",
    ]
    possible_paths = []
    for name in possible_names:
        possible_paths.append(os.path.join(app_dir, name))
        possible_paths.append(os.path.join(app_dir, "..", name))

    # Also search for any xlsx in app_dir
    try:
        for f in os.listdir(app_dir):
            if f.endswith('.xlsx') and not f.startswith('~'):
                possible_paths.append(os.path.join(app_dir, f))
    except:
        pass

    # Usa o primeiro candidato que realmente é a planilha-fonte (tem a aba 'IA');
    # evita quebrar se outro .xlsx qualquer estiver na pasta.
    xlsx_path = None
    for p in possible_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            try:
                wb_test = openpyxl.load_workbook(p, read_only=True)
                has_ia = 'IA' in wb_test.sheetnames
                wb_test.close()
            except Exception:
                has_ia = False
            if has_ia:
                xlsx_path = p
                break

    if not xlsx_path:
        st.error("Arquivo Excel não encontrado. Faça upload na barra lateral.")
        return None, None, None, None, None, None

    return process_excel(xlsx_path)

def _handle_planilha_upload(uploaded):
    """Salva a planilha enviada localmente e tenta commitá-la no branch main
    do GitHub (persistência real — sobrevive a reinícios do Streamlit Cloud).
    Retorna True se o commit remoto funcionou."""
    data = bytes(uploaded.getbuffer())
    app_dir = os.path.dirname(__file__)
    with open(os.path.join(app_dir, "Relatorio Distribuidores Mensal.xlsx"), "wb") as f:
        f.write(data)
    # Remove o nome antigo para não sombrear a planilha nova na ordem de busca
    old = os.path.join(app_dir, "RELATORIOS ESTADO-CLIENTES - ATUALIZADO.xlsx")
    try:
        if os.path.exists(old):
            os.remove(old)
    except Exception:
        pass
    pushed = _gh_put_file("Relatorio Distribuidores Mensal.xlsx", data,
                          "Atualização da planilha via app", "main")
    st.cache_data.clear()
    return pushed

# ============================================================
# CURVA ABC POR VALOR — abc_valor.json traz o faturamento por SKU do canal
# Distribuição (últimos 12 meses, extraído da Base Mãe pelo script
# atualizar_abc_valor.py, que o deploy.bat roda automaticamente).
# ============================================================
ABC_VALOR_FILE = os.path.join(os.path.dirname(__file__), "abc_valor.json")

def load_abc_valor():
    """Retorna o dict do abc_valor.json ou None se não existir/estiver inválido."""
    if os.path.exists(ABC_VALOR_FILE):
        try:
            with open(ABC_VALOR_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get("faturamento"):
                return data
        except Exception:
            pass
    return None

def apply_abc_by_value(products):
    """Recalcula a curva ABC dos produtos por FATURAMENTO (Pareto: A = 80%
    acumulado, B = até 95%, C = resto). Produtos sem venda no período = C.
    Se o abc_valor.json não existir, mantém a curva original da planilha."""
    abc_data = load_abc_valor()
    if not abc_data:
        for p in products:
            p['valor_12m'] = 0
            p['qty_12m'] = 0
        return products
    fat = abc_data["faturamento"]
    qts = abc_data.get("quantidade", {})
    for p in products:
        try:
            p['valor_12m'] = float(fat.get(p['code'], 0))
            p['qty_12m'] = float(qts.get(p['code'], 0))
        except Exception:
            p['valor_12m'] = 0
            p['qty_12m'] = 0
    total_val = sum(p['valor_12m'] for p in products)
    if total_val <= 0:
        return products
    cum = 0
    for p in sorted(products, key=lambda x: -x['valor_12m']):
        if p['valor_12m'] <= 0:
            p['abc'] = 'C'
            continue
        cum += p['valor_12m']
        p['abc'] = 'A' if cum <= 0.80 * total_val else ('B' if cum <= 0.95 * total_val else 'C')
    return products

# Mapeamento de vendedores (unificação de carteiras)
VENDOR_MERGE = {
    "Ellen Propetz Distribuição": "Emanuel Propetz Distribuição",
}

def normalize_vendor(name):
    """Normaliza nome do vendedor aplicando mapeamento de carteiras."""
    if not name:
        return ''
    name = str(name).strip()
    return VENDOR_MERGE.get(name, name)

def process_excel(xlsx_path):
    """Process the Excel file and return structured data."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)

    # ---- MONTH LABELS from IA sheet ----
    ws_ia = wb['IA']
    month_labels = []
    for c in range(9, 73):
        v = ws_ia.cell(3, c).value
        if v:
            month_labels.append(str(v))
        else:
            break

    # Trim to actual data (find last month with data)
    valid_states = {'SP','PR','SC','MG','RS','RJ','CE','GO','ES','DF','BA','PB','RN','PE','MT','MS','RO','EX','PA','SE','MA','AM','PI','AP','AL','TO','RR','AC'}

    # ---- CLIENTS from IA sheet ----
    clients = []
    for r in range(4, ws_ia.max_row + 1):
        name = ws_ia.cell(r, 4).value
        state = ws_ia.cell(r, 5).value
        client_id = ws_ia.cell(r, 6).value
        vendor = ws_ia.cell(r, 7).value
        status = ws_ia.cell(r, 8).value

        if not name or not state or str(state).strip() not in valid_states:
            continue

        monthly = []
        for c in range(9, 9 + len(month_labels)):
            v = ws_ia.cell(r, c).value
            try:
                monthly.append(round(float(v), 2) if v else 0)
            except:
                monthly.append(0)

        status_str = str(status).strip().lower() if status else ''
        if 'inadimplente' in status_str:
            norm_status = 'Inadimplente'
        elif 'ativo' in status_str and 'ina' not in status_str:
            norm_status = 'Ativo'
        elif 'inativo' in status_str or 'ina' in status_str:
            norm_status = 'Inativo'
        elif 'permuta' in status_str:
            norm_status = 'Permuta'
        else:
            norm_status = status_str.title() if status_str else 'Desconhecido'

        clients.append({
            'name': str(name).strip(),
            'state': str(state).strip(),
            'id': str(client_id).strip() if client_id else '',
            'vendor': normalize_vendor(vendor),
            'status': norm_status,
            'monthly': monthly
        })

    # ---- ANALISES (optional – may not exist in lighter spreadsheets) ----
    analises = {}
    if 'Analises' in wb.sheetnames:
        ws_an = wb['Analises']
        for r in range(4, ws_an.max_row + 1):
            name = ws_an.cell(r, 3).value
            if not name:
                continue
            name = str(name).strip()
            credit = ws_an.cell(r, 7).value
            try:
                credit = float(credit) if credit else 0
            except:
                credit = 0

            totals = {}
            for idx, year in enumerate(['2021','2022','2023','2024','2025','2026']):
                v = ws_an.cell(r, 10 + idx).value
                try:
                    totals[year] = round(float(v), 2) if v else 0
                except:
                    totals[year] = 0

            mb = {}
            for idx, year in enumerate(['2021','2022','2023','2024','2025']):
                v = ws_an.cell(r, 17 + idx).value
                try:
                    mb[year] = int(v) if v else 0
                except:
                    mb[year] = 0

            am = {}
            for idx, year in enumerate(['2021','2022','2023','2024','2025']):
                v = ws_an.cell(r, 22 + idx).value
                try:
                    am[year] = round(float(v), 2) if v else 0
                except:
                    am[year] = 0

            analises[name] = {'credit': credit, 'totals': totals, 'months_bought': mb, 'avg_month': am}

    # ---- RECUPERAÇÃO (optional – may not exist in lighter spreadsheets) ----
    recuperacao = {}
    if 'Recuperação' in wb.sheetnames:
        ws_rec = wb['Recuperação']
        for r in range(5, ws_rec.max_row + 1):
            name = ws_rec.cell(r, 4).value
            if not name:
                continue
            name = str(name).strip()
            rec = ws_rec.cell(r, 9).value
            atencao = ws_rec.cell(r, 10).value
            if rec and str(rec).strip():
                recuperacao[name] = 'Recuperação'
            elif atencao and str(atencao).strip():
                recuperacao[name] = 'Atenção'
            else:
                recuperacao[name] = 'Saudável'

    # ---- PRODUTOS ABC (optional) ----
    products = []
    if 'Dados Demanda' in wb.sheetnames:
        ws_dem = wb['Dados Demanda']
        for r in range(6, ws_dem.max_row + 1):
            cod = ws_dem.cell(r, 3).value
            name = ws_dem.cell(r, 4).value
            cat = ws_dem.cell(r, 5).value
            total = ws_dem.cell(r, 30).value
            abc = ws_dem.cell(r, 32).value
            if not cod:
                continue
            try:
                total_val = int(float(total)) if total else 0
            except:
                total_val = 0
            cat_str = str(cat).strip() if cat else ''
            if cat_str.isdigit():
                cat_str = ''  # planilha às vezes traz o NCM no lugar da categoria
            products.append({
                'code': str(cod).strip(),
                'name': str(name).strip() if name else '',
                'category': cat_str,
                'total_qty': total_val,
                'abc': str(abc).strip() if abc else 'C'
            })
        products.sort(key=lambda x: -x['total_qty'])
        # Curva por VALOR substitui a curva por quantidade vinda da planilha
        products = apply_abc_by_value(products)

    # ---- CLIENT × PRODUCT DATA (Base de DadosProdutos, RIGHT SIDE cols 31+) ----
    client_products = []
    if 'Base de DadosProdutos' in wb.sheetnames:
        ws_bp = wb['Base de DadosProdutos']
        # Right side: C32=product_name, C34=product_code, C35=total_qty, C37=client_name, C38=client_code
        for r in range(5, ws_bp.max_row + 1):
            product_name = ws_bp.cell(r, 32).value
            product_code = ws_bp.cell(r, 34).value
            client_name_bp = ws_bp.cell(r, 37).value
            client_code_bp = ws_bp.cell(r, 38).value
            if not client_name_bp or not product_code:
                continue
            raw_qty = ws_bp.cell(r, 35).value
            try:
                total_qty = int(float(raw_qty)) if raw_qty else 0
            except:
                total_qty = 0
            if total_qty > 0:
                client_products.append({
                    'client_id': str(client_code_bp).strip() if client_code_bp else '',
                    'client_name': str(client_name_bp).strip(),
                    'product_code': str(product_code).strip(),
                    'product_name': str(product_name).strip() if product_name else '',
                    'total_qty': total_qty
                })
    df_client_products = pd.DataFrame(client_products) if client_products else pd.DataFrame()

    # ---- TRIM MONTHS TO ACTUAL DATA (must happen BEFORE risk calc) ----
    last_data_idx = 0
    for mi in range(len(month_labels)-1, -1, -1):
        total = sum(c['monthly'][mi] for c in clients)
        if total > 0:
            last_data_idx = mi
            break

    month_labels = month_labels[:last_data_idx+1]
    for c in clients:
        c['monthly'] = c['monthly'][:last_data_idx+1]

    # ---- ENRICH CLIENTS ----
    year_ranges = {'2021':(0,4),'2022':(4,16),'2023':(16,28),'2024':(28,40),'2025':(40,52),'2026':(52,54)}

    for client in clients:
        cn = client['name']
        a = analises.get(cn)
        if not a:
            for ak, av in analises.items():
                if cn[:20].upper() == ak[:20].upper():
                    a = av
                    break

        if a:
            client['credit_limit'] = a['credit']
            client['yearly_totals'] = a['totals']
            client['months_bought'] = a['months_bought']
            client['avg_month'] = a['avg_month']
        else:
            client['credit_limit'] = 0
            yt = {}
            mb = {}
            am = {}
            for year, (start, end) in year_ranges.items():
                vals = client['monthly'][start:end]
                yt[year] = round(sum(vals), 2)
                bought = sum(1 for v in vals if v > 0)
                mb[year] = bought
                am[year] = round(yt[year] / bought, 2) if bought > 0 else 0
            client['yearly_totals'] = yt
            client['months_bought'] = mb
            client['avg_month'] = am

        client['total_geral'] = round(sum(client['monthly']), 2)

        # Risk — based on months since last purchase (using trimmed data)
        risk = recuperacao.get(cn)
        if not risk:
            for rk, rv in recuperacao.items():
                if cn[:20].upper() == rk[:20].upper():
                    risk = rv
                    break

        if not risk:
            last_idx = -1
            for i in range(len(client['monthly'])-1, -1, -1):
                if client['monthly'][i] > 0:
                    last_idx = i
                    break
            months_since = (len(month_labels) - 1 - last_idx) if last_idx >= 0 else 999
            risk = 'Recuperação' if months_since >= 6 else ('Atenção' if months_since >= 3 else 'Saudável')

        client['risk'] = risk

        last_idx = -1
        for i in range(len(client['monthly'])-1, -1, -1):
            if client['monthly'][i] > 0:
                last_idx = i
                break
        client['last_purchase'] = month_labels[last_idx] if last_idx >= 0 else 'Nunca'
        client['months_since'] = (len(month_labels) - 1 - last_idx) if last_idx >= 0 else 999

    # Convert to DataFrame
    df_clients = pd.DataFrame(clients)
    df_products = pd.DataFrame(products)

    # ---- SKU QUANTITY DATA ----
    df_sku = pd.DataFrame()
    sku_sheet_name = None
    for sn in wb.sheetnames:
        if 'qtd' in sn.lower() and 'cliente' in sn.lower():
            sku_sheet_name = sn
            break
    if sku_sheet_name:
        ws_sku = wb[sku_sheet_name]
        sku_data = []

        # Auto-detect month column positions from row 1
        month_cols = []
        for c in range(1, ws_sku.max_column + 1):
            v = ws_sku.cell(1, c).value
            if v and '/' in str(v):
                month_cols.append(c)
        month_headers = []
        for col in month_cols:
            h = ws_sku.cell(1, col).value
            if h:
                month_headers.append(str(h).strip())
        
        # Read data rows starting from row 3 (0-indexed row 2)
        for r in range(3, ws_sku.max_row + 1):
            # For each month block
            for month_idx, base_col in enumerate(month_cols):
                if month_idx >= len(month_headers):
                    break
                mes = month_headers[month_idx]
                
                # Columns within each block: Produto, SKU, Quantidade, Vendedor, Cliente, Código Cliente
                # Offsets from base_col (1-indexed): 0, 1, 2, 3, 4, 5
                produto = ws_sku.cell(r, base_col).value
                sku = ws_sku.cell(r, base_col + 1).value
                quantidade_raw = ws_sku.cell(r, base_col + 2).value
                vendedor = ws_sku.cell(r, base_col + 3).value
                cliente = ws_sku.cell(r, base_col + 4).value
                cod_cliente = ws_sku.cell(r, base_col + 5).value
                
                # Only add if we have the key fields
                if produto and sku and cod_cliente:
                    try:
                        quantidade = int(float(quantidade_raw)) if quantidade_raw else 0
                    except:
                        quantidade = 0
                    
                    if quantidade > 0:
                        sku_data.append({
                            'mes': mes,
                            'produto': str(produto).strip(),
                            'sku': str(sku).strip(),
                            'quantidade': quantidade,
                            'vendedor': str(vendedor).strip() if vendedor else '',
                            'cliente': str(cliente).strip() if cliente else '',
                            'cod_cliente': str(cod_cliente).strip()
                        })
        
        if sku_data:
            df_sku = pd.DataFrame(sku_data)

    # If no Base de DadosProdutos but we have SKU data, build client×product from SKU
    if len(df_client_products) == 0 and len(df_sku) > 0:
        cp_from_sku = df_sku.groupby(['cod_cliente', 'sku', 'produto']).agg(
            total_qty=('quantidade', 'sum')
        ).reset_index()
        # Try to match client names from df_clients
        id_to_name = dict(zip(df_clients['id'].astype(str).str.strip(), df_clients['name']))
        cp_from_sku['client_id'] = cp_from_sku['cod_cliente'].astype(str).str.strip()
        cp_from_sku['client_name'] = cp_from_sku['client_id'].map(id_to_name).fillna('')
        cp_from_sku['product_code'] = cp_from_sku['sku']
        cp_from_sku['product_name'] = cp_from_sku['produto']
        df_client_products = cp_from_sku[['client_id','client_name','product_code','product_name','total_qty']].copy()

    return df_clients, df_products, df_client_products, month_labels, year_ranges, df_sku

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def fmt_brl(v):
    if v >= 1e6:
        return f"R$ {v/1e6:.1f}M"
    if v >= 1e3:
        return f"R$ {v/1e3:.1f}k"
    return f"R$ {v:.0f}"

def fmt_brl_full(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _year_of_label(lbl):
    """Extrai o ano (ex: '2025') de um rótulo de mês tipo 'jan/25'."""
    parts = str(lbl).replace('-', '/').split('/')
    y = parts[-1].strip() if len(parts) >= 2 else ''
    return f"20{y}" if len(y) == 2 else y

def compute_preset_indices(preset, months):
    """Converte um preset de período ('Últimos 12 meses' etc.) no set de
    índices correspondentes da lista de meses."""
    n = len(months)
    years = []
    for lbl in months:
        y = _year_of_label(lbl)
        if y and y not in years:
            years.append(y)
    cur = years[-1] if years else ''
    prev = years[-2] if len(years) >= 2 else ''

    if preset == "Este mês":
        return set([n - 1]) if n else set()
    if preset == "Últimos 3 meses":
        return set(range(max(0, n - 3), n))
    if preset == "Últimos 6 meses":
        return set(range(max(0, n - 6), n))
    if preset == "Últimos 12 meses":
        return set(range(max(0, n - 12), n))
    if preset.startswith("Este ano") and cur:
        return {i for i, lbl in enumerate(months) if _year_of_label(lbl) == cur}
    if preset.startswith("Ano passado") and prev:
        return {i for i, lbl in enumerate(months) if _year_of_label(lbl) == prev}
    return set(range(n))  # "Tudo" (desde o início)

def show_money_table(df_disp, money_cols, **kwargs):
    """Tabela com colunas em R$ formatadas SEM virar texto — assim a ordenação
    por clique no cabeçalho continua numérica (e não alfabética).
    Retorna o resultado de st.dataframe (evento de seleção, quando usado)."""
    fmt_map = {c: fmt_brl_full for c in money_cols if c in df_disp.columns}
    try:
        return st.dataframe(df_disp.style.format(fmt_map), **kwargs)
    except Exception:
        d = df_disp.copy()
        for c in fmt_map:
            d[c] = d[c].apply(fmt_brl_full)
        return st.dataframe(d, **kwargs)

def _sku_stats(df_sku):
    """Por SKU: (qtd típica/mês = mediana entre compradores, nº de compradores,
    qtd/mês por cliente). Base para todas as estimativas de oportunidade."""
    if len(df_sku) == 0:
        return {}, {}, pd.DataFrame()
    per = df_sku.groupby(['sku', 'cod_cliente']).agg(q=('quantidade', 'sum'), m=('mes', 'nunique')).reset_index()
    per['pm'] = per['q'] / per['m'].clip(lower=1)
    per['cod_cliente'] = per['cod_cliente'].astype(str).str.strip()
    typical = per.groupby('sku')['pm'].median().to_dict()
    buyers = per.groupby('sku')['cod_cliente'].nunique().to_dict()
    return typical, buyers, per

def _preco_medio_map(products_df):
    """Preço médio real por SKU (faturamento 12m ÷ quantidade 12m, Base Mãe)."""
    out = {}
    if 'valor_12m' in products_df.columns and 'qty_12m' in products_df.columns:
        for code, v, q in zip(products_df['code'], products_df['valor_12m'], products_df['qty_12m']):
            if q and q > 0 and v and v > 0:
                out[code] = v / q
    return out

def annual_value_estimate(monthly):
    """Valor anual estimado do cliente: ticket médio dos meses COM compra
    nos últimos 12 meses × 12. Se não comprou nos últimos 12 meses, usa o
    ticket médio histórico. (Substitui o cálculo antigo travado em 2024/2023.)"""
    if not isinstance(monthly, (list, tuple)) or len(monthly) == 0:
        return 0
    last12 = [v for v in monthly[-12:] if v > 0]
    if last12:
        return sum(last12) / len(last12) * 12
    hist = [v for v in monthly if v > 0]
    if hist:
        return sum(hist) / len(hist) * 12
    return 0

def risk_badge(risk):
    if risk == 'Recuperação':
        return '<span class="badge badge-red">Recuperação</span>'
    elif risk == 'Atenção':
        return '<span class="badge badge-yellow">Atenção</span>'
    return '<span class="badge badge-green">Saudável</span>'

def status_badge(status):
    if status == 'Ativo':
        return '<span class="badge badge-green">Ativo</span>'
    elif status == 'Inativo':
        return '<span class="badge badge-red">Inativo</span>'
    return f'<span class="badge badge-blue">{status}</span>'

def insight_html(type_, label, text, action):
    css_class = f"insight-{type_}" if type_ in ('danger','warning','success') else ''
    return f"""
    <div class="insight-card {css_class}">
        <div class="insight-type">{label}</div>
        <div class="insight-text">{text}</div>
        <div class="insight-action">{action}</div>
    </div>
    """

# ============================================================
# PAGE: PAINEL DO GESTOR (tela inicial do admin/diretor)
# ============================================================
def page_manager(df, months, df_sku, products_df):
    st.header("🎛️ Painel do Gestor")
    st.caption(f"Acompanhamento objetivo do canal Distribuição — dados até **{months[-1]}**.")

    _n_pend = len(pending_inactivation_requests())
    if _n_pend > 0:
        st.warning(f"📋 **{_n_pend} solicitação(ões) de inativação** aguardando sua aprovação — "
                   f"veja a seção *Solicitações de Inativação* abaixo.")

    n = len(months)
    monthly_tot = [df['monthly'].apply(lambda m: m[i] if i < len(m) else 0).sum() for i in range(n)]

    # ---- LINHA 1: O MÊS E O ANO, SEM RODEIO ----
    last = monthly_tot[-1]
    prev = monthly_tot[-2] if n >= 2 else 0
    yoy = monthly_tot[n - 13] if n >= 13 else 0
    last3 = sum(monthly_tot[-3:])
    prev3 = sum(monthly_tot[-6:-3]) if n >= 6 else 0

    cur_year = _year_of_label(months[-1])
    prev_year = str(int(cur_year) - 1) if cur_year.isdigit() else ''
    ytd_idx = [i for i in range(n) if _year_of_label(months[i]) == cur_year]
    py_idx = [i for i in range(n) if _year_of_label(months[i]) == prev_year][:len(ytd_idx)]
    ytd = sum(monthly_tot[i] for i in ytd_idx)
    pytd = sum(monthly_tot[i] for i in py_idx)

    def _pct(cur, base):
        return f"{(cur - base) / base * 100:+.1f}%" if base > 0 else None

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"Receita {months[-1]}", fmt_brl(last), _pct(last, prev),
              help="Variação vs mês anterior")
    k2.metric("vs Mesmo Mês Ano Passado", _pct(last, yoy) or "—", f"{fmt_brl(yoy)} em {months[n-13]}" if n >= 13 else "")
    k3.metric("Últimos 3 Meses", fmt_brl(last3), _pct(last3, prev3),
              help="Variação vs trimestre móvel anterior")
    k4.metric(f"Acumulado {cur_year}", fmt_brl(ytd), _pct(ytd, pytd),
              help=f"vs mesmo período de {prev_year}")

    # Concentração de receita (últimos 12 meses)
    df_conc = df.copy()
    df_conc['r12'] = df_conc['monthly'].apply(lambda m: sum(m[-12:]))
    r12_total = df_conc['r12'].sum()
    top5 = df_conc.nlargest(5, 'r12')['r12'].sum()
    if r12_total > 0:
        st.caption(f"⚖️ Concentração: os 5 maiores clientes respondem por **{top5/r12_total*100:.0f}%** "
                   f"da receita dos últimos 12 meses.")

    st.divider()

    # ---- LINHA 2: DESEMPENHO POR VENDEDOR ----
    st.subheader("👥 Desempenho por Vendedor")
    st.caption(f"Mês de referência: {months[-1]}. Tendência = mês atual vs média dos 3 meses anteriores.")
    rows = []
    for v, g in df.groupby('vendor'):
        if not v:
            continue
        rev_m = g['monthly'].apply(lambda m: m[-1] if len(m) >= 1 else 0).sum()
        base3 = g['monthly'].apply(lambda m: sum(m[-4:-1])).sum() / 3 if n >= 4 else 0
        buyers = len(g[g['monthly'].apply(lambda m: m[-1] > 0 if len(m) >= 1 else False)])
        risk_rs = g[g['risk'].isin(['Recuperação', 'Atenção'])]['monthly'].apply(annual_value_estimate).sum()
        rows.append({
            'Vendedor': str(v).replace(' Propetz Distribuição', '').replace(' La Maison Propetz', ''),
            'Receita no Mês': round(rev_m, 2),
            'Média 3m Anteriores': round(base3, 2),
            'Tendência': f"{(rev_m / base3 - 1) * 100:+.0f}%" if base3 > 0 else '—',
            'Compraram no Mês': f"{buyers}/{len(g)}",
            'Cobertura': f"{buyers / len(g) * 100:.0f}%" if len(g) > 0 else '—',
            'R$ em Risco (ano)': round(risk_rs, 2),
        })
    if rows:
        vend_df = pd.DataFrame(rows).sort_values('Receita no Mês', ascending=False)
        show_money_table(vend_df, ['Receita no Mês', 'Média 3m Anteriores', 'R$ em Risco (ano)'],
                         use_container_width=True, hide_index=True,
                         height=min(350, 35 * len(vend_df) + 38))

    st.divider()

    # ---- LINHA 3: ONDE AGIR AGORA ----
    st.subheader("🚨 Maiores Recuperações em Jogo")
    st.caption("Top 10 clientes ativos esfriando, da base inteira, por receita anual em jogo — cobre isso nas reuniões com o time.")
    risky = df[(df['risk'].isin(['Recuperação', 'Atenção'])) & (df['status'] == 'Ativo')].copy()
    risky['_cid'] = risky['id'].astype(str).str.strip()
    risky = risky[~risky['_cid'].isin(load_inactive_clients())]
    if len(risky) > 0:
        _busca_m = st.text_input("🔍 Buscar cliente (nome, UF, vendedor ou código)", key="mgr_risky_search",
                                 placeholder="Digite parte do nome para achar qualquer cliente em risco...")
        _pend_ids_m = {r['client_id'] for r in pending_inactivation_requests()}
        risky['valor'] = risky['monthly'].apply(annual_value_estimate)
        risky['Prioridade'] = risky['risk'].map({'Recuperação': '🔴 Urgente', 'Atenção': '🟡 Atenção'})
        risky.loc[risky['_cid'].isin(_pend_ids_m), 'Prioridade'] = \
            risky.loc[risky['_cid'].isin(_pend_ids_m), 'Prioridade'] + ' ⏳'
        risky = risky.sort_values('valor', ascending=False)
        # Sem busca: top 10. Com busca: TODOS os que casam (da base inteira em risco).
        if _busca_m and str(_busca_m).strip():
            risky = _filter_clients_by_term(risky, _busca_m).reset_index(drop=True)
            _nota_m = f"{len(risky)} resultado(s) para “{_busca_m}”."
        else:
            risky = risky.head(10).reset_index(drop=True)
            _nota_m = "Top 10 por valor — use a busca acima para achar qualquer outro cliente em risco."
        if len(risky) == 0:
            st.info("Nenhum cliente encontrado com esse termo.")
        else:
            disp_r = risky[['Prioridade', 'name', 'vendor', 'state', 'last_purchase', 'months_since', 'valor']].copy()
            disp_r['vendor'] = disp_r['vendor'].str.replace(' Propetz Distribuição', '').str.replace(' La Maison Propetz', '')
            disp_r.columns = ['Prioridade', 'Cliente', 'Vendedor', 'UF', 'Última Compra', 'Meses', 'R$ em Jogo (ano)']
            ev_r = show_money_table(disp_r, ['R$ em Jogo (ano)'], use_container_width=True, hide_index=True,
                                    height=min(400, 35 * len(disp_r) + 38),
                                    on_select="rerun", selection_mode="multi-row", key="mgr_risky_sel")
            _act = "Marque a caixinha na linha para inativar" if can_approve_inactivations() \
                else "Cliente fechou? Marque a caixinha na linha para sugerir a inativação"
            st.caption(f"☑️ {_act}. ⏳ = já há uma solicitação pendente.")
            try:
                _rows = list(ev_r.selection.rows) if ev_r and ev_r.selection and ev_r.selection.rows else []
            except Exception:
                _rows = []
            if _rows:
                _sel = risky.iloc[_rows]
                _prev = ", ".join(_sel['name'].head(3).tolist()) + ("…" if len(_sel) > 3 else "")
                if can_approve_inactivations():
                    if st.button(f"🚫 Inativar {len(_rows)} selecionado(s): {_prev}", key="mgr_inact_btn", type="primary"):
                        _ic = load_inactive_clients()
                        for _, rw in _sel.iterrows():
                            _ic.add(rw['_cid'])
                        save_inactive_clients(_ic)
                        st.success(f"{len(_rows)} cliente(s) inativado(s).")
                        st.rerun()
                else:
                    if st.button(f"📨 Sugerir inativação de {len(_rows)} selecionado(s): {_prev}", key="mgr_inact_btn", type="primary"):
                        _s = 0
                        for _, rw in _sel.iterrows():
                            if add_inactivation_request(rw['_cid'], rw['name'], rw['vendor']):
                                _s += 1
                        st.success(f"{_s} sugestão(ões) enviada(s) para aprovação do administrador.")
                        st.rerun()
            st.caption(_nota_m)
    else:
        st.success("Nenhum cliente ativo em risco no momento.")

    st.divider()

    # ---- LINHA 4: SOLICITAÇÕES DE INATIVAÇÃO ----
    # Admin aprova/rejeita; diretora vê a fila como informativa (ela sugere, não decide).
    _can_approve = can_approve_inactivations()
    st.subheader("📋 Solicitações de Inativação")
    reqs = load_inactive_requests()
    pend = [r for r in reqs if r.get('status') == 'pendente']
    if not pend:
        st.caption("Nenhuma solicitação pendente.")
    elif not _can_approve:
        st.caption("Solicitações aguardando aprovação do administrador. Você pode sugerir novas "
                   "inativações nas tabelas abaixo e nas páginas de Ações e Churn.")
        for r in pend:
            _vend_short = r.get('vendor', '').replace(' Propetz Distribuição', '').replace(' La Maison Propetz', '')
            st.markdown(f"⏳ **{r['client_name']}** ({_vend_short}) — solicitado por "
                        f"*{r.get('requested_by_name', '?')}* em {r.get('date', '')}")
    else:
        st.caption("Aprovando, o cliente sai das listas de ação e churn de todo o time. "
                   "Rejeitando, ele continua como está.")
        for idx, r in enumerate(pend):
            c1, c2, c3 = st.columns([6, 1.2, 1.2])
            _vend_short = r.get('vendor', '').replace(' Propetz Distribuição', '').replace(' La Maison Propetz', '')
            c1.markdown(f"**{r['client_name']}** ({_vend_short}) — solicitado por "
                        f"*{r.get('requested_by_name', '?')}* em {r.get('date', '')}")
            if c2.button("✅ Aprovar", key=f"apr_{r['client_id']}_{idx}"):
                inact = load_inactive_clients()
                inact.add(r['client_id'])
                save_inactive_clients(inact)
                r['status'] = 'aprovado'
                r['decidido_em'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                save_inactive_requests(reqs)
                st.rerun()
            if c3.button("❌ Rejeitar", key=f"rej_{r['client_id']}_{idx}"):
                r['status'] = 'rejeitado'
                r['decidido_em'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                save_inactive_requests(reqs)
                st.rerun()

    # Histórico curto das últimas decisões
    decided = [r for r in reversed(reqs) if r.get('status') in ('aprovado', 'rejeitado')][:10]
    if decided:
        with st.expander(f"Últimas decisões ({len(decided)})"):
            for r in decided:
                _icon = '✅' if r['status'] == 'aprovado' else '❌'
                st.markdown(f"{_icon} **{r['client_name']}** — {r['status']} em {r.get('decidido_em', '')} "
                            f"(solicitado por {r.get('requested_by_name', '?')})")

    # Reativação de clientes inativados (somente admin)
    inact_ids = load_inactive_clients()
    _df_inact = df[df['id'].astype(str).str.strip().isin(inact_ids)]
    with st.expander(f"♻️ Clientes inativados ({len(inact_ids)})" + (" — reativar" if _can_approve else "")):
        if len(_df_inact) == 0:
            st.caption("Nenhum cliente inativado.")
        elif not _can_approve:
            st.caption("Reativação é feita pelo administrador.")
            st.dataframe(_df_inact[['name', 'vendor', 'state']].rename(
                columns={'name': 'Cliente', 'vendor': 'Vendedor', 'state': 'UF'}),
                use_container_width=True, hide_index=True)
        else:
            sel_react = st.multiselect("Selecione para reativar:",
                                       sorted(_df_inact['name'].tolist()), key="mgr_react")
            if sel_react:
                if st.button(f"♻️ Reativar {len(sel_react)} cliente(s)", key="btn_mgr_react", type="primary"):
                    new_inact = set(inact_ids)
                    for nm in sel_react:
                        m = _df_inact[_df_inact['name'] == nm]
                        if len(m) > 0:
                            new_inact.discard(str(m.iloc[0]['id']).strip())
                    save_inactive_clients(new_inact)
                    st.success(f"{len(sel_react)} cliente(s) reativado(s).")
                    st.rerun()

    st.divider()

    # ---- LINHA 5: O TIME ESTÁ USANDO O BI? ----
    st.subheader("📡 Uso do BI pelo Time (últimos 14 dias)")
    access_log = _load_access_log()
    if not access_log:
        st.info("Sem registros de acesso ainda. (Para o log sobreviver a reinícios do servidor, configure o GITHUB_TOKEN — ver COMO-USAR.md.)")
    else:
        df_log = pd.DataFrame(access_log)
        cutoff = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
        recent = df_log[(df_log['action'] == 'login') & (df_log['date'] >= cutoff)]
        users_all = load_users().get('users', {})
        urows = []
        for uname, info in users_all.items():
            if info.get('role') == 'admin':
                continue
            u_logins = recent[recent['user'] == uname]
            last_seen = df_log[df_log['user'] == uname]['date'].max() if len(df_log[df_log['user'] == uname]) > 0 else None
            urows.append({
                'Usuário': info.get('name', uname),
                'Logins (14d)': len(u_logins),
                'Último Acesso': last_seen or 'Nunca',
                'Situação': '✅ Ativo' if len(u_logins) >= 3 else ('🟡 Pouco uso' if len(u_logins) >= 1 else '🔴 Sem uso'),
            })
        if urows:
            st.dataframe(pd.DataFrame(urows).sort_values('Logins (14d)', ascending=False),
                         use_container_width=True, hide_index=True)
            n_inactive = sum(1 for r in urows if r['Logins (14d)'] == 0)
            if n_inactive > 0:
                st.warning(f"{n_inactive} usuário(s) sem nenhum login nos últimos 14 dias — ferramenta não vira resultado se o time não usa.")

# ============================================================
# PAGE: MINHAS AÇÕES (tela inicial — lista priorizada de trabalho)
# ============================================================
def _csv_download(df_export, label, filename, key):
    """Botão de download CSV no padrão Excel brasileiro (; e vírgula decimal)."""
    csv_bytes = df_export.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
    st.download_button(label, csv_bytes, file_name=filename, mime="text/csv", key=key)

def _filter_clients_by_term(df, term, name_col='name', vendor_col='vendor', state_col='state', id_col='id'):
    """Filtra um DataFrame de clientes por nome, UF, vendedor ou código.
    Termo vazio devolve o df inteiro. Busca sem acento/maiúscula."""
    if not term or not str(term).strip():
        return df
    s = str(term).strip().lower()
    mask = None
    for col in (name_col, vendor_col, state_col, id_col):
        if col and col in df.columns:
            m = df[col].astype(str).str.lower().str.contains(s, na=False, regex=False)
            mask = m if mask is None else (mask | m)
    return df[mask] if mask is not None else df

def page_actions(df, df_sku, products_df, df_client_products, months):
    st.header("✅ Minhas Ações")
    st.caption(f"Sua lista de trabalho priorizada — dados até {months[-1]}. "
               "Comece pelo topo: são os contatos com mais receita em jogo.")

    work = df.copy()

    # Admin/diretor escolhem a carteira; vendedor já chega filtrado
    if has_full_data_access():
        vendors = ["Todas"] + sorted(work['vendor'].unique().tolist())
        sel_v = st.selectbox("Carteira", vendors, key="act_vendor")
        if sel_v != "Todas":
            work = work[work['vendor'] == sel_v]

    # Remove clientes inativados manualmente (página Churn)
    inactive_ids = load_inactive_clients()
    work['_cid'] = work['id'].astype(str).str.strip()
    work = work[~work['_cid'].isin(inactive_ids)].copy()

    if len(work) == 0:
        st.info("Nenhum cliente na carteira selecionada.")
        return

    work['valor_anual'] = work['monthly'].apply(annual_value_estimate)
    work['vendor_short'] = work['vendor'].str.replace(' Propetz Distribuição', '').str.replace(' La Maison Propetz', '')

    # ---- Produtos favoritos por cliente (o que ele sempre comprou) ----
    fav = {}
    if len(df_sku) > 0:
        g = df_sku.groupby(['cod_cliente', 'produto'])['quantidade'].sum().reset_index()
        g['cod_cliente'] = g['cod_cliente'].astype(str).str.strip()
        for cid, grp in g.groupby('cod_cliente'):
            fav[cid] = ', '.join(grp.nlargest(3, 'quantidade')['produto'].tolist())

    # ---- 1. CONTATOS PRIORITÁRIOS (clientes esfriando, por receita em jogo) ----
    calls = work[(work['risk'].isin(['Recuperação', 'Atenção'])) & (work['status'] == 'Ativo')].copy()
    calls = calls.sort_values('valor_anual', ascending=False)

    # ---- 2. OFERTAS PRONTAS (produtos Curva A que o cliente ainda não compra) ----
    offers = []
    if len(df_client_products) > 0 and len(products_df) > 0:
        carteira_ids = set(work['_cid'])
        cp = df_client_products.copy()
        cp['client_id'] = cp['client_id'].astype(str).str.strip()
        cp = cp[cp['client_id'].isin(carteira_ids)]
        n_cart = max(cp['client_id'].nunique(), 1)
        pen = cp.groupby('product_code')['client_id'].nunique() / n_cart * 100
        bought_by = cp.groupby('client_id')['product_code'].apply(set).to_dict()
        prod_a = products_df[products_df['abc'] == 'A']
        _preco = _preco_medio_map(products_df)
        _typ, _nbuy, _ = _sku_stats(df_sku)

        # Foca nos 30 clientes ativos mais valiosos da carteira
        targets = work[work['status'] == 'Ativo'].sort_values('valor_anual', ascending=False).head(30)
        for _, cl in targets.iterrows():
            owned = bought_by.get(cl['_cid'], set())
            if not owned:
                continue  # sem histórico de produto para cruzar
            for _, pr in prod_a.iterrows():
                code = pr['code']
                if code in owned:
                    continue
                p = float(pen.get(code, 0))
                if p >= 30:
                    pot = round((_typ.get(code) or 0) * (_preco.get(code) or 0), 2)
                    offers.append({
                        'Cliente': cl['name'],
                        'Vendedor': cl['vendor_short'],
                        'Produto Sugerido': pr['name'],
                        'Categoria': pr['category'],
                        '% da Carteira que Compra': round(p),
                        'R$ Potencial/Mês': pot,
                        '_valor_cliente': cl['valor_anual'],
                        '_score': p * max(cl['valor_anual'], 1),
                    })
    offers_df = pd.DataFrame(offers)
    if len(offers_df) > 0:
        offers_df = offers_df.sort_values(['R$ Potencial/Mês', '_score'], ascending=False)

    # ---- KPIs ----
    n_urgent = len(calls[calls['risk'] == 'Recuperação'])
    n_warn = len(calls[calls['risk'] == 'Atenção'])
    at_stake = calls['valor_anual'].sum()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 Contatos Urgentes", f"{n_urgent}", "6+ meses sem comprar")
    k2.metric("🟡 Contatos de Atenção", f"{n_warn}", "3-5 meses sem comprar")
    k3.metric("💰 Receita em Jogo", fmt_brl(at_stake), "estimativa anual")
    k4.metric("🎯 Ofertas Identificadas", f"{len(offers_df)}", "produtos Curva A")

    st.divider()

    # ---- SEÇÃO 1: LIGAR / VISITAR ----
    st.subheader("📞 Quem contatar primeiro")
    if len(calls) == 0:
        st.success("Nenhum cliente esfriando na carteira. Foque nas ofertas abaixo!")
    else:
        _busca = st.text_input("🔍 Buscar cliente na lista (nome, UF, vendedor ou código)", key="calls_search",
                               placeholder="Digite parte do nome para encontrar qualquer cliente da lista...")
        _calls_f = _filter_clients_by_term(calls, _busca)
        # Sem busca: mostra os 20 maiores. Com busca: mostra TODOS os que casam.
        if _busca and str(_busca).strip():
            top_calls = _calls_f.copy()
            _nota = f"{len(top_calls)} resultado(s) para “{_busca}”."
        else:
            top_calls = calls.head(20).copy()
            _nota = (f"Mostrando os 20 maiores de {len(calls)} clientes esfriando — "
                     "use a busca acima para achar qualquer outro." if len(calls) > 20 else "")
        if len(top_calls) == 0:
            st.info("Nenhum cliente encontrado com esse termo.")
        else:
            _pend_ids = {r['client_id'] for r in pending_inactivation_requests()}
            top_calls['Prioridade'] = top_calls['risk'].map({'Recuperação': '🔴 Urgente', 'Atenção': '🟡 Atenção'})
            # ⏳ = já existe solicitação de inativação aguardando aprovação
            top_calls.loc[top_calls['_cid'].isin(_pend_ids), 'Prioridade'] = \
                top_calls.loc[top_calls['_cid'].isin(_pend_ids), 'Prioridade'] + ' ⏳'
            top_calls['Sempre Comprou'] = top_calls['_cid'].map(fav).fillna('—')
            top_calls = top_calls.reset_index(drop=True)
            disp_calls = top_calls[['Prioridade', 'name', 'vendor_short', 'state', 'last_purchase',
                                    'months_since', 'valor_anual', 'Sempre Comprou']].copy()
            disp_calls.columns = ['Prioridade', 'Cliente', 'Vendedor', 'UF', 'Última Compra',
                                  'Meses sem Comprar', 'Valor Anual Est.', 'Sempre Comprou']
            ev = show_money_table(disp_calls, ['Valor Anual Est.'], use_container_width=True, hide_index=True,
                                  height=min(500, 35 * len(disp_calls) + 38),
                                  on_select="rerun", selection_mode="multi-row", key="calls_sel")
            st.caption("☑️ Cliente fechou ou não existe mais? Marque a caixinha à esquerda da linha "
                       "e use o botão que aparece abaixo. ⏳ = solicitação já enviada.")
            try:
                _sel_rows = list(ev.selection.rows) if ev and ev.selection and ev.selection.rows else []
            except Exception:
                _sel_rows = []
            if _sel_rows:
                _sel_clients = top_calls.iloc[_sel_rows]
                _names_prev = ", ".join(_sel_clients['name'].head(3).tolist()) + ("…" if len(_sel_clients) > 3 else "")
                if can_approve_inactivations():
                    if st.button(f"🚫 Inativar {len(_sel_rows)} selecionado(s): {_names_prev}",
                                 key="btn_inact_inline", type="primary"):
                        _inact = load_inactive_clients()
                        for _, rw in _sel_clients.iterrows():
                            _inact.add(rw['_cid'])
                        save_inactive_clients(_inact)
                        st.success(f"{len(_sel_rows)} cliente(s) inativado(s).")
                        st.rerun()
                else:
                    if st.button(f"📨 Solicitar inativação de {len(_sel_rows)} selecionado(s): {_names_prev}",
                                 key="btn_inact_inline", type="primary"):
                        _sent = 0
                        for _, rw in _sel_clients.iterrows():
                            if add_inactivation_request(rw['_cid'], rw['name'], rw['vendor']):
                                _sent += 1
                        st.success(f"{_sent} solicitação(ões) enviada(s) para aprovação do administrador.")
                        st.rerun()
            if _nota:
                st.caption(_nota)

        export_calls = calls[['name', 'vendor_short', 'state', 'risk', 'last_purchase',
                              'months_since', 'valor_anual']].copy()
        export_calls.columns = ['Cliente', 'Vendedor', 'UF', 'Risco', 'Última Compra',
                                'Meses sem Comprar', 'Valor Anual Estimado']
        export_calls['Sempre Comprou'] = calls['_cid'].map(fav).fillna('')
        _csv_download(export_calls, "⬇️ Baixar lista de contatos (Excel/CSV)",
                      "contatos_prioritarios.csv", "dl_calls")

    # ---- SOLICITAR INATIVAÇÃO (vendedor/diretora pedem, admin aprova) ----
    if not can_approve_inactivations():
        with st.expander("🚫 Solicitar inativação de cliente FORA da lista acima"):
            st.caption("Para os clientes da tabela, use a caixinha de seleção na própria linha. "
                       "A solicitação vai para aprovação do administrador — até lá, o cliente continua nas listas.")
            _pend = pending_inactivation_requests()
            _pend_ids = {r['client_id'] for r in _pend}
            _opts = work[~work['_cid'].isin(_pend_ids)].sort_values('name')['name'].tolist()
            sel_inact = st.multiselect("Clientes para inativar:", _opts, key="req_inact")
            if sel_inact:
                if st.button(f"📨 Enviar solicitação ({len(sel_inact)})", key="btn_req_inact", type="primary"):
                    sent = 0
                    for nm in sel_inact:
                        row = work[work['name'] == nm]
                        if len(row) > 0 and add_inactivation_request(row.iloc[0]['_cid'], nm, row.iloc[0]['vendor']):
                            sent += 1
                    st.success(f"{sent} solicitação(ões) enviada(s) para aprovação do administrador.")
                    st.rerun()
            _mine = [r for r in _pend if r.get('requested_by') == st.session_state.get('username')]
            if _mine:
                st.info("⏳ Aguardando aprovação: " + ", ".join(r['client_name'] for r in _mine))

    st.divider()

    # ---- SEÇÃO 2: OFERTAS PRONTAS ----
    st.subheader("🎯 Ofertas prontas para os seus melhores clientes")
    st.caption("Produtos Curva A (os que mais faturam no canal Distribuição) que pelo menos 30% da carteira compra, "
               "mas estes clientes ainda não — argumento de venda pronto.")
    if len(offers_df) == 0:
        st.info("Nenhuma oferta identificada — clientes principais já compram os produtos Curva A relevantes, "
                "ou não há dados de produto por cliente na planilha.")
    else:
        disp_offers = offers_df[['Cliente', 'Vendedor', 'Produto Sugerido', 'Categoria',
                                 '% da Carteira que Compra', 'R$ Potencial/Mês']].head(40)
        show_money_table(disp_offers, ['R$ Potencial/Mês'], use_container_width=True, hide_index=True,
                         height=min(500, 35 * len(disp_offers) + 38))
        _csv_download(offers_df.drop(columns=['_valor_cliente', '_score']),
                      "⬇️ Baixar lista de ofertas (Excel/CSV)",
                      "ofertas_mix.csv", "dl_offers")

# ============================================================
# PAGE: VISÃO GERAL
# ============================================================
def page_overview(df, months, year_ranges, sel_indices, sel_indices_sorted, sel_months):
    st.header("📊 Visão Geral")

    n_sel_months = len(sel_months)

    # --- FILTERS (Vendedor, Estado, Status) ---
    fc1, fc2, fc3 = st.columns(3)
    vendors = ["Todos"] + sorted(df['vendor'].unique().tolist())
    states = ["Todos"] + sorted(df['state'].unique().tolist())
    statuses = ["Todos"] + sorted(df['status'].unique().tolist())

    with fc1:
        sel_vendor = st.selectbox("Vendedor", vendors, key="ov_vendor")
    with fc2:
        sel_state = st.selectbox("Estado", states, key="ov_state")
    with fc3:
        sel_status = st.selectbox("Status", statuses, key="ov_status")

    # Apply client filters
    filtered = df.copy()
    if sel_vendor != "Todos":
        filtered = filtered[filtered['vendor'] == sel_vendor]
    if sel_state != "Todos":
        filtered = filtered[filtered['state'] == sel_state]
    if sel_status != "Todos":
        filtered = filtered[filtered['status'] == sel_status]

    # Helper: sum monthly values in selected period (uses sel_indices set)
    def period_sum(m):
        return sum(m[i] for i in sel_indices_sorted if i < len(m))

    # Helper: sum monthly values for a specific set of indices
    def range_sum_set(m, idx_set):
        return sum(m[i] for i in idx_set if i < len(m))

    # --- KPIs ---
    period_rev = filtered['monthly'].apply(period_sum).sum()
    n_active = len(filtered[filtered['status'] == 'Ativo'])
    n_inactive = len(filtered[filtered['status'] == 'Inativo'])
    n_risk = len(filtered[filtered['risk'].isin(['Recuperação', 'Atenção'])])

    # Buyers in period = clients with any revenue > 0 in selected months
    period_buyers = len(filtered[filtered['monthly'].apply(
        lambda m: any(m[i] > 0 for i in sel_indices_sorted if i < len(m))
    )])
    avg_ticket = period_rev / period_buyers / max(n_sel_months, 1) if period_buyers > 0 else 0

    # Compare with same-length previous period (shift selected indices back by n_sel_months)
    prev_indices = set(max(0, i - n_sel_months) for i in sel_indices_sorted)
    prev_indices = prev_indices - sel_indices  # remove overlap
    prev_rev = filtered['monthly'].apply(lambda m: range_sum_set(m, prev_indices)).sum()
    period_growth = ((period_rev - prev_rev) / prev_rev * 100) if prev_rev > 0 else 0

    # Retention: of clients who bought in prev period, how many bought in current period
    if len(prev_indices) > 0:
        bought_prev = set(filtered[filtered['monthly'].apply(
            lambda m: any(m[i] > 0 for i in prev_indices if i < len(m))
        )].index)
        bought_curr = set(filtered[filtered['monthly'].apply(
            lambda m: any(m[i] > 0 for i in sel_indices_sorted if i < len(m))
        )].index)
        retained = len(bought_prev & bought_curr)
        retention_rate = (retained / len(bought_prev) * 100) if len(bought_prev) > 0 else 0
    else:
        retention_rate = 0
        retained = 0
        bought_prev = set()
        bought_curr = set()

    k1, k2, k3, k4, k5 = st.columns(5)
    period_label = f"{sel_months[0]} - {sel_months[-1]}" if len(sel_months) > 1 else sel_months[0] if sel_months else ""
    k1.metric("Receita do Período", fmt_brl(period_rev), period_label)
    k2.metric("vs Período Anterior", f"{'↑' if period_growth >= 0 else '↓'} {abs(period_growth):.1f}%",
              f"{fmt_brl(prev_rev)} anterior")
    k3.metric("Retenção", f"{retention_rate:.0f}%",
              f"{retained} de {len(bought_prev)} retidos")
    k4.metric("Base Ativa", f"{n_active}", f"Inativos: {n_inactive} | Risco: {n_risk}")
    k5.metric("Ticket Médio/Mês", fmt_brl(avg_ticket), f"{period_buyers} comprando no período")

    st.divider()

    # Insights aparecem AQUI no topo; o conteúdo é calculado ao longo da
    # página e renderizado neste container no final.
    st.subheader("🧠 Insights Automáticos")
    insights_box = st.container()

    st.divider()

    # --- REVENUE TREND (clickable bar chart with CTRL+click) ---
    monthly_totals = []
    for i in range(len(months)):
        total = filtered['monthly'].apply(lambda m: m[i] if i < len(m) else 0).sum()
        monthly_totals.append(total)

    # Bars: selected period = bold color, others = subtle
    bar_colors = ['#3b82f6' if i in sel_indices else 'rgba(59,130,246,0.2)' for i in range(len(months))]

    fig_rev = go.Figure()
    fig_rev.add_trace(go.Bar(
        x=months, y=monthly_totals, name='Receita',
        marker_color=bar_colors,
        hovertemplate='%{x}: R$ %{y:,.0f}<extra></extra>',
        selectedpoints=None
    ))
    fig_rev.update_layout(
        title="Receita Mensal (R$) — clique para filtrar | CTRL+clique para adicionar | arraste para selecionar",
        height=400,
        template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
        yaxis=dict(gridcolor='#e2e8f0'),
        xaxis=dict(gridcolor='#e2e8f0'),
        showlegend=False,
        clickmode='event+select',
        dragmode='select',
        selectdirection='h'
    )

    # Use on_select for box/lasso selection (drag)
    event = st.plotly_chart(fig_rev, use_container_width=True, on_select="rerun",
                            selection_mode=["points", "box", "lasso"], key="rev_chart_sel")

    # Process chart selection (click or drag)
    if event and event.selection and event.selection.points:
        clicked_labels = []
        for pt in event.selection.points:
            x_val = pt.get("x", None) if isinstance(pt, dict) else getattr(pt, 'x', None)
            if x_val and x_val in months:
                clicked_labels.append(x_val)
        # Only update if selection changed
        current_chart_sel = set(st.session_state.get("chart_sel_months", []))
        new_sel = set(clicked_labels)
        if new_sel and new_sel != current_chart_sel:
            st.session_state["chart_sel_months"] = list(new_sel)
            st.rerun()

    # --- Interactive month grid below chart ---
    chart_sel_current = st.session_state.get("chart_sel_months", [])

    with st.expander("Seleção individual de meses (clique para selecionar/remover)", expanded=False):
        # Group months by year for compact display
        _year_groups = {}
        for i, lbl in enumerate(months):
            parts = lbl.replace('-', '/').split('/')
            yr = parts[-1].strip() if len(parts) >= 2 else '??'
            _year_groups.setdefault(yr, []).append(lbl)

        for yr, yr_months in _year_groups.items():
            yr_label = f"20{yr}" if len(yr) == 2 else yr
            n_m = len(yr_months)
            cols = st.columns([0.6] + [1] * n_m + [1] * max(0, 12 - n_m))
            cols[0].markdown(f"**{yr_label}**")
            for j, m_lbl in enumerate(yr_months):
                is_selected = m_lbl in chart_sel_current or (not chart_sel_current and months.index(m_lbl) in sel_indices)
                btn_label = m_lbl.split('/')[0] if '/' in m_lbl else m_lbl
                with cols[j + 1]:
                    if is_selected:
                        if st.button(f"**{btn_label}**", key=f"mbtn_{m_lbl}", use_container_width=True, type="primary"):
                            new_sel = [x for x in chart_sel_current if x != m_lbl]
                            if new_sel:
                                st.session_state["chart_sel_months"] = new_sel
                            else:
                                if "chart_sel_months" in st.session_state:
                                    del st.session_state["chart_sel_months"]
                            st.rerun()
                    else:
                        if st.button(btn_label, key=f"mbtn_{m_lbl}", use_container_width=True):
                            if chart_sel_current:
                                st.session_state["chart_sel_months"] = chart_sel_current + [m_lbl]
                            else:
                                st.session_state["chart_sel_months"] = [m_lbl]
                            st.rerun()

    st.divider()

    # --- RECEITA NOVA vs RECORRENTE ---
    col_nr, col_ret = st.columns(2)

    with col_nr:
        # For each month in the period, classify revenue as new/reactivated vs recurring
        new_rev_list = []
        rec_rev_list = []
        for i in sel_indices_sorted:
            new_r = 0
            rec_r = 0
            for _, row in filtered.iterrows():
                m = row['monthly']
                if i >= len(m) or m[i] <= 0:
                    continue
                # Check if client bought in any of the previous 3 months
                had_recent = any(m[j] > 0 for j in range(max(0, i - 3), i))
                if had_recent:
                    rec_r += m[i]
                else:
                    new_r += m[i]
            new_rev_list.append(new_r)
            rec_rev_list.append(rec_r)

        fig_nr = go.Figure()
        fig_nr.add_trace(go.Bar(x=sel_months, y=rec_rev_list, name='Recorrente', marker_color='#3b82f6'))
        fig_nr.add_trace(go.Bar(x=sel_months, y=new_rev_list, name='Nova/Reativação', marker_color='#22c55e'))
        fig_nr.update_layout(
            title="Receita Recorrente vs Nova", barmode='stack', height=380,
            template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
            yaxis=dict(gridcolor='#e2e8f0', title=''),
            xaxis=dict(gridcolor='#e2e8f0'),
            legend=dict(orientation='h', y=1.12)
        )
        fig_nr.update_traces(hovertemplate='%{x}: R$ %{y:,.0f}<extra></extra>')
        st.plotly_chart(fig_nr, use_container_width=True)

        total_rec = sum(rec_rev_list)
        total_new = sum(new_rev_list)
        pct_rec = total_rec / (total_rec + total_new) * 100 if (total_rec + total_new) > 0 else 0
        st.caption(f"Recorrente: {pct_rec:.0f}% | Nova/Reativação: {100 - pct_rec:.0f}%")

    with col_ret:
        # Retention curve: for each month, % of prev month buyers who bought again
        ret_months = []
        ret_rates = []
        for i in sel_indices_sorted:
            if i < 1:
                continue
            prev_buyers = set()
            curr_buyers = set()
            for idx, row in filtered.iterrows():
                m = row['monthly']
                if i - 1 < len(m) and m[i - 1] > 0:
                    prev_buyers.add(idx)
                if i < len(m) and m[i] > 0:
                    curr_buyers.add(idx)
            if len(prev_buyers) > 0:
                ret_months.append(months[i])
                ret_rates.append(len(prev_buyers & curr_buyers) / len(prev_buyers) * 100)

        if ret_rates:
            fig_ret = go.Figure()
            fig_ret.add_trace(go.Scatter(
                x=ret_months, y=ret_rates, mode='lines+markers',
                line=dict(color='#22c55e', width=2), marker=dict(size=5),
                hovertemplate='%{x}: %{y:.1f}%<extra></extra>'
            ))
            avg_ret = sum(ret_rates) / len(ret_rates)
            fig_ret.add_hline(y=avg_ret, line_dash="dash", line_color="rgba(234,179,8,0.5)",
                             annotation_text=f"Média: {avg_ret:.0f}%", annotation_position="top right")
            fig_ret.update_layout(
                title="Retenção Mensal (%)", height=380,
                template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                yaxis=dict(gridcolor='#e2e8f0', range=[0, 100], title=''),
                xaxis=dict(gridcolor='#e2e8f0'),
                showlegend=False
            )
            st.plotly_chart(fig_ret, use_container_width=True)
            st.caption(f"Média de retenção no período: {avg_ret:.0f}%")

    st.divider()

    # --- COBERTURA POR VENDEDOR + STATUS ---
    col_left, col_right = st.columns(2)

    with col_left:
        # Vendor coverage: % of their clients that bought in the period
        vendor_cov = filtered.groupby('vendor').apply(
            lambda g: pd.Series({
                'total_clients': len(g),
                'active_buyers': len(g[g['monthly'].apply(
                    lambda m: any(m[i] > 0 for i in sel_indices_sorted if i < len(m))
                )]),
                'revenue': g['monthly'].apply(period_sum).sum()
            })
        ).reset_index()
        vendor_cov = vendor_cov[vendor_cov['total_clients'] > 0].copy()
        vendor_cov['coverage'] = (vendor_cov['active_buyers'] / vendor_cov['total_clients'] * 100).round(1)
        vendor_cov['vendor_short'] = vendor_cov['vendor'].str.replace(' Propetz Distribuição', '').str.replace(' La Maison Propetz', '')
        vendor_cov = vendor_cov.sort_values('revenue', ascending=False)

        fig_cov = go.Figure()
        fig_cov.add_trace(go.Bar(
            x=vendor_cov['vendor_short'], y=vendor_cov['coverage'],
            marker_color=['#22c55e' if c >= 50 else '#eab308' if c >= 30 else '#ef4444' for c in vendor_cov['coverage']],
            text=[f"{c:.0f}%" for c in vendor_cov['coverage']], textposition='outside',
            hovertemplate='%{x}<br>Cobertura: %{y:.1f}%<br>Comprando: %{customdata[0]} de %{customdata[1]}<extra></extra>',
            customdata=list(zip(vendor_cov['active_buyers'].astype(int), vendor_cov['total_clients'].astype(int)))
        ))
        fig_cov.update_layout(
            title="Cobertura por Vendedor (% clientes comprando)", height=380,
            template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
            yaxis=dict(gridcolor='#e2e8f0', range=[0, 100], title=''),
            xaxis=dict(title=''), showlegend=False
        )
        st.plotly_chart(fig_cov, use_container_width=True)

    with col_right:
        status_counts = filtered['status'].value_counts()
        colors = {'Ativo': '#22c55e', 'Inativo': '#ef4444', 'Inadimplente': '#eab308', 'Permuta': '#f97316'}
        fig_st = px.pie(values=status_counts.values, names=status_counts.index,
                        title="Clientes por Status", color=status_counts.index,
                        color_discrete_map=colors)
        fig_st.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff', height=380)
        st.plotly_chart(fig_st, use_container_width=True)

    st.divider()

    # --- TOP CLIENTES + RECEITA POR VENDEDOR ---
    col_l2, col_r2 = st.columns(2)

    with col_l2:
        top10 = filtered.copy()
        top10['period_total'] = top10['monthly'].apply(period_sum)
        top10 = top10.nlargest(10, 'period_total')
        fig_top = px.bar(top10, y='name', x='period_total', orientation='h',
                         title="Top 10 Clientes (Receita no Período)", color_discrete_sequence=['#3b82f6'])
        fig_top.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                              yaxis=dict(autorange='reversed', title=''),
                              xaxis=dict(title='Receita', gridcolor='#e2e8f0'),
                              showlegend=False, height=400)
        fig_top.update_traces(hovertemplate='%{y}: R$ %{x:,.0f}<extra></extra>')
        st.plotly_chart(fig_top, use_container_width=True)

    with col_r2:
        vendor_data = filtered.groupby('vendor').apply(
            lambda g: pd.Series({
                'total': g['monthly'].apply(period_sum).sum(),
                'clients': len(g),
                'active': len(g[g['status'] == 'Ativo'])
            })
        ).reset_index()
        vendor_data = vendor_data[vendor_data['total'] > 0].sort_values('total', ascending=False)
        vendor_data['vendor_short'] = vendor_data['vendor'].str.replace(' Propetz Distribuição', '').str.replace(' La Maison Propetz', '')

        fig_vend = px.bar(vendor_data, x='vendor_short', y='total',
                          title="Receita por Vendedor (Período)", color_discrete_sequence=['#2563eb'])
        fig_vend.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                               xaxis=dict(title=''), yaxis=dict(title='Receita', gridcolor='#e2e8f0'),
                               showlegend=False, height=400)
        fig_vend.update_traces(hovertemplate='%{x}: R$ %{y:,.0f}<extra></extra>')
        st.plotly_chart(fig_vend, use_container_width=True)

    st.divider()

    # --- CLIENTES INATIVOS COM POTENCIAL ---
    st.subheader("💰 Clientes Inativos com Maior Potencial")
    inactive_pot = filtered.copy()
    inactive_pot['total_hist'] = inactive_pot['monthly'].apply(sum)
    inactive_pot['period_rev'] = inactive_pot['monthly'].apply(period_sum)
    # Clients with zero revenue in last 6 months but significant historical revenue
    last_6_start = max(0, len(months) - 6)
    inactive_pot['last6'] = inactive_pot['monthly'].apply(lambda m: sum(m[last_6_start:]) if len(m) > last_6_start else 0)
    dormant = inactive_pot[(inactive_pot['last6'] == 0) & (inactive_pot['total_hist'] > 0)].copy()
    dormant = dormant.nlargest(10, 'total_hist')

    if len(dormant) > 0:
        dormant_display = dormant[['name', 'vendor', 'state', 'total_hist']].copy()
        dormant_display.columns = ['Cliente', 'Vendedor', 'UF', 'Receita Histórica']
        dormant_display['Vendedor'] = dormant_display['Vendedor'].str.replace(' Propetz Distribuição', '').str.replace(' La Maison Propetz', '')
        dormant_display = dormant_display.reset_index(drop=True)
        dormant_display.index = dormant_display.index + 1
        show_money_table(dormant_display, ['Receita Histórica'], use_container_width=True, height=min(400, 35 * len(dormant_display) + 38))
        total_dormant_rev = dormant['total_hist'].sum()
        st.caption(f"Estes {len(dormant)} clientes já geraram {fmt_brl_full(total_dormant_rev)} em receita total. Uma ligação pode reativá-los.")
    else:
        st.success("Todos os clientes com histórico relevante estão comprando!")

    st.divider()

    # --- INSIGHTS AUTOMÁTICOS (renderizados no insights_box, no topo) ---
    insights = []

    # Insight: Churn risk
    at_risk = filtered[filtered['risk'] == 'Recuperação']
    if len(at_risk) > 0:
        lost = at_risk['monthly'].apply(annual_value_estimate).sum()
        insights.append(insight_html('danger', 'RISCO DE CHURN',
            f"{len(at_risk)} clientes há 6+ meses sem comprar. Perda anual estimada: {fmt_brl_full(lost)}.",
            "Priorize contato imediato com os maiores tickets."))

    # Insight: Period trend
    monthly_sel = [monthly_totals[i] for i in sel_indices_sorted if i < len(monthly_totals)]
    if len(monthly_sel) >= 6:
        half = len(monthly_sel) // 2
        first_half = sum(monthly_sel[:half])
        second_half = sum(monthly_sel[half:])
        if first_half > 0:
            trend = (second_half - first_half) / first_half
            if trend > 0.05:
                insights.append(insight_html('success', 'TENDÊNCIA POSITIVA',
                    f"A 2ª metade do período selecionado cresceu {trend*100:.1f}% vs a 1ª metade.",
                    "Manter estratégia atual e identificar o que está funcionando."))
            elif trend < -0.05:
                insights.append(insight_html('warning', 'ALERTA DE QUEDA',
                    f"A 2ª metade do período selecionado caiu {abs(trend)*100:.1f}% vs a 1ª metade.",
                    "Investigar: clientes perdidos? Sazonalidade? Problema de produto?"))

    # Insight: Concentration
    sorted_by_rev = filtered.copy()
    sorted_by_rev['p_total'] = sorted_by_rev['monthly'].apply(period_sum)
    sorted_by_rev = sorted_by_rev.sort_values('p_total', ascending=False)
    if len(sorted_by_rev) >= 5:
        top5_rev = sorted_by_rev.head(5)['p_total'].sum()
        all_rev = sorted_by_rev['p_total'].sum()
        conc = top5_rev / all_rev if all_rev > 0 else 0
        if conc > 0.3:
            insights.append(insight_html('warning', 'CONCENTRAÇÃO',
                f"Os 5 maiores clientes representam {conc*100:.1f}% da receita no período. Risco de dependência.",
                "Diversificar: focar em clientes médios com potencial de crescimento."))

    # Insight: Retention
    if retention_rate > 0 and retention_rate < 50:
        insights.append(insight_html('danger', 'RETENÇÃO BAIXA',
            f"Apenas {retention_rate:.0f}% dos clientes do período anterior voltaram a comprar.",
            "Ação urgente: entender por que clientes não estão recomprando."))
    elif retention_rate >= 70:
        insights.append(insight_html('success', 'RETENÇÃO SAUDÁVEL',
            f"{retention_rate:.0f}% dos clientes do período anterior voltaram a comprar.",
            "Base fiel. Foco em aumentar ticket médio dos recorrentes."))

    # Insight: Revenue mix
    if (total_rec + total_new) > 0 and total_new / (total_rec + total_new) > 0.4:
        insights.append(insight_html('success', 'CONQUISTA FORTE',
            f"{total_new/(total_rec+total_new)*100:.0f}% da receita vem de clientes novos ou reativados.",
            "Crescimento saudável. Garantir que esses novos clientes se tornem recorrentes."))

    # Insight: Vendor coverage
    if len(vendor_cov) > 0:
        low_cov = vendor_cov[vendor_cov['coverage'] < 30]
        if len(low_cov) > 0:
            names = ', '.join(low_cov['vendor_short'].tolist())
            insights.append(insight_html('warning', 'COBERTURA BAIXA',
                f"Vendedor(es) com menos de 30% dos clientes comprando: {names}.",
                "Revisar: carteira grande demais? Clientes desatualizados? Falta de follow-up?"))

    with insights_box:
        for ins in insights:
            st.markdown(ins, unsafe_allow_html=True)
        if not insights:
            st.info("Nenhum insight crítico para o período selecionado. Operação estável.")

# ============================================================
# PAGE: CLIENTES
# ============================================================
def page_clients(df, df_sku, months, year_ranges, sel_indices_sorted, sel_months):
    st.header("👤 Visão por Cliente")

    search = st.text_input("🔍 Buscar cliente (nome, estado, código ou vendedor)", key="client_search")

    filtered = df.copy()
    if search:
        s = search.lower()
        filtered = filtered[
            filtered['name'].str.lower().str.contains(s, na=False) |
            filtered['state'].str.lower().str.contains(s, na=False) |
            filtered['id'].str.contains(s, na=False) |
            filtered['vendor'].str.lower().str.contains(s, na=False)
        ]

    # Period-based revenue
    def _period_sum(m):
        return sum(m[i] for i in sel_indices_sorted if i < len(m))

    filtered = filtered.copy()
    filtered['total_rev'] = filtered['monthly'].apply(_period_sum)
    filtered = filtered.sort_values('total_rev', ascending=False)

    # Client selector
    client_names = filtered['name'].tolist()

    if not client_names:
        st.info("Nenhum cliente encontrado.")
        return

    # Show table
    period_label = f"{sel_months[0]} - {sel_months[-1]}" if len(sel_months) > 1 else (sel_months[0] if sel_months else "")
    display_df = filtered[['name','state','vendor','status','risk','total_rev','last_purchase']].head(50).copy()
    rev_col = f'Receita ({period_label})'
    display_df.columns = ['Cliente','UF','Vendedor','Status','Risco',rev_col,'Última Compra']
    display_df['Vendedor'] = display_df['Vendedor'].str.replace(' Propetz Distribuição','').str.replace(' La Maison Propetz','')

    show_money_table(display_df, [rev_col], use_container_width=True, height=300, hide_index=True)

    st.divider()

    # Client detail
    selected = st.selectbox("Selecione um cliente para ver detalhes:", client_names[:100], key="client_select")

    if selected:
        c = df[df['name'] == selected].iloc[0]
        client_id = str(c['id']).strip()
        monthly = c['monthly']
        period_total = _period_sum(monthly)
        total = sum(monthly)
        months_active = sum(1 for i in sel_indices_sorted if i < len(monthly) and monthly[i] > 0)
        avg_ticket = period_total / months_active if months_active > 0 else 0

        st.subheader(f"📋 {c['name']}")

        meta_cols = st.columns(6)
        meta_cols[0].markdown(f"**UF:** {c['state']}")
        meta_cols[1].markdown(f"**ID:** {c['id']}")
        meta_cols[2].markdown(f"**Vendedor:** {c['vendor'].replace(' Propetz Distribuição','').replace(' La Maison Propetz','')}")
        meta_cols[3].markdown(f"**Status:** {status_badge(c['status'])}", unsafe_allow_html=True)
        meta_cols[4].markdown(f"**Risco:** {risk_badge(c['risk'])}", unsafe_allow_html=True)
        if c['credit_limit'] > 0:
            meta_cols[5].markdown(f"**Limite:** {fmt_brl_full(c['credit_limit'])}")

        # KPIs
        n_sel = len(sel_indices_sorted)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Receita no Período", fmt_brl(period_total), f"Total histórico: {fmt_brl(total)}")
        k2.metric("Ticket Médio/Mês", fmt_brl(avg_ticket), f"{months_active} meses com compra")
        k3.metric("Última Compra", c['last_purchase'], f"{c['months_since']} meses atrás" if c['months_since'] < 999 else "Nunca")
        k4.metric("Frequência no Período", f"{months_active}/{n_sel}", f"{months_active/n_sel*100:.0f}% dos meses" if n_sel > 0 else "")

        # Trend chart
        ma3 = []
        for i in range(len(monthly)):
            if i < 2:
                ma3.append(monthly[i])
            else:
                ma3.append((monthly[i] + monthly[i-1] + monthly[i-2]) / 3)

        # Color bars: selected period = bold, others = subtle
        bar_colors = ['#3b82f6' if i in set(sel_indices_sorted) else 'rgba(59,130,246,0.2)' for i in range(len(monthly))]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=months, y=monthly, name='Receita Mensal', marker_color=bar_colors))
        fig.add_trace(go.Scatter(x=months, y=ma3, name='Média Móvel (3m)', line=dict(color='#f97316', width=2), mode='lines'))
        fig.update_layout(title="Evolução de Vendas", height=400,
                         template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                         yaxis=dict(gridcolor='#e2e8f0'),
                         hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)

        # Yearly comparison
        col1, col2 = st.columns(2)
        yt = c['yearly_totals'] if isinstance(c['yearly_totals'], dict) else {}
        am = c['avg_month'] if isinstance(c['avg_month'], dict) else {}

        with col1:
            years = ['2021','2022','2023','2024','2025','2026']
            fig_yr = px.bar(x=years, y=[yt.get(y,0) for y in years],
                           title="Receita por Ano", color_discrete_sequence=['#3b82f6'])
            fig_yr.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                                showlegend=False, height=300, yaxis=dict(gridcolor='#e2e8f0'))
            st.plotly_chart(fig_yr, use_container_width=True)

        with col2:
            fig_am = px.bar(x=['2021','2022','2023','2024','2025'], y=[am.get(y,0) for y in ['2021','2022','2023','2024','2025']],
                           title="Ticket Médio por Ano", color_discrete_sequence=['#22c55e'])
            fig_am.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                                showlegend=False, height=300, yaxis=dict(gridcolor='#e2e8f0'))
            st.plotly_chart(fig_am, use_container_width=True)

        # Client insights
        st.subheader("🧠 Insights do Cliente")

        last6 = sum(monthly[-6:])
        prev6 = sum(monthly[-12:-6])
        if prev6 > 0:
            change = (last6 - prev6) / prev6
            if change < -0.3:
                st.markdown(insight_html('danger', 'QUEDA ACENTUADA',
                    f"Volume caiu {abs(change)*100:.0f}% nos últimos 6 meses ({fmt_brl(last6)}) vs anteriores ({fmt_brl(prev6)}).",
                    "Ação urgente: agendar visita ou ligação para entender a causa."), unsafe_allow_html=True)
            elif change < -0.1:
                st.markdown(insight_html('warning', 'TENDÊNCIA DE QUEDA',
                    f"Volume reduziu {abs(change)*100:.0f}% nos últimos 6 meses.",
                    "Monitorar e investigar causas possíveis."), unsafe_allow_html=True)
            elif change > 0.2:
                st.markdown(insight_html('success', 'CRESCIMENTO',
                    f"Volume cresceu {change*100:.0f}%! De {fmt_brl(prev6)} para {fmt_brl(last6)}.",
                    "Aproveitar momento para ampliar mix de produtos."), unsafe_allow_html=True)

        if months_active / len(months) < 0.3 and total > 10000:
            st.markdown(insight_html('warning', 'BAIXA RECORRÊNCIA',
                f"Comprou em apenas {months_active} de {len(months)} meses ({months_active/len(months)*100:.0f}%), mas tem ticket relevante.",
                "Oportunidade: criar rotina de compras recorrentes."), unsafe_allow_html=True)

        if c['months_since'] >= 3 and c['months_since'] < 6 and c['status'] == 'Ativo':
            st.markdown(insight_html('warning', 'ATENÇÃO - INATIVIDADE',
                f"Cliente ativo sem compras há {c['months_since']} meses. Última: {c['last_purchase']}.",
                "Entrar em contato antes que vire churn."), unsafe_allow_html=True)
        elif c['months_since'] >= 6 and c['status'] == 'Ativo':
            st.markdown(insight_html('danger', 'URGENTE - RECUPERAÇÃO',
                f"Cliente ativo sem compras há {c['months_since']} meses! Risco iminente de perda.",
                "Ação imediata: contato direto + oferta especial."), unsafe_allow_html=True)

        avg_all = df[df['status']=='Ativo']['monthly'].apply(sum).mean() / len(months)
        if avg_ticket > avg_all * 2:
            st.markdown(insight_html('success', 'CLIENTE PREMIUM',
                f"Ticket médio de {fmt_brl(avg_ticket)} é {avg_ticket/avg_all:.1f}x acima da média ({fmt_brl(avg_all)}).",
                "Cliente estratégico: garantir atendimento diferenciado."), unsafe_allow_html=True)

        if c['status'] == 'Ativo' and c['months_since'] < 3 and (prev6 == 0 or (last6 - prev6) / prev6 >= -0.1):
            st.markdown(insight_html('success', 'CLIENTE SAUDÁVEL',
                f"Cliente ativo com compras recentes ({c['last_purchase']}). Manter relacionamento.",
                "Explorar oportunidades de mix de produtos."), unsafe_allow_html=True)

        # ============================================================
        # SEÇÃO: DETALHES DE PRODUTOS COM SKU E QUANTIDADE (from df_sku)
        # ============================================================
        st.subheader("📦 Produtos Comprados (Detalhes por SKU)")
        
        if len(df_sku) > 0:
            # Get products this client bought
            client_skus = df_sku[df_sku['cod_cliente'].astype(str).str.strip() == str(client_id).strip()].copy()
            
            if len(client_skus) > 0:
                # Aggregate by SKU and product
                sku_detail = client_skus.groupby(['sku', 'produto']).agg({
                    'quantidade': 'sum',
                    'mes': 'nunique'
                }).reset_index()
                sku_detail.columns = ['SKU', 'Produto', 'Qtd Total', 'Meses']
                
                # Calculate global mix % (from total all quantities across all clients/products)
                total_all_qty = df_sku['quantidade'].sum()
                sku_detail['% Mix Global'] = (sku_detail['Qtd Total'] / total_all_qty * 100).round(2) if total_all_qty > 0 else 0
                
                sku_detail = sku_detail.sort_values('Qtd Total', ascending=False)
                
                st.dataframe(sku_detail, use_container_width=True, hide_index=True, 
                           height=min(400, 35 * len(sku_detail) + 38))
            else:
                st.info("Nenhum dado de quantidade por SKU disponível para este cliente.")
        else:
            st.info("Dados de SKU não carregados.")

# ============================================================
# PAGE: MIX
# ============================================================
def page_mix(df, products_df, df_client_products, df_sku, months, sel_indices_sorted, sel_months):
    st.header("🧩 Oportunidades de Mix de Produtos")

    _abc_meta = load_abc_valor()
    if _abc_meta:
        st.caption(f"Curvas A/B/C e estimativas em R$ calculadas pelo **faturamento real** do canal "
                   f"Distribuição ({_abc_meta.get('periodo', 'últimos 12 meses')}, Base Mãe).")

    def _period_sum(m):
        return sum(m[i] for i in sel_indices_sorted if i < len(m))

    active_clients = df[df['status'] == 'Ativo'].copy()
    active_clients['total'] = active_clients['monthly'].apply(_period_sum)
    active_clients = active_clients.sort_values('total', ascending=False)

    period_label = f"{sel_months[0]} - {sel_months[-1]}" if len(sel_months) > 1 else (sel_months[0] if sel_months else "")

    selected = st.selectbox("Selecione um cliente:", active_clients['name'].tolist(), key="mix_client")
    if not selected:
        return

    c = df[df['name'] == selected].iloc[0]
    client_id = str(c['id']).strip()
    total = _period_sum(c['monthly'])
    months_active = sum(1 for i in sel_indices_sorted if i < len(c['monthly']) and c['monthly'][i] > 0)
    avg = total / months_active if months_active > 0 else 0
    is_admin = has_full_data_access()

    # Motor de valor: preço médio real por SKU + estatísticas dos compradores
    preco_map = _preco_medio_map(products_df)
    typical, buyers_n, per_buyer = _sku_stats(df_sku)
    client_pm = {}
    if len(per_buyer) > 0:
        _mine = per_buyer[per_buyer['cod_cliente'] == client_id]
        client_pm = dict(zip(_mine['sku'], _mine['pm']))

    # Produtos que o cliente compra (histórico completo)
    cp_client = pd.DataFrame()
    if len(df_client_products) > 0:
        cp_client = df_client_products[df_client_products['client_id'].astype(str).str.strip() == client_id].copy()
    bought_codes = set(cp_client['product_code']) if len(cp_client) > 0 else set(client_pm.keys())
    has_product_data = len(bought_codes) > 0

    # ---- OPORTUNIDADES: produtos A/B onde há dinheiro na mesa ----
    ops = []
    if has_product_data:
        catalog = products_df[products_df['abc'].isin(['A', 'B'])]
        for code, name, abc in zip(catalog['code'], catalog['name'], catalog['abc']):
            prc = preco_map.get(code)
            typ = typical.get(code)
            nb = buyers_n.get(code, 0)
            if not prc or not typ or typ <= 0 or nb < 5:
                continue  # sem base estatística suficiente
            if code not in bought_codes:
                pot = typ * prc
                tipo = '🆕 Não compra'
                why = f"{nb} clientes compram (típico {typ:.0f}/mês)"
            else:
                atual = client_pm.get(code)
                if atual is None or atual >= typ * 0.5:
                    continue  # já compra em nível razoável
                pot = (typ - atual) * prc
                tipo = '📉 Compra pouco'
                why = f"compra {atual:.1f}/mês vs típico {typ:.0f}/mês"
            if pot < 100:
                continue  # materialidade mínima: R$ 100/mês
            ops.append({
                'Tipo': tipo,
                'Código': code,
                'Produto': name,
                'Curva': abc,
                'Por quê': why,
                'R$ Potencial/Mês': round(pot, 2),
            })
    ops_df = pd.DataFrame(ops)
    if len(ops_df) > 0:
        ops_df = ops_df.sort_values('R$ Potencial/Mês', ascending=False)
    pot_total = ops_df['R$ Potencial/Mês'].sum() if len(ops_df) > 0 else 0

    # ---- KPIs ----
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"Receita ({period_label})", fmt_brl(total))
    k2.metric("Ticket Médio/Mês", fmt_brl(avg), f"{months_active} meses com compra")
    k3.metric("Produtos Comprados", f"{len(bought_codes)}", f"de {len(products_df)} no catálogo")
    k4.metric("💰 Potencial de Mix", f"{fmt_brl(pot_total)}/mês", f"{len(ops_df)} oportunidades")

    st.divider()

    # ---- SEÇÃO 1: O QUE OFERECER (a receita vem primeiro) ----
    st.subheader("🎯 O que oferecer para este cliente")
    if not has_product_data:
        st.info("Sem histórico de produtos para este cliente — não é possível calcular oportunidades.")
    elif len(ops_df) == 0:
        st.success("Este cliente já compra os produtos Curva A/B em nível típico — sem gaps relevantes.")
    else:
        st.caption("Produtos **Curva A/B** com 5+ compradores, priorizados pelo R$ estimado "
                   "(quantidade típica dos compradores × preço médio real). Entram na lista apenas "
                   "oportunidades acima de R$ 100/mês.")
        show_money_table(ops_df.head(15), ['R$ Potencial/Mês'], use_container_width=True, hide_index=True,
                         height=min(560, 35 * min(len(ops_df), 15) + 38))
        if len(ops_df) > 15:
            st.caption(f"Mostrando as 15 maiores de {len(ops_df)} oportunidades — baixe a lista completa.")
        _csv_download(ops_df, "⬇️ Baixar oportunidades (Excel/CSV)", "oportunidades_mix.csv", "dl_mix_ops")

    st.divider()

    # ---- SEÇÃO 2: RAIO-X — o que o cliente compra hoje (em valor) ----
    st.subheader("📊 O que o cliente compra hoje")
    if len(cp_client) == 0:
        st.info("Sem dados de produtos comprados para este cliente.")
        return

    cp = cp_client.merge(
        products_df[['code', 'abc']].rename(columns={'code': 'product_code'}),
        on='product_code', how='left'
    )
    cp['abc'] = cp['abc'].fillna('C')
    cp['preco'] = cp['product_code'].map(preco_map)
    cp['valor_est'] = (cp['total_qty'] * cp['preco']).fillna(0)
    _tot_val = cp['valor_est'].sum()
    cp['mix_pct'] = (cp['valor_est'] / _tot_val * 100).round(1) if _tot_val > 0 else 0.0
    cp = cp.sort_values('valor_est', ascending=False)

    top12 = cp.head(12)
    if is_admin:
        fig_top = px.bar(top12, y='product_name', x='valor_est', orientation='h', color='abc',
                         title="Top 12 do Cliente (R$ estimado, histórico)",
                         color_discrete_map={'A': '#22c55e', 'B': '#eab308', 'C': '#ef4444'})
        fig_top.update_traces(hovertemplate='%{y}: R$ %{x:,.0f}<extra></extra>')
        fig_top.update_layout(xaxis=dict(title='R$ estimado'))
    else:
        fig_top = px.bar(top12, y='product_name', x='mix_pct', orientation='h', color='abc',
                         title="Top 12 do Cliente (% do mix em valor)",
                         color_discrete_map={'A': '#22c55e', 'B': '#eab308', 'C': '#ef4444'})
        fig_top.update_traces(hovertemplate='%{y}: %{x:.1f}%<extra></extra>')
        fig_top.update_layout(xaxis=dict(title='% do mix'))
    fig_top.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                          yaxis=dict(autorange='reversed', title=''), height=420, showlegend=True)
    st.plotly_chart(fig_top, use_container_width=True)

    if is_admin:
        disp_cp = cp[['product_code', 'product_name', 'abc', 'total_qty', 'valor_est', 'mix_pct']].copy()
        disp_cp.columns = ['Código', 'Produto', 'Curva', 'Qtd Total', 'R$ Estimado', '% Mix (valor)']
        show_money_table(disp_cp, ['R$ Estimado'], use_container_width=True, hide_index=True,
                         height=min(420, 35 * len(disp_cp) + 38))
    else:
        disp_cp = cp[['product_code', 'product_name', 'abc', 'mix_pct']].copy()
        disp_cp.columns = ['Código', 'Produto', 'Curva', '% Mix (valor)']
        st.dataframe(disp_cp, use_container_width=True, hide_index=True,
                     height=min(420, 35 * len(disp_cp) + 38))

# ============================================================
# PAGE: CHURN
# ============================================================
def page_churn(df, months, sel_indices_sorted, sel_months):
    st.header("⚠️ Gestão de Churn")

    period_label = f"{sel_months[0]} - {sel_months[-1]}" if len(sel_months) > 1 else (sel_months[0] if sel_months else "")

    def _period_sum(m):
        return sum(m[i] for i in sel_indices_sorted if i < len(m))

    # Load inactive clients
    inactive_ids = load_inactive_clients()

    # Separate inactive from active
    df['_client_id_str'] = df['id'].astype(str).str.strip()
    df_active = df[~df['_client_id_str'].isin(inactive_ids)].copy()
    df_inactive = df[df['_client_id_str'].isin(inactive_ids)].copy()

    recup = df_active[df_active['risk'] == 'Recuperação'].copy()
    atencao = df_active[df_active['risk'] == 'Atenção'].copy()
    saudavel = df_active[df_active['risk'] == 'Saudável']

    recup_impact = recup['monthly'].apply(annual_value_estimate).sum()
    atencao_impact = atencao['monthly'].apply(annual_value_estimate).sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 Recuperação (6+ meses)", f"{len(recup)}", f"Impacto: {fmt_brl(recup_impact)}/ano")
    k2.metric("🟡 Atenção (3-5 meses)", f"{len(atencao)}", f"Impacto: {fmt_brl(atencao_impact)}/ano")
    k3.metric("🟢 Saudáveis", f"{len(saudavel)}")
    k4.metric("💰 Receita Total em Risco", fmt_brl(recup_impact + atencao_impact), "Estimativa anual")

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["🔴 Recuperação", "🟡 Atenção", "📊 Ranking Vendedores", f"🚫 Inativos ({len(df_inactive)})"])

    # --- Helper to render a churn table with inactivate buttons ---
    def _render_churn_table(data, tab_key):
        if len(data) == 0:
            st.success(f"Nenhum cliente nesta categoria!")
            return

        data['total_rev'] = data['monthly'].apply(_period_sum)
        data['impact'] = data['monthly'].apply(annual_value_estimate)
        data['vendor_short'] = data['vendor'].str.replace(' Propetz Distribuição','').str.replace(' La Maison Propetz','')
        data = data.sort_values('total_rev', ascending=False)

        # Busca: filtra a tabela E o seletor de inativação ao mesmo tempo
        _busca_c = st.text_input("🔍 Buscar cliente (nome, UF, vendedor ou código)", key=f"churn_search_{tab_key}",
                                 placeholder="Digite parte do nome para filtrar a lista...")
        data = _filter_clients_by_term(data, _busca_c)
        if len(data) == 0:
            st.info("Nenhum cliente encontrado com esse termo.")
            return

        # Multiselect to choose clients to inactivate
        _is_full = can_approve_inactivations()
        client_names = data['name'].tolist()
        selected_to_inactivate = st.multiselect(
            "Selecione clientes para INATIVAR:" if _is_full else "Selecione clientes para SOLICITAR inativação:",
            options=client_names,
            key=f"inactivate_{tab_key}",
            help="Clientes inativados saem das listas de churn e ações" if _is_full
                 else "A solicitação vai para aprovação do administrador"
        )

        if selected_to_inactivate:
            if _is_full:
                if st.button(f"🚫 Inativar {len(selected_to_inactivate)} cliente(s)", key=f"btn_inactivate_{tab_key}", type="primary"):
                    new_inactive = inactive_ids.copy()
                    for name in selected_to_inactivate:
                        match = data[data['name'] == name]
                        if len(match) > 0:
                            cid = str(match.iloc[0]['id']).strip()
                            new_inactive.add(cid)
                    save_inactive_clients(new_inactive)
                    st.success(f"{len(selected_to_inactivate)} cliente(s) marcado(s) como inativo(s)!")
                    st.rerun()
            else:
                if st.button(f"📨 Solicitar inativação de {len(selected_to_inactivate)} cliente(s)",
                             key=f"btn_inactivate_{tab_key}", type="primary"):
                    sent = 0
                    for name in selected_to_inactivate:
                        match = data[data['name'] == name]
                        if len(match) > 0 and add_inactivation_request(
                                str(match.iloc[0]['id']).strip(), name, match.iloc[0].get('vendor', '')):
                            sent += 1
                    st.success(f"{sent} solicitação(ões) enviada(s) para aprovação do administrador.")
                    st.rerun()

        display = data[['name','state','vendor_short','last_purchase','months_since','impact','total_rev']].copy()
        display.columns = ['Cliente','UF','Vendedor','Última Compra','Meses Inativo','Impacto Anual Est.',f'Receita ({period_label})']
        show_money_table(display, ['Impacto Anual Est.', f'Receita ({period_label})'],
                         use_container_width=True, hide_index=True, height=500)

    with tab1:
        _render_churn_table(recup, "recup")

    with tab2:
        _render_churn_table(atencao, "atencao")

    with tab3:
        vendor_risk = df_active.groupby('vendor').apply(lambda g: pd.Series({
            'total': len(g),
            'recuperacao': len(g[g['risk']=='Recuperação']),
            'atencao': len(g[g['risk']=='Atenção']),
            'impact': g[g['risk'].isin(['Recuperação','Atenção'])]['monthly'].apply(annual_value_estimate).sum()
        })).reset_index()
        vendor_risk['vendor_short'] = vendor_risk['vendor'].str.replace(' Propetz Distribuição','').str.replace(' La Maison Propetz','')
        vendor_risk['pct_risco'] = ((vendor_risk['recuperacao'] + vendor_risk['atencao']) / vendor_risk['total'] * 100).round(1)
        vendor_risk = vendor_risk[vendor_risk['total'] > 0].sort_values('pct_risco', ascending=False)

        display = vendor_risk[['vendor_short','total','recuperacao','atencao','pct_risco']].copy()
        display.columns = ['Vendedor','Total Clientes','Recuperação','Atenção','% em Risco']
        st.dataframe(display, use_container_width=True, hide_index=True)

        fig = px.bar(vendor_risk, x='vendor_short', y=['recuperacao','atencao'],
                    title="Clientes em Risco por Vendedor",
                    color_discrete_map={'recuperacao':'#ef4444','atencao':'#eab308'},
                    labels={'value':'Clientes','vendor_short':'Vendedor'},
                    barmode='stack')
        fig.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff', height=350)
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.subheader("🚫 Clientes Inativados")
        st.caption("Clientes marcados como inativos são removidos das tabelas de Churn. Você pode reativá-los aqui.")

        if len(df_inactive) == 0:
            st.info("Nenhum cliente inativado ainda.")
        else:
            df_inactive['total_rev'] = df_inactive['monthly'].apply(_period_sum)
            df_inactive['vendor_short'] = df_inactive['vendor'].str.replace(' Propetz Distribuição','').str.replace(' La Maison Propetz','')
            df_inactive_sorted = df_inactive.sort_values('name')

            _busca_i = st.text_input("🔍 Buscar cliente inativado (nome, UF, vendedor ou código)", key="inativ_search",
                                     placeholder="Digite parte do nome para filtrar...")
            df_inactive_sorted = _filter_clients_by_term(df_inactive_sorted, _busca_i)
            if len(df_inactive_sorted) == 0:
                st.info("Nenhum cliente inativado encontrado com esse termo.")
                return

            # Multiselect to reactivate (somente admin)
            if can_approve_inactivations():
                inactive_names = df_inactive_sorted['name'].tolist()
                selected_to_reactivate = st.multiselect(
                    "Selecione clientes para REATIVAR:",
                    options=inactive_names,
                    key="reactivate_clients",
                    help="Selecione clientes para devolvê-los às tabelas de Churn"
                )

                if selected_to_reactivate:
                    if st.button(f"✅ Reativar {len(selected_to_reactivate)} cliente(s)", key="btn_reactivate", type="primary"):
                        new_inactive = inactive_ids.copy()
                        for name in selected_to_reactivate:
                            match = df_inactive[df_inactive['name'] == name]
                            if len(match) > 0:
                                cid = str(match.iloc[0]['id']).strip()
                                new_inactive.discard(cid)
                        save_inactive_clients(new_inactive)
                        st.success(f"{len(selected_to_reactivate)} cliente(s) reativado(s)!")
                        st.rerun()
            else:
                st.caption("Reativação de clientes é feita pelo administrador.")

            display_inact = df_inactive_sorted[['name','state','vendor_short','risk','last_purchase','months_since','total_rev']].copy()
            display_inact.columns = ['Cliente','UF','Vendedor','Risco Original','Última Compra','Meses Inativo',f'Receita ({period_label})']
            show_money_table(display_inact, [f'Receita ({period_label})'],
                             use_container_width=True, hide_index=True, height=500)

# ============================================================
# PAGE: PRODUTOS
# ============================================================
def page_products(products_df, df_sku):
    st.header("📦 Análise de Produtos")

    is_admin = has_full_data_access()

    # Critério da curva: faturamento (abc_valor.json) ou quantidade (fallback)
    abc_meta = load_abc_valor()
    has_val = abc_meta is not None and 'valor_12m' in products_df.columns and products_df['valor_12m'].sum() > 0
    if has_val:
        st.caption(f"Curva ABC calculada por **faturamento** do canal Distribuição — "
                   f"{abc_meta.get('periodo', 'últimos 12 meses')} (Base Mãe, atualizado em "
                   f"{abc_meta.get('gerado_em', '—')}). A = 80% do faturamento acumulado, B = 15%, C = 5%. "
                   f"Produtos sem venda no período ficam na curva C.")
        abc_base = products_df['valor_12m']
        base_label = "do faturamento"
    else:
        st.caption("Curva ABC por quantidade (planilha). Gere o abc_valor.json para usar faturamento.")
        abc_base = products_df['total_qty']
        base_label = "do volume"

    count_a = len(products_df[products_df['abc']=='A'])
    count_b = len(products_df[products_df['abc']=='B'])
    count_c = len(products_df[products_df['abc']=='C'])
    total_qty = products_df['total_qty'].sum()
    total_base = abc_base.sum()
    pct_a = abc_base[products_df['abc']=='A'].sum() / total_base * 100 if total_base > 0 else 0
    pct_b = abc_base[products_df['abc']=='B'].sum() / total_base * 100 if total_base > 0 else 0
    pct_c = abc_base[products_df['abc']=='C'].sum() / total_base * 100 if total_base > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Produtos", f"{len(products_df)}")
    k2.metric("Curva A", f"{count_a}", f"{pct_a:.1f}% {base_label}")
    k3.metric("Curva B", f"{count_b}", f"{pct_b:.1f}% {base_label}")
    k4.metric("Curva C", f"{count_c}", f"{pct_c:.1f}% {base_label}")

    col1, col2 = st.columns(2)

    with col1:
        _df_abc = products_df.copy()
        _df_abc['_base'] = abc_base
        abc_data = _df_abc.groupby('abc')['_base'].sum().reset_index().rename(columns={'_base': 'total_qty'})
        abc_data['pct'] = (abc_data['total_qty'] / abc_data['total_qty'].sum() * 100).round(1)
        fig_abc = px.pie(abc_data, values='total_qty', names='abc',
                        title=f"Curva ABC - % {base_label.replace('do ', '')}",
                        color='abc', color_discrete_map={'A':'#22c55e','B':'#eab308','C':'#ef4444'})
        fig_abc.update_traces(textinfo='label+percent', hovertemplate='Curva %{label}: %{percent}<extra></extra>')
        fig_abc.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff', height=400)
        st.plotly_chart(fig_abc, use_container_width=True)

    with col2:
        top20 = products_df.head(20).copy()
        if is_admin:
            fig_top = px.bar(top20, y='name', x='total_qty', orientation='h', color='abc',
                            title="Top 20 Produtos (Volume)",
                            color_discrete_map={'A':'#22c55e','B':'#eab308','C':'#ef4444'})
            fig_top.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                                 yaxis=dict(autorange='reversed', title=''), height=500, showlegend=True)
        else:
            # Vendor view: show % of total instead of quantities
            top20['pct'] = (top20['total_qty'] / total_qty * 100).round(2)
            fig_top = px.bar(top20, y='name', x='pct', orientation='h', color='abc',
                            title="Top 20 Produtos (% do Volume Total)",
                            color_discrete_map={'A':'#22c55e','B':'#eab308','C':'#ef4444'})
            fig_top.update_traces(hovertemplate='%{y}: %{x:.2f}%<extra></extra>')
            fig_top.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                                 yaxis=dict(autorange='reversed', title=''),
                                 xaxis=dict(title='% do Volume'), height=500, showlegend=True)
        st.plotly_chart(fig_top, use_container_width=True)

    st.subheader("Catálogo Completo")
    search = st.text_input("🔍 Buscar produto", key="prod_search")

    if is_admin:
        cols = ['code','name','category','abc','total_qty'] + (['valor_12m'] if has_val else [])
        display = products_df[cols].copy()
        if has_val:
            display = display.sort_values('valor_12m', ascending=False)
    else:
        # Vendor view: show % instead of raw quantities
        display = products_df[['code','name','category','abc','total_qty']].copy()
        display['pct_volume'] = (display['total_qty'] / total_qty * 100).round(2)
        display = display.drop(columns=['total_qty'])

    if search:
        s = search.lower()
        display = display[
            display['name'].str.lower().str.contains(s, na=False) |
            display['code'].str.lower().str.contains(s, na=False) |
            display['category'].str.lower().str.contains(s, na=False)
        ]

    if is_admin:
        display.columns = ['Código','Produto','Categoria','Curva','Volume Total'] + (['Faturamento 12m'] if has_val else [])
        show_money_table(display, ['Faturamento 12m'], use_container_width=True, hide_index=True, height=500)
    else:
        display.columns = ['Código','Produto','Categoria','Curva','% do Volume']
        st.dataframe(display, use_container_width=True, hide_index=True, height=500)

    # ---- ANÁLISE DE GAP GLOBAL (visão de portfólio do gestor) ----
    if is_admin and len(df_sku) > 0:
        st.divider()
        st.subheader("📉 Análise de Gap — Potencial da Base Inteira")
        st.caption("Produtos com 5+ compradores: se os demais compradores chegassem ao nível do top 25%, "
                   "quanto a mais venderíamos por mês. Use para escolher campanhas de produto.")
        sku_cov = max(df_sku['mes'].nunique(), 1)
        preco_map = _preco_medio_map(products_df)
        nome_map = df_sku.groupby('sku')['produto'].first().to_dict()
        per = df_sku.groupby(['sku', 'cod_cliente'])['quantidade'].sum().reset_index()
        gap_rows = []
        for sku_code, grp in per.groupby('sku'):
            if grp['cod_cliente'].nunique() < 5:
                continue
            qs = grp['quantidade'].sort_values(ascending=False)
            n_top = max(1, int(len(qs) * 0.25))
            top25 = qs.head(n_top).mean()
            avg_all = qs.mean()
            extra_q = (top25 - avg_all) * len(qs) / sku_cov
            prc = preco_map.get(str(sku_code), 0)
            gap_rows.append({
                'Produto': nome_map.get(sku_code, ''),
                'SKU': sku_code,
                'Clientes': grp['cod_cliente'].nunique(),
                'Média/Cliente': round(avg_all, 1),
                'Média Top 25%': round(top25, 1),
                'Qtd Extra/Mês': round(extra_q, 1),
                'R$ Potencial/Mês': round(extra_q * prc, 2),
            })
        if gap_rows:
            gap_df = pd.DataFrame(gap_rows).sort_values('R$ Potencial/Mês', ascending=False)
            show_money_table(gap_df.head(30), ['R$ Potencial/Mês'], use_container_width=True,
                             hide_index=True, height=500)
            _csv_download(gap_df, "⬇️ Baixar análise completa (Excel/CSV)", "gap_portfolio.csv", "dl_gap")

# ============================================================
# PAGE: ADMIN
# ============================================================
def page_admin():
    st.header("⚙️ Administração")

    st.subheader("Gerenciar Usuários")
    users = load_users()

    # Show current users
    user_data = []
    for username, info in users["users"].items():
        user_data.append({
            "Usuário": username,
            "Nome": info["name"],
            "Papel": info["role"],
            "Filtro Vendedor": info.get("vendor_filter", "Todos")
        })
    st.dataframe(pd.DataFrame(user_data), use_container_width=True, hide_index=True)

    st.divider()

    # Add new user
    st.subheader("Adicionar Novo Usuário")
    with st.form("add_user"):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("Usuário (login)")
            new_name = st.text_input("Nome completo")
        with col2:
            new_password = st.text_input("Senha", type="password")
            new_role = st.selectbox("Papel", ["vendedor", "admin"])

        new_vendor = st.text_input("Filtro de vendedor (deixe vazio para admin)",
                                   help="Nome exato do vendedor na planilha, ex: 'Emanuel Propetz Distribuição'")

        if st.form_submit_button("Adicionar Usuário", type="primary"):
            if new_username and new_name and new_password:
                users["users"][new_username] = {
                    "name": new_name,
                    "password": hash_password(new_password),
                    "role": new_role,
                    "vendor_filter": new_vendor if new_vendor else None
                }
                save_users(users)
                st.success(f"Usuário '{new_username}' criado com sucesso!")
                st.rerun()
            else:
                st.error("Preencha todos os campos.")

    st.divider()

    # Change password
    st.subheader("Alterar Senha")
    with st.form("change_pwd"):
        pwd_user = st.selectbox("Usuário", list(users["users"].keys()))
        new_pwd = st.text_input("Nova senha", type="password", key="new_pwd")
        if st.form_submit_button("Alterar Senha"):
            if new_pwd:
                users["users"][pwd_user]["password"] = hash_password(new_pwd)
                save_users(users)
                st.success(f"Senha de '{pwd_user}' alterada!")

    st.divider()

    # ============================================================
    # DIAGNÓSTICO DE PERSISTÊNCIA (GitHub)
    # ============================================================
    st.subheader("🔌 Persistência (salvamento permanente)")
    if _gh_token():
        st.caption("Há um token configurado. Clique para testar se ele realmente salva no GitHub — "
                   "o teste tenta gravar um arquivo de verdade no branch 'state'.")
    else:
        st.warning("Nenhum token detectado nos secrets agora. Inativações, usuários e logs "
                   "serão perdidos no próximo reinício. Configure o GITHUB_TOKEN (ver COMO-USAR.md) "
                   "e use o botão abaixo para validar.")
    if st.button("🔍 Testar conexão com o GitHub", key="btn_gh_diag"):
        with st.spinner("Testando..."):
            resultados = _gh_diagnose()
        for ok, titulo, detalhe in resultados:
            if ok:
                st.success(f"**{titulo}** — {detalhe}")
            else:
                st.error(f"**{titulo}** — {detalhe}")
        if resultados and resultados[-1][0] and 'Escrita' in resultados[-1][1]:
            st.info("Tudo certo! Agora refaça as inativações uma vez — daqui em diante elas ficam permanentes.")

    st.divider()

    # Upload new data
    st.subheader("Atualizar Base de Dados")
    if _gh_token():
        st.caption("✅ Persistência ativada: a planilha enviada é salva no GitHub e sobrevive a reinícios do servidor.")
    else:
        st.warning("⚠️ GITHUB_TOKEN não configurado nos secrets do Streamlit Cloud. "
                   "O upload vale só até o próximo reinício do servidor — para tornar permanente, "
                   "salve a planilha na pasta do projeto e rode o deploy.bat, ou configure o token (ver COMO-USAR.md).")
    uploaded = st.file_uploader("Envie a planilha atualizada (.xlsx)", type=['xlsx'])
    if uploaded:
        pushed = _handle_planilha_upload(uploaded)
        if pushed:
            st.success("Planilha atualizada e salva no GitHub! O app pode reiniciar em ~1 min para aplicar — os dados ficam permanentes.")
        else:
            st.success("Planilha atualizada nesta sessão! (Sem token GitHub: será perdida no próximo reinício.)")
        st.rerun()

    st.divider()

    # ============================================================
    # ACCESS MONITORING PANEL
    # ============================================================
    st.subheader("📡 Monitoramento de Acessos")
    st.caption("Acompanhe quando e como o time está utilizando o sistema")

    access_log = _load_access_log()

    if len(access_log) == 0:
        st.info("Nenhum acesso registrado ainda. Os logs começam a ser gerados a partir do próximo login.")
    else:
        df_log = pd.DataFrame(access_log)

        # --- Filters ---
        log_col1, log_col2 = st.columns(2)
        with log_col1:
            _all_users_log = sorted(df_log['user'].unique().tolist())
            _filter_users = st.multiselect("Filtrar por usuário", options=_all_users_log, default=_all_users_log, key="log_filter_users")
        with log_col2:
            _all_dates = sorted(df_log['date'].unique().tolist(), reverse=True)
            _default_dates = _all_dates[:7] if len(_all_dates) > 7 else _all_dates
            _filter_dates = st.multiselect("Filtrar por data", options=_all_dates, default=_default_dates, key="log_filter_dates")

        df_filtered = df_log[df_log['user'].isin(_filter_users) & df_log['date'].isin(_filter_dates)].copy()

        # --- KPIs ---
        _logins = df_filtered[df_filtered['action'] == 'login']
        _page_views = df_filtered[df_filtered['action'] == 'page_view']
        _unique_users = _logins['user'].nunique()
        _total_logins = len(_logins)
        _total_views = len(_page_views)

        mk1, mk2, mk3 = st.columns(3)
        mk1.metric("👥 Usuários Ativos", f"{_unique_users}")
        mk2.metric("🔑 Total de Logins", f"{_total_logins}")
        mk3.metric("📄 Páginas Visitadas", f"{_total_views}")

        # --- Logins per user per day ---
        if len(_logins) > 0:
            st.markdown("**📊 Logins por Usuário por Dia**")
            login_pivot = _logins.groupby(['date', 'name']).size().reset_index(name='logins')
            fig_logins = px.bar(login_pivot, x='date', y='logins', color='name',
                               title="Histórico de Logins",
                               labels={'date': 'Data', 'logins': 'Logins', 'name': 'Usuário'},
                               barmode='group')
            fig_logins.update_layout(template='plotly_white', paper_bgcolor='#ffffff',
                                    plot_bgcolor='#ffffff', height=350)
            st.plotly_chart(fig_logins, use_container_width=True)

        # --- Pages most visited ---
        if len(_page_views) > 0:
            st.markdown("**📄 Páginas Mais Acessadas por Usuário**")
            page_usage = _page_views.groupby(['name', 'page']).size().reset_index(name='visitas')
            page_usage = page_usage.sort_values('visitas', ascending=False)
            st.dataframe(page_usage.rename(columns={'name': 'Usuário', 'page': 'Página', 'visitas': 'Visitas'}),
                        use_container_width=True, hide_index=True, height=300)

        # --- Full log table ---
        st.markdown("**📋 Log Completo de Acessos**")
        display_log = df_filtered.sort_values('timestamp', ascending=False)
        display_cols = ['timestamp', 'name', 'action']
        if 'page' in display_log.columns:
            display_cols.append('page')
        display_log_show = display_log[display_cols].copy()
        col_names = {'timestamp': 'Data/Hora', 'name': 'Usuário', 'action': 'Ação', 'page': 'Página'}
        display_log_show = display_log_show.rename(columns=col_names)
        display_log_show['Ação'] = display_log_show['Ação'].replace({'login': '🔑 Login', 'page_view': '📄 Página'})
        st.dataframe(display_log_show, use_container_width=True, hide_index=True, height=400)

# ============================================================
# MAIN APP
# ============================================================
def main():
    # Restaura estado persistido no GitHub (1x por boot do container)
    _sync_state_from_github()

    # Check authentication — try auto-login from URL params first
    if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
        if not _auto_login_from_params():
            login_page()
            return

    # Load data
    result = load_data()
    if result[0] is None or len(result) < 6:
        st.warning("Não foi possível carregar os dados. Verifique se o arquivo Excel está na pasta do app.")
        if st.session_state.get("role") == "admin":
            st.subheader("Upload da planilha")
            uploaded = st.file_uploader("Envie a planilha (.xlsx)", type=['xlsx'])
            if uploaded:
                pushed = _handle_planilha_upload(uploaded)
                if pushed:
                    st.success("Planilha salva no GitHub! Recarregando...")
                else:
                    st.success("Planilha salva nesta sessão! Recarregando...")
                st.rerun()
        return

    df_clients, df_products, df_client_products, months, year_ranges, df_sku = result

    # Apply vendor filter for non-admin users
    if st.session_state.get("vendor_filter"):
        df_clients = df_clients[df_clients['vendor'] == st.session_state["vendor_filter"]].copy()

    # --- Parse unique years and month names from labels (e.g. "jan/21") ---
    all_years_ordered = []
    _seen_years = set()
    for lbl in months:
        parts = lbl.replace('-', '/').split('/')
        if len(parts) >= 2:
            y_raw = parts[-1].strip()
            y_full = f"20{y_raw}" if len(y_raw) == 2 else y_raw
        else:
            y_full = ""
        if y_full and y_full not in _seen_years:
            all_years_ordered.append(y_full)
            _seen_years.add(y_full)

    # ========== COMPACT SIDEBAR ==========

    # --- Map month names to numbers (jan=1, fev=2, ...) ---
    MONTH_NAME_TO_NUM = {'jan':'1','fev':'2','mar':'3','abr':'4','mai':'5','jun':'6',
                         'jul':'7','ago':'8','set':'9','out':'10','nov':'11','dez':'12'}
    # Build unique month numbers that exist in data
    _existing_month_nums = []
    _seen_mnums = set()
    for lbl in months:
        parts = lbl.replace('-', '/').split('/')
        if len(parts) >= 2:
            m_name = parts[0].strip().lower()
            m_num = MONTH_NAME_TO_NUM.get(m_name, m_name)
            if m_num not in _seen_mnums:
                _existing_month_nums.append(m_num)
                _seen_mnums.add(m_num)
    # Sort numerically
    _existing_month_nums.sort(key=lambda x: int(x) if x.isdigit() else 0)

    # Default year: most recent with 6+ months of data
    _best_default_year = all_years_ordered[-1] if all_years_ordered else ""
    for yr in reversed(all_years_ordered):
        yr_months = [lbl for lbl in months if lbl.split('/')[-1].strip() in [yr[-2:], yr]]
        if len(yr_months) >= 6:
            _best_default_year = yr
            break

    with st.sidebar:
        # --- User greeting (compact) ---
        _role = st.session_state['role']
        _role_icon = "🔑" if _role == 'admin' else ("👔" if _role == 'diretor' else "👤")
        _role_label = {'admin': 'Admin', 'diretor': 'Diretora', 'vendedor': 'Vendedor'}.get(_role, _role.title())
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:8px;padding:4px 0 8px 0">
            <div style="background:linear-gradient(135deg,#FF6B35,#FF8F5E);border-radius:50%;width:36px;height:36px;
                        display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0">{_role_icon}</div>
            <div>
                <div style="font-weight:700;font-size:14px;line-height:1.2">{st.session_state['user_name']}</div>
                <div style="font-size:11px;opacity:.6">{_role_label}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # --- Navigation ---
        if has_full_data_access():
            pages = {
                "🎛️ Painel do Gestor": "manager",
                "✅ Ações do Time": "actions",
                "📊 Visão Geral": "overview",
                "👤 Clientes": "clients",
                "🧩 Mix de Produtos": "mix",
                "⚠️ Churn": "churn",
                "📦 Produtos": "products",
            }
            if st.session_state["role"] == "admin":
                pages["⚙️ Admin"] = "admin"
        else:
            pages = {
                "✅ Minhas Ações": "actions",
                "📊 Minha Visão Geral": "overview",
                "👤 Meus Clientes": "clients",
                "🧩 Mix de Produtos": "mix",
                "⚠️ Churn": "churn",
                "📦 Produtos": "products",
            }

        selected_page = st.radio("Navegação", list(pages.keys()), label_visibility="collapsed")

        st.markdown("---")

        # --- Period Filter: compact multiselects ---
        st.markdown("**📅 Período**")

        # Chart click override indicator
        chart_override_active = "chart_sel_months" in st.session_state and st.session_state["chart_sel_months"]
        if chart_override_active:
            n_chart = len(st.session_state["chart_sel_months"])
            st.info(f"📊 Seleção via gráfico ({n_chart} {'mês' if n_chart == 1 else 'meses'})")
            if st.button("✕ Limpar seleção", use_container_width=True, key="clear_chart"):
                del st.session_state["chart_sel_months"]
                st.rerun()

        # Seletor único com presets (substitui os multiselects de ano + mês)
        _cur_year = all_years_ordered[-1] if all_years_ordered else ""
        _prev_year = all_years_ordered[-2] if len(all_years_ordered) >= 2 else ""
        preset_options = ["Últimos 12 meses"]
        if _cur_year:
            preset_options.append(f"Este ano ({_cur_year})")
        preset_options += ["Últimos 6 meses", "Últimos 3 meses", "Este mês"]
        if _prev_year:
            preset_options.append(f"Ano passado ({_prev_year})")
        preset_options += ["Tudo (desde o início)", "Personalizado…"]

        sel_preset = st.selectbox("Período", preset_options, key="global_preset",
                                  label_visibility="collapsed")

        # Modo avançado: escolher anos e meses manualmente
        selected_years, selected_month_nums = [], []
        if sel_preset == "Personalizado…":
            selected_years = st.multiselect(
                "Ano",
                options=all_years_ordered,
                default=[_best_default_year] if _best_default_year else [],
                key="global_years"
            )
            selected_month_nums = st.multiselect(
                "Mês (1-12)",
                options=_existing_month_nums,
                default=_existing_month_nums,
                key="global_months"
            )

        # --- Compact CSS to reduce multiselect pill size ---
        st.markdown("""
        <style>
        /* Smaller multiselect pills */
        section[data-testid="stSidebar"] span[data-baseweb="tag"] {
            font-size: 12px !important;
            padding: 2px 6px !important;
            margin: 1px !important;
            height: auto !important;
            line-height: 1.3 !important;
        }
        section[data-testid="stSidebar"] span[data-baseweb="tag"] span {
            font-size: 12px !important;
        }
        /* Smaller multiselect input */
        section[data-testid="stSidebar"] [data-baseweb="select"] {
            font-size: 13px !important;
        }
        section[data-testid="stSidebar"] .stMultiSelect > label {
            font-size: 13px !important;
            margin-bottom: 2px !important;
        }
        /* Compact radio buttons */
        section[data-testid="stSidebar"] .stRadio > div {
            gap: 0px !important;
        }
        section[data-testid="stSidebar"] .stRadio > div > label {
            padding: 4px 0 !important;
            font-size: 14px !important;
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # --- Data summary ---
        _total_clients = len(df_clients)
        _risk_counts = df_clients['risk'].value_counts() if 'risk' in df_clients.columns else {}
        _healthy = _risk_counts.get('Saudável', 0)
        _attention = _risk_counts.get('Atenção', 0)
        _recovery = _risk_counts.get('Recuperação', 0)

        st.markdown(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px">
            <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:6px 8px;text-align:center">
                <div style="font-size:18px;font-weight:800;color:#FF6B35">{_total_clients}</div>
                <div style="font-size:10px;opacity:.5">Clientes</div>
            </div>
            <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:6px 8px;text-align:center">
                <div style="font-size:18px;font-weight:800;color:#4CAF50">{_healthy}</div>
                <div style="font-size:10px;opacity:.5">Saudáveis</div>
            </div>
            <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:6px 8px;text-align:center">
                <div style="font-size:18px;font-weight:800;color:#FFC107">{_attention}</div>
                <div style="font-size:10px;opacity:.5">Atenção</div>
            </div>
            <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:6px 8px;text-align:center">
                <div style="font-size:18px;font-weight:800;color:#F44336">{_recovery}</div>
                <div style="font-size:10px;opacity:.5">Recuperação</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        if st.button("🚪 Sair", use_container_width=True):
            _clear_login_params()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # --- Build selected indices ---
    # Chart click override takes priority over sidebar filters
    chart_override_active = "chart_sel_months" in st.session_state and st.session_state["chart_sel_months"]

    if chart_override_active:
        sel_indices = set()
        for lbl in st.session_state["chart_sel_months"]:
            if lbl in months:
                sel_indices.add(months.index(lbl))
    elif sel_preset != "Personalizado…":
        sel_indices = compute_preset_indices(sel_preset, months)
    else:
        # Personalizado: match months by year + month number
        sel_indices = set()
        for i, lbl in enumerate(months):
            parts = lbl.replace('-', '/').split('/')
            if len(parts) >= 2:
                m_name = parts[0].strip().lower()
                y_raw = parts[-1].strip()
                y_full = f"20{y_raw}" if len(y_raw) == 2 else y_raw
                m_num = MONTH_NAME_TO_NUM.get(m_name, "")
            else:
                y_full = ""
                m_num = ""
            if y_full in selected_years and m_num in selected_month_nums:
                sel_indices.add(i)

    # Fallback: if nothing selected, select all
    if not sel_indices:
        sel_indices = set(range(len(months)))

    sel_indices_sorted = sorted(sel_indices)
    sel_months = [months[i] for i in sel_indices_sorted]

    # Header banner
    st.markdown(f"""
    <div class="propetz-header">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <h1 style="color:#fff !important; margin:0; font-size:26px; font-weight:800">PROPETZ</h1>
                <div class="sub">Painel Estratégico - Dashboard Comercial</div>
            </div>
            <div style="text-align:right;font-size:12px;opacity:.7">
                <div>Dados: {months[0]} a {months[-1]}</div>
                <div>{len(df_clients)} clientes</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Alerta de persistência: sem GITHUB_TOKEN, inativações/usuários/logs são
    # perdidos quando o servidor reinicia. Visível só para admin/diretor.
    if has_full_data_access() and not _gh_token():
        st.error(
            "⚠️ **Persistência DESATIVADA.** As inativações de clientes, novos usuários e o "
            "log de acessos ficam só na memória temporária do servidor e **são perdidos quando "
            "ele reinicia**. Para tornar permanente, configure o `GITHUB_TOKEN` nos secrets do "
            "Streamlit Cloud (passo a passo no COMO-USAR.md). Enquanto isso não for feito, evite "
            "depender das inativações."
        )

    # Route to page
    page = pages[selected_page]

    # Log page view (only once per page per session to avoid spam)
    _page_log_key = f"_logged_page_{page}"
    if _page_log_key not in st.session_state:
        st.session_state[_page_log_key] = True
        log_page_view(st.session_state.get("username", ""), selected_page)

    if page == "manager":
        page_manager(df_clients, months, df_sku, df_products)
    elif page == "actions":
        page_actions(df_clients, df_sku, df_products, df_client_products, months)
    elif page == "overview":
        page_overview(df_clients, months, year_ranges, sel_indices, sel_indices_sorted, sel_months)
    elif page == "clients":
        page_clients(df_clients, df_sku, months, year_ranges, sel_indices_sorted, sel_months)
    elif page == "mix":
        page_mix(df_clients, df_products, df_client_products, df_sku, months, sel_indices_sorted, sel_months)
    elif page == "churn":
        page_churn(df_clients, months, sel_indices_sorted, sel_months)
    elif page == "products":
        page_products(df_products, df_sku)
    elif page == "admin":
        page_admin()

if __name__ == "__main__":
    main()
