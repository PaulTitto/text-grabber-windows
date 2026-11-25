$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonW = "C:\Users\PaulTitto\AppData\Local\Programs\Python\Python312\pythonw.exe"
$ScriptPath = Join-Path $AppDir "text_grabber_app.py"
$IconPath = Join-Path $AppDir "app_icon.ico"

$WshShell = New-Object -ComObject WScript.Shell

$Targets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Text Grabber.lnk"),
    (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\Text Grabber.lnk")
)

foreach ($LnkPath in $Targets) {
    $Shortcut = $WshShell.CreateShortcut($LnkPath)
    $Shortcut.TargetPath = $PythonW
    $Shortcut.Arguments = "`"$ScriptPath`""
    $Shortcut.WorkingDirectory = $AppDir
    $Shortcut.Description = "Text Grabber - Local Offline OCR"
    $Shortcut.Hotkey = "CTRL+ALT+T"
    if (Test-Path $IconPath) {
        $Shortcut.IconLocation = $IconPath
    }
    $Shortcut.Save()
    Write-Output "Installed shortcut: $LnkPath"
}
