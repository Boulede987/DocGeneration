# Export all .puml files under Modelisation/ to SVG and PNG, mirroring folder structure.

$root      = $PSScriptRoot
$sourceDir = Join-Path $root "Modelisation"
$jarPath   = Join-Path $root "plantuml.jar"
$logPath   = Join-Path $root "export-svg.log"

$startTime = Get-Date
[System.IO.File]::WriteAllText($logPath, "[$startTime] export-svg.ps1 started`r`n", [System.Text.UTF8Encoding]::new($false))

function Log($msg) {
    Write-Host $msg
    Add-Content -Path $logPath -Value $msg -Encoding utf8
}

if (-not (Test-Path $jarPath)) {
    Log "plantuml.jar not found - downloading..."
    Invoke-WebRequest -Uri "https://github.com/plantuml/plantuml/releases/latest/download/plantuml.jar" -OutFile $jarPath
    Log "Downloaded plantuml.jar"
}

$pumls = Get-ChildItem -Path $sourceDir -Filter "*.puml" -Recurse |
         Where-Object { $_.FullName -notlike "*\Fragments\*" -and $_.FullName -notlike "*\Fragments-Full\*" }
if ($pumls.Count -eq 0) {
    Log "No .puml files found under $sourceDir"
    exit 0
}
Log "Found $($pumls.Count) .puml files. Exporting SVG + PNG..."

$pumlPaths = $pumls | Select-Object -ExpandProperty FullName
$batchSize = 100

foreach ($format in @('svg', 'png')) {
    $outDir = Join-Path $root "Modelisation\$format"
    Log ""
    Log "=== $($format.ToUpper()) ==="

    # Clean up stale files left beside .puml sources from a previous run
    Get-ChildItem -Path $sourceDir -Filter "*.$format" -Recurse | Remove-Item -Force

    # Batch into chunks of 100 to stay under the Windows 32K command-line limit
    for ($i = 0; $i -lt $pumlPaths.Count; $i += $batchSize) {
        $batch    = $pumlPaths[$i..([Math]::Min($i + $batchSize - 1, $pumlPaths.Count - 1))]
        $javaArgs = @('-Xmx2g', '-DPLANTUML_LIMIT_SIZE=65536', '-jar', $jarPath, "-t$format", '-nbthread', 'auto') + $batch
        $javaOut  = & java @javaArgs 2>&1
        $javaOut | ForEach-Object { Log "  [plantuml] $_" }
    }

    # Move each generated file to outDir, preserving folder structure
    $ok = 0; $fail = 0
    foreach ($puml in $pumls) {
        $rel      = $puml.FullName.Substring($sourceDir.Length).TrimStart('\')
        $fileRel  = $rel -replace '\.puml$', ".$format"
        $fileSrc  = Join-Path $puml.DirectoryName ($puml.BaseName + ".$format")
        $fileDest = Join-Path $outDir $fileRel
        $destDir  = Split-Path $fileDest -Parent

        if (Test-Path $fileSrc) {
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Force -Path $destDir | Out-Null
            }
            Move-Item -Force $fileSrc $fileDest
            Log "  OK   $rel"
            $ok++
        } else {
            Log "  FAIL $rel"
            $fail++
        }
    }
    Log "$($format.ToUpper()) done | OK: $ok  FAIL: $fail  ->  $outDir"
}

$elapsed = (Get-Date) - $startTime
Log ""
Log "Done in $([math]::Round($elapsed.TotalSeconds, 1))s"
Log "Log: $logPath"
