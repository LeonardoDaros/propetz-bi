param(
    [string]$RepositoryPath = $PSScriptRoot,
    [string]$GitExecutable = 'git',
    [switch]$AtualizarAbc
)

# Compativel com Windows PowerShell 5.1; nao depende de bibliotecas Python.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

function Invoke-DeployGit {
    param([string[]]$GitArgs, [int[]]$AllowedCodes = @(0))
    # Captura o exit code mesmo quando o comando nativo escreve em stderr.
    $ErrorActionPreference = 'Continue'
    $lines = @(& $GitExecutable -C $script:DeployRepo -c core.quotepath=false @GitArgs 2>&1)
    $code = $LASTEXITCODE
    $out = ($lines | ForEach-Object { "$_" }) -join "`n"
    if ($code -notin $AllowedCodes) {
        throw "Git falhou ($code): git $($GitArgs -join ' ')`n$out"
    }
    return [pscustomobject]@{ Code = $code; Output = $out }
}

function Get-DeployPaths {
    param([string]$Raw)
    return @($Raw.Split([char]0) | ForEach-Object { $_.Trim("`r", "`n") } | Where-Object { $_ })
}

function Test-AllowedDeployPath {
    param([string]$Path)
    return ($Path -cin $script:DeployFiles) -or ($Path -cmatch '^teste_etapa[12]_[A-Za-z0-9_]+\.py$')
}

