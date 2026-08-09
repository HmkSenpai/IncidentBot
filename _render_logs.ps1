param(
  [string]$Key = "rnd_a46nvawR77sarbS0pRiLci4d4BP2",
  [string]$ServiceId = "srv-d9qtfvlbedkc73fnsccg",
  [string]$OwnerId = "tea-d2mf4j15pdvs738p98hg",
  [int]$Limit = 400,
  [string]$Level = "info"
)
# direction backward = plus récents d'abord
$uri = "https://api.render.com/v1/logs?ownerId=$OwnerId&resource=$ServiceId&limit=$Limit&direction=backward&level=$Level"
$resp = Invoke-WebRequest -Uri $uri -Headers @{ Authorization = "Bearer $Key" } -Method Get -TimeoutSec 30 -UseBasicParsing
$json = $resp.Content | ConvertFrom-Json
$x = 0
foreach ($l in $json.logs) {
  $type = ($l.labels | Where-Object { $_.name -eq "type" }).value
  $inst = ($l.labels | Where-Object { $_.name -eq "instance" }).value
  $msg = ($l.message -replace "`r", " " -replace "`n", " ").Trim()
  if ($type -eq "app" -and $msg) {
    $x++
    Write-Output ("[{0}] {1} | {2}" -f $l.timestamp, $inst, $msg)
  }
}
Write-Output "=== ($x logs app) ==="
