# Propetz BI — Guia Rápido

## Setup (só na primeira vez)

1. **Instale o Git** — baixe em https://git-scm.com/download/win (instale com opções padrão)
2. **Rode o `setup.bat`** — clique duplo no arquivo. Ele vai configurar tudo.
   - Na primeira vez, o Git vai pedir login: use seu usuário do GitHub e o **Personal Access Token** como senha.

## Como fazer deploy (após edições)

1. Peça as alterações no Cowork (ex: "adiciona filtro por estado")
2. As alterações serão salvas na pasta `propetz-bi/` do seu computador
3. **Clique duplo no `deploy.bat`**
4. Pronto! O app atualiza em ~1 minuto em https://propetz-bi.streamlit.app

## Como atualizar a planilha

1. Acesse https://propetz-bi.streamlit.app
2. Faça login como admin (leonardo / propetz2026)
3. Clique em **Admin** no menu lateral
4. Faça upload da planilha atualizada

Com o GITHUB_TOKEN configurado (abaixo), o upload é salvo direto no GitHub e
**fica permanente** — o app não perde mais os dados quando o servidor reinicia.
Alternativa: salvar a planilha nesta pasta e rodar o `deploy.bat`.

## GITHUB_TOKEN (persistência — configurar 1 vez)

O disco do Streamlit Cloud é temporário: sem o token, uploads, usuários novos,
clientes inativados e o log de acessos são perdidos a cada reinício do servidor.

1. Crie um token em https://github.com/settings/tokens → "Generate new token (classic)",
   marque a permissão **repo**, sem expiração (ou renove quando expirar).
2. Acesse https://share.streamlit.io → app **propetz-bi** → ⋮ → **Settings** → **Secrets**.
3. Cole (com as aspas) e salve:

   ```
   GITHUB_TOKEN = "ghp_seu_token_aqui"
   ```

4. O app reinicia sozinho. Pronto: estado salvo no branch `state` do repo,
   planilha salva no branch `main`.

⚠️ Com o token ativo, gerencie usuários/senhas **pelo app** (página Admin), não
editando o `users.yaml` local — a versão do app tem prioridade no boot.

## Credenciais

| Usuário    | Senha          | Perfil    |
|------------|----------------|-----------|
| leonardo   | propetz2026    | Admin     |
| cristiane  | cristiane2026  | Vendedora |
| emanuel    | emanuel2026    | Vendedor  |
| yasmin     | yasmin2026     | Vendedora |

## Estrutura de arquivos

```
propetz-bi/
├── app.py           ← código do dashboard (editado pelo Claude)
├── users.yaml       ← usuários e senhas
├── requirements.txt ← dependências Python
├── .streamlit/      ← configuração do tema
├── deploy.bat       ← script de deploy (1 clique)
├── setup.bat        ← configuração inicial
└── COMO-USAR.md     ← este arquivo
```
