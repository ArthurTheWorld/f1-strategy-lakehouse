# Uso (PowerShell, dentro desta pasta):
#   .\rodar.ps1            -> baixa corridas REAIS de 2024 (FastF1), processa e abre o dashboard
#   .\rodar.ps1 -Sintetico -> usa dados sinteticos (sem internet)
param([switch]$Sintetico, [int]$Ano = 2024, [int[]]$Rodadas = @(1,2,3,4,5,6))
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python nao encontrado. Instale em python.org (marque 'Add to PATH')." }

if (-not (Test-Path .venv\Scripts\python.exe))     { python -m venv .venv }
if (-not (Test-Path .venv-dbt\Scripts\python.exe)) { python -m venv .venv-dbt }
Write-Host ">> Instalando dependencias (so na primeira vez demora)..."
& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
& .\.venv-dbt\Scripts\python.exe -m pip install -q -r requirements-dbt.txt
$env:DBT_BIN = (Resolve-Path .\.venv-dbt\Scripts\dbt.exe).Path

if (Test-Path data) { Remove-Item data -Recurse -Force }
if ($Sintetico) {
    Write-Host ">> Gerando corridas sinteticas..."
    & .\.venv\Scripts\python.exe -m f1lab.pipeline synth --races 8 --seed 7
} else {
    Write-Host ">> Baixando corridas reais $Ano, rodadas $($Rodadas -join ',') (a 1a vez demora)..."
    & .\.venv\Scripts\python.exe -m f1lab.fetch_fastf1 --year $Ano --rounds $Rodadas --out data/bronze
}
if ($LASTEXITCODE -ne 0) { throw "Falha na etapa de dados. Copie a mensagem de erro e mande para o Claude." }
& .\.venv\Scripts\python.exe -m f1lab.pipeline build
if ($LASTEXITCODE -ne 0) { throw "Falha no dbt." }
& .\.venv\Scripts\python.exe -m f1lab.pipeline train
if ($LASTEXITCODE -ne 0) { throw "Falha no treino." }
Write-Host ">> Abrindo o dashboard em http://localhost:8501"
& .\.venv\Scripts\streamlit.exe run dashboard/app.py
