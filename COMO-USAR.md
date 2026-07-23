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
2. Faça login como admin (usuário `leonardo`)
3. Clique em **Admin** no menu lateral
4. Faça upload da planilha atualizada

Com o GITHUB_TOKEN configurado (abaixo), o upload é salvo direto no GitHub e
**fica permanente** — o app não perde mais os dados quando o servidor reinicia.
Alternativa: salvar a planilha nesta pasta e rodar o `deploy.bat`.

## GITHUB_TOKEN (persistência — configurar 1 vez, com escopo MÍNIMO)

O disco do Streamlit Cloud é temporário: sem o token, uploads, usuários novos,
clientes inativados e o log de acessos são perdidos a cada reinício do servidor.

⚠️ Use um token **fine-grained** restrito a ESTE repositório (não um clássico com
`repo` inteiro, que dá escrita em toda a sua conta). Passo a passo para
**rotacionar** o token atual por um seguro:

1. https://github.com/settings/tokens → aba **Fine-grained tokens** →
   **Generate new token**.
2. **Expiration**: defina uma data (ex.: 90 dias — anote para renovar).
3. **Resource owner**: sua conta. **Repository access**: *Only select
   repositories* → escolha **apenas** `propetz-bi`.
4. **Permissions** → *Repository permissions* → **Contents: Read and write**
   (só isso; deixe todo o resto em *No access*).
5. **Generate** e copie o token (começa com `github_pat_`).
6. https://share.streamlit.io → app **propetz-bi** → ⋮ → **Settings** →
   **Secrets** → substitua o valor:

   ```
   GITHUB_TOKEN = "github_pat_seu_token_aqui"
   ```

7. Salve. O app reinicia sozinho e passa a usar o token novo.
8. Volte em https://github.com/settings/tokens e **revogue o token antigo**
   (o clássico com escopo `repo`).

Estado salvo no branch `state`, planilha no `main`. Renove o token antes da
data de expiração (o app avisa se a persistência parar de funcionar).

Opcional — `BREAKGLASS_PASS`: se quiser uma senha de admin de emergência para o
caso (raro) do `users.yaml` sumir, adicione nos Secrets
`BREAKGLASS_PASS = "uma-senha-forte"`. Sem ela, o acesso de emergência fica
desativado (mais seguro).

⚠️ Com o token ativo, gerencie usuários/senhas **pelo app** (página Admin), não
editando o `users.yaml` local — a versão do app tem prioridade no boot.

## Credenciais

As senhas **não ficam aqui** (este arquivo vai para o GitHub). A lista completa
dos 8 usuários está em **`CREDENCIAIS-LOCAL.md`** (na pasta do projeto, fora do
Git). Trocar/criar senhas pela **página Admin** do app.

Usuários: `leonardo` (admin), `grasiele` (diretor), `cristiane`/`emanuel`/`yasmin`
(vendedores), `marcos`/`pedro` (garantia), `jacson` (garantia master).

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
