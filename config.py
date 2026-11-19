# ===================================================================
# CONFIGURATION LOADER — MY CONTROL SAAS
# Reads settings from '.env' file or system environment variables
# ===================================================================

import os

# Pure-Python .env reader (zero external dependencies required)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                os.environ.setdefault(key, val)

# Database Configuration
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "1033721412"),
    "database": os.environ.get("DB_NAME", "my_control"),
}

# Flask Application Secret Key
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-to-any-long-random-text")

# Dedicated Customer Support Information
SUPPORT_PHONE = os.environ.get("SUPPORT_PHONE", "8019963524")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "rohithreddi2007@gmail.com")
