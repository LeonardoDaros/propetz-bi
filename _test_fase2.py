# -*- coding: utf-8 -*-
"""FASE 2: churn com data real de NF — validação contra os baldes da sombra."""
import warnings
warnings.filterwarnings("ignore")
import os, shutil
import app

app._gh_token = lambda: None
app._STATE_RAW_CACHE.clear()

sv = app.load_silver_distribuicao()
assert sv.get("clientes"), "json do silver deveria existir localmente"
print(f"silver carregado: {len(sv['clientes'])} códigos, gerado em {sv['gerado_em']}")

res = app.load_data()
df, dp, dcp, months, yr, dsku = res
por_id = {r["id"]: r for _, r in df.iterrows()}

esperados = {"1475": "Atenção", "1069": "Atenção", "1152": "Recuperação",
             "1394": "Recuperação", "1010": "Saudável", "1086": "Saudável",
             "1494": "Saudável", "1037": "Saudável"}
ok = True
for cod, classe in esperados.items():
    got = por_id[cod]["risk"]
    ok &= got == classe
    print(f"{'OK  ' if got == classe else 'FAIL'} {cod}: '{got}' (esperado '{classe}') "
          f"| última: {por_id[cod]['last_purchase']}")
assert ok

for role, user in [("vendedor", "cristiane"), ("diretor", "grasiele"), ("admin", "leonardo")]:
    app.st.session_state.clear()
    app.st.session_state["role"] = role
    app.st.session_state["username"] = user
    app.st.session_state["user_name"] = user.title()
    if role == "vendedor":
        app.st.session_state["vendor_filter"] = "Cristiane La Maison Propetz"
    app.page_churn(df.copy(), months, list(range(len(months))), months)
    app.page_actions(df.copy(), dsku, dp.copy(), dcp.copy(), months)
    app.page_manager(df.copy(), months, dsku, dp)
    print(f"OK   render churn/ações/gestor ({role})")

print("\nFASE 2 OK")
