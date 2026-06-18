# Registra o worker.py como tarefa agendada no Windows Task Scheduler
# Execute como Administrador: powershell -ExecutionPolicy Bypass -File setup_task.ps1

$TaskName     = "APIMEI Worker"
$PythonExe    = (Get-Command python).Source -replace "python\.exe$", "pythonw.exe"
$WorkerDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkerScript = Join-Path $WorkerDir "worker.py"

# Remove task e bat anteriores
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$OldBat = Join-Path $WorkerDir "run_worker.bat"
if (Test-Path $OldBat) { Remove-Item $OldBat -Force }

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$WorkerScript`"" `
    -WorkingDirectory $WorkerDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Force | Out-Null

Write-Host "Task '$TaskName' registrada com sucesso."
Write-Host "Iniciando agora..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3
$state = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "Estado: $state"
