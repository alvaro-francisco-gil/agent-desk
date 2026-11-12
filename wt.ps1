# Windows Terminal, set up for herdr over SSH.
#
# Windows Terminal keeps some Alt keys for itself, so herdr on the other end
# never sees them. This frees them, and makes Alt+R type "/rename " (Ghostty
# does the same on Omarchy). Safe to run again: it replaces what it added.
# A copy of the old settings is kept next to them.
#
# Run in PowerShell on the Windows machine:
#   irm https://raw.githubusercontent.com/alvaro-francisco-gil/agent-desk/main/wt.ps1 | iex

$ErrorActionPreference = 'Stop'

$freedKeys = @(
    'alt+enter',                                              # fullscreen -> herdr: new shell
    'alt+up', 'alt+down', 'alt+left', 'alt+right',            # pane focus -> herdr: agents, tabs
    'alt+shift+up', 'alt+shift+down',                         # pane resize
    'alt+shift+left', 'alt+shift+right',                      # pane resize -> herdr: move tab
    'alt+shift+enter'                                         # -> herdr: split
)
$renameKey = 'alt+r'
$renameId = 'User.agentDesk.rename'
$ourKeys = $freedKeys + $renameKey

$settingsPath = @(
    'Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState',
    'Packages/Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe/LocalState',
    'Microsoft/Windows Terminal'
) | ForEach-Object { Join-Path (Join-Path $env:LOCALAPPDATA $_) 'settings.json' } | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $settingsPath) {
    throw 'No Windows Terminal settings.json found. Open Windows Terminal once, then run this again.'
}

# settings.json may carry // comment lines, which Windows PowerShell 5.1 cannot parse.
$raw = Get-Content -Raw -LiteralPath $settingsPath
$json = ($raw -split "`r?`n" | Where-Object { $_ -notmatch '^\s*//' }) -join "`n"
try {
    $settings = $json | ConvertFrom-Json
} catch {
    throw "Could not read $settingsPath as JSON; nothing was changed. $_"
}

function Get-Entries($name) {
    if ($settings.PSObject.Properties.Name -contains $name) { return @($settings.$name) }
    return @()
}

function Set-Entries($name, $entries) {
    if ($settings.PSObject.Properties.Name -contains $name) {
        $settings.$name = $entries
    } else {
        $settings | Add-Member -NotePropertyName $name -NotePropertyValue $entries
    }
}

# Drops our keys from any entry; an entry left with no key, or one we added, goes.
function Remove-OurKeys($entries) {
    $kept = @()
    foreach ($entry in $entries) {
        if ($entry.id -eq $renameId) { continue }
        $names = $entry.PSObject.Properties.Name
        if ($names -notcontains 'keys') { $kept += $entry; continue }
        $remaining = @(@($entry.keys) | Where-Object { $ourKeys -notcontains $_.ToLower() })
        if ($remaining.Count -eq 0) { continue }
        if ($remaining.Count -lt @($entry.keys).Count) {
            $entry.keys = if ($remaining.Count -eq 1) { $remaining[0] } else { $remaining }
        }
        $kept += $entry
    }
    return , $kept
}

$actions = Remove-OurKeys (Get-Entries 'actions')

# Windows Terminal 1.21+ splits commands ("actions", with an id) from keys
# ("keybindings"); older versions put both in "actions".
if ($settings.PSObject.Properties.Name -contains 'keybindings') {
    $keybindings = Remove-OurKeys (Get-Entries 'keybindings')
    $actions += [pscustomobject][ordered]@{
        command = [pscustomobject][ordered]@{ action = 'sendInput'; input = '/rename ' }
        id      = $renameId
    }
    foreach ($key in $freedKeys) { $keybindings += [pscustomobject][ordered]@{ id = $null; keys = $key } }
    $keybindings += [pscustomobject][ordered]@{ id = $renameId; keys = $renameKey }
    Set-Entries 'keybindings' $keybindings
} else {
    foreach ($key in $freedKeys) { $actions += [pscustomobject][ordered]@{ command = $null; keys = $key } }
    $actions += [pscustomobject][ordered]@{
        command = [pscustomobject][ordered]@{ action = 'sendInput'; input = '/rename ' }
        keys    = $renameKey
    }
}
Set-Entries 'actions' $actions

$backup = "$settingsPath.before-agent-desk-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item -LiteralPath $settingsPath -Destination $backup
[IO.File]::WriteAllText($settingsPath, ($settings | ConvertTo-Json -Depth 32), (New-Object Text.UTF8Encoding $false))

Write-Host "Done. Windows Terminal reloads its settings by itself."
Write-Host "Freed: $($freedKeys -join ', '). Alt+R types '/rename '."
Write-Host "The old settings are in $backup"
Write-Host "Alt+Esc stays with Windows (switch windows); in herdr, Ctrl+Space then X closes a pane."
