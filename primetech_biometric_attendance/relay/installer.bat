@echo off
chcp 65001 >nul
setlocal
title Installation de la passerelle de pointeuse PrimeTech

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Ce programme doit etre lance en tant qu'administrateur :
    echo  clic droit sur installer.bat ^> "Executer en tant qu'administrateur".
    echo.
    pause
    exit /b 1
)

set "DOSSIER=%~dp0"
if "%DOSSIER:~-1%"=="\" set "DOSSIER=%DOSSIER:~0,-1%"
set "PROGRAMME=%DOSSIER%\primetech_zk_relay.exe"
set "ARGUMENTS="
if not exist "%PROGRAMME%" (
    where pythonw >nul 2>&1
    if errorlevel 1 (
        echo  primetech_zk_relay.exe est introuvable et Python n'est pas installe.
        pause
        exit /b 1
    )
    for /f "delims=" %%P in ('where pythonw') do set "PROGRAMME=%%P"
    set "ARGUMENTS=""%DOSSIER%\primetech_zk_relay.py"""
)

echo.
echo  1/3 Verification de la pointeuse et de la connexion a Odoo...
echo.
if exist "%DOSSIER%\primetech_zk_relay.exe" (
    "%DOSSIER%\primetech_zk_relay.exe" --test
) else (
    python "%DOSSIER%\primetech_zk_relay.py" --test
)
if errorlevel 1 (
    echo.
    echo  Le test a echoue : verifiez config.ini ^(adresse de la pointeuse, adresse d'Odoo^).
    echo  Vous pouvez quand meme installer : la passerelle reessaiera automatiquement.
    choice /M "  Installer quand meme"
    if errorlevel 2 exit /b 1
)

echo.
echo  2/3 Creation de la tache planifiee "PrimeTech Pointeuse" (demarrage du PC)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$action = New-ScheduledTaskAction -Execute '%PROGRAMME%' -Argument '%ARGUMENTS%' -WorkingDirectory '%DOSSIER%';" ^
  "$triggers = @((New-ScheduledTaskTrigger -AtStartup), (New-ScheduledTaskTrigger -AtLogOn));" ^
  "$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew;" ^
  "$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;" ^
  "Register-ScheduledTask -TaskName 'PrimeTech Pointeuse' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null"
if errorlevel 1 (
    echo  Impossible de creer la tache planifiee.
    pause
    exit /b 1
)

echo  3/3 Demarrage de la passerelle...
schtasks /Run /TN "PrimeTech Pointeuse" >nul
echo.
echo  Installation terminee. La passerelle demarre automatiquement avec le PC.
echo  Journal : %DOSSIER%\passerelle.log
echo.
pause
