@echo off
cd /d "%~dp0"
python -m pip install --upgrade pillow pyinstaller
python -m PyInstaller --noconfirm --onefile --noconsole --name "HungPet" --add-data "assets;assets" kai_pet.py
echo.
echo Hoan tat! File exe da duoc tao tai: %~dp0dist\HungPet.exe
pause
