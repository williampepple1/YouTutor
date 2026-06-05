import subprocess, sys

# Use uv to install into the venv
cmd = ["uv", "pip", "install", "fastapi", "uvicorn", "--python", r"C:\Users\PC\.venv\Scripts\python.exe"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print(result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout)
print(result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)
print("exit:", result.returncode)
