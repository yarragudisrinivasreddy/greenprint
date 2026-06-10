"""GreenPrint application entry point.

Boots the Flask application via the app factory so that Cloud Run's
gunicorn worker (`gunicorn main:app`) and local development
(`python main.py`) share one identical construction path.

Author: Srinivas Reddy Yarragudi
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Local development only — Cloud Run uses gunicorn (see Dockerfile).
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
