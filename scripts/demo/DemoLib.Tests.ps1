#Requires -Version 7.2
# Pruebas de scripts/demo/DemoLib.psm1 y de Invoke-Compose de demo.ps1, sin Docker y en un
# directorio temporal.
# Uso: pwsh -NoProfile -File scripts/demo/DemoLib.Tests.ps1   (sale con 1 si alguna falla)
# Sin Pester a propósito: así corren con cualquier PowerShell 7.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'DemoLib.psm1') -Force

$script:Passed = 0
$script:Failed = 0
function Check {
    param([string] $Name, [scriptblock] $Condition)
    $ok = $false
    try { $ok = [bool](& $Condition) } catch { $ok = $false }
    if ($ok) { $script:Passed++ } else { $script:Failed++; Write-Host "FALLA: $Name" }
}
function Read-Raw { param([string] $Path) [System.IO.File]::ReadAllText($Path) }
function Count-CR { param([string] $Path) @((Read-Raw $Path).ToCharArray() | Where-Object { $_ -eq "`r" }).Count }
function Count-Lines { param([string] $Path) ((Read-Raw $Path) -split "`n").Count - 1 }
function Write-Raw { param([string] $Path, [string] $Text) [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false)) }
function Get-Hash { param([string] $Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }

# Un .env.example de mentira, con CRLF como el real; nunca se lee el del repo.
function New-Example {
    param([string] $Dir)
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    Write-Raw (Join-Path $Dir '.env.example') "# Demo`r`nDJANGO_SECRET_KEY=cambiar`r`nDJANGO_DEBUG=False`r`nPOSTGRES_DB=mvp_credit`r`n# AUTH_JWT_SIGNING_KEY=comentada`r`nAUTH_JWT_SIGNING_KEY=cambiar`r`n"
}

$work = Join-Path ([System.IO.Path]::GetTempPath()) "demo-tests-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $work | Out-Null
try {
    # --- Códigos de salida ---------------------------------------------------------------
    Check 'códigos de salida iguales a los de bash' {
        (Get-DemoExitCode Ok) -eq 0 -and (Get-DemoExitCode Error) -eq 1 -and (Get-DemoExitCode Usage) -eq 2 -and
        (Get-DemoExitCode Docker) -eq 3 -and (Get-DemoExitCode Timeout) -eq 4 -and (Get-DemoExitCode Cancelled) -eq 5
    }

    # --- Secretos ------------------------------------------------------------------------
    $s1 = New-DemoSecret
    $s2 = New-DemoSecret
    Check 'el secreto tiene 48 bytes en base64 de URL' { Test-DemoSecret $s1 }
    Check 'el secreto tiene exactamente 64 caracteres' { $s1.Length -eq 64 }
    Check 'dos secretos son distintos' { $s1 -ne $s2 }
    Check 'un secreto corto no es válido' { -not (Test-DemoSecret 'abc') }
    Check 'un secreto con espacios no es válido' { -not (Test-DemoSecret (('a' * 63) + ' ')) }

    # --- Set-DemoEnvValue y Get-DemoEnvValue ---------------------------------------------
    $f = Join-Path $work 'lf.env'
    Write-Raw $f "A=1`nB=2`n"
    Set-DemoEnvValue -Path $f -Key 'B' -Value '9'
    Check 'reemplaza una clave (LF)' { (Read-Raw $f) -ceq "A=1`nB=9`n" }
    Set-DemoEnvValue -Path $f -Key 'C' -Value '3'
    Check 'agrega una clave que falta (LF)' { (Get-DemoEnvValue -Path $f -Key 'C') -eq '3' }
    Check 'no agrega CR a un archivo LF' { (Count-CR $f) -eq 0 }

    $f = Join-Path $work 'crlf.env'
    Write-Raw $f "A=1`r`n# B=comentada`r`nB=2`r`n"
    Set-DemoEnvValue -Path $f -Key 'B' -Value '9'
    Check 'reemplaza una clave y conserva CRLF' { (Count-CR $f) -eq 3 }
    Check 'no toca la línea comentada' { (Read-Raw $f).Contains("# B=comentada`r`n") }
    Check 'lee el valor sin el CR' { (Get-DemoEnvValue -Path $f -Key 'B') -ceq '9' }
    Set-DemoEnvValue -Path $f -Key 'D' -Value '4'
    Check 'agrega con CRLF en un archivo CRLF' { (Count-CR $f) -eq 4 }
    Check 'valor por omisión si falta la clave' { (Get-DemoEnvValue -Path $f -Key 'NADA' -Default '8000') -eq '8000' }
    Check 'valor por omisión si falta el archivo' { (Get-DemoEnvValue -Path (Join-Path $work 'no-existe') -Key 'X' -Default '3000') -eq '3000' }

    # --- Initialize-DemoEnv --------------------------------------------------------------
    $dir = Join-Path $work 'backend-nuevo'
    New-Example $dir
    $envFile = Join-Path $dir '.env'
    $example = Join-Path $dir '.env.example'
    Check 'crea backend/.env si no existe' { (Initialize-DemoEnv -BackendDir $dir) -eq 'Created' }
    Check 'el .env existe' { Test-Path -LiteralPath $envFile }
    $key1 = Get-DemoEnvValue -Path $envFile -Key 'DJANGO_SECRET_KEY'
    $key2 = Get-DemoEnvValue -Path $envFile -Key 'AUTH_JWT_SIGNING_KEY'
    Check 'DJANGO_SECRET_KEY es nueva y fuerte' { Test-DemoSecret $key1 }
    Check 'AUTH_JWT_SIGNING_KEY es nueva y fuerte' { Test-DemoSecret $key2 }
    Check 'las dos claves son distintas' { $key1 -ne $key2 }
    Check 'DJANGO_DEBUG=True' { (Get-DemoEnvValue -Path $envFile -Key 'DJANGO_DEBUG') -ceq 'True' }
    Check 'conserva las demás variables' { (Get-DemoEnvValue -Path $envFile -Key 'POSTGRES_DB') -eq 'mvp_credit' }
    Check 'conserva la línea comentada' { (Read-Raw $envFile).Contains('# AUTH_JWT_SIGNING_KEY=comentada') }
    Check 'no agrega ni quita líneas' { (Count-Lines $envFile) -eq (Count-Lines $example) }
    Check 'conserva el CRLF del ejemplo' { (Count-CR $envFile) -eq (Count-CR $example) }
    Check 'no deja temporales' { @(Get-ChildItem -LiteralPath $dir -Force -Filter '.env.demo.*').Count -eq 0 }
    Check 'no cambia el .env.example' { (Read-Raw $example).Contains('DJANGO_SECRET_KEY=cambiar') }

    $before = Get-Hash $envFile
    Check 'si ya existe, devuelve Existed' { (Initialize-DemoEnv -BackendDir $dir) -eq 'Existed' }
    Check 'si ya existe, no lo toca' { (Get-Hash $envFile) -eq $before }

    $dir = Join-Path $work 'backend-propio'
    New-Example $dir
    Write-Raw (Join-Path $dir '.env') "MI_CONFIG=no-tocar`n"
    $before = Get-Hash (Join-Path $dir '.env')
    Initialize-DemoEnv -BackendDir $dir | Out-Null
    Check 'un .env propio queda idéntico' { (Get-Hash (Join-Path $dir '.env')) -eq $before }

    $dir = Join-Path $work 'backend-sin-ejemplo'
    New-Item -ItemType Directory -Path $dir | Out-Null
    $threw = $false
    try { Initialize-DemoEnv -BackendDir $dir | Out-Null } catch { $threw = $true }
    Check 'sin .env.example es un error' { $threw }
    Check 'sin .env.example no crea nada' { -not (Test-Path -LiteralPath (Join-Path $dir '.env')) }

    # --- Invoke-Compose de demo.ps1, con un docker falso ---------------------------------
    # Se toma la función del archivo con el parser (demo.ps1 no se ejecuta). El docker
    # falso es una función: tapa al de verdad (las funciones van antes que los programas),
    # guarda sus argumentos y la carpeta, y devuelve un código propio.
    $demoAst = [System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $PSScriptRoot '../../demo.ps1'), [ref] $null, [ref] $null)
    $composeAst = $demoAst.Find({
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Compose'
        }, $true)
    Check 'demo.ps1 define Invoke-Compose' { $null -ne $composeAst }
    # Con param() o [CmdletBinding()] es función avanzada y PowerShell toma `-d` como su
    # `-Debug`: `up -d` quedaba en primer plano y el script nunca llegaba al seed.
    Check 'Invoke-Compose es una función simple (sin param ni CmdletBinding)' { $null -eq $composeAst.Body.ParamBlock }

    $BackendDir = Join-Path $work 'compose-backend'
    New-Item -ItemType Directory -Path $BackendDir | Out-Null
    $script:DockerCalls = [System.Collections.Generic.List[object]]::new()
    function docker {
        $script:DockerCalls.Add([pscustomobject]@{ Args = @($args); Dir = (Get-Location).Path })
        $global:LASTEXITCODE = 7
    }
    . ([scriptblock]::Create($composeAst.Extent.Text))

    $here = (Get-Location).Path
    $code = Invoke-Compose up -d --build
    Check 'up -d --build le llega completo a docker' { ($script:DockerCalls[0].Args -join ' ') -ceq 'compose up -d --build' }
    Check 'corre desde backend/' { $script:DockerCalls[0].Dir -eq (Get-Item -LiteralPath $BackendDir).FullName }
    Check 'devuelve el código de docker' { $code -eq 7 }
    Check 'vuelve a la carpeta de antes' { (Get-Location).Path -eq $here }

    Invoke-Compose --profile full up -d --build | Out-Null
    Check 'el perfil full y up -d llegan completos' { ($script:DockerCalls[1].Args -join ' ') -ceq 'compose --profile full up -d --build' }
    Invoke-Compose exec -T backend python manage.py seed_demo_data --new-portal-link | Out-Null
    Check 'exec -T y el seed llegan completos' {
        ($script:DockerCalls[2].Args -join ' ') -ceq 'compose exec -T backend python manage.py seed_demo_data --new-portal-link'
    }
    Remove-Item -LiteralPath Function:docker

    # --- Confirmación del borrado --------------------------------------------------------
    Check 'BORRAR confirma' { Test-DemoResetAnswer 'BORRAR' }
    Check 'borrar en minúsculas no confirma' { -not (Test-DemoResetAnswer 'borrar') }
    Check 'BORRAR con espacio no confirma' { -not (Test-DemoResetAnswer 'BORRAR ') }
    Check 'una respuesta vacía no confirma' { -not (Test-DemoResetAnswer '') }
    Check 'sin respuesta no confirma' { -not (Test-DemoResetAnswer $null) }
}
finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "$($script:Passed) pruebas pasaron, $($script:Failed) fallaron"
if ($script:Failed -gt 0) { exit 1 }
exit 0
