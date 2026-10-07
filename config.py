import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST      = os.getenv("DB_HOST",      "localhost")
DB_USER      = os.getenv("DB_USER",      "root")
DB_PASS      = os.getenv("DB_PASS",      "")
DB_NAME      = os.getenv("DB_NAME",      "coindrop")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))

EXPLORER_SIGNING_SECRET = os.getenv("EXPLORER_SIGNING_SECRET", "change_me")
EXPLORER_BASE_URL       = os.getenv("EXPLORER_BASE_URL", "https://explorer.coindrop.cc")

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "change_me")
