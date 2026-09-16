$ErrorActionPreference = "Stop"

$nodes = @(
    @{ Url="http://127.0.0.1:8101"; Key="manufacturer-key" },
    @{ Url="http://127.0.0.1:8102"; Key="supplier-key" },
    @{ Url="http://127.0.0.1:8103"; Key="contractor-key" },
    @{ Url="http://127.0.0.1:8104"; Key="owner-key" },
    @{ Url="http://127.0.0.1:8105"; Key="inspector-key" },
    @{ Url="http://127.0.0.1:8106"; Key="relay-key" }
)

foreach ($node in $nodes) {
    $deadline = (Get-Date).AddSeconds(45)
    while ($true) {
        try {
            $node.Info = Invoke-RestMethod -Uri "$($node.Url)/v3/node/info" -TimeoutSec 2
            break
        } catch {
            if ((Get-Date) -gt $deadline) { throw "Node $($node.Url) did not become ready" }
            Start-Sleep -Milliseconds 500
        }
    }
}

function New-Record($Url, $Key, $Kind, $Subject, $Availability = $null) {
    $payload = @{ record_kind=$Kind; subject=$Subject }
    if ($Availability) { $payload.availability = $Availability }
    $body = $payload | ConvertTo-Json -Depth 12
    Invoke-RestMethod -Method Post -Uri "$Url/v3/records" `
        -Headers @{ "x-api-key"=$Key } -ContentType "application/json" -Body $body
}

function Add-Relationship($StakeholderUrl, $StakeholderKey, $OwnerUrl, $OwnerKey, $Root, $Target, $Role, $Type, $Claims) {
    $proposalBody = @{
        source=$Root.id
        target=$Target.id
        role=$Role
        relation_type=$Type
        claims=$Claims
    } | ConvertTo-Json -Depth 12
    $proposal = Invoke-RestMethod -Method Post -Uri "$StakeholderUrl/v3/relationships/proposals" `
        -Headers @{ "x-api-key"=$StakeholderKey } -ContentType "application/json" -Body $proposalBody
    Invoke-RestMethod -Method Post -Uri "$OwnerUrl/v3/relationships/accept" `
        -Headers @{ "x-api-key"=$OwnerKey } -ContentType "application/json" `
        -Body ($proposal | ConvertTo-Json -Depth 20) | Out-Null
}

Write-Host "Publishing independently governed lifecycle records..." -ForegroundColor Cyan
$public = @{ visibility="public"; allowed_nodes=@() }
$ownerAndClient = @{
    visibility="restricted"
    allowed_nodes=@($nodes[3].Info.routing_host, $nodes[5].Info.routing_host)
}

$type = New-Record "http://127.0.0.1:8101" "manufacturer-key" "type" @{
    name="Air Handling Unit AHU-100"
    manufacturer="Global HVAC Co"
    model_number="AHU-100"
    attributes=@{ airflow_m3h=10000; service_life="P20Y"; declaration="UKCA" }
} $public
$custody = New-Record "http://127.0.0.1:8102" "supplier-key" "assertion" @{
    name="AHU-100 delivery"
    event_type="delivered"
    asset="pending-owner-instance"
    issuer_sequence=1
    batch="B-20418"
    conformance="accepted"
    effective_at=(Get-Date).ToUniversalTime().ToString("o")
} $ownerAndClient
$procurement = New-Record "http://127.0.0.1:8103" "contractor-key" "assertion" @{
    name="AHU-100 procurement approval"
    event_type="procured"
    project="North Wing Refurbishment"
    approved_substitution=$false
} $ownerAndClient
$inspection = New-Record "http://127.0.0.1:8105" "inspector-key" "assertion" @{
    name="AHU-100 commissioning inspection"
    event_type="inspected"
    result="pass"
    standard="CIBSE Commissioning Code A"
} $ownerAndClient
$instance = New-Record "http://127.0.0.1:8104" "owner-key" "instance" @{
    name="North Wing AHU-03"
    serial_number="AHU-2026-009184"
    asset_owner="North Wing Hospital Trust"
    site=@{ building="North Wing"; storey="03"; space="Plant Room 03"; ifc_guid="2XQ-n5SLP5VgceJx2B9mA1" }
} $ownerAndClient

Write-Host "Exchanging stakeholder and owner relationship proofs..." -ForegroundColor Cyan
Add-Relationship "http://127.0.0.1:8101" "manufacturer-key" "http://127.0.0.1:8104" "owner-key" $instance $type "manufacturer" "defines_type" @{ baseline="accepted at commissioning" }
Add-Relationship "http://127.0.0.1:8102" "supplier-key" "http://127.0.0.1:8104" "owner-key" $instance $custody "supplier" "custody_event" @{ delivery="verified" }
Add-Relationship "http://127.0.0.1:8103" "contractor-key" "http://127.0.0.1:8104" "owner-key" $instance $procurement "main_contractor" "procured_under" @{ package="MEP-04" }
Add-Relationship "http://127.0.0.1:8105" "inspector-key" "http://127.0.0.1:8104" "owner-key" $instance $inspection "inspector" "inspected_by" @{ result="pass" }

$state = @{
    root=$instance.id
    records=@($type.id, $custody.id, $procurement.id, $inspection.id, $instance.id)
} 
$state | ConvertTo-Json -Depth 5 | Set-Content "$PSScriptRoot/data/demo-state.json"

$deadline = (Get-Date).AddSeconds(15)
do {
    try {
        $graph = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8106/v3/resolve-graph" `
            -Headers @{ "x-api-key"="relay-key" } -ContentType "application/json" `
            -Body (@{ root=$instance.id; depth=2; max_nodes=50; view="confidential" } | ConvertTo-Json)
    } catch {
        $graph = $null
    }
} until (($graph -and @($graph.nodes.PSObject.Properties.Name).Count -eq 5 -and $graph.edges.Count -eq 4) -or (Get-Date) -gt $deadline)
if (-not $graph -or @($graph.nodes.PSObject.Properties.Name).Count -ne 5 -or $graph.edges.Count -ne 4) {
    throw "Permitted relay did not receive the complete confidential graph within 15 seconds"
}
Write-Host "Seeded root: $($instance.id)" -ForegroundColor Green
$nodeCount = @($graph.nodes.PSObject.Properties.Name).Count
Write-Host "Resolved $nodeCount nodes and $($graph.edges.Count) governed relationships through the relay." -ForegroundColor Green