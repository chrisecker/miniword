# Puts a working libcairo-2.dll into the wx package folder, where cairocffi
# finds it (wx.lib.wxcairo puts that folder in front of PATH).
#
# wxPython 4.2.2 - 4.2.5 ship no cairo DLL on Windows. wxPython 4.2.1 and
# 4.3.x ship one, but it is preshing/cairo-windows' cairo.dll 1.15.12
# (byte-identical), whose PDF backend is broken: every PDF surface fails
# with CAIRO_STATUS_NO_MEMORY on show_page()/finish(); preshing's 1.17.2
# has the same bug. So we always overwrite it with apotocki/cairo-win's
# build of cairo 1.18.4 (statically linked pixman/freetype/libpng/zlib,
# needs only system DLLs and the MSVC runtime that Python ships).
# cairocffi's dlopen-by-name call also isn't visible to PyInstaller's
# static analysis, so without this step the built app depends on whatever
# cairo happens to be on the DLL search path.
#
# usage: bundle_cairo_windows.ps1 <directory tree containing the installed wx package>
# (e.g. dist\MiniWord after a PyInstaller build, or a venv's site-packages)
$ErrorActionPreference = "Stop"

$distDir = $args[0]

$wxDir = Get-ChildItem -Path $distDir -Recurse -Directory -Filter "wx" | Select-Object -First 1
if (-not $wxDir) {
    throw "Could not find the bundled wx package directory under $distDir"
}

$url = "https://github.com/apotocki/cairo-win/releases/download/1.18.4.0/cairo-1.18.4.zip"
$entry = "bin/cairo.dll"
$dllSha256 = "104aa67829da347e818ee59bfc2801a3970e5a2c95962c583fe87a886021ecb0"

$zip = Join-Path ([System.IO.Path]::GetTempPath()) "cairo-1.18.4.zip"
$dst = Join-Path $wxDir.FullName "libcairo-2.dll"
Invoke-WebRequest -Uri $url -OutFile $zip

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    $e = $archive.GetEntry($entry)
    if (-not $e) { throw "$entry not found in $url" }
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $dst, $true)
} finally {
    $archive.Dispose()
    Remove-Item $zip
}

$hash = (Get-FileHash -Algorithm SHA256 $dst).Hash.ToLower()
if ($hash -ne $dllSha256) {
    Remove-Item $dst
    throw "libcairo-2.dll has SHA-256 $hash, expected $dllSha256"
}
Write-Host "Installed cairo 1.18.4 as $dst"
