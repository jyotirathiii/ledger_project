import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

class KeyConflict(Exception):
    pass
class RiskBLocked(Exception):  
    pass

LARGE_AMOUNT= 500
VELOCITY_LIMIT= 3
VELOCITY_MINUTES= 5
NEW_RECIEVER_AMOUNT = 200      

def get_connection():
    return mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)

ALLOWED = {
    "created":["pending"],
    "pending":["processing","failed"],
    "processing":["completed","failed"],
    "completed":["partially_refunded", "refunded"],
    "partially_refunded": ["partially_refunded", "refunded"],
    "failed":[],
    "refunded":[]

}

def change_status(cur,transfer_id,new_status):
    cur.execute("SELECT status FROM transfers WHERE id = %s FOR UPDATE",(transfer_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError("Transfer Not Found")
    old_status = row[0]

    if new_status not in ALLOWED.get(old_status,[]):
        raise ValueError(f"Invalid status change:{old_status}-> {new_status}")
    cur.execute("UPDATE transfers SET status = %s WHERE id = %s",(new_status,transfer_id)) 
    cur.execute("INSERT INTO transfer_status_history(transfer_id,old_status,new_status) VALUES(%s,%s,%s)",(transfer_id,old_status,new_status))  

def evaluate_risk(cur,from_id,to_id,amount):
    score=0
    reasons=[]
    if amount > LARGE_AMOUNT:
        score+=40
        reasons.append("Large Amount")

    cur.execute("SElECT COUNT(*) FROM transfers WHERE from_account_id = %s " 
    "AND created_at >= NOW() - INTERVAL %s MINUTE",(from_id,VELOCITY_MINUTES))
    if cur.fetchone()[0] > VELOCITY_LIMIT:
        score+=50
        reasons.append("TOO many transfers in short time")

    cur.execute("SELECT AVG(amount),COUNT(*) FROM transfers "
    "WHERE from_account_id = %s AND status IN ('completed','partially_refunded','refunded') ",
        (from_id,))         

    avg_amount,past_amounts=cur.fetchone()
    if past_amounts >=3 and amount > avg_amount *5: 
       score+=30
       reasons.append("Amount is much higher than usual")      

    cur.execute("SELECT COUNT(*) FROM transfers WHERE from_account_id = %s AND to_account_id = %s",(from_id,to_id)) 

    if cur.fetchone()[0] == 0 and amount > NEW_RECIEVER_AMOUNT:
        score+=20
        reasons.append("New Reciever ")

    if score >=80:
        decisions = "BLOCK"
    elif score >=40:
        decisions = "REVIEW"
    else:
        decisions = "ALLOW"        
    return score,reasons,decisions

def log_risk(from_id,to_id,amount,score,decision,reasons):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO risk_checks (from_account_id,to_account_id,amount,score,decision,reasons) VALUES (%s,%s,%s,%s,%s,%s)",(from_id,to_id,amount,score,decision,",".join(reasons)))
        conn.commit()
  
    finally:
        cur.close()
        conn.close()






def transfer(from_id, to_id,amount,idem_key):
    if from_id == to_id:
        raise ValueError('Sender and reciever cannot be same')

    conn = get_connection()
    cur = conn.cursor()
    try:
        fingerprint=f"{from_id}:{to_id}:{amount:.2f}"

        try:
            cur.execute(
                "INSERT INTO idempotency_keys(idem_key,request_hash) VALUES (%s, %s) ",(idem_key,fingerprint)
            )

        except mysql.connector.IntegrityError as e:
            if e.errno != 1062:
                raise
            conn.rollback()

            cur.execute("SELECT request_hash, transfer_id FROM idempotency_keys WHERE idem_key = %s",(idem_key,)
            )
            old=cur.fetchone()
            if old[0] != fingerprint:
                raise KeyConflict("Key already used with different details")
            return old[1],True    


  
        cur.execute("SELECT id FROM accounts where id = %s ",(to_id,))
        if cur.fetchone() is None:

            raise ValueError("Reciever account are not found")
    

        cur.execute("SELECT balance FROM accounts where id = %s FOR UPDATE",(from_id,))
        row=cur.fetchone()

        if row is None:
            raise ValueError("Sender account are not found")
        if row[0]<amount:
            raise ValueError("Balance is Low")

        score,reasons,decision=evaluate_risk(cur,from_id,to_id,amount)
        log_risk(from_id,to_id,amount,score,decision,reasons)
        if decision == "BLOCK":
            raise RiskBLocked("Transfer Blocked due to risk")    


        cur.execute("INSERT INTO transfers (from_account_id,to_account_id,amount,status) VALUES (%s, %s ,%s,'created')",(from_id,to_id,amount))
        transfer_id= cur.lastrowid
        
        cur.execute("INSERT INTO transfer_status_history(transfer_id,old_status,new_status) VALUES(%s,NULL,'created')",(transfer_id,))

        change_status(cur,transfer_id,"pending")
        change_status(cur,transfer_id,"processing")
        cur.execute("INSERT INTO ledger_entries(transfer_id,account_id,type,amount) VALUES(%s ,%s,'debit', %s) ",(transfer_id,from_id,amount))
        cur.execute("INSERT INTO ledger_entries(transfer_id,account_id,type,amount) VALUES(%s ,%s,'credit',  %s) ",(transfer_id,to_id,amount))

        cur.execute("UPDATE accounts set balance = balance - %s WHERE id = %s", (amount,from_id))
        cur.execute("UPDATE accounts set balance = balance + %s WHERE id = %s", (amount,to_id))

        change_status(cur,transfer_id,"completed")

        cur.execute(
            "UPDATE idempotency_keys SET transfer_id = %s WHERE idem_key = %s",(transfer_id,idem_key)
        )

        conn.commit()
        return transfer_id,False

  

    except Exception:
        conn.rollback()

        raise

    finally:
            cur.close()
            conn.close()



def get_balance(account_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM accounts where id = %s",(account_id,))
    row=cur.fetchone()
    cur.close()
    conn.close()

    return row[0] if row else None


def get_history(account_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""SELECT t.id,a1.name,a2.name,t.amount,t.status,t.created_at, COALESCE((SELECT SUM(r.amount) FROM refunds r WHERE r.transfer_id = t.id), 0)

    FROM transfers t 
    JOIN accounts a1 on t.from_account_id = a1.id
    JOIN accounts a2 on t.to_account_id= a2.id
    where t.from_account_id = %s OR t.to_account_id = %s
    ORDER BY t.created_at DESC
    """,(account_id,account_id)
    )
    rows=cur.fetchall()
    cur.close()
    conn.close()
    return rows    


def create_user(email,password_hash):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (email,password_hash) VALUES ( %s, %s)",
        (email, password_hash))    
        user_id = cur.lastrowid
        cur.execute("INSERT INTO accounts (name,balance,user_id) VALUES (%s,1000,%s)",(email,user_id))
        conn.commit()
        return user_id
    except mysql.connector.Error as e:
        conn.rollback()
        if(e.errno==1062):
            raise ValueError("Email already registered")
        raise
    finally:
        cur.close()
        conn.close()

def get_user(email):
    conn= get_connection()
    cur= conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE email = %s",(email,))
    row= cur.fetchone()
    cur.close()
    conn.close()
    return row

def get_account_id(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM accounts WHERE user_id = %s",(user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def refund(receiver_account_id ,transfer_id,amount,idem_key):
    conn = get_connection()
    cur=conn.cursor()

    try:
        cur.execute("""SELECT from_account_id,to_account_id,amount,status FROM transfers where id = %s FOR UPDATE """,(transfer_id,))    
        t = cur.fetchone()

        if t is None:
            raise ValueError("Transfer Not Found")
        from_acc,to_acc,t_amount,t_status=t

        if to_acc != receiver_account_id:
            raise ValueError("Only the reciever can refund the transfer") 

        cur.execute(
            "SELECT id,transfer_id,amount FROM refunds WHERE idem_key=%s",(idem_key,)

        )    
        old = cur.fetchone()
        if old:
            if old[1] != transfer_id or old[2] != amount:
                raise KeyConflict("Key already used with differen details")
            return  old[0], True

        if t_status not in ("completed","partially_refunded"):
            raise ValueError("Transfer is not refundable")     

        cur.execute(
            "SELECT COALESCE(SUM(amount),0) FROM refunds WHERE transfer_id = %s",(transfer_id,))
            
        already_refunded = cur.fetchone()[0]
        if already_refunded + amount > t_amount:
            raise ValueError("Refunds exceeds orginial amount ")

        cur.execute("SElECT balance FROM accounts WHERE id = %s FOR UPDATE",(to_acc,))
        if cur.fetchone()[0]<amount:
            raise ValueError("Balance is Low")

        cur.execute("INSERT INTO refunds (transfer_id,amount,idem_key) VALUES(%s, %s, %s )",(transfer_id,amount,idem_key))    

        refund_id = cur.lastrowid

        cur.execute("INSERT INTO ledger_entries(transfer_id,refund_id,account_id,type,amount) VALUES (%s, %s,%s,'debit',%s )",(transfer_id,refund_id,to_acc,amount))

        cur.execute("INSERT INTO ledger_entries(transfer_id,refund_id,account_id,type,amount) VALUES (%s,%s,%s,'credit',%s) ",(transfer_id,refund_id,from_acc,amount))

        cur.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, to_acc))
        cur.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, from_acc))
        new_total= already_refunded+amount
        change_status(cur,transfer_id,"refunded" if new_total == t_amount else "partially_refunded")

        conn.commit()
        return refund_id,False

    except mysql.connector.IntegrityError as e:
        conn.rollback()

        if e.errno == 1062:
            raise KeyConflict("Key already used")
        raise

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()              







