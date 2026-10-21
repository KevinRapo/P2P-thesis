<#
TalTech HPC helper: start, connect to, watch and stop the Jupyter job.
Reference: docs/hpc/notebooks.md (https://kevinrapo.github.io/P2P-thesis/hpc/notebooks/)

  hpc start [sbatch options]   submit hpc/jupyter.slurm, wait until Jupyter runs, open the tunnel
                               e.g. hpc start -c 78 --mem=60G -t 01:30:00
                               (Jupyter runs in ~/<current git branch> on the cluster)
  hpc tunnel                   (re)open the tunnel to the running job
  hpc status                   your jobs and the end of the Jupyter log
  hpc log                      the last 30 lines of the Jupyter log
  hpc top                      live top inside the job (q to quit)
  hpc stop                     cancel the job and close local tunnels
#>

# This machine's settings: the environment variable, else .env in the repository root
# (see .env.example), else the default. The same rule as core/settings.py.
function Get-Setting([string]$Key, [string]$Default = "") {
    $value = [Environment]::GetEnvironmentVariable($Key)
    if ($value) { return $value }
    $file = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
    if (Test-Path $file) {
        foreach ($line in Get-Content $file) {
            $line = $line.Trim()
            if ($line -and -not $line.StartsWith("#") -and $line -match "^([^=]+)=(.*)$") {
                if ($Matches[1].Trim() -eq $Key) {
                    $found = $Matches[2].Trim().Trim('"').Trim("'")
                    if ($found) { return $found }
                }
            }
        }
    }
    return $Default
}

$HostAlias = Get-Setting "MARLEM_SSH_HOST" "taltech"
$Account = Get-Setting "MARLEM_SLURM_ACCOUNT"
$Port = [int](Get-Setting "MARLEM_JUPYTER_PORT" "9437")
$JobName = "jupyter"

function Remote([string]$Command) {
    # The cluster's login scripts print a harmless tput warning on stderr: dropped.
    ssh -o BatchMode=yes $HostAlias $Command 2>$null
}

function Get-Job {
    $line = Remote "squeue -u `$USER -n $JobName -h -o '%i %T %N %C %M %l'" | Select-Object -First 1
    if (-not $line) { return $null }
    $f = "$line".Trim() -split "\s+"
    [pscustomobject]@{ Id = $f[0]; State = $f[1]; Node = $f[2]; Cpus = $f[3]; Time = $f[4]; Limit = $f[5] }
}

function Stop-Tunnels {
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
        Where-Object { $_.CommandLine -match "-L $Port`:" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Open-Tunnel {
    $job = Get-Job
    if (-not $job -or $job.State -ne "RUNNING") {
        Write-Host "No running '$JobName' job. Start one with: hpc start"
        return
    }
    Stop-Tunnels
    Write-Host ""
    Write-Host "Job $($job.Id) on $($job.Node): $($job.Cpus) CPUs, running $($job.Time) of $($job.Limit)"
    Write-Host "Tunnel localhost:$Port -> $($job.Node):$Port open. In VS Code: kernel 'TalTech', restart it."
    Write-Host "Ctrl+C closes the tunnel (the job keeps running; 'hpc stop' ends it)."
    ssh -N -L "${Port}:$($job.Node):${Port}" $HostAlias 2>$null
}

function Start-Jupyter([string[]]$SbatchArgs) {
    $job = Get-Job
    if ($job) {
        Write-Host "A '$JobName' job already exists: $($job.Id) $($job.State) on $($job.Node)."
        Write-Host "Use 'hpc tunnel' to connect or 'hpc stop' to end it."
        return
    }
    # The cluster folder of the code is named after the branch checked out here
    # (marlem-v2 -> ~/marlem-v2); the job script starts Jupyter in $REPO.
    $branch = (git rev-parse --abbrev-ref HEAD 2>$null)
    if (-not $branch) { $branch = "marlem-v2" }
    $clusterHome = "$(Remote 'echo $HOME' | Select-Object -Last 1)".Trim()
    if (-not $clusterHome) {
        Write-Host "No answer from '$HostAlias' (VPN? ssh $HostAlias)."
        return
    }
    $repo = "$clusterHome/$branch"
    $script = "$repo/hpc/jupyter.slurm"
    if (-not (Remote "test -f $script && echo yes")) {
        Write-Host "No $script on the cluster. Push and pull the code there (git pushc), or clone it (docs/hpc/setup.md)."
        return
    }
    $options = @("--parsable", "--export=ALL,REPO=$repo,PORT=$Port")
    if ($Account) { $options += "--account=$Account" }
    $options += $SbatchArgs
    $id = Remote "sbatch $($options -join ' ') $script" | Select-Object -Last 1
    if (-not ("$id" -match "^\d+")) {
        Write-Host "sbatch failed: $id"
        return
    }
    $id = "$id".Split(";")[0].Trim()
    Write-Host "Submitted job $id ($($SbatchArgs -join ' ')), code in $repo. Waiting for Jupyter..."
    $last = ""
    while ($true) {
        $job = Get-Job
        if (-not $job) {
            Write-Host "Job $id is gone. Its log:"
            Remote "tail -20 ~/$JobName-$id.out"
            return
        }
        if ($job.State -ne $last) {
            Write-Host "  $($job.State) $($job.Node)"
            $last = $job.State
        }
        if ($job.State -eq "RUNNING") {
            $ready = Remote "grep -c 'is running at' ~/$JobName-$id.out 2>/dev/null"
            if ([int]("0$ready".Trim()) -gt 0) { break }
        }
        Start-Sleep -Seconds 3
    }
    Open-Tunnel
}

$command = if ($args.Count -gt 0) { $args[0] } else { "help" }
$rest = if ($args.Count -gt 1) { [string[]]$args[1..($args.Count - 1)] } else { @() }

switch ($command) {
    "start" { Start-Jupyter $rest }
    "tunnel" { Open-Tunnel }
    "status" {
        Remote "squeue -u `$USER -o '%.10i %.9P %.10j %.8T %.10M %.9l %.5C %.6m %R'"
        $job = Get-Job
        if ($job) { Remote "tail -3 ~/$JobName-$($job.Id).out" }
    }
    "log" {
        $job = Get-Job
        if ($job) { Remote "tail -30 ~/$JobName-$($job.Id).out" } else { Remote "tail -30 `$(ls -t ~/$JobName-*.out | head -1)" }
    }
    "top" {
        $job = Get-Job
        if ($job) { ssh -t $HostAlias "srun --jobid=$($job.Id) --overlap --pty top -u `$USER" } else { Write-Host "No '$JobName' job." }
    }
    "stop" {
        Remote "scancel -u `$USER -n $JobName"
        Stop-Tunnels
        Write-Host "Cancelled '$JobName' jobs and closed local tunnels."
        Remote "squeue -u `$USER"
    }
    default {
        Get-Content $PSCommandPath | Select-Object -Skip 1 -First 11
    }
}
