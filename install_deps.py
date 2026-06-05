import subprocess, sys

# Install fastapi and uvicorn in the venv
venv_pip = r"C:\Users\PC\.venv\Scripts\python.exe" 
pkg1 = "fastapi"
pkg2 = "uvicorn"

cmd = [venv_pip, "-m", "pip", "install", pkg1, pkg2]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
print("exit:", result.returncode)
