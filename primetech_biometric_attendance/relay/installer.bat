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
if not exist "%PROGRAMME%" (
    echo  primetech_zk_relay.exe est introuvable dans %DOSSIER%.
    pause
    exit /b 1
)

echo.
echo  1/4 Arret d'une ancienne version eventuelle...
schtasks /End /TN "PrimeTech Pointeuse" >nul 2>&1
taskkill /IM primetech_zk_relay.exe /F >nul 2>&1

echo  2/4 Verification (si une pointeuse est deja configuree)...
"%PROGRAMME%" --test

echo.
echo  3/4 Creation de la tache planifiee "PrimeTech Pointeuse" (demarrage du PC)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$action = New-ScheduledTaskAction -Execute '%PROGRAMME%' -Argument '--service' -WorkingDirectory '%DOSSIER%';" ^
  "$triggers = @((New-ScheduledTaskTrigger -AtStartup), (New-ScheduledTaskTrigger -AtLogOn));" ^
  "$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew;" ^
  "$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;" ^
  "Register-ScheduledTask -TaskName 'PrimeTech Pointeuse' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null"
if errorlevel 1 (
    echo  Impossible de creer la tache planifiee.
    pause
    exit /b 1
)

echo  4/4 Raccourci "Pointeuse PrimeTech" sur le Bureau et demarrage...
(
    echo [InternetShortcut]
    echo URL=http://localhost:47321/
    echo IconFile=%PROGRAMME%
    echo IconIndex=0
) > "%PUBLIC%\Desktop\Pointeuse PrimeTech.url"
schtasks /Run /TN "PrimeTech Pointeuse" >nul
timeout /t 4 /nobreak >nul
start "" "http://localhost:47321/"

echo.
echo  Installation terminee.
echo  - La passerelle demarre automatiquement avec le PC, meme sans ouvrir de session.
echo  - Console : raccourci "Pointeuse PrimeTech" sur le Bureau (http://localhost:47321).
echo  - Journal : %DOSSIER%\passerelle.log
echo.
pause
