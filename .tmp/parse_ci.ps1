$errs = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    'X:\devkit_projects\projects\atlas\repo\atlas\scripts\setup-ci-runner.ps1',
    [ref]$null,
    [ref]$errs
)
if ($errs.Count -eq 0) { 'parse ok' } else { $errs | ForEach-Object { $_.Message } }