try {
    $script:DeployRepo = (Resolve-Path -LiteralPath $RepositoryPath).Path
    # Nunca preparar automaticamente users.yaml, estado, secrets ou Backups.
    $script:DeployFiles = @(
        'app.py', 'util_comum.py', 'agenda_comercial.py', 'ui_propetz.py',
        'ficha_cliente_dados.py', 'ficha_cliente_ui.py',
        'teste_ficha_cliente_dados.py', 'teste_ficha_cliente_interface.py',
        'teste_auditoria_comercial.py', 'teste_auditoria_garantias.py',
        'teste_auditoria_integracao.py', 'teste_auditoria_seguranca.py',
        'painel_garantias.py', 'garantia_analytics.py', 'teste_painel_garantias.py',
        'exportacao_csv.py', 'teste_exportacao_csv.py',
        'requirements.txt', '.gitignore',
        '.streamlit/config.toml', 'abc_valor.json',
        'Relatorio Distribuidores Mensal.xlsx',
        'teste_seguranca_login.py', 'deploy_seguro.ps1'
    )
    $branch = (Invoke-DeployGit -GitArgs @('branch', '--show-current')).Output.Trim()
    if ($branch -cne 'main') {
        throw 'O checkout precisa estar na branch main. Nenhuma troca de branch foi feita.'
    }
    $index = (Invoke-DeployGit -GitArgs @('rev-parse', '--git-path', 'index')).Output.Trim()
    if (-not [IO.Path]::IsPathRooted($index)) { $index = Join-Path $script:DeployRepo $index }
    if (Test-Path -LiteralPath ($index + '.lock')) {
        throw 'Existe um index.lock. Feche outras operacoes Git e confira o lock antes de tentar novamente. Ele foi preservado.'
    }
    foreach ($marker in @('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply')) {
        $path = (Invoke-DeployGit -GitArgs @('rev-parse', '--git-path', $marker)).Output.Trim()
        if (-not [IO.Path]::IsPathRooted($path)) { $path = Join-Path $script:DeployRepo $path }
        if (Test-Path -LiteralPath $path) { throw 'Ha uma operacao Git em andamento. Conclua ou revise essa operacao antes do deploy.' }
    }
    $staged = Invoke-DeployGit -GitArgs @('diff', '--cached', '--quiet', '--exit-code') -AllowedCodes @(0, 1)
    if ($staged.Code -eq 1) {
        throw 'Ja existem arquivos preparados no staging. Revise esse trabalho antes do deploy; o staging foi preservado.'
    }

    Write-Host 'Verificando atualizacoes feitas no site...'
    $null = Invoke-DeployGit -GitArgs @('fetch', '--no-tags', 'origin', 'refs/heads/main')
    $remoteBefore = (Invoke-DeployGit -GitArgs @('rev-parse', 'FETCH_HEAD')).Output.Trim()
    $ancestor = Invoke-DeployGit -GitArgs @('merge-base', '--is-ancestor', $remoteBefore, 'HEAD') -AllowedCodes @(0, 1)
    if ($ancestor.Code -ne 0) {
        throw ('O main remoto tem atualizacoes ainda nao integradas, possivelmente um upload do site. ' +
               'Nada foi preparado, commitado ou enviado. Suas alteracoes locais foram preservadas. ' +
               'Integre o main remoto preservando as alteracoes locais antes de repetir; veja DEPLOY.md. Nao use push --force.')
    }
    # Verifica todos os commits pendentes, inclusive arquivos depois removidos.
    $pending = (Invoke-DeployGit -GitArgs @('log', '--diff-merges=first-parent', '--format=', '--name-only', '-z', ($remoteBefore + '..HEAD'))).Output
    $unexpected = @(Get-DeployPaths -Raw $pending | Where-Object { -not (Test-AllowedDeployPath $_) })
    if ($unexpected.Count) {
        throw ('Ha commits locais pendentes com arquivos fora da lista de publicacao. Revise-os antes de enviar: ' + ($unexpected -join ', '))
    }

    if ($AtualizarAbc) {
        $pythonAbc = 'C:\Users\leoda\AppData\Local\Programs\Python\Python312\python.exe'
        if (Test-Path -LiteralPath $pythonAbc) {
            Write-Host 'Atualizando curva ABC por valor...'
            Push-Location -LiteralPath $script:DeployRepo
            try {
                & $pythonAbc 'atualizar_abc_valor.py'
                if ($LASTEXITCODE -ne 0) { Write-Warning 'ABC nao atualizado; sera mantida a versao disponivel. Confira o indicador no app.' }
            } finally { Pop-Location }
        } else {
            Write-Warning 'Python da rotina ABC nao encontrado; sera mantida a versao disponivel.'
        }
    }

    $tracked = @(Get-DeployPaths -Raw (Invoke-DeployGit -GitArgs @('ls-files', '-z')).Output)
    $candidates = @($script:DeployFiles) + @($tracked | Where-Object { $_ -cmatch '^teste_etapa[12]_[A-Za-z0-9_]+\.py$' })
    $candidates += @(Get-ChildItem -LiteralPath $script:DeployRepo -File -Filter 'teste_etapa*.py' | ForEach-Object { $_.Name })
    $toStage = @($candidates | Sort-Object -Unique | Where-Object {
        (Test-AllowedDeployPath $_) -and (($_ -cin $tracked) -or (Test-Path -LiteralPath (Join-Path $script:DeployRepo $_) -PathType Leaf))
    })
    if ($toStage.Count) { $null = Invoke-DeployGit -GitArgs (@('add', '--') + $toStage) }
    $changed = Invoke-DeployGit -GitArgs @('diff', '--cached', '--quiet', '--exit-code') -AllowedCodes @(0, 1)
    if ($changed.Code -eq 1) {
        Write-Host 'Arquivos que serao publicados:'
        Write-Host (Invoke-DeployGit -GitArgs @('diff', '--cached', '--name-only')).Output
        $message = 'Atualizacao ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
        # Identidade apenas deste commit; nao altera o config do usuario.
        $null = Invoke-DeployGit -GitArgs @('-c', 'user.name=Leonardo Daros', '-c', 'user.email=leonardo@daroscorp.com.br', 'commit', '-m', $message)
    } else {
        Write-Host 'Nenhuma alteracao nova nos arquivos de publicacao.'
    }
    $localHead = (Invoke-DeployGit -GitArgs @('rev-parse', 'HEAD')).Output.Trim()
    Write-Host 'Enviando sem sobrescrever o historico remoto...'
    $null = Invoke-DeployGit -GitArgs @('push', 'origin', 'HEAD:refs/heads/main')
    $remoteLine = (Invoke-DeployGit -GitArgs @('ls-remote', '--exit-code', 'origin', 'refs/heads/main')).Output.Trim()
    $remoteHead = ($remoteLine -split '\s+')[0]
    if ($localHead -cne $remoteHead) {
        throw 'O SHA remoto mudou ou nao corresponde ao enviado. O deploy nao foi confirmado; confira o main antes de repetir.'
    }
    Write-Host ''
    Write-Host 'DEPLOY CONFIRMADO: o main remoto corresponde ao commit local.'
    Write-Host 'O Streamlit ainda precisa concluir a atualizacao. Confira https://propetz-bi.streamlit.app'
    Write-Host 'Arquivos fora da lista de publicacao permaneceram locais.'
    exit 0
} catch {
    Write-Host ''
    Write-Host ('[ERRO] Deploy interrompido: ' + $_.Exception.Message)
    Write-Host 'Nenhum push forcado, reset destrutivo ou reparo automatico do Git foi executado.'
    exit 1
}
