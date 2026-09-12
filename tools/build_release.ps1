# QC Bridge Maya-Blender - release builder
#
#     powershell -ExecutionPolicy Bypass -File tools/build_release.ps1
#
# Produces, from one build:
#
#   dist/mutaform_bridge_blender-<version>.zip   Blender extension, manifest at the root
#   dist/mutaform_bridge_maya-<version>.zip      Maya companion: unzip anywhere, drag
#                                                install/install.py into a viewport
#   pages/                                       what the workflow publishes: both
#                                                archives under permanent names, the
#                                                Maya update manifest version.json,
#                                                index.html. The workflow adds the
#                                                Blender repository index.json.
#
# The Maya manifest is generated here rather than written by hand for one
# reason: a manifest whose version disagrees with the archive beside it
# advertises an update that installs nothing and is then offered forever.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$repoRoot = Split-Path -Parent $PSScriptRoot
$addonDir = Join-Path $repoRoot "mutaform_bridge"
$manifest = Join-Path $addonDir "blender_manifest.toml"
$mayaRoot = Join-Path $repoRoot "maya"
$mayaPackage = Join-Path $mayaRoot "mutaform_bridge"
$mayaInit = Join-Path $mayaPackage "__init__.py"

# Build output. On CI it has to be the repository root, because the workflow
# publishes from the checkout. Locally it goes to the project's Dev folder
# beside the repository, so the working copy holds only the files that are
# actually in the repository.
$onCI = ($env:GITHUB_ACTIONS -eq 'true')
if ($onCI) {
    $outRoot = $repoRoot
} else {
    $outRoot = Join-Path (Split-Path -Parent $repoRoot) "Dev"
    if (-not (Test-Path -LiteralPath $outRoot)) {
        New-Item -ItemType Directory -Force -Path $outRoot | Out-Null
    }
}
$distDir = Join-Path $outRoot "dist"
$pagesDir = Join-Path $outRoot "pages"

foreach ($required in @($manifest, $mayaInit)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing $required"
    }
}

# ---------------------------------------------------------------------------
# Version. The Blender manifest is the source of truth for the extension; the
# Maya package carries its own VERSION tuple because the installer and the
# updater read it from there. The three must agree, so the archive names can
# never disagree with what either window reports.
# ---------------------------------------------------------------------------
function Get-VersionFromFile([string]$path, [string]$pattern) {
    $match = Select-String -LiteralPath $path -Pattern $pattern | Select-Object -First 1
    if (-not $match) { throw "No version found in $path" }
    return $match.Matches[0].Groups[1].Value
}

$version = Get-VersionFromFile $manifest '^\s*version\s*=\s*"([^"]+)"'
$blenderInitVersion = Get-VersionFromFile (Join-Path $addonDir "__init__.py") '^BRIDGE_VERSION\s*=\s*"([^"]+)"'
$mayaTuple = Get-VersionFromFile $mayaInit '^VERSION\s*=\s*\((.+)\)'
$mayaVersion = ($mayaTuple -replace '\s', '') -replace ',', '.'
if ($blenderInitVersion -ne $version) {
    throw "Version mismatch: blender_manifest.toml=$version, mutaform_bridge/__init__.py=$blenderInitVersion"
}
if ($mayaVersion -ne $version) {
    throw "Version mismatch: blender_manifest.toml=$version, maya/mutaform_bridge/__init__.py=$mayaVersion"
}
Write-Host "QC Bridge Maya-Blender $version"

$blenderZip = Join-Path $distDir "mutaform_bridge_blender-$version.zip"
$mayaZip = Join-Path $distDir "mutaform_bridge_maya-$version.zip"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Copy-Stage([string]$source, [string]$target) {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
    Get-ChildItem -LiteralPath $target -Directory -Recurse -Filter "__pycache__" |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $target -File -Recurse |
        Where-Object {
            $_.Extension -in @(".pyc", ".pyo") -or
            $_.Name -in @(".DS_Store", "Thumbs.db") -or
            $_.Name -match "\.blend\d+$"
        } |
        Remove-Item -Force
}

