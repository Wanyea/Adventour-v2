@echo off
SET ENV_NAME=adventour-server-venv

echo Checking for virtual environment: %ENV_NAME%

IF NOT EXIST "%ENV_NAME%\Scripts\activate.bat" (
    echo Virtual environment not found. Creating one named %ENV_NAME%...
    python -m venv %ENV_NAME%
    IF %ERRORLEVEL% NEQ 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call %ENV_NAME%\Scripts\activate.bat

IF %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

echo Installing dependencies...
pip install -r requirements.txt

echo Starting Flask backend...
python app.py

pause
