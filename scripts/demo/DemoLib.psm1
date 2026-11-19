# Lógica de la demo para PowerShell 7, separada de Docker para poder probarla sola
# (scripts/demo/DemoLib.Tests.ps1). La usa demo.ps1, en la raíz del repo. Es la misma
# lógica que scripts/demo/demo-lib.sh.
#
# Reglas:
# - backend/.env se crea desde backend/.env.example SOLO si no existe; si existe, no se
#   toca nunca.
# - Las claves nuevas salen de un generador criptográfico y tienen 48 bytes de azar.
# - Los mensajes van en español; los colores, solo si la salida es una terminal.

Set-StrictMode -Version Latest

# Códigos de salida (también los documenta docs/guia/10-operacion-local.md).
$script:DemoExit = [ordered]@{
    Ok        = 0
    Error     = 1
    Usage     = 2
    Docker    = 3
    Timeout   = 4
    Cancelled = 5
}
$script:DemoSecretKeys = @('DJANGO_SECRET_KEY', 'AUTH_JWT_SIGNING_KEY')
$script:DemoSecretBytes = 48
$script:DemoResetWord = 'BORRAR'
$script:UseColor = $false

function Get-DemoExitCode {
    param([Parameter(Mandatory)][string] $Name)
    return $script:DemoExit[$Name]
}

# --- Salida --------------------------------------------------------------------------

function Initialize-DemoColor {
    $script:UseColor = (-not $env:NO_COLOR) -and
        ($env:TERM -ne 'dumb') -and
        (-not [Console]::IsOutputRedirected) -and
        $Host.UI.SupportsVirtualTerminal
}

function Format-DemoText {
    param([string] $Text, [string] $Code)
    if ($script:UseColor) { return "$([char]27)[$($Code)m$Text$([char]27)[0m" }
    return $Text
}

function Write-DemoStep { param([string] $Message) Write-Host "$(Format-DemoText '==>' '1;36') $Message" }
function Write-DemoOk { param([string] $Message) Write-Host "$(Format-DemoText '✓' '32') $Message" }
function Write-DemoWarn { param([string] $Message) [Console]::Error.WriteLine("$(Format-DemoText '!' '33') $Message") }
function Write-DemoError { param([string] $Message) [Console]::Error.WriteLine("$(Format-DemoText 'Error:' '1;31') $Message") }

# --- Secretos y backend/.env ---------------------------------------------------------

function Test-DemoSecret {
    param([AllowEmptyString()][string] $Secret)
    return [bool]($Secret -cmatch '^[A-Za-z0-9_-]{64,}$')
}

# Un secreto aleatorio de 48 bytes en base64 de URL (sin "="), con el generador
# criptográfico del sistema.
function New-DemoSecret {
    $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes($script:DemoSecretBytes)
    return [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_').TrimEnd('=')
}

function Read-DemoText {
    param([Parameter(Mandatory)][string] $Path)
    return [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false))
}

function Write-DemoText {
    param([Parameter(Mandatory)][string] $Path, [Parameter(Mandatory)][AllowEmptyString()][string] $Text)
    [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}

# Reemplaza la primera línea "CLAVE=..." (sin comentar) o la agrega al final. Conserva el
# fin de línea del archivo (LF o CRLF).
function Set-DemoEnvValue {
    param(
        [Parameter(Mandatory)][string] $Path,
        [Parameter(Mandatory)][string] $Key,
        [Parameter(Mandatory)][string] $Value
    )
    $text = Read-DemoText -Path $Path
    $eol = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $endsWithEol = $text.EndsWith("`n")
    $lines = [System.Collections.Generic.List[string]]::new()
    if ($text.Length -gt 0) {
        $body = if ($endsWithEol) { $text.Substring(0, $text.Length - $eol.Length) } else { $text }
        $lines.AddRange([string[]]($body -split [regex]::Escape($eol)))
    }
    $done = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].StartsWith("$Key=", [System.StringComparison]::Ordinal)) {
            $lines[$i] = "$Key=$Value"
            $done = $true
            break
        }
    }
    if (-not $done) { $lines.Add("$Key=$Value") }
    $result = ($lines -join $eol)
    if ($endsWithEol -or -not $done) { $result += $eol }
    Write-DemoText -Path $Path -Text $result
}

function Get-DemoEnvValue {
    param(
        [Parameter(Mandatory)][string] $Path,
        [Parameter(Mandatory)][string] $Key,
        [string] $Default = ''
    )
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        foreach ($line in (Read-DemoText -Path $Path) -split "`r?`n") {
            if ($line.StartsWith("$Key=", [System.StringComparison]::Ordinal)) {
                $value = $line.Substring($Key.Length + 1)
                if ($value) { return $value }
                break
            }
        }
    }
    return $Default
}

# Devuelve 'Created' o 'Existed'. Lanza un error si no puede crearlo.
function Initialize-DemoEnv {
    param([Parameter(Mandatory)][string] $BackendDir)
    $envFile = Join-Path $BackendDir '.env'
    $example = Join-Path $BackendDir '.env.example'
    if (Test-Path -LiteralPath $envFile) { return 'Existed' }
    if (-not (Test-Path -LiteralPath $example -PathType Leaf)) {
        throw "No existe $example`: no hay de dónde crear backend/.env."
    }
    $tmp = Join-Path $BackendDir ".env.demo.$([guid]::NewGuid().ToString('N'))"
    try {
        [System.IO.File]::Copy($example, $tmp)
        foreach ($key in $script:DemoSecretKeys) {
            Set-DemoEnvValue -Path $tmp -Key $key -Value (New-DemoSecret)
        }
        Set-DemoEnvValue -Path $tmp -Key 'DJANGO_DEBUG' -Value 'True'
        try {
            # Move sin sobrescribir: si apareció un .env mientras tanto, se respeta.
            [System.IO.File]::Move($tmp, $envFile, $false)
        }
        catch [System.IO.IOException] {
            return 'Existed'
        }
        return 'Created'
    }
    finally {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
    }
}

# --- Espera y confirmación -----------------------------------------------------------

# Espera un 2xx. Devuelve $true o $false si se acabó el tiempo.
function Wait-DemoUrl {
    param(
        [Parameter(Mandatory)][string] $Url,
        [Parameter(Mandatory)][int] $TimeoutSeconds,
        [int] $IntervalSeconds = 3
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ($true) {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 5 -SkipHttpErrorCheck -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { return $true }
        }
        catch {
            # Todavía no responde: se reintenta.
        }
        if ([DateTime]::UtcNow -ge $deadline) { return $false }
        Start-Sleep -Seconds $IntervalSeconds
    }
}

# Acepta solo la palabra exacta (sin espacios ni minúsculas).
function Test-DemoResetAnswer {
    param([AllowNull()][AllowEmptyString()][string] $Answer)
    return [bool]($Answer -ceq $script:DemoResetWord)
}

function Get-DemoResetWord { return $script:DemoResetWord }

Export-ModuleMember -Function Get-DemoExitCode, Initialize-DemoColor, Write-DemoStep, Write-DemoOk,
    Write-DemoWarn, Write-DemoError, Test-DemoSecret, New-DemoSecret, Set-DemoEnvValue,
    Get-DemoEnvValue, Initialize-DemoEnv, Wait-DemoUrl, Test-DemoResetAnswer, Get-DemoResetWord
