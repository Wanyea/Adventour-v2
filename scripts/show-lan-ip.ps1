$addresses = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.PrefixOrigin -ne "WellKnown"
    } |
    Select-Object -ExpandProperty IPAddress

Write-Host "Candidate LAN IP addresses:"
$addresses | ForEach-Object { Write-Host "  $_" }
Write-Host ""
Write-Host "For a physical phone on the same Wi-Fi, set AdventourApp/.env.phone.local:"
Write-Host "BACKEND_BASE_URL=http://<one-of-these-ips>:8080"
