# app/security.py
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException


CLE_DEV = "azdncbszhhckfd"
SECRET_KEY = os.environ.get("SECRET_KEY", CLE_DEV)
ALGORITHM = "HS256"
TOKEN_DURATION = timedelta(hours=2)


def hash_password(password):
    password_bytes = password.encode()
    salt = bcrypt.gensalt() # graine randoù
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode()#byte vers txt
