<#
  Vicky Mommy site - downloader (RAW mode, WebClient). ASCII-only.
  Uses System.Net.WebClient.DownloadString which reads the FULL response
  (fixes the truncation/garble seen with Invoke-WebRequest on long pages).
  Saves raw <article> HTML to articles\<id>.html and images to assets\images\.
  Run (last arg -Force re-downloads all):
    powershell -ExecutionPolicy Bypass -File "<full path to this .ps1>" -Force
#>
param([switch]$Force)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$root   = $PSScriptRoot
$dataFp = Join-Path $root 'data\articles.json'
$artDir = Join-Path $root 'articles'
$imgDir = Join-Path $root 'assets\images'
New-Item -ItemType Directory -Force -Path $artDir, $imgDir | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)

function New-WC {
  $wc = New-Object System.Net.WebClient
  $wc.Encoding = [Text.Encoding]::UTF8
  $wc.Headers.Add('User-Agent','Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36')
  return $wc
}

$json = [IO.File]::ReadAllText($dataFp, [Text.Encoding]::UTF8)
$data = $json | ConvertFrom-Json

$imgDone = @{}
function Save-Image($uuid, $ext) {
  if ($imgDone.ContainsKey($uuid)) { return }
  try {
    $wc = New-WC
    $bytes = $wc.DownloadData("https://images.vocus.cc/$uuid.$ext")
    $wc.Dispose()
    if ($bytes.Length -gt 100) { [IO.File]::WriteAllBytes((Join-Path $imgDir "$uuid.$ext"), $bytes) }
    $imgDone[$uuid] = $true
  } catch { $imgDone[$uuid] = $false }
}

$done = 0; $skip = 0; $fail = 0
foreach ($a in $data.articles) {
  $outFp = Join-Path $artDir "$($a.id).html"
  if ((Test-Path $outFp) -and -not $Force) { $skip++; continue }
  Write-Host ("Downloading {0} ..." -f $a.id) -NoNewline
  try {
    $wc = New-WC
    $html = $wc.DownloadString($a.source)
    $wc.Dispose()

    $mm = [regex]::Match($html, '<article[^>]*>(.*?)</article>', [Text.RegularExpressions.RegexOptions]::Singleline)
    if (-not $mm.Success) { throw 'no article body' }
    $body = $mm.Groups[1].Value

    foreach ($im in [regex]::Matches($body, 'images\.vocus\.cc/([0-9a-fA-F-]{8,})(?:\.([a-zA-Z0-9]+))?')) {
      $uuid = $im.Groups[1].Value
      $ext  = if ($im.Groups[2].Success) { $im.Groups[2].Value } else { 'jpg' }
      Save-Image $uuid $ext
    }
    $cm = [regex]::Match("$($a.cover)", 'images\.vocus\.cc/([0-9a-fA-F-]{8,})(?:\.([a-zA-Z0-9]+))?')
    if ($cm.Success) { Save-Image $cm.Groups[1].Value ($(if($cm.Groups[2].Success){$cm.Groups[2].Value}else{'jpg'})) }

    [IO.File]::WriteAllText($outFp, $body, $utf8)
    Write-Host ("  OK ({0} chars)" -f $body.Length) -ForegroundColor Green
    $done++
  } catch {
    Write-Host ("  X {0}" -f $_.Exception.Message) -ForegroundColor Red
    $fail++
  }
  Start-Sleep -Milliseconds 400
}

Write-Host ""
Write-Host "========================================"
Write-Host ("Done: saved {0}, skipped {1}, failed {2}" -f $done, $skip, $fail)
Write-Host "Go back to chat and tell Claude 'done'."
Write-Host "========================================"
