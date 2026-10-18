# Windows'ta (dpkg-deb olmadan) scripts/build-deb.sh ile aynı .deb paketini üretir.
# Gereken: Windows 10/11 ile gelen tar.exe (bsdtar). Dosya izinleri ve root sahipliği mtree tanımıyla verilir.
# Kullanım: powershell -ExecutionPolicy Bypass -File scripts\build-deb.ps1
$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $PSScriptRoot
$Changelog = Get-Content -LiteralPath (Join-Path $ProjectDir 'debian\changelog') -TotalCount 1
if ($Changelog -notmatch '^[^(]*\(([^)]+)\)') { throw 'debian/changelog içinden paket sürümü okunamadı.' }
$Version = $Matches[1]

$Utf8 = New-Object System.Text.UTF8Encoding $false
$Work = Join-Path ([IO.Path]::GetTempPath()) ('tahta-kilit-package-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Work | Out-Null
$OutputDir = Join-Path $ProjectDir 'dist'
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Write-Lf([string]$Source, [string]$Name) {
    # build-deb.sh'deki sed 's/\r$//' karşılığı: satır sonlarını LF yapar.
    $text = [IO.File]::ReadAllText($Source, $Utf8).Replace("`r`n", "`n")
    $target = Join-Path $Work $Name
    [IO.File]::WriteAllText($target, $text, $Utf8)
    return $target
}

function Src([string]$Relative) { return (Join-Path $ProjectDir $Relative) }

# Paket içi yol => (kaynak dosya, izin)
$files = [ordered]@{}
$files['etc/xdg/autostart/bb-kilit-session.desktop'] = @((Src 'share\bb-kilit-session.desktop'), '0644')
Get-ChildItem -LiteralPath (Src 'src\tahta_kilit') -Filter *.py | Sort-Object Name | ForEach-Object {
    $files["usr/lib/python3/dist-packages/tahta_kilit/$($_.Name)"] = @($_.FullName, '0644')
}
$files['lib/systemd/system/tahta-kilit-master-sync.service'] = @((Src 'share\tahta-kilit-master-sync.service'), '0644')
$files['lib/systemd/system/tahta-kilit-master-sync.timer'] = @((Src 'share\tahta-kilit-master-sync.timer'), '0644')
$files['lib/systemd/system/tahta-kilit-verifier.service'] = @((Src 'share\tahta-kilit-verifier.service'), '0644')
$files['lib/systemd/user/tahta-kilit-ui.service'] = @((Src 'share\tahta-kilit-ui.service'), '0644')
$files['usr/lib/tahta-kilit/start-ui.sh'] = @((Write-Lf (Src 'share\start-ui.sh') 'start-ui.sh'), '0755')
$files['usr/lib/tahta-kilit/setup-helper'] = @((Write-Lf (Src 'share\setup-helper') 'setup-helper'), '0755')
$files['usr/share/applications/tahta-kilit-setup.desktop'] = @((Src 'share\tahta-kilit-setup.desktop'), '0644')
$files['usr/share/applications/bb-kilit.desktop'] = @((Src 'share\bb-kilit.desktop'), '0644')
if (Test-Path -LiteralPath (Src 'share\assets\borusan-mtal-logo.png')) {
    $files['usr/share/tahta-kilit/borusan-mtal-logo.png'] = @((Src 'share\assets\borusan-mtal-logo.png'), '0644')
}
$files['usr/share/polkit-1/actions/org.tahtakilit.setup.policy'] = @((Src 'share\org.tahtakilit.setup.policy'), '0644')
# build-deb.sh'de boş da olsa oluşturulan dizin.
$extraDirs = @('usr/share/tahta-kilit')

function MtreePath([string]$Path) { return ($Path -replace '\\', '/') }

function Write-Mtree([string]$Name, $Entries, $Dirs) {
    $dirSet = New-Object System.Collections.Generic.SortedSet[string]
    foreach ($d in $Dirs) { [void]$dirSet.Add($d) }
    foreach ($p in $Entries.Keys) {
        $parts = $p.Split('/')
        for ($i = 1; $i -lt $parts.Length; $i++) { [void]$dirSet.Add(($parts[0..($i - 1)] -join '/')) }
    }
    $lines = New-Object System.Collections.Generic.List[string]
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $lines.Add('#mtree')
    $lines.Add(". type=dir mode=0755 uid=0 gid=0 uname=root gname=root time=$now.0")
    foreach ($d in $dirSet) { $lines.Add("./$d type=dir mode=0755 uid=0 gid=0 uname=root gname=root time=$now.0") }
    foreach ($p in $Entries.Keys) {
        $src = MtreePath $Entries[$p][0]
        if ($src -match '\s') { throw "Kaynak yolda boşluk olmamalı: $src" }
        $lines.Add("./$p type=file mode=$($Entries[$p][1]) uid=0 gid=0 uname=root gname=root contents=$src")
    }
    $mtree = Join-Path $Work $Name
    [IO.File]::WriteAllText($mtree, (($lines -join "`n") + "`n"), $Utf8)
    return $mtree
}

# control
$control = @"
Package: tahta-kilit
Version: $Version
Section: utils
Priority: optional
Architecture: all
Depends: ca-certificates, adduser, passwd, systemd, pkexec, policykit-1-gnome | polkit-kde-agent-1, python3, python3-gi, gir1.2-gtk-3.0, python3-qrcode, python3-pil, xdg-user-dirs
Maintainer: enderkarahanli09 <301288247+enderkarahanli09@users.noreply.github.com>
Description: BB Kilit offline QR code application
  Python GTK 3 fullscreen session lock and local verifier for six-digit QR unlock codes.

"@
$controlFile = Join-Path $Work 'control'
[IO.File]::WriteAllText($controlFile, $control.Replace("`r`n", "`n").TrimEnd("`n") + "`n", $Utf8)
$controlEntries = [ordered]@{
    'control'  = @($controlFile, '0644')
    'postinst' = @((Write-Lf (Src 'debian\postinst') 'postinst'), '0755')
    'prerm'    = @((Write-Lf (Src 'debian\prerm') 'prerm'), '0755')
}

$controlTar = Join-Path $Work 'control.tar.gz'
$dataTar = Join-Path $Work 'data.tar.gz'
& tar.exe -c -z --format gnutar -f $controlTar ('@' + (Write-Mtree 'control.mtree' $controlEntries @()))
if ($LASTEXITCODE -ne 0) { throw 'control.tar.gz oluşturulamadı.' }
& tar.exe -c -z --format gnutar -f $dataTar ('@' + (Write-Mtree 'data.mtree' $files $extraDirs))
if ($LASTEXITCODE -ne 0) { throw 'data.tar.gz oluşturulamadı.' }

# ar arşivi: debian-binary, control.tar.gz, data.tar.gz (bu sırayla).
$debianBinary = Join-Path $Work 'debian-binary'
[IO.File]::WriteAllText($debianBinary, "2.0`n", (New-Object System.Text.ASCIIEncoding))
$deb = Join-Path $OutputDir "tahta-kilit_${Version}_all.deb"
$mtime = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$stream = [IO.File]::Create($deb)
try {
    $ascii = New-Object System.Text.ASCIIEncoding
    $magic = $ascii.GetBytes("!<arch>`n"); $stream.Write($magic, 0, $magic.Length)
    foreach ($member in @(@('debian-binary', $debianBinary), @('control.tar.gz', $controlTar), @('data.tar.gz', $dataTar))) {
        $bytes = [IO.File]::ReadAllBytes($member[1])
        # Başlık sonu: ters tırnak (0x60) + satır sonu (0x0A).
        $header = ('{0,-16}{1,-12}{2,-6}{3,-6}{4,-8}{5,-10}' -f $member[0], $mtime, 0, 0, 100644, $bytes.Length) + [char]0x60 + [char]0x0A
        $hb = $ascii.GetBytes($header)
        if ($hb.Length -ne 60) { throw 'ar başlığı 60 bayt olmalı.' }
        $stream.Write($hb, 0, 60)
        $stream.Write($bytes, 0, $bytes.Length)
        if ($bytes.Length % 2 -eq 1) { $stream.WriteByte(10) }
    }
} finally { $stream.Dispose() }

Remove-Item -LiteralPath $Work -Recurse -Force
Write-Output "Paket hazır: $deb"
