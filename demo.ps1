<#
.SYNOPSIS
    Demo con un solo comando (Windows, PowerShell 7).

.DESCRIPTION
    Sin opciones: revisa Docker, crea backend/.env si no existe (con claves nuevas),
    levanta el modo simple (postgres, backend y frontend), espera a la API, carga los
    datos de demo e imprime las URL y los usuarios.

    Guía: docs/guia/10-operacion-local.md. La lógica que no necesita Docker vive en
    scripts/demo/DemoLib.psm1 y se prueba con scripts/demo/DemoLib.Tests.ps1.

.PARAMETER Full
    Levanta también el perfil "full" (Redis, SeaweedFS, worker y ClamAV). Requiere el
    bloque "Full" activo en backend/.env.

.PARAMETER Stop
    Detiene los contenedores sin borrar nada.

.PARAMETER Reset
    Borra contenedores y volúmenes (base de datos y documentos). Pide escribir BORRAR.

.EXAMPLE
    ./demo.ps1
.EXAMPLE
    ./demo.ps1 -Stop
#>
#Requires -Version 7.2
[CmdletBinding()]
param(
    [switch] $Full,
    [switch] $Stop,
    [switch] $Reset,
    [switch] $Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = $PSScriptRoot
$BackendDir = Join-Path $RootDir 'backend'
Import-Module (Join-Path $RootDir 'scripts/demo/DemoLib.psm1') -Force
Initialize-DemoColor

function Exit-Demo {
    param([Parameter(Mandatory)][string] $Code)
    exit (Get-DemoExitCode $Code)
}

# Corre `docker compose` desde backend/, donde están el compose y el .env.
function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments)][string[]] $Arguments)
    Push-Location $BackendDir
    try {
        # Out-Host: la salida va a la pantalla y la función devuelve solo el código.
        & docker compose @Arguments | Out-Host
        return $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

if ($Help) {
    Get-Help $PSCommandPath -Detailed
    Exit-Demo Ok
}
if ($Stop -and $Reset) {
    Write-DemoError '-Stop y -Reset no van juntos.'
    Exit-Demo Usage
}

# --- 1. Docker -----------------------------------------------------------------------
Write-DemoStep 'Revisando Docker'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-DemoError 'No encuentro el comando docker. Instala Docker Desktop.'
    Exit-Demo Docker
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-DemoError 'Docker no está corriendo. Abre Docker Desktop y vuelve a intentarlo.'
    Exit-Demo Docker
}
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-DemoError "Falta Docker Compose v2 (el comando 'docker compose')."
    Exit-Demo Docker
}
Write-DemoOk 'Docker responde'

# --- Detener o borrar ----------------------------------------------------------------
if ($Stop) {
    Write-DemoStep 'Deteniendo los contenedores (los datos se conservan)'
    if ((Invoke-Compose --profile full stop) -ne 0) { Exit-Demo Error }
    Write-DemoOk 'Demo detenida. Vuelve a levantarla con ./demo.ps1'
    Exit-Demo Ok
}

if ($Reset) {
    if ([Console]::IsInputRedirected) {
        Write-DemoError 'Borrar los datos exige confirmarlo en una terminal interactiva.'
        Exit-Demo Cancelled
    }
    $word = Get-DemoResetWord
    $answer = Read-Host "Esto borra la base de datos y los documentos de la demo. Escribe $word para confirmar"
    if (-not (Test-DemoResetAnswer $answer)) {
        Write-DemoWarn 'No se borró nada.'
        Exit-Demo Cancelled
    }
    Write-DemoStep 'Borrando contenedores y volúmenes'
    if ((Invoke-Compose --profile full down --volumes --remove-orphans) -ne 0) { Exit-Demo Error }
    Write-DemoOk 'Listo. backend/.env no se tocó. Vuelve a empezar con ./demo.ps1'
    Exit-Demo Ok
}

