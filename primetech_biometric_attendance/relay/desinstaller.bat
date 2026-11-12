@echo off
chcp 65001 >nul
title Desinstallation de la passerelle de pointeuse PrimeTech

net session >nul 2>&1
if errorlevel 1 (
    echo  Lancez ce fichier en tant qu'administrateur.
    pause
    exit /b 1
)

schtasks /End /TN "PrimeTech Pointeuse" >nul 2>&1
schtasks /Delete /TN "PrimeTech Pointeuse" /F >nul 2>&1
taskkill /IM primetech_zk_relay.exe /F >nul 2>&1
del "%PUBLIC%\Desktop\Pointeuse PrimeTech.url" >nul 2>&1
echo  La passerelle est arretee et ne demarrera plus avec le PC.
echo  Vous pouvez supprimer ce dossier (config.json contient la configuration).
pause
