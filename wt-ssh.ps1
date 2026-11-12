# A Windows Terminal profile, and a Start menu shortcut with a key, that open
# herdr on another machine over SSH. Asks for the machine; safe to run again
# (same name: the profile and shortcut are replaced). Backs up settings first.
#
# Run in PowerShell on the Windows machine:
#   irm https://raw.githubusercontent.com/alvaro-francisco-gil/agent-desk/main/wt-ssh.ps1 | iex

$ErrorActionPreference = 'Stop'

$target = (Read-Host 'SSH target, as user@host').Trim()
if ($target -notmatch '^[^\s@]+@[^\s@]+$') { throw "'$target' is not user@host; nothing was changed." }
$label = (Read-Host "Name for it [$($target.Split('@')[1].Split('.')[0])]").Trim()
if (-not $label) { $label = $target.Split('@')[1].Split('.')[0] }
$hotkey = (Read-Host 'Key to open it from anywhere [Ctrl+Alt+H]').Trim()
if (-not $hotkey) { $hotkey = 'Ctrl+Alt+H' }

$profileName = "herdr on $label"
# A login shell, so a herdr server started from here gets the full PATH.
$commandline = "ssh.exe -t $target bash -lc herdr"

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

if ($settings.profiles -is [array]) {
    $list = $settings.profiles
} else {
    if ($settings.profiles.PSObject.Properties.Name -notcontains 'list') {
        $settings.profiles | Add-Member -NotePropertyName list -NotePropertyValue @()
    }
    $list = $settings.profiles.list
}

$existing = @($list) | Where-Object { $_.name -eq $profileName } | Select-Object -First 1
$guid = if ($existing) { $existing.guid } else { "{$([guid]::NewGuid())}" }
$entry = [pscustomobject][ordered]@{
    guid        = $guid
    name        = $profileName
    commandline = $commandline
    hidden      = $false
}
$list = @(@($list) | Where-Object { $_.name -ne $profileName }) + $entry
if ($settings.profiles -is [array]) { $settings.profiles = $list } else { $settings.profiles.list = $list }

$backup = "$settingsPath.before-agent-desk-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item -LiteralPath $settingsPath -Destination $backup
[IO.File]::WriteAllText($settingsPath, ($settings | ConvertTo-Json -Depth 32), (New-Object Text.UTF8Encoding $false))

Write-Host "Added '$profileName' to Windows Terminal's new-tab menu."

if ($env:OS -eq 'Windows_NT') {
    $programs = [Environment]::GetFolderPath('Programs')
    $link = Join-Path $programs "$profileName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($link)
    $shortcut.TargetPath = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\wt.exe'
    $shortcut.Arguments = "-p `"$profileName`""
    $shortcut.Hotkey = $hotkey
    $shortcut.Description = "herdr on $target"
    $shortcut.Save()
    Write-Host "Start menu: '$profileName'. $hotkey opens it from anywhere (may need a sign-out the first time)."
}
Write-Host "The old settings are in $backup"