# --- 2. backend/.env -----------------------------------------------------------------
Write-DemoStep 'Revisando backend/.env'
try {
    $envState = Initialize-DemoEnv -BackendDir $BackendDir
}
catch {
    Write-DemoError $_.Exception.Message
    Exit-Demo Error
}
if ($envState -eq 'Created') {
    Write-DemoOk 'Creé backend/.env desde .env.example, con claves nuevas (DJANGO_SECRET_KEY y AUTH_JWT_SIGNING_KEY) y DJANGO_DEBUG=True'
}
else {
    Write-DemoOk 'backend/.env ya existe: no lo toco'
}

$envFile = Join-Path $BackendDir '.env'
$backendPort = if ($env:BACKEND_HOST_PORT) { $env:BACKEND_HOST_PORT } else { Get-DemoEnvValue -Path $envFile -Key 'BACKEND_HOST_PORT' -Default '8000' }
$frontendPort = if ($env:FRONTEND_HOST_PORT) { $env:FRONTEND_HOST_PORT } else { Get-DemoEnvValue -Path $envFile -Key 'FRONTEND_HOST_PORT' -Default '3000' }
$apiUrl = "http://localhost:$backendPort"
$webUrl = "http://localhost:$frontendPort"

# --- 3. Contenedores -----------------------------------------------------------------
$profileArgs = @()
$timeout = 300
if ($Full) {
    $profileArgs = @('--profile', 'full')
    $timeout = 600
    Write-DemoWarn 'Modo completo: el backend usa Redis, SeaweedFS y ClamAV solo si backend/.env tiene activo el bloque "Full". ClamAV tarda varios minutos en bajar sus firmas la primera vez.'
    Write-DemoStep 'Levantando la demo en el modo completo (la primera vez construye las imágenes)'
}
else {
    Write-DemoStep 'Levantando la demo en el modo simple: postgres, backend y frontend (la primera vez construye las imágenes)'
}
if ($env:DEMO_TIMEOUT_SECONDS) { $timeout = [int] $env:DEMO_TIMEOUT_SECONDS }
if ((Invoke-Compose @profileArgs up -d --build) -ne 0) {
    Write-DemoError 'docker compose no pudo levantar los contenedores. Revisa el mensaje de arriba.'
    Exit-Demo Error
}

# --- 4. Salud ------------------------------------------------------------------------
Write-DemoStep "Esperando a la API (hasta $timeout s): migraciones y arranque"
foreach ($probe in 'health', 'ready') {
    if (-not (Wait-DemoUrl -Url "$apiUrl/$probe" -TimeoutSeconds $timeout)) {
        Write-DemoError "La API no respondió en $apiUrl/$probe después de $timeout s."
        Write-DemoError 'Mira qué pasó con: cd backend; docker compose logs --tail 80 backend'
        Exit-Demo Timeout
    }
}
Write-DemoOk "API lista en $apiUrl"

# --- 5. Datos de demo ----------------------------------------------------------------
Write-DemoStep 'Cargando los datos de demo (se puede repetir: no duplica ni borra nada)'
Write-Host ''
if ((Invoke-Compose exec -T backend python manage.py seed_demo_data) -ne 0) {
    Write-DemoError 'Falló la carga de datos de demo. Revisa el mensaje de arriba.'
    Exit-Demo Error
}
Write-Host ''

# --- 6. Resumen ----------------------------------------------------------------------
if (-not (Wait-DemoUrl -Url "$webUrl/login" -TimeoutSeconds 120)) {
    Write-DemoWarn "El frontend todavía no responde en $webUrl. Revisa: cd backend; docker compose logs --tail 80 frontend"
}

Write-Host 'Demo lista'
Write-Host "  Backoffice ................ $webUrl/login"
Write-Host '  Portal del comprador ...... el enlace de un solo uso que imprimió el seed, arriba'
Write-Host "  API ....................... $apiUrl/api/v1/"
Write-Host "  Documentación de la API ... $apiUrl/docs (solo con DEBUG)"
Write-Host '  Usuarios y contraseña ..... en la tabla que imprimió el seed, arriba'
Write-Host ''
Write-Host '  Detener sin borrar ........ ./demo.ps1 -Stop'
Write-Host '  Empezar de cero ........... ./demo.ps1 -Reset'
Write-Host '  Recorrido sugerido ........ docs/guia/10-operacion-local.md'
Exit-Demo Ok
