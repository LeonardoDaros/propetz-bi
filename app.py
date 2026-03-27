import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import openpyxl
import yaml
import os
import hashlib
import json
from datetime import datetime

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
            }
        }
    }

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def save_users(users_data):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(users_data, f, default_flow_style=False, allow_unicode=True)

def verify_login(username, password):
    users = load_users()
    user = users["users"].get(username)
    if user and user["password"] == hash_password(password):
        return user
    return None

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

    username = st.text_input("Usuário", key="login_user")
    password = st.text_input("Senha", type="password", key="login_pass")

    if st.button("Entrar", use_container_width=True, type="primary"):
        user = verify_login(username, password)
        if user:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.session_state["user_name"] = user["name"]
            st.session_state["role"] = user["role"]
            st.session_state["vendor_filter"] = user.get("vendor_filter")
            _set_login_params(username, user)
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")

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

    xlsx_path = None
    for p in possible_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            xlsx_path = p
            break

    if not xlsx_path:
        st.error("Arquivo Excel não encontrado. Faça upload na barra lateral.")
        return None, None, None, None, None, None

    return process_excel(xlsx_path)

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
            products.append({
                'code': str(cod).strip(),
                'name': str(name).strip() if name else '',
                'category': str(cat).strip() if cat else '',
                'total_qty': total_val,
                'abc': str(abc).strip() if abc else 'C'
            })
        products.sort(key=lambda x: -x['total_qty'])

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
        dormant_display['Receita Histórica'] = dormant_display['Receita Histórica'].apply(fmt_brl_full)
        dormant_display = dormant_display.reset_index(drop=True)
        dormant_display.index = dormant_display.index + 1
        st.dataframe(dormant_display, use_container_width=True, height=min(400, 35 * len(dormant_display) + 38))
        total_dormant_rev = dormant['total_hist'].sum()
        st.caption(f"Estes {len(dormant)} clientes já geraram {fmt_brl_full(total_dormant_rev)} em receita total. Uma ligação pode reativá-los.")
    else:
        st.success("Todos os clientes com histórico relevante estão comprando!")

    st.divider()

    # --- INSIGHTS AUTOMÁTICOS ---
    st.subheader("🧠 Insights Automáticos")
    insights = []

    # Insight: Churn risk
    at_risk = filtered[filtered['risk'] == 'Recuperação']
    if len(at_risk) > 0:
        lost = at_risk['avg_month'].apply(lambda am: (am.get('2024', 0) or am.get('2023', 0)) * 12 if isinstance(am, dict) else 0).sum()
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
    display_df[rev_col] = display_df[rev_col].apply(fmt_brl_full)

    st.dataframe(display_df, use_container_width=True, height=300, hide_index=True)

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

    is_admin = st.session_state.get('role') == 'admin'
    total_qty_all = products_df['total_qty'].sum()

    # Check if we have client×product data
    has_cp_data = len(df_client_products) > 0
    cp_client = pd.DataFrame()
    if has_cp_data:
        cp_client = df_client_products[df_client_products['client_id'] == client_id].copy()

    # --- KPIs ---
    n_products_bought = len(cp_client) if has_cp_data else 0
    n_products_total = len(products_df)
    n_curva_a = len(products_df[products_df['abc'] == 'A'])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"Receita ({period_label})", fmt_brl(total))
    k2.metric("Ticket Médio", fmt_brl(avg))
    k3.metric("Produtos Comprados", f"{n_products_bought}", f"de {n_products_total} no catálogo")
    k4.metric("Curva A no Mercado", f"{n_curva_a}")

    st.divider()

    # ============================================================
    # SEÇÃO 1: PRODUTOS QUE O CLIENTE COMPRA
    # ============================================================
    if has_cp_data and len(cp_client) > 0:
        st.subheader("📊 Produtos Comprados pelo Cliente")

        # Enrich with ABC curve
        cp_enriched = cp_client.merge(
            products_df[['code', 'abc', 'category']].rename(columns={'code': 'product_code', 'category': 'prod_category'}),
            on='product_code', how='left'
        )
        cp_enriched['abc'] = cp_enriched['abc'].fillna('C')
        cp_enriched['prod_category'] = cp_enriched['prod_category'].fillna('')

        # Calculate metrics per product (no monthly breakdown available)
        cp_enriched['share_pct'] = (cp_enriched['total_qty'] / cp_enriched['total_qty'].sum() * 100).round(1)
        cp_enriched['global_mix_pct'] = (cp_enriched['total_qty'] / total_qty_all * 100).round(1)

        cp_enriched = cp_enriched.sort_values('total_qty', ascending=False)

        # Top products chart
        top15 = cp_enriched.head(15)
        fig_top = px.bar(top15, y='product_name', x='total_qty', orientation='h', color='abc',
                        title="Top 15 Produtos do Cliente (quantidade total comprada)",
                        color_discrete_map={'A':'#22c55e','B':'#eab308','C':'#ef4444'},
                        text='total_qty')
        fig_top.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        fig_top.update_layout(template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                             yaxis=dict(autorange='reversed', title=''),
                             xaxis=dict(title='Quantidade Total Comprada'), height=450, showlegend=True)
        st.plotly_chart(fig_top, use_container_width=True)

        # Table
        if is_admin:
            display_cp = cp_enriched[['product_code','product_name','abc','total_qty','share_pct','global_mix_pct']].copy()
            display_cp.columns = ['Código','Produto','Curva','Qtd Total','% Mix Cliente','% Mix Global']
        else:
            display_cp = cp_enriched[['product_code','product_name','abc','share_pct','global_mix_pct']].copy()
            display_cp.columns = ['Código','Produto','Curva','% Mix Cliente','% Mix Global']
        st.dataframe(display_cp, use_container_width=True, hide_index=True, height=min(400, 35 * len(display_cp) + 38))

        st.divider()

        # ============================================================
        # SEÇÃO 2: PRODUTOS ABAIXO DO POTENCIAL (vs demanda do mercado)
        # ============================================================
        st.subheader("📉 Produtos Abaixo do Potencial")
        st.caption("Produtos que o cliente compra, mas em volume menor do que a demanda de mercado sugere")

        # Compare client share vs market share for each product
        total_market = products_df['total_qty'].sum()
        if total_market > 0 and len(cp_enriched) > 0:
            cp_potential = cp_enriched.drop_duplicates(subset=['product_code']).merge(
                products_df[['code','total_qty']].rename(columns={'code':'product_code','total_qty':'market_qty'}),
                on='product_code', how='left'
            )
            cp_potential['market_qty'] = cp_potential['market_qty'].fillna(0)
            cp_potential['market_share_pct'] = (cp_potential['market_qty'] / total_market * 100).round(2)
            # Gap = how much the client underbuys relative to market importance
            cp_potential['gap'] = (cp_potential['market_share_pct'] - cp_potential['share_pct']).round(2)
            # Impact = gap weighted by market relevance
            cp_potential['impact_score'] = (cp_potential['gap'] * cp_potential['market_share_pct'] / 10).round(2)

            # Show products with positive gap (client buys less than expected), broader filter
            underperforming = cp_potential[(cp_potential['gap'] > 0.5)].copy()
            underperforming = underperforming.sort_values('impact_score', ascending=False)

            if len(underperforming) > 0:
                def severity(row):
                    if row['impact_score'] >= 2:
                        return '🔴 Alto Potencial'
                    elif row['impact_score'] >= 0.5:
                        return '🟡 Potencial Médio'
                    else:
                        return '⚪ Potencial Baixo'
                underperforming['severidade'] = underperforming.apply(severity, axis=1)

                # Calcular qtd potencial de compra mensal baseado na amostragem do mercado
                total_client_qty = cp_potential['total_qty'].sum()
                n_months_data = max(len(sel_indices_sorted), 1)
                for idx_r in underperforming.index:
                    mkt_share = underperforming.loc[idx_r, 'market_share_pct'] / 100
                    current_qty = underperforming.loc[idx_r, 'total_qty']
                    potencial_mensal = (total_client_qty * mkt_share) / n_months_data
                    underperforming.loc[idx_r, 'qtd_potencial_mensal'] = round(max(potencial_mensal, current_qty / n_months_data), 1)
                    underperforming.loc[idx_r, 'qtd_atual_mensal'] = round(current_qty / n_months_data, 1)

                top_under = underperforming.head(3)
                if len(top_under) > 0:
                    names = ', '.join(top_under['product_name'].tolist())
                    st.markdown(insight_html('warning', 'PRODUTOS COM ESPAÇO PARA CRESCER',
                        f"Os produtos com maior potencial de aumento: {names}.",
                        "Estes produtos são relevantes no mercado mas o cliente compra abaixo do esperado."), unsafe_allow_html=True)

                disp_under = underperforming[['product_code','product_name','abc','total_qty','qtd_atual_mensal','qtd_potencial_mensal','share_pct','market_share_pct','gap','severidade']].head(30).copy()
                disp_under.columns = ['Código','Produto','Curva','Qtd Total','Qtd Atual/Mês','Qtd Potencial/Mês','% Mix Cliente','% Mercado','Gap (pp)','Potencial']
                st.dataframe(disp_under, use_container_width=True, hide_index=True,
                           height=min(500, 35 * len(disp_under) + 38))
            else:
                st.success("Mix do cliente está alinhado com o mercado! Nenhum gap significativo encontrado.")
        else:
            st.info("Dados de mercado insuficientes para análise de potencial.")

        st.divider()

    # ============================================================
    # SEÇÃO 3: PRODUTOS QUE O CLIENTE NUNCA COMPROU
    # ============================================================
    st.subheader("🎯 Oportunidades: Produtos que o Cliente Não Compra")
    st.caption("Produtos do catálogo que este cliente nunca adquiriu, organizados por relevância (Curva A → B → C)")

    # Get codes the client bought
    bought_codes = set(cp_client['product_code'].tolist()) if len(cp_client) > 0 else set()

    # Products never bought
    never_bought = products_df[~products_df['code'].isin(bought_codes)].copy()

    if len(never_bought) > 0:
        # Count per curve
        nb_a = never_bought[never_bought['abc'] == 'A']
        nb_b = never_bought[never_bought['abc'] == 'B']
        nb_c = never_bought[never_bought['abc'] == 'C']

        nc1, nc2, nc3 = st.columns(3)
        nc1.metric("Curva A não comprados", f"{len(nb_a)} de {n_curva_a}",
                   f"{len(nb_a)/n_curva_a*100:.0f}% de oportunidade" if n_curva_a > 0 else "")
        nc2.metric("Curva B não comprados", f"{len(nb_b)}")
        nc3.metric("Curva C não comprados", f"{len(nb_c)}")

        if len(nb_a) > 0:
            st.markdown(insight_html('warning', f'CURVA A - {len(nb_a)} PRODUTOS FALTANDO',
                f"Este cliente não compra {len(nb_a)} dos {n_curva_a} produtos mais vendidos da Propetz.",
                "Prioridade máxima: apresentar estes produtos ao cliente."), unsafe_allow_html=True)

        # Tabs for each curve
        tab_a, tab_b, tab_c = st.tabs([
            f"🟢 Curva A ({len(nb_a)})",
            f"🟡 Curva B ({len(nb_b)})",
            f"🔴 Curva C ({len(nb_c)})"
        ])

        # Calcular qtd potencial mensal baseado no % de mercado do produto * volume médio do cliente
        _client_monthly_avg = total / max(months_active, 1) if months_active > 0 else 0

        def show_never_bought(df_nb, tab):
            with tab:
                if len(df_nb) == 0:
                    st.success("Cliente já compra todos os produtos desta curva!")
                    return
                disp = df_nb[['code','name','category','total_qty']].copy()
                # Calcular potencial mensal: % mercado do produto * volume total do mercado / 14 meses
                disp['Qtd Potencial/Mês'] = (disp['total_qty'] / max(total_qty_all, 1) * disp['total_qty'] / 14).round(1)
                # Usar média dos compradores deste produto como referência
                disp['% Mercado'] = (disp['total_qty'] / max(total_qty_all, 1) * 100).round(2)
                disp = disp.drop(columns=['total_qty'])
                disp.columns = ['Código','Produto','Categoria','Qtd Potencial/Mês','% Mercado']
                st.dataframe(disp, use_container_width=True, hide_index=True, height=min(400, 35 * len(disp) + 38))

        show_never_bought(nb_a, tab_a)
        show_never_bought(nb_b, tab_b)
        show_never_bought(nb_c, tab_c)
    else:
        st.success("Incrível! Este cliente compra todos os produtos do catálogo!")

