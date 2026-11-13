import os
import datetime
import bcrypt
import jwt
from fastapi import Depends,HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from dotenv import load_dotenv
 
load_dotenv()

SECRET = os.environ["JWT_SECRET"]
ALGO = "HS256"
bearer = HTTPBearer()

def hash_password(password):
    return bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()

def verify_password(password,password_hash):
    return bcrypt.checkpw(password.encode(),password_hash.encode())

def create_token(user_id):
    payload={
        "sub":str(user_id),
        "exp":datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=7)
    }        
    return jwt.encode(payload,SECRET,algorithm=ALGO)

def current_user_id(cred:HTTPAuthorizationCredentials=Depends(bearer)):
    try:
        data=jwt.decode(cred.credentials,SECRET,algorithms=[ALGO])
        return int (data["sub"])
    except Exception:
        raise HTTPException(status_code=401,detail='Invalid or expired token')    