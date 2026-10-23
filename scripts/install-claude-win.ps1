# Link ~/.claude/settings.json to the dotfiles Windows settings.
# Needs Developer Mode or an elevated shell (symlink creation).
# Keeping the dotfiles copy as the live file stops the context-mode plugin from
# appending its own (PowerShell-invalid) cache-heal hook.
$ErrorActionPreference = 'Stop'

$src = Join-Path $PSScriptRoot '..\.claude_custom\settings.win.json' | Resolve-Path
$dst = Join-Path $HOME '.claude\settings.json'

$item = Get-Item $dst -ErrorAction SilentlyContinue
if ($item -and $item.LinkType -eq 'SymbolicLink' -and $item.Target -eq $src.Path) {
    Write-Host "Already linked: $dst -> $($src.Path)"
    return
}

$backup = $null
if ($item) {
    $backup = "$dst.bak"
    Move-Item $dst $backup -Force
}

try {
    New-Item -ItemType SymbolicLink -Path $dst -Target $src.Path | Out-Null
} catch {
    if ($backup) { Move-Item $backup $dst -Force }
    throw "Symlink failed (enable Developer Mode or run elevated): $_"
}

Write-Host "Linked: $dst -> $($src.Path)"
if ($backup) { Write-Host "Previous file saved at $backup" }
