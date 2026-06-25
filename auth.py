from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from database import get_db
from auth_utils import hash_password, verify_password, create_token, get_current_user

router = APIRouter()

# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class StudentRegister(BaseModel):
    name: str
    email: EmailStr
    phone: str = ""
    password: str
    level: str = "Secondary"
    state: str = "Lagos"

class TutorRegister(BaseModel):
    name: str
    email: EmailStr
    phone: str = ""
    password: str
    state: str = "Lagos"
    subject: str
    experience: int = 0
    qualification: str = "B.Sc"
    hourly_rate: int
    bio: str = ""
    availability: str = ""
    id_type: str = "National ID"
    id_number: str = ""

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.post("/register/student", status_code=201)
def register_student(body: StudentRegister):
    with get_db() as conn:
        existing = conn.run("SELECT id FROM users WHERE email = :e", e=body.email)
        if existing:
            raise HTTPException(400, "Email already registered")
        rows = conn.run(
            """INSERT INTO users (name, email, phone, password, role, level, state)
               VALUES (:name, :email, :phone, :pw, 'student', :level, :state)
               RETURNING id, name, email, role""",
            name=body.name, email=body.email, phone=body.phone,
            pw=hash_password(body.password), level=body.level, state=body.state
        )
        user = dict(zip(["id","name","email","role"], rows[0]))
        token = create_token({"sub": str(user["id"]), "email": user["email"], "role": "student", "name": user["name"]})
        return {"token": token, "user": user}


@router.post("/register/tutor", status_code=201)
def register_tutor(body: TutorRegister):
    with get_db() as conn:
        existing = conn.run("SELECT id FROM users WHERE email = :e", e=body.email)
        if existing:
            raise HTTPException(400, "Email already registered")

        user_rows = conn.run(
            """INSERT INTO users (name, email, phone, password, role, state)
               VALUES (:name, :email, :phone, :pw, 'tutor', :state)
               RETURNING id, name, email, role""",
            name=body.name, email=body.email, phone=body.phone,
            pw=hash_password(body.password), state=body.state
        )
        user = dict(zip(["id","name","email","role"], user_rows[0]))

        conn.run(
            """INSERT INTO tutors
               (user_id, subject, experience, qualification, hourly_rate, bio,
                availability, location, id_type, id_number, status)
               VALUES (:uid, :sub, :exp, :qual, :rate, :bio,
                       :avail, :loc, :idt, :idn, 'pending')""",
            uid=user["id"], sub=body.subject, exp=body.experience,
            qual=body.qualification, rate=body.hourly_rate, bio=body.bio,
            avail=body.availability, loc=body.state,
            idt=body.id_type, idn=body.id_number
        )

        token = create_token({"sub": str(user["id"]), "email": user["email"], "role": "tutor", "name": user["name"]})
        return {"token": token, "user": {**user, "verification_status": "pending"}}


@router.post("/login")
def login(body: LoginRequest):
    with get_db() as conn:
        rows = conn.run(
            "SELECT id, name, email, password, role FROM users WHERE email = :e",
            e=body.email
        )
        if not rows:
            raise HTTPException(401, "Invalid email or password")
        uid, name, email, pw_hash, role = rows[0]
        if not verify_password(body.password, pw_hash):
            raise HTTPException(401, "Invalid email or password")

        extra = {}
        if role == "tutor":
            t = conn.run("SELECT status, verified FROM tutors WHERE user_id = :uid", uid=uid)
            if t:
                extra = {"verification_status": t[0][0], "verified": t[0][1]}

        token = create_token({"sub": str(uid), "email": email, "role": role, "name": name})
        return {"token": token, "user": {"id": uid, "name": name, "email": email, "role": role, **extra}}


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])
    with get_db() as conn:
        rows = conn.run(
            "SELECT id, name, email, phone, role, level, state, created_at FROM users WHERE id = :uid",
            uid=user_id
        )
        if not rows:
            raise HTTPException(404, "User not found")
        keys = ["id","name","email","phone","role","level","state","created_at"]
        user = dict(zip(keys, rows[0]))
        user["created_at"] = str(user["created_at"])

        if user["role"] == "tutor":
            t = conn.run(
                """SELECT subject, experience, qualification, hourly_rate, bio,
                          availability, location, verified, rating, total_sessions,
                          total_students, status
                   FROM tutors WHERE user_id = :uid""", uid=user_id
            )
            if t:
                keys2 = ["subject","experience","qualification","hourly_rate","bio",
                         "availability","location","verified","rating","total_sessions","total_students","status"]
                user["tutor_profile"] = dict(zip(keys2, t[0]))
        return user
