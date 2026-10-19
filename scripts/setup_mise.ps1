# Install mise on Windows, link its config, and install the global tools.
# Idempotent. Usage: pwsh scripts/setup_mise.ps1
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repo '.config/mise/config.win.toml'
$target = Join-Path $HOME '.config/mise/config.toml'

if (-not (Get-Command mise -ErrorAction SilentlyContinue)) {
    if (Get-Command scoop -ErrorAction SilentlyContinue) {
        scoop install mise
    } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id jdx.mise -e --accept-source-agreements --accept-package-agreements
    } else {
        throw 'Neither scoop nor winget found; install mise manually: https://mise.jdx.dev'
    }
    # Pick up the new PATH in this session
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
}

New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
$existing = Get-Item $target -Force -ErrorAction SilentlyContinue
if ($existing -and $existing.LinkType -and ($existing.Target -contains $source -or $existing.Target -eq $source)) {
    Write-Host "config already linked: $target"
} elseif ($existing -and -not $existing.LinkType -and (Get-FileHash $target).Hash -eq (Get-FileHash $source).Hash) {
    Write-Host "config already up to date: $target"
} else {
    if ($existing) {
        Move-Item $target "$target.bak" -Force
        Write-Host "backed up existing config to $target.bak"
    }
    try {
        New-Item -ItemType SymbolicLink -Path $target -Target $source | Out-Null
        Write-Host "linked $target -> $source"
    } catch {
        # Symlinks need Developer Mode or admin; fall back to a copy
        Copy-Item $source $target
        Write-Host "symlink not permitted, copied config to $target"
    }
}

mise install
mise ls
Write-Host 'Shell activation lives in ps1/Microsoft.PowerShell_profile.ps1; restart PowerShell.'
