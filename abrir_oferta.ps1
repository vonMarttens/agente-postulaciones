param([string]$Carpeta = ".")

$anuncio = Join-Path $Carpeta "stellenanzeige.txt"

if (-not (Test-Path $anuncio)) {
    Write-Host "No hay stellenanzeige.txt en $Carpeta"
    exit 1
}

$m = Select-String -Path $anuncio -Pattern "^ENLACE:\s*(.+)$"
if (-not $m) {
    Write-Host "El anuncio no tiene linea ENLACE:"
    exit 1
}

Start-Process $m.Matches.Groups[1].Value.Trim()