"""
Lambda handler for YouTutor backend.
Adapts the FastAPI app for AWS Lambda + API Gateway via Mangum.
"""
import sys
import os

# Ensure the parent directory is on the path so we can import backend
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# IMPORTANT: Set env vars BEFORE importing backend so certifi is configured
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

from mangum import Mangum
from backend import app

# Create the Lambda handler
handler = Mangum(app, lifespan="off")