# ============================================================
# PAGE: CHURN
# ============================================================

    st.divider()

    # ============================================================
    # NOVA SEÇÃO: TOP 20 PRODUTOS POR QUANTIDADE (usando df_sku)
    # ============================================================
    if len(df_sku) > 0:
        st.subheader("📊 Top 20 Produtos por Quantidade")
        st.caption("Produtos mais comprados em quantidade geral (todos os clientes)")
        
        # Aggregate by SKU and product
        sku_qty = df_sku.groupby(['sku', 'produto']).agg({
            'quantidade': 'sum'
        }).reset_index()
        sku_qty = sku_qty.sort_values('quantidade', ascending=False).head(20)
        
        if len(sku_qty) > 0:
            # Create label with SKU + product name
            sku_qty['label'] = sku_qty['sku'] + ' - ' + sku_qty['produto']
            
            fig_top20 = px.bar(
                sku_qty,
                y='label',
                x='quantidade',
                orientation='h',
                title="Top 20 Produtos por Quantidade",
                color='quantidade',
                color_continuous_scale='Blues'
            )
            fig_top20.update_layout(
                template='plotly_white',
                paper_bgcolor='#ffffff',
                plot_bgcolor='#ffffff',
                yaxis=dict(autorange='reversed', title=''),
                xaxis=dict(title='Quantidade Total'),
                height=500,
                showlegend=False
            )
            st.plotly_chart(fig_top20, use_container_width=True)
            
            # Table view
            disp_top20 = sku_qty[['sku', 'produto', 'quantidade']].copy()
            disp_top20.columns = ['SKU', 'Produto', 'Quantidade Total']
            st.dataframe(disp_top20, use_container_width=True, hide_index=True)
        
        st.divider()

        # ============================================================
        # NOVA SEÇÃO: PRODUTOS ABAIXO DO POTENCIAL (Gap Analysis)
        # ============================================================
        st.subheader("📉 Produtos Abaixo do Potencial - Análise de Gap")
        st.caption("Produtos com >=5 clientes compradores: identifica oportunidades com base na diferença entre média de top 25% buyers vs média geral")
        
        # Aggregate by product SKU across all clients
        prod_by_sku = df_sku.groupby('sku').agg({
            'produto': 'first',
            'cliente': 'nunique',
            'quantidade': ['sum', 'mean']
        }).reset_index()
        prod_by_sku.columns = ['sku', 'produto', 'num_clientes', 'total_qty', 'avg_qty_per_client']
        
        # Filter products with >= 5 buyers
        prod_potential = prod_by_sku[prod_by_sku['num_clientes'] >= 5].copy()
        
        if len(prod_potential) > 0:
            # For each product, calculate top 25% average
            gap_data = []
            for _, row in prod_potential.iterrows():
                sku_code = row['sku']
                prod_name = row['produto']
                num_clientes = row['num_clientes']
                avg_all = row['avg_qty_per_client']
                
                # Get all clients and their quantities for this SKU
                sku_clients = df_sku[df_sku['sku'] == sku_code].groupby('cliente')['quantidade'].sum().reset_index()
                sku_clients = sku_clients.sort_values('quantidade', ascending=False)
                
                # Top 25% of clients
                n_top25 = max(1, int(len(sku_clients) * 0.25))
                top25_qty = sku_clients.head(n_top25)['quantidade'].mean()
                
                # Gap percentage
                gap_pct = ((top25_qty - avg_all) / top25_qty * 100) if top25_qty > 0 else 0
                
                # Potential extra per month (assuming 14 days = 2 weeks working period per month)
                potencial_extra_mensal = (top25_qty - avg_all) * num_clientes / 14
                
                gap_data.append({
                    'Produto': prod_name,
                    'SKU': sku_code,
                    'Clientes': num_clientes,
                    'Média/Cliente': round(avg_all, 1),
                    'Média Top 25%': round(top25_qty, 1),
                    'Gap %': round(gap_pct, 1),
                    'Potencial Extra/Mês': round(potencial_extra_mensal, 1)
                })
            
            gap_df = pd.DataFrame(gap_data)
            gap_df = gap_df.sort_values('Potencial Extra/Mês', ascending=False)
            
            if len(gap_df) > 0:
                st.dataframe(gap_df, use_container_width=True, hide_index=True)
                
                # Top opportunities insight
                top_gap = gap_df.head(3)
                if len(top_gap) > 0:
                    top_prods = ', '.join(top_gap['Produto'].tolist())
                    st.markdown(insight_html('warning', 'TOP OPORTUNIDADES DE GAP',
                        f"Produtos com maior potencial: {top_prods}.",
                        "Estes produtos têm clientes que compram muito (top 25%) e clientes que compram pouco. Oportunidade de aumentar compras dos demais clientes."), unsafe_allow_html=True)
        else:
            st.info("Nenhum produto com 5+ clientes para análise de gap.")
        
        st.divider()

        # ============================================================
        # NOVA SEÇÃO: OPORTUNIDADES DE CADASTRO DE PRODUTOS
        # ============================================================
        st.subheader("🎯 Oportunidades de Cadastro de Produtos")
        st.caption("Produtos que >30% de clientes do mesmo vendedor compram, mas este cliente não compra ainda")
        
        # Get current client's vendor
        client_vendor = df[df['name'] == selected].iloc[0]['vendor'] if selected in df['name'].values else ''
        
        if client_vendor:
            # Get all clients of same vendor
            same_vendor_clients = df[df['vendor'] == client_vendor]['id'].unique()
            
            # Get products bought by same vendor clients
            vendor_products = df_sku[df_sku['cod_cliente'].isin(same_vendor_clients)].copy()
            
            # Products this client already buys
            client_sku = set(df_sku[df_sku['cod_cliente'].astype(str).str.strip() == str(client_id).strip()]['sku'].unique())
            
            # Find products not yet bought by this client
            opp_data = []
            for sku_code in vendor_products['sku'].unique():
                if sku_code not in client_sku:
                    # % of same-vendor clients buying this SKU
                    buyers = vendor_products[vendor_products['sku'] == sku_code]['cod_cliente'].nunique()
                    pct_buyers = (buyers / len(same_vendor_clients)) * 100 if len(same_vendor_clients) > 0 else 0
                    
                    if pct_buyers >= 30:
                        # Average quantity from similar buyers
                        avg_qty = vendor_products[vendor_products['sku'] == sku_code]['quantidade'].mean()
                        prod_name = vendor_products[vendor_products['sku'] == sku_code]['produto'].iloc[0]
                        vendedor = vendor_products[vendor_products['sku'] == sku_code]['vendedor'].iloc[0]
                        
                        opp_data.append({
                            'Cliente': selected,
                            'Vendedor': vendedor.replace(' Propetz Distribuição', '').replace(' La Maison Propetz', ''),
                            'Produto': prod_name,
                            'SKU': sku_code,
                            '% Clientes Similares': round(pct_buyers, 1),
                            'Qtd Potencial/Mês': round(avg_qty / 4, 1)  # Approx monthly
                        })
            
            if opp_data:
                opp_df = pd.DataFrame(opp_data)
                opp_df = opp_df.sort_values('% Clientes Similares', ascending=False)
                st.dataframe(opp_df, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma oportunidade de cadastro encontrada (todos produtos já comprados ou sem 30% de penetração).")
        else:
            st.info("Não foi possível identificar o vendedor do cliente.")

def page_churn(df, months, sel_indices_sorted, sel_months):
    st.header("⚠️ Gestão de Churn")

    period_label = f"{sel_months[0]} - {sel_months[-1]}" if len(sel_months) > 1 else (sel_months[0] if sel_months else "")

    def _period_sum(m):
        return sum(m[i] for i in sel_indices_sorted if i < len(m))

    recup = df[df['risk'] == 'Recuperação'].copy()
    atencao = df[df['risk'] == 'Atenção'].copy()
    saudavel = df[df['risk'] == 'Saudável']

    recup_impact = recup['avg_month'].apply(lambda am: ((am.get('2024',0) or am.get('2023',0)) * 12) if isinstance(am, dict) else 0).sum()
    atencao_impact = atencao['avg_month'].apply(lambda am: ((am.get('2024',0) or am.get('2023',0)) * 12) if isinstance(am, dict) else 0).sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 Recuperação (6+ meses)", f"{len(recup)}", f"Impacto: {fmt_brl(recup_impact)}/ano")
    k2.metric("🟡 Atenção (3-5 meses)", f"{len(atencao)}", f"Impacto: {fmt_brl(atencao_impact)}/ano")
    k3.metric("🟢 Saudáveis", f"{len(saudavel)}")
    k4.metric("💰 Receita Total em Risco", fmt_brl(recup_impact + atencao_impact), "Estimativa anual")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["🔴 Recuperação", "🟡 Atenção", "📊 Ranking Vendedores"])

    with tab1:
        if len(recup) > 0:
            recup['total_rev'] = recup['monthly'].apply(_period_sum)
            recup['impact'] = recup['avg_month'].apply(lambda am: ((am.get('2024',0) or am.get('2023',0)) * 12) if isinstance(am, dict) else 0)
            recup['vendor_short'] = recup['vendor'].str.replace(' Propetz Distribuição','').str.replace(' La Maison Propetz','')
            display = recup[['name','state','vendor_short','last_purchase','months_since','impact','total_rev']].sort_values('total_rev', ascending=False).copy()
            display.columns = ['Cliente','UF','Vendedor','Última Compra','Meses Inativo','Impacto Anual Est.',f'Receita ({period_label})']
            display['Impacto Anual Est.'] = display['Impacto Anual Est.'].apply(fmt_brl_full)
            display[f'Receita ({period_label})'] = display[f'Receita ({period_label})'].apply(fmt_brl_full)
            st.dataframe(display, use_container_width=True, hide_index=True, height=500)
        else:
            st.success("Nenhum cliente em recuperação!")

    with tab2:
        if len(atencao) > 0:
            atencao['total_rev'] = atencao['monthly'].apply(_period_sum)
            atencao['impact'] = atencao['avg_month'].apply(lambda am: ((am.get('2024',0) or am.get('2023',0)) * 12) if isinstance(am, dict) else 0)
            atencao['vendor_short'] = atencao['vendor'].str.replace(' Propetz Distribuição','').str.replace(' La Maison Propetz','')
            display = atencao[['name','state','vendor_short','last_purchase','months_since','impact','total_rev']].sort_values('total_rev', ascending=False).copy()
            display.columns = ['Cliente','UF','Vendedor','Última Compra','Meses Inativo','Impacto Anual Est.',f'Receita ({period_label})']
            display['Impacto Anual Est.'] = display['Impacto Anual Est.'].apply(fmt_brl_full)
            display[f'Receita ({period_label})'] = display[f'Receita ({period_label})'].apply(fmt_brl_full)
            st.dataframe(display, use_container_width=True, hide_index=True, height=400)
        else:
            st.success("Nenhum cliente em atenção!")

    with tab3:
        vendor_risk = df.groupby('vendor').apply(lambda g: pd.Series({
            'total': len(g),
            'recuperacao': len(g[g['risk']=='Recuperação']),
            'atencao': len(g[g['risk']=='Atenção']),
            'impact': g[g['risk'].isin(['Recuperação','Atenção'])]['avg_month'].apply(
                lambda am: ((am.get('2024',0) or am.get('2023',0)) * 12) if isinstance(am, dict) else 0
            ).sum()
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

# ============================================================
# PAGE: PRODUTOS
# ============================================================
def page_products(products_df):
    st.header("📦 Análise de Produtos")

    is_admin = st.session_state.get('role') == 'admin'

    count_a = len(products_df[products_df['abc']=='A'])
    count_b = len(products_df[products_df['abc']=='B'])
    count_c = len(products_df[products_df['abc']=='C'])
    total_qty = products_df['total_qty'].sum()
    qty_a = products_df[products_df['abc']=='A']['total_qty'].sum()
    pct_a = qty_a / total_qty * 100 if total_qty > 0 else 0
    pct_b = products_df[products_df['abc']=='B']['total_qty'].sum() / total_qty * 100 if total_qty > 0 else 0
    pct_c = products_df[products_df['abc']=='C']['total_qty'].sum() / total_qty * 100 if total_qty > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Produtos", f"{len(products_df)}")
    k2.metric("Curva A", f"{count_a}", f"{pct_a:.1f}% do volume")
    k3.metric("Curva B", f"{count_b}", f"{pct_b:.1f}% do volume")
    k4.metric("Curva C", f"{count_c}", f"{pct_c:.1f}% do volume")

    col1, col2 = st.columns(2)

    with col1:
        abc_data = products_df.groupby('abc')['total_qty'].sum().reset_index()
        abc_data['pct'] = (abc_data['total_qty'] / abc_data['total_qty'].sum() * 100).round(1)
        fig_abc = px.pie(abc_data, values='total_qty', names='abc', title="Curva ABC - Distribuição %",
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
        display = products_df[['code','name','category','abc','total_qty']].copy()
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
        display.columns = ['Código','Produto','Categoria','Curva','Volume Total']
    else:
        display.columns = ['Código','Produto','Categoria','Curva','% do Volume']
    st.dataframe(display, use_container_width=True, hide_index=True, height=500)

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

    # Upload new data
    st.subheader("Atualizar Base de Dados")
    uploaded = st.file_uploader("Envie a planilha atualizada (.xlsx)", type=['xlsx'])
    if uploaded:
        save_path = os.path.join(os.path.dirname(__file__), "RELATORIOS ESTADO-CLIENTES - ATUALIZADO.xlsx")
        with open(save_path, 'wb') as f:
            f.write(uploaded.getbuffer())
        st.success("Planilha atualizada! Recarregando dados...")
        st.cache_data.clear()
        st.rerun()

# ============================================================
# MAIN APP
# ============================================================
def main():
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
                save_path = os.path.join(os.path.dirname(__file__), "RELATORIOS ESTADO-CLIENTES - ATUALIZADO.xlsx")
                with open(save_path, 'wb') as f:
                    f.write(uploaded.getbuffer())
                st.success("Planilha salva! Recarregando...")
                st.cache_data.clear()
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

    # Month name order (lowercase, matching Excel labels)
    MONTH_ORDER = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez']
    # Only show months that actually exist in the data
    existing_month_names = set()
    for lbl in months:
        parts = lbl.replace('-', '/').split('/')
        if len(parts) >= 2:
            existing_month_names.add(parts[0].strip().lower())
    month_options = [m for m in MONTH_ORDER if m in existing_month_names]

    # Sidebar navigation
    with st.sidebar:
        st.markdown(f"### 👋 {st.session_state['user_name']}")
        st.caption(f"{'🔑 Admin' if st.session_state['role'] == 'admin' else '👤 Vendedor'}")

        if st.session_state.get("vendor_filter"):
            st.info(f"📋 Sua carteira: {len(df_clients)} clientes")

        st.divider()

        pages = {
            "📊 Visão Geral": "overview",
            "👤 Clientes": "clients",
            "🧩 Mix de Produtos": "mix",
            "⚠️ Gestão de Churn": "churn",
            "📦 Produtos": "products",
        }

        if st.session_state["role"] == "admin":
            pages["⚙️ Admin"] = "admin"

        selected_page = st.radio("Navegação", list(pages.keys()), label_visibility="collapsed")

        st.divider()

        # --- Period filters (visible on all pages) ---
        st.markdown("**Filtro de Período**")

        # Chart click override indicator
        chart_override_active = "chart_sel_months" in st.session_state and st.session_state["chart_sel_months"]
        if chart_override_active:
            n_chart = len(st.session_state["chart_sel_months"])
            st.info(f"📊 Seleção do gráfico ativa ({n_chart} {'mês' if n_chart == 1 else 'meses'})")
            if st.button("✕ Limpar seleção do gráfico", use_container_width=True, key="clear_chart"):
                del st.session_state["chart_sel_months"]
                st.rerun()

        # Default year: most recent with 6+ months of data
        _best_default_year = all_years_ordered[-1] if all_years_ordered else ""
        for yr in reversed(all_years_ordered):
            yr_months = [lbl for lbl in months if lbl.split('/')[-1].strip() in [yr[-2:], yr]]
            if len(yr_months) >= 6:
                _best_default_year = yr
                break

        selected_years = st.multiselect(
            "Ano",
            options=all_years_ordered,
            default=[_best_default_year] if _best_default_year else [],
            key="global_years"
        )
        selected_month_names = st.multiselect(
            "Mês",
            options=month_options,
            default=month_options,
            key="global_months"
        )

        st.divider()

        if st.button("🚪 Sair", use_container_width=True):
            _clear_login_params()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        st.divider()
        st.caption(f"📅 Dados: {months[0]} a {months[-1]}")
        st.caption(f"👥 {len(df_clients)} clientes")

    # --- Build selected indices ---
    # Chart click override takes priority over sidebar filters
    chart_override_active = "chart_sel_months" in st.session_state and st.session_state["chart_sel_months"]

    if chart_override_active:
        sel_indices = set()
        for lbl in st.session_state["chart_sel_months"]:
            if lbl in months:
                sel_indices.add(months.index(lbl))
    else:
        sel_indices = set()
        for i, lbl in enumerate(months):
            parts = lbl.replace('-', '/').split('/')
            if len(parts) >= 2:
                m_name = parts[0].strip().lower()
                y_raw = parts[-1].strip()
                y_full = f"20{y_raw}" if len(y_raw) == 2 else y_raw
            else:
                m_name = lbl.lower()
                y_full = ""
            if y_full in selected_years and m_name in selected_month_names:
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

    # Route to page
    page = pages[selected_page]

    if page == "overview":
        page_overview(df_clients, months, year_ranges, sel_indices, sel_indices_sorted, sel_months)
    elif page == "clients":
        page_clients(df_clients, df_sku, months, year_ranges, sel_indices_sorted, sel_months)
    elif page == "mix":
        page_mix(df_clients, df_products, df_client_products, df_sku, months, sel_indices_sorted, sel_months)
    elif page == "churn":
        page_churn(df_clients, months, sel_indices_sorted, sel_months)
    elif page == "products":
        page_products(df_products)
    elif page == "admin":
        page_admin()

if __name__ == "__main__":
    main()
