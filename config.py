# ===================================================================
# CONFIGURATION LOADER — MY CONTROL SAAS
# Reads settings from '.env' file or system environment variables
# ===================================================================

import os
from urllib.parse import urlparse

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

# Check DATABASE_URL or MYSQL_URL (standard for cloud hosts like Render / Railway / TiDB Cloud)
database_url = os.environ.get("DATABASE_URL") or os.environ.get("MYSQL_URL")
if database_url and (database_url.startswith("mysql://") or database_url.startswith("mysql2://")):
    url = urlparse(database_url)
    db_host = url.hostname or "localhost"
    db_port = url.port or 3306
    db_user = url.username or "root"
    db_password = url.password or "1033721412Reddy#"
    db_name = url.path.lstrip("/") if url.path else "my_control"
else:
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = int(os.environ.get("DB_PORT", 3306))
    db_user = os.environ.get("DB_USER", "root")
    db_password = os.environ.get("DB_PASSWORD", "1033721412Reddy#")
    db_name = os.environ.get("DB_NAME", "my_control")

DB_CONFIG = {
    "host": db_host,
    "port": db_port,
    "user": db_user,
    "password": db_password,
    "database": db_name,
}

# TiDB Cloud Serverless / Remote MySQL requires SSL connection
if db_host not in ("localhost", "127.0.0.1"):
    DB_CONFIG["ssl_disabled"] = False
    DB_CONFIG["ssl_verify_identity"] = False
    DB_CONFIG["ssl_verify_cert"] = False

# Flask Application Secret Key
SECRET_KEY = os.environ.get("SECRET_KEY", "mycontrol-saas-secret-key-9f8e7d6c5b4a3210-2026")

# Dedicated Customer Support Information
SUPPORT_PHONE = os.environ.get("SUPPORT_PHONE", "8019963524")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "rohithreddi2007@gmail.com")
