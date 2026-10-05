param([switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Set-Location -LiteralPath $PSScriptRoot
$appDataPath = Join-Path $env:LOCALAPPDATA 'GameHarness'
$downloadsPath = Join-Path $appDataPath 'downloads'
$configuration = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'bootstrap.json') -Raw | ConvertFrom-Json

function Test-Python312([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    & $Executable -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) and sys.maxsize > 2**32 else 1)' 2>$null
    return $LASTEXITCODE -eq 0
}

try {
    Write-Host 'Codex Vibe Game Creator - preparing your workspace...'
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required.' }
    $runtimePython = Join-Path $PSScriptRoot '.venv-runtime\Scripts\python.exe'
    if (-not (Test-Python312 $runtimePython)) {
        $runtimePython = Join-Path $appDataPath 'tools\python312\python.exe'
    }
    if (-not (Test-Python312 $runtimePython)) {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) {
            try {
                $candidate = & $launcher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0 -and (Test-Python312 $candidate)) { $runtimePython = $candidate }
            } catch { Write-Host 'Preparing a private Python runtime...' }
        }
    }
    if (-not (Test-Python312 $runtimePython)) {
        New-Item -ItemType Directory -Force -Path $downloadsPath | Out-Null
        $pythonVersion = $configuration.python_version
        $installer = Join-Path $downloadsPath "python-$pythonVersion-amd64.exe"
        Write-Host 'Downloading Python from python.org...'
        Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-amd64.exe" -OutFile $installer
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
            throw 'Python installer signature verification failed.'
        }
        $pythonFolder = Join-Path $appDataPath 'tools\python312'
        $installArgs = '/quiet InstallAllUsers=0 Include_pip=1 Include_launcher=0 InstallLauncherAllUsers=0 PrependPath=0 Shortcuts=0 AssociateFiles=0 Include_test=0 TargetDir="' + $pythonFolder + '"'
        $process = Start-Process -FilePath $installer -ArgumentList $installArgs -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -notin @(0,3010)) { throw "Python setup failed ($($process.ExitCode))." }
        $runtimePython = Join-Path $pythonFolder 'python.exe'
        if (-not (Test-Python312 $runtimePython)) { throw 'Python 3.12 setup could not be verified.' }
    }

    # Install the complete native package, including Windows sandbox helpers.
    # Child environment variables do not change the user's Codex configuration.
    $managedCodex = Join-Path $appDataPath 'tools\codex\bin\codex.exe'
    $probe = "from codex_bridge import find_codex`ntry: print(find_codex())`nexcept (OSError, RuntimeError): raise SystemExit(1)"
    $existingCodex = & $runtimePython -B -c $probe
    if ($LASTEXITCODE -ne 0) {
        New-Item -ItemType Directory -Force -Path $downloadsPath | Out-Null
        $codexInstaller = Join-Path $downloadsPath 'codex-install.ps1'
        Write-Host 'Downloading the official Codex CLI installer...'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://chatgpt.com/codex/install.ps1' -OutFile $codexInstaller
        $child = New-Object Diagnostics.ProcessStartInfo
        $child.FileName = 'powershell.exe'
        $child.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $codexInstaller + '" -Release ' + $configuration.codex_version
        $child.UseShellExecute = $false
        $child.CreateNoWindow = $true
        $child.EnvironmentVariables['CODEX_HOME'] = Join-Path $appDataPath 'tools\codex\home'
        $child.EnvironmentVariables['CODEX_INSTALL_DIR'] = Split-Path -Parent $managedCodex
        $child.EnvironmentVariables['CODEX_NON_INTERACTIVE'] = '1'
        $process = [Diagnostics.Process]::Start($child)
        $process.WaitForExit()
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $managedCodex)) { throw 'Codex CLI setup failed. Run the launcher again to retry.' }
    }
    $runtimeArgs = @('-B', (Join-Path $PSScriptRoot 'runtime_setup.py'))
    if ((Test-Path -LiteralPath (Join-Path $PSScriptRoot '.installed')) -and -not $PrepareOnly) {
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Codex Vibe Game Creator.lnk'))
        $shortcut.TargetPath = Join-Path $PSScriptRoot 'start.bat'
        $shortcut.WorkingDirectory = $PSScriptRoot
        $shortcut.Description = 'Codex Vibe Game Creator'
        $shortcut.Save()
    }
    if (-not $PrepareOnly) { $runtimeArgs += '--launch' }
    & $runtimePython @runtimeArgs
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
