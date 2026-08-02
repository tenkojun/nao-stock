# 바탕화면에 [나오 주식] 바로가기를 만든다.
# 바로가기는 pythonw.exe 로 실행하므로 검은 명령창이 뜨지 않는다.
param([string]$Root = (Split-Path -Parent $PSScriptRoot))

$pyw = ''
try { $pyw = & python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" } catch {}
if (-not $pyw -or -not (Test-Path $pyw)) { $pyw = 'pythonw.exe' }

$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) '나오 주식.lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath       = $pyw
$s.Arguments        = '"' + (Join-Path $Root '나오주식.pyw') + '"'
$s.WorkingDirectory = $Root
$s.Description      = '나오 주식'
$ico = Join-Path $Root 'assets\nao.ico'
if (Test-Path $ico) { $s.IconLocation = $ico }
$s.Save()

Write-Output "바로가기 생성 완료: $lnk"
