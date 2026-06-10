<#
  Resize all images in assets\images to max width 1000px (web size), ASCII-only.
  Run:
    powershell -ExecutionPolicy Bypass -File "<full path to this .ps1>"
#>
Add-Type -AssemblyName System.Drawing
$root = $PSScriptRoot
$dir  = Join-Path $root 'assets\images'
$jpg  = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
$ep   = New-Object System.Drawing.Imaging.EncoderParameters(1)
$ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, [long]80)

$files = Get-ChildItem -Path $dir -File
$done = 0; $skip = 0
foreach ($f in $files) {
  try {
    if ($f.Length -lt 260000) { $skip++; continue }   # already small enough
    $bytes = [IO.File]::ReadAllBytes($f.FullName)
    $ms = New-Object IO.MemoryStream(,$bytes)
    $img = [System.Drawing.Image]::FromStream($ms)
    $w = $img.Width; $h = $img.Height
    $nw = [Math]::Min(1000, $w); $nh = [int]([math]::Round($h * $nw / $w))
    $bmp = New-Object System.Drawing.Bitmap($nw, $nh)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.DrawImage($img, 0, 0, $nw, $nh)
    $g.Dispose(); $img.Dispose(); $ms.Dispose()
    if ($f.Extension -ieq '.png') { $bmp.Save($f.FullName, [System.Drawing.Imaging.ImageFormat]::Png) }
    else { $bmp.Save($f.FullName, $jpg, $ep) }
    $bmp.Dispose()
    $done++
  } catch { Write-Host ("skip " + $f.Name + " : " + $_.Exception.Message) -ForegroundColor DarkYellow }
}
Write-Host ""
Write-Host ("Resize done: processed {0}, skipped {1}. Folder is now much smaller." -f $done, $skip)
Write-Host "You can now zip the folder (right-click > Send to > Compressed folder) and send it."
