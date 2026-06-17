# Registra o worker.py como tarefa agendada no Windows Task Scheduler
# Execute como Administrador: powershell -ExecutionPolicy Bypass -File setup_task.ps1

$TaskName   = "APIMEI Worker"
$PythonExe  = (Get-Command python).Source
$WorkerDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkerScript = Join-Path $WorkerDir "worker.py"

# Remove task anterior se existir
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action  = New-ScheduledTaskAction -Execute $PythonExe -Argument $WorkerScript -WorkingDirectory $WorkerDir
$Trigger = New-ScheduledTaskTrigger -AtStartup

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "Task '$TaskName' registrada com sucesso."
Write-Host "Iniciando agora..."
Start-ScheduledTask -TaskName $TaskName
Write-Host "Worker rodando. Verifique com: Get-ScheduledTask -TaskName '$TaskName'"