# Compress-Archive on Windows PowerShell writes backslashes into entry names,
# which Python's zipfile (used by Blender and by the Maya updater) only
# tolerates on Windows. Write the archive through .NET with forward slashes
# so it is valid everywhere.
function New-ZipArchive([string]$sourceDir, [string]$zipPath, [string]$rootPrefix) {
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    $sourceDir = (Resolve-Path -LiteralPath $sourceDir).Path.TrimEnd('\', '/')
    $archive = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        Get-ChildItem -LiteralPath $sourceDir -File -Recurse | Sort-Object FullName | ForEach-Object {
            $relative = $_.FullName.Substring($sourceDir.Length).TrimStart('\', '/') -replace '\\', '/'
            if ($rootPrefix) { $relative = "$rootPrefix/$relative" }
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive, $_.FullName, $relative, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
        }
    } finally {
        $archive.Dispose()
    }
}

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
foreach ($dir in @($distDir, $pagesDir)) {
    if (Test-Path -LiteralPath $dir) {
        Remove-Item -LiteralPath $dir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

# Blender extension: files at the archive root.
$stageBlender = Join-Path $distDir "_stage_blender"
Copy-Stage $addonDir $stageBlender
New-ZipArchive $stageBlender $blenderZip ""
Remove-Item -LiteralPath $stageBlender -Recurse -Force

# Maya companion: one top folder holding the package, the installer and the
# docs, so unzipping it anywhere and dragging install/install.py into a Maya
# viewport is the whole installation.
$stageMaya = Join-Path $distDir "_stage_maya"
Copy-Stage $mayaPackage (Join-Path $stageMaya "mutaform_bridge")
Copy-Stage (Join-Path $mayaRoot "install") (Join-Path $stageMaya "install")
foreach ($doc in @(@{ from = (Join-Path $mayaRoot "README.md"); to = "README.md" },
                   @{ from = (Join-Path $repoRoot "CHANGELOG.md"); to = "CHANGELOG.md" })) {
    if (Test-Path -LiteralPath $doc.from) {
        Copy-Item -LiteralPath $doc.from -Destination (Join-Path $stageMaya $doc.to) -Force
    }
}
New-ZipArchive $stageMaya $mayaZip "mutaform_bridge_maya"
Remove-Item -LiteralPath $stageMaya -Recurse -Force

Write-Host "Built $blenderZip"
Write-Host "Built $mayaZip"

# ---------------------------------------------------------------------------
# Publishing payload
# ---------------------------------------------------------------------------
$publishedBlender = Join-Path $pagesDir "mutaform_bridge_blender.zip"
$publishedMaya = Join-Path $pagesDir "mutaform_bridge_maya.zip"
Copy-Item -LiteralPath $blenderZip -Destination $publishedBlender -Force
Copy-Item -LiteralPath $mayaZip -Destination $publishedMaya -Force

$digest = (Get-FileHash -LiteralPath $publishedMaya -Algorithm SHA256).Hash.ToLower()

$notes = ""
$changelog = Join-Path $repoRoot "CHANGELOG.md"
if (Test-Path -LiteralPath $changelog) {
    # One sentence describing the newest release, taken from the first
    # paragraph under its heading. Markdown wraps lines, so the continuation
    # lines have to be gathered too - reading only the first physical line
    # produces a sentence that stops mid-clause, which is what the window
    # would then show the artist.
    $seenHeading = $false
    $collected = @()
    foreach ($line in Get-Content -LiteralPath $changelog) {
        if ($line -match '^##\s') {
            if ($seenHeading) { break }
            $seenHeading = $true
            continue
        }
        if (-not $seenHeading) { continue }
        $trimmed = $line.Trim()
        if ($trimmed -eq "") {
            if ($collected.Count -gt 0) { break }
            continue
        }
        $collected += ($trimmed -replace '^\s*[-*]\s+', '')
    }
    if ($collected.Count -gt 0) {
        $notes = ($collected -join ' ') -replace '\*\*', '' -replace '`', ''
        $notes = ($notes -replace '\s+', ' ').Trim()
        # Take whole sentences until there is something worth reading. A
        # single sentence is not enough on its own: an entry that opens with a
        # bold lead-in would otherwise publish one word as its release note.
        $sentences = [regex]::Matches($notes, '.+?([.!?](\s|$)|$)')
        $built = ""
        foreach ($sentence in $sentences) {
            $candidate = ($built + " " + $sentence.Value).Trim()
            if ($built.Length -ge 40 -and $candidate.Length -gt 160) { break }
            $built = $candidate
            if ($built.Length -ge 90) { break }
        }
        $notes = $built.Trim()
        if ($notes.Length -gt 160) {
            $notes = $notes.Substring(0, 157).TrimEnd() + "..."
        }
    }
}

$baseUrl = $env:QCBRIDGE_PAGES_URL
if (-not $baseUrl) { $baseUrl = "https://mutaform.github.io/qc-bridge-blender-maya" }

$updateManifest = [ordered]@{
    id       = "mutaform_bridge"
    name     = "QC Bridge Maya-Blender"
    version  = $version
    download = "$baseUrl/mutaform_bridge_maya.zip"
    sha256   = $digest
    notes    = $notes
    maya     = @("2025")
}
$manifestPath = Join-Path $pagesDir "version.json"
# Written without a byte-order mark, deliberately. PowerShell's -Encoding UTF8
# prepends one, and Python's json.loads refuses a BOM outright - so a manifest
# written the obvious way is rejected by the very updater it is meant to feed.
$manifestJson = $updateManifest | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText(
    $manifestPath, $manifestJson, (New-Object System.Text.UTF8Encoding($false)))

$indexHtml = @"
<!doctype html>
<html>
  <head><meta charset="utf-8"><title>QC Bridge Maya-Blender</title></head>
  <body>
    <h1>QC Bridge Maya-Blender</h1>
    <p>Version $version</p>
    <h2>Blender</h2>
    <p><a href="index.json">Extension repository index</a> - add this address as a repository in Blender.</p>
    <p><a href="mutaform_bridge_blender.zip">Download Blender extension ZIP</a></p>
    <h2>Maya</h2>
    <p><a href="mutaform_bridge_maya.zip">Download Maya companion ZIP</a></p>
    <p><a href="version.json">Update manifest</a></p>
    <p>Install: unzip, then drag <code>install/install.py</code> into a Maya viewport.</p>
  </body>
</html>
"@
[System.IO.File]::WriteAllText(
    (Join-Path $pagesDir "index.html"), $indexHtml, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "Publishing payload in $pagesDir"
Write-Host "  version.json -> $version  sha256 $digest"

# ---------------------------------------------------------------------------
# Local release drop: <project>\Zip Addon\ keeps the current version by name,
# previous versions move to Zip Addon\old\. Skipped on CI, where that folder
# does not exist and there is nobody to hand anything to.
# ---------------------------------------------------------------------------
if (-not $onCI) {
    $zipAddonDir = Join-Path (Split-Path -Parent $repoRoot) "Zip Addon"
    $oldDir = Join-Path $zipAddonDir "old"
    New-Item -ItemType Directory -Force -Path $oldDir | Out-Null
    $releases = @{
        $blenderZip = "mutaform_bridge_blender_$version.zip"
        $mayaZip = "mutaform_bridge_maya_$version.zip"
    }
    Get-ChildItem -LiteralPath $zipAddonDir -File -Filter "mutaform_bridge_*.zip" | ForEach-Object {
        if ($releases.Values -notcontains $_.Name) {
            Move-Item -LiteralPath $_.FullName -Destination (Join-Path $oldDir $_.Name) -Force
            Write-Host "Moved to old: $($_.Name)"
        }
    }
    foreach ($entry in $releases.GetEnumerator()) {
        Copy-Item -LiteralPath $entry.Key -Destination (Join-Path $zipAddonDir $entry.Value) -Force
        Write-Host "Release $(Join-Path $zipAddonDir $entry.Value)"
    }
}
