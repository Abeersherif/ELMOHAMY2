# View Render audit_log + chat_sessions in DB Browser for SQLite
#
# Usage:
#   .\scripts\view-audit.ps1            # download fresh snapshot, open if DB Browser is installed
#   .\scripts\view-audit.ps1 -Cli       # skip download, run a quick inline SQL summary instead
#
# Privacy: this script only works because YOUR SSH key is added to Render.
# No one without the key can access /data — and there is no public URL.

param(
    [switch]$Cli
)

$ErrorActionPreference = "Stop"

$RenderHost = "srv-d83s0hjtqb8s73ensu20@ssh.oregon.render.com"
$RemotePath = "/data/mohamy_runtime.db"
$LocalSnapshot = Join-Path $PSScriptRoot "..\mohamy_runtime_RENDER.db"

if ($Cli) {
    Write-Host "Recent /ask activity (last 20):" -ForegroundColor Cyan
    ssh $RenderHost "sqlite3 -header -column $RemotePath 'SELECT id, substr(timestamp,1,19) ts, event_type, source, relevance_score score, latency_ms ms, substr(query,1,40) query FROM audit_log ORDER BY id DESC LIMIT 20;'"
    Write-Host "`nLow-confidence answers (score < 5):" -ForegroundColor Yellow
    ssh $RenderHost "sqlite3 -header -column $RemotePath 'SELECT id, substr(timestamp,1,19) ts, relevance_score score, substr(query,1,60) query FROM audit_log WHERE event_type=''ask'' AND relevance_score < 5 ORDER BY id DESC LIMIT 10;'"
    Write-Host "`nRecent errors:" -ForegroundColor Red
    ssh $RenderHost "sqlite3 -header -column $RemotePath 'SELECT id, substr(timestamp,1,19) ts, event_type, substr(error,1,80) error FROM audit_log WHERE source=''error'' ORDER BY id DESC LIMIT 10;'"
    return
}

Write-Host "Downloading fresh snapshot from Render..." -ForegroundColor Cyan
scp "${RenderHost}:${RemotePath}" $LocalSnapshot

if (-not (Test-Path $LocalSnapshot)) {
    Write-Host "Download failed." -ForegroundColor Red
    exit 1
}

$size = (Get-Item $LocalSnapshot).Length / 1KB
Write-Host ("Saved: {0} ({1:N0} KB)" -f $LocalSnapshot, $size) -ForegroundColor Green

# Try to open in DB Browser for SQLite if it is installed.
$dbBrowser = $null
foreach ($candidate in @(
    "C:\Program Files\DB Browser for SQLite\DB Browser for SQLite.exe",
    "C:\Program Files (x86)\DB Browser for SQLite\DB Browser for SQLite.exe"
)) {
    if (Test-Path $candidate) {
        $dbBrowser = $candidate
        break
    }
}

if ($dbBrowser) {
    Write-Host "Opening in DB Browser..." -ForegroundColor Cyan
    Start-Process $dbBrowser -ArgumentList "`"$LocalSnapshot`""
} else {
    Write-Host "DB Browser for SQLite not found. Install from https://sqlitebrowser.org/dl/" -ForegroundColor Yellow
    Write-Host "Or open the file manually: $LocalSnapshot" -ForegroundColor Yellow
}
