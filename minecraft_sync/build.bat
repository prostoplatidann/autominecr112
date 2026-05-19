@echo off
echo Building Minecraft World Sync...
echo.

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet

REM Build executable
echo Building executable...
pyinstaller --onefile --windowed --name "MinecraftWorldSync" --icon=NONE src/main.py

echo.
echo Build complete! Executable is in dist/ folder.
pause
