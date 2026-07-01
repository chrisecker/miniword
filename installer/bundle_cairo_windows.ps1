# wxPython >=4.2.2 stopped bundling libcairo-2.dll on Windows: migrating
# their release CI from Buildbot to GitHub Actions dropped the --cairo
# build flag (reported upstream at wxWidgets/Phoenix). cairocffi's
# dlopen-by-name call also isn't visible to PyInstaller's static analysis,
# so without this step the built app only works on machines that happen
# to already have cairo on their DLL search path.
#
# usage: bundle_cairo_windows.ps1 <directory tree containing the installed wx package>
# (e.g. dist\MiniWord after a PyInstaller build, or a venv's site-packages)
$ErrorActionPreference = "Stop"

$distDir = $args[0]

$wxDir = Get-ChildItem -Path $distDir -Recurse -Directory -Filter "wx" | Select-Object -First 1
if (-not $wxDir) {
    throw "Could not find the bundled wx package directory under $distDir"
}

# Pinned to the last wxPython release tag whose wheel still shipped this
# DLL (4.2.1), since that's the last confirmed-good copy.
$url = "https://raw.githubusercontent.com/wxWidgets/Phoenix/wxPython-4.2.1/packaging/msw-cairo/x64/bin/libcairo-2.dll"
Invoke-WebRequest -Uri $url -OutFile (Join-Path $wxDir.FullName "libcairo-2.dll")
