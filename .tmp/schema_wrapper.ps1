$o = (& .\scripts\validate-schema.ps1) 2>&1 | Out-String
Write-Host $o
if ($o -match 'ERROR:') { exit 1 }
