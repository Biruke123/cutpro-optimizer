$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "`n[1/6] Syncing files..." -ForegroundColor Cyan
Copy-Item backend.py CutPro_Package\backend.py -Force
Copy-Item frontend\index.html CutPro_Package\frontend\index.html -Force

Write-Host "[2/6] Killing running instances..." -ForegroundColor Cyan
Get-Process CutPro, python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1

Write-Host "[3/6] Rebuilding CutPro.exe..." -ForegroundColor Cyan
Push-Location CutPro_Package
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
python -m PyInstaller --name CutPro --onefile --noconsole --icon=CutPro.ico `
    --add-data "frontend;frontend" `
    --add-data "CutPro.ico;." `
    --add-data "CutPro_v3.0.zip;." `
    --hidden-import=flask --hidden-import=flask_cors --hidden-import=rectpack `
    --hidden-import=bcrypt --hidden-import=jwt --hidden-import=werkzeug `
    --hidden-import=pystray --hidden-import=PIL --hidden-import=PIL.Image `
    --hidden-import=PIL.ImageDraw launcher.py
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "PyInstaller failed" -ForegroundColor Red; exit 1 }

Write-Host "[4/6] Staging..." -ForegroundColor Cyan
Copy-Item dist\CutPro.exe ..\CutPro_Staging\CutPro.exe -Force
Pop-Location

Write-Host "[5/6] Building installer (temporarily needs Defender off if error 110)..." -ForegroundColor Cyan
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
if ($LASTEXITCODE -ne 0) { Write-Host "Inno failed — try disabling Defender real-time" -ForegroundColor Yellow; exit 1 }

Write-Host "[6/6] Done!" -ForegroundColor Green
Get-Item dist_installer\CutProSetup_v3.0.exe | Select-Object Name, Length, LastWriteTime