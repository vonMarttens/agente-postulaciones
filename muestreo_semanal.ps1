$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$fecha     = Get-Date -Format "yyyy-MM-dd"
$log       = Join-Path $PSScriptRoot "muestreo\_log.txt"
$propuesta = Join-Path $PSScriptRoot "muestreo\terminos-propuestos.md"

# ── 1. Muestreo ──────────────────────────────────────────────
try {
    $salida  = & python muestrear_titulos.py 2>&1 | Out-String
    $archivo = Join-Path $PSScriptRoot "muestreo\titulos_$fecha.txt"
    if (-not (Test-Path $archivo)) { throw "No se genero titulos_$fecha.txt" }
    $cabecera = (Get-Content $archivo -TotalCount 3)[2]
} catch {
    "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') · FALLO MUESTREO ===`n$_" |
        Add-Content $log -Encoding UTF8
    $mensaje = "Fallo el muestreo. Revisa muestreo\_log.txt"
    $salida  = ""
}

# ── 1.1 Limpiar ofertas caducadas ────────────────────────────────
$purga = & python verificar_vigencia.py --aplicar 2>&1 | Out-String

# ── 2. Subagente, solo si el muestreo salio bien ─────────────
if ($cabecera) {
    $antes = if (Test-Path $propuesta) {
        (Get-Item $propuesta).LastWriteTime
    } else { [datetime]::MinValue }

    $instruccion = "Usa el subagente explorador-terminos con el muestreo mas " +
                   "reciente (muestreo/titulos_$fecha.txt). Escribe tus " +
                   "propuestas en muestreo/terminos-propuestos.md. No " +
                   "modifiques terminos.json ni exclusiones.json."

    try {
        $agente = & claude -p $instruccion `
                    --output-format text `
                    --allowedTools "Read,Write,Glob,Grep" 2>&1 | Out-String

        $despues = if (Test-Path $propuesta) {
            (Get-Item $propuesta).LastWriteTime
        } else { [datetime]::MinValue }

        $mensaje = if ($despues -gt $antes) {
            "$cabecera`nPropuestas listas en terminos-propuestos.md"
        } elseif ($agente -match "permiso|autoriza|¿Lo autorizas|necesito que") {
            "$cabecera`nEl agente pidio permiso y quedo esperando. Revisa el log."
        } else {
            "$cabecera`nSin propuestas nuevas esta semana."
        }
    } catch {
        $agente  = $_ | Out-String
        $mensaje = "$cabecera`nFallo el subagente. Muestreo si quedo guardado."
    }
}

# ── 3. Log y aviso ───────────────────────────────────────────
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') ===`n$salida`n--- agente ---`n$agente" |
    Add-Content $log -Encoding UTF8

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$aviso = New-Object System.Windows.Forms.NotifyIcon
$aviso.Icon            = [System.Drawing.SystemIcons]::Information
$aviso.BalloonTipTitle = "agente-postulaciones"
$aviso.BalloonTipText  = $mensaje
$aviso.Visible         = $true
$aviso.ShowBalloonTip(20000)
Start-Sleep -Seconds 25
$aviso.Dispose()