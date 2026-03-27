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
