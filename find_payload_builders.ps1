$patterns = @(
    'payload\s*=\s*\{',
    'return\s+\{',
    '"analysis"\s*:',
    '"fixture"\s*:',
    '"league"\s*:',
    "'analysis'\s*:",
    "'fixture'\s*:",
    "'league'\s*:",
    'home_team',
    'away_team',
    'idEvent',
    'save_prediction_db\('
)

$files = Get-ChildItem -Path . -Recurse -Include *.py | Where-Object {
    $_.FullName -notmatch '\\.venv\\|\\__pycache__\\|\\migrations\\|\\site-packages\\'
}

foreach ($pattern in $patterns) {
    Write-Host ""
    Write-Host "=============================="
    Write-Host "BUSCANDO: $pattern"
    Write-Host "=============================="

    $files | Select-String -Pattern $pattern | ForEach-Object {
        Write-Host "$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
    }
}