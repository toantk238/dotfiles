# $env:HOME = "$env:HOMEPATH"
$Env:HOME = $HOME

Set-PSReadLineKeyHandler -Key Tab -Function AcceptSuggestion
Set-PSReadLineKeyHandler -Chord "Shift+Tab" -Function TabCompleteNext
Set-PSReadLineKeyHandler -Key UpArrow -Function HistorySearchBackward
Set-PSReadLineKeyHandler -Key DownArrow -Function HistorySearchForward
Set-PSReadLineKeyHandler -Chord "RightArrow" -Function ForwardWord
Set-PSReadLineKeyHandler -Chord "LeftArrow" -Function BackwardWord

Set-PSReadLineOption -EditMode Vi

Set-Alias -Name nv -Value nvim -Force
Set-Alias -Name lg -Value lazygit -Force
Set-Alias -Name n -Value lfcd.ps1 -Force
Set-Alias -Name cat -Value bat -Force
Set-Alias -Name top -Value btop -Force
Set-Alias awk C:\Users\Rock\scoop\apps\msys2\current\usr\bin\awk.exe

# $Env:DIRENV_BASH = "C:\Users\Rock\scoop\shims\bash.exe"
# Invoke-Expression "$(direnv hook pwsh)"

oh-my-posh init pwsh | Invoke-Expression
Import-Module git-aliases -DisableNameChecking

. (Join-Path -Path $PSScriptRoot -ChildPath "lf.ps1")
. (Join-Path -Path $PSScriptRoot -ChildPath "just.ps1")

Invoke-Expression (& { (zoxide init powershell --cmd j | Out-String) })

$env:CLAUDE_CODE_GIT_BASH_PATH="C:\Program Files\Git\bin\bash.exe"
$env:ANTHROPIC_MODEL="opusplan"

# pyenv-venv init

# function findVersion {
#     $currentPath = Get-Location
#     $versionFileFound = $false
#
#     # 检查当前目录
#     if (Test-Path (Join-Path -Path $currentPath -ChildPath ".python-version")) {
#         $versionFileFound = $true
#     } 
#     if (-not $versionFileFound) {
#         # 检查父级目录
#         $parentPath = Split-Path -Path $currentPath -Parent
#         while ($parentPath -and -not $versionFileFound) {
#             if (Test-Path (Join-Path -Path $parentPath -ChildPath ".python-version")) {
#                 $versionFileFound = $true
#                 break
#             }
#             $parentPath = Split-Path -Path $parentPath -Parent
#         }
#     }
#     return $versionFileFound
# }
#
# ### set-location start ###
# function Set-LocationWithAction {
#     param(
#         [Parameter(ValueFromPipeline=$true)]
#         [string]$Path
#     )
#
#     # 调用原始的 Set-Location 命令
#     Microsoft.PowerShell.Management\Set-Location -Path $Path
#
#     # 切换目录后要执行的命令
#     # 检查当前目录及其父级目录是否存在 .python-version 文件
#     $VENV = $env:VIRTUAL_ENV
#
#     $versionFileFound = findVersion
#
#     # 根据是否找到 .version 文件执行相应命令
#     if ($versionFileFound -and -not $VENV) {
#         # "找到 .python-version 文件，执行 pyenv-venv init"
#         pyenv-venv init root
#         return 
#     } 
#     if (-not $versionFileFound -and $VENV) {
#         pyenv-venv deactivate
#     }
# }
#
# # 创建别名，替换原有的 cd 命令
# Remove-Item alias:\cd -Force -ErrorAction SilentlyContinue
# Set-Alias -Name cd -Value Set-LocationWithAction
# ### set-location end ###
#
# ### 初始进入默认执行pyenv-venv init root ###
# $versionFileFound = findVersion
# if ($versionFileFound) {
#     pyenv-venv init root
# }
# ### 初始进入默认执行pyenv-venv init root ###


[System.Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding("utf-8")
[System.Console]::InputEncoding = [System.Text.Encoding]::GetEncoding("utf-8")

$env:LESSCHARSET = "utf-8"
Set-PSReadlineOption -BellStyle None
Set-PSReadLineKeyHandler -Chord Ctrl+r -ScriptBlock {
    # いつからかawkの表示がされないようになったので、以下コマンドを実行
    # Set-Alias awk C:\Users\saido\scoop\apps\msys2\current\usr\bin\awk.exe
    $command = Get-Content (Get-PSReadlineOption).HistorySavePath | awk '!a[$0]++' | fzf --tac
    [Microsoft.PowerShell.PSConsoleReadLine]::Insert($command)
}

function l { ls -Force @args }
