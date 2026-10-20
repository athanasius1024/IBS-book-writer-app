<#
Build the single-file Windows program:  dist\IBSBookWriter.exe

    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1            # build
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Test      # build, then smoke-test it

Needs, installed first:
  * Python 3.11 or newer for Windows (python.org) on the PATH
  * MSYS2 (https://www.msys2.org), by default in C:\msys64, with Pango installed once:
        C:\msys64\usr\bin\bash.exe -lc "pacman -S --noconfirm mingw-w64-x86_64-pango mingw-w64-x86_64-ntldd"
  (the GitHub workflow does both of these for you).

Pango and the libraries it needs (GLib, HarfBuzz, fontconfig, FreeType ...) come from MSYS2 and are packed inside
the .exe, so the people who run it install nothing.
#>
param(
    [switch]$Test,
    [string]$Msys = $(if ($env:MSYS2_ROOT) { $env:MSYS2_ROOT } else { 'C:\msys64' })
)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$bin = Join-Path $Msys 'mingw64\bin'
$ntldd = Join-Path $bin 'ntldd.exe'
if (-not (Test-Path (Join-Path $bin 'libpango-1.0-0.dll'))) {
    throw "Pango was not found in $bin. Install it with: $Msys\usr\bin\bash.exe -lc 'pacman -S --noconfirm mingw-w64-x86_64-pango mingw-w64-x86_64-ntldd'"
}

# 1. Collect Pango and everything it needs into build\native-libs
$libs = Join-Path (Get-Location) 'build\native-libs'
Remove-Item -Recurse -Force $libs -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $libs | Out-Null
$roots = 'libpango-1.0-0.dll', 'libpangoft2-1.0-0.dll', 'libgobject-2.0-0.dll', 'libglib-2.0-0.dll',
         'libharfbuzz-0.dll', 'libharfbuzz-subset-0.dll', 'libfontconfig-1.dll', 'libfreetype-6.dll'
$seen = @{}
$queue = [System.Collections.Queue]::new()
foreach ($r in $roots) { $queue.Enqueue($r) }
while ($queue.Count -gt 0) {
    $name = $queue.Dequeue()
    if ($seen.ContainsKey($name.ToLower())) { continue }
    $seen[$name.ToLower()] = $true
    $path = Join-Path $bin $name
    if (-not (Test-Path $path)) { continue }              # a Windows system DLL, not an MSYS2 one
    Copy-Item $path $libs
    if (Test-Path $ntldd) {
        foreach ($line in (& $ntldd $path)) {
            if ($line -match '^\s*(\S+\.dll)\s*=>') { $queue.Enqueue($Matches[1]) }
        }
    }
}
Write-Host ("Bundling {0} native libraries from {1}" -f (Get-ChildItem $libs -Filter *.dll).Count, $bin)
$env:IBS_NATIVE_LIBS = $libs

# 2. Python environment and PyInstaller
$venv = '.venv-desktop'
if (-not (Test-Path "$venv\Scripts\python.exe")) { python -m venv $venv }
& "$venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$venv\Scripts\python.exe" -m pip install --quiet -r requirements-desktop.txt

Remove-Item -Recurse -Force build\pyinstaller, dist\IBSBookWriter.exe -ErrorAction SilentlyContinue
& "$venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --workpath build\pyinstaller --distpath dist packaging\ibsbook.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

Get-Item dist\IBSBookWriter.exe | Format-List Name, Length
(Get-FileHash dist\IBSBookWriter.exe -Algorithm SHA256).Hash.ToLower() + '  IBSBookWriter.exe' | Set-Content -Encoding ascii dist\IBSBookWriter.exe.sha256

if ($Test) {
    & "$venv\Scripts\python.exe" -m pip install --quiet pypdf          # only the test uses it, to read the PDF it gets
    & "$venv\Scripts\python.exe" packaging\smoke_test.py dist\IBSBookWriter.exe
    if ($LASTEXITCODE -ne 0) { throw 'Smoke test failed' }
}
