# DAID — Start 4 nodes (Alpha/Beta/Gamma resolvers :8001-8003, Delta producer :8004)
# Each opens in its own terminal window, then seeds demo data.
# Run from anywhere: .\examples\run-nodes.ps1

# Repo root is one level up from this script's location (examples/)
$root = Split-Path $PSScriptRoot -Parent

# Resolver seeds point at the 3 resolver nodes only (producer doesn't gossip)
$resolverSeeds = "http://localhost:8001,http://localhost:8002,http://localhost:8003"

$nodes = @(
    @{ Name="Alpha";  Port=8001; Key="alpha-key";  DB="alpha.db";  Bin="alpha.bin";  Role="resolver"
       Seeds=$resolverSeeds },
    @{ Name="Beta";   Port=8002; Key="beta-key";   DB="beta.db";   Bin="beta.bin";   Role="resolver"
       Seeds=$resolverSeeds },
    @{ Name="Gamma";  Port=8003; Key="gamma-key";  DB="gamma.db";  Bin="gamma.bin";  Role="resolver"
       Seeds=$resolverSeeds },
    @{ Name="Delta";  Port=8004; Key="delta-key";  DB="delta.db";  Bin="delta.bin";  Role="producer"
       Seeds="" }
)

# ── Kill any processes already on these ports ─────────────────────────────
$ports = $nodes | ForEach-Object { $_.Port }
foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "  Cleared port $port (PID $($conn.OwningProcess))" -ForegroundColor DarkYellow
    }
}

foreach ($n in $nodes) {
    $cmd = @"
`$host.UI.RawUI.WindowTitle = 'DAID $($n.Name) :$($n.Port)'
Set-Location '$root'
`$env:NODE_DOMAIN      = 'localhost:$($n.Port)'
`$env:NODE_API_BASE    = 'http://localhost:$($n.Port)'
`$env:API_KEY          = '$($n.Key)'
`$env:DATABASE_URL     = 'sqlite+aiosqlite:///./$($n.DB)'
`$env:PRIVATE_KEY_FILE = './$($n.Bin)'
`$env:GOSSIP_SEEDS     = '$($n.Seeds)'
`$env:NODE_ROLE        = '$($n.Role)'
Write-Host "Starting DAID $($n.Name) on port $($n.Port) [$($n.Role)]..." -ForegroundColor Cyan
.venv\Scripts\uvicorn.exe node.app.main:app --port $($n.Port) --log-level warning
Read-Host 'Press Enter to close'
"@
    Start-Process pwsh -ArgumentList "-NoExit", "-Command", $cmd
}

Write-Host ""
Write-Host "4 nodes starting in separate windows:" -ForegroundColor Green
Write-Host "  Alpha  http://localhost:8001/ui/manufacturer  (resolver, api key: alpha-key)" -ForegroundColor White
Write-Host "  Beta   http://localhost:8002/ui/manufacturer  (resolver, api key: beta-key)"  -ForegroundColor White
Write-Host "  Gamma  http://localhost:8003/ui/manufacturer  (resolver, api key: gamma-key)" -ForegroundColor White
Write-Host "  Delta  http://localhost:8004/ui/manufacturer  (producer,  api key: delta-key)" -ForegroundColor White
Write-Host ""
Write-Host "Client lookup UI on any node, e.g. http://localhost:8001/ui/client" -ForegroundColor DarkCyan
Write-Host ""

# Seed demo data (waits 6 s for nodes to be ready)
& "$PSScriptRoot\seed-data.ps1" -WaitSeconds 6
