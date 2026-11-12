# A Windows Terminal profile, a Start menu shortcut and a key (Win+H by
# default) that open herdr on another machine over SSH, with a sheep icon.
# Asks for the machine; safe to run again (same name: everything is replaced).
# Backs up the Windows Terminal settings first. A key with Win in it needs
# AutoHotkey, which it installs with winget when missing; Win+H was Windows
# voice typing.
#
# Run in PowerShell on the Windows machine:
#   irm https://raw.githubusercontent.com/alvaro-francisco-gil/agent-desk/main/wt-ssh.ps1 | iex

$ErrorActionPreference = 'Stop'

$target = (Read-Host 'SSH target, as user@host').Trim()
if ($target -notmatch '^[^\s@]+@[^\s@]+$') { throw "'$target' is not user@host; nothing was changed." }
$label = (Read-Host "Name for it [$($target.Split('@')[1].Split('.')[0])]").Trim()
if (-not $label) { $label = $target.Split('@')[1].Split('.')[0] }
$hotkey = (Read-Host 'Key to open it from anywhere [Win+H]').Trim()
if (-not $hotkey) { $hotkey = 'Win+H' }

# "Win+H" -> "#h", AutoHotkey's spelling.
function ConvertTo-AhkHotkey([string]$text) {
    $parts = @($text -split '\+' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($parts.Count -lt 2) { throw "'$text' needs a modifier and a key, like Win+H; nothing was changed." }
    $mods = ''
    foreach ($mod in $parts[0..($parts.Count - 2)]) {
        switch -regex ($mod) {
            '^(win|super|sup)$' { $mods += '#' }
            '^(ctrl|control)$'  { $mods += '^' }
            '^alt$'             { $mods += '!' }
            '^shift$'           { $mods += '+' }
            default { throw "Unknown modifier '$mod' in '$text'; nothing was changed." }
        }
    }
    return $mods + $parts[-1].ToLower()
}
$ahkHotkey = ConvertTo-AhkHotkey $hotkey

$profileName = "herdr on $label"
$deskDir = Join-Path $env:LOCALAPPDATA 'agent-desk'
$iconPath = Join-Path $deskDir 'sheep.ico'
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
    icon        = $iconPath
    hidden      = $false
}
$list = @(@($list) | Where-Object { $_.name -ne $profileName }) + $entry
if ($settings.profiles -is [array]) { $settings.profiles = $list } else { $settings.profiles.list = $list }

New-Item -ItemType Directory -Force -Path $deskDir | Out-Null
Invoke-WebRequest -UseBasicParsing -OutFile $iconPath 'https://raw.githubusercontent.com/alvaro-francisco-gil/agent-desk/main/sheep.ico'

$backup = "$settingsPath.before-agent-desk-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item -LiteralPath $settingsPath -Destination $backup
[IO.File]::WriteAllText($settingsPath, ($settings | ConvertTo-Json -Depth 32), (New-Object Text.UTF8Encoding $false))

Write-Host "Added '$profileName' to Windows Terminal's new-tab menu."

if ($env:OS -eq 'Windows_NT') {
    $shell = New-Object -ComObject WScript.Shell
    $wt = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\wt.exe'

    $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Programs')) "$profileName.lnk"))
    $shortcut.TargetPath = $wt
    $shortcut.Arguments = "-p `"$profileName`""
    $shortcut.IconLocation = "$iconPath,0"
    $shortcut.Hotkey = ''
    $shortcut.Description = "herdr on $target"
    $shortcut.Save()
    Write-Host "Start menu: '$profileName' (right-click it to pin it to the taskbar)."

    function Find-AutoHotkey {
        @(
            (Join-Path $env:LOCALAPPDATA 'Programs\AutoHotkey\v2\AutoHotkey64.exe'),
            (Join-Path $env:ProgramFiles 'AutoHotkey\v2\AutoHotkey64.exe')
        ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    $ahkExe = Find-AutoHotkey
    if (-not $ahkExe) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'AutoHotkey is needed for the key and winget is missing: install AutoHotkey v2 from autohotkey.com, then run this again.'
        }
        Write-Host 'Installing AutoHotkey v2 (runs the key)...'
        winget install --id AutoHotkey.AutoHotkey --exact --scope user --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            winget install --id AutoHotkey.AutoHotkey --exact --accept-source-agreements --accept-package-agreements
        }
        $ahkExe = Find-AutoHotkey
        if (-not $ahkExe) { throw 'AutoHotkey did not install; the profile and Start menu shortcut are in place, the key is not.' }
    }

    $ahkScript = Join-Path $deskDir "herdr-on-$label.ahk"
    $ahkText = @(
        '#Requires AutoHotkey v2.0',
        '#SingleInstance Force',
        '#NoTrayIcon',
        "${ahkHotkey}::Run('wt.exe -p `"$profileName`"')"
    ) -join "`r`n"
    [IO.File]::WriteAllText($ahkScript, $ahkText, (New-Object Text.UTF8Encoding $true))

    $startup = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) "herdr on $label key.lnk"))
    $startup.TargetPath = $ahkExe
    $startup.Arguments = "`"$ahkScript`""
    $startup.Save()
    Start-Process -FilePath $ahkExe -ArgumentList "`"$ahkScript`""
    Write-Host "$hotkey opens it from anywhere, now and after every sign-in."
}
Write-Host "The old settings are in $backup"
