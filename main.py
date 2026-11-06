from decimal import Decimal
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, Field
import ledger
import auth

app = FastAPI()


class TransferRequest(BaseModel):
    to_id: int
    amount: Decimal = Field(gt=0)


class RefundRequest(BaseModel):
    transfer_id: int
    amount: Decimal = Field(gt=0)


class AuthRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)


@app.post("/signup")
def signup(req: AuthRequest):
    try:
        user_id = ledger.create_user(req.email, auth.hash_password(req.password))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "created", "user_id": user_id}


@app.post("/login")
def login(req: AuthRequest):
    user = ledger.get_user(req.email)
    if user is None or not auth.verify_password(req.password, user[1]):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return {"token": auth.create_token(user[0])}


@app.post("/transfer")
def do_transfer(
    req: TransferRequest,
    idempotency_key: str = Header(...),
    user_id: int = Depends(auth.current_user_id),
):
    from_id = ledger.get_account_id(user_id)
    if from_id is None:
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        transfer_id, duplicate = ledger.transfer(
            from_id, req.to_id, req.amount, idempotency_key
        )
    except ledger.KeyConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ledger.RiskBLocked as e:
        raise HTTPException(status_code=403, detail=str(e))    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Transfer failed")
    return {"status": "success", "transfer_id": transfer_id, "duplicate": duplicate}


@app.post("/refund")
def do_refund(
    req: RefundRequest,
    idempotency_key: str = Header(...),
    user_id: int = Depends(auth.current_user_id),
):
    account_id = ledger.get_account_id(user_id)
    if account_id is None:
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        refund_id, duplicate = ledger.refund(
            account_id, req.transfer_id, req.amount, idempotency_key
        )
    except ledger.KeyConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Refund failed")
    return {"status": "success", "refund_id": refund_id, "duplicate": duplicate}


@app.get("/balance/me")
def my_balance(user_id: int = Depends(auth.current_user_id)):
    account_id = ledger.get_account_id(user_id)
    if account_id is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"account_id": account_id, "balance": ledger.get_balance(account_id)}


@app.get("/history/me")
def my_history(user_id: int = Depends(auth.current_user_id)):
    account_id = ledger.get_account_id(user_id)
    if account_id is None:
        raise HTTPException(status_code=404, detail="Account not found")
    rows = ledger.get_history(account_id)
    return [
        {
            "transfer_id": r[0], "from": r[1], "to": r[2],
            "amount": r[3], "status": r[4], "date": r[5]
        }
        for r in rows
    ]