from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth_utils import require_role

router = APIRouter()

@router.get("/stats")
def admin_stats(admin=Depends(require_role("admin"))):
    with get_db() as conn:
        users       = conn.run("SELECT COUNT(*) FROM users")[0][0]
        students    = conn.run("SELECT COUNT(*) FROM users WHERE role = 'student'")[0][0]
        tutors      = conn.run("SELECT COUNT(*) FROM tutors")[0][0]
        approved    = conn.run("SELECT COUNT(*) FROM tutors WHERE status = 'approved'")[0][0]
        pending     = conn.run("SELECT COUNT(*) FROM tutors WHERE status = 'pending'")[0][0]
        bookings    = conn.run("SELECT COUNT(*) FROM bookings")[0][0]
        confirmed   = conn.run("SELECT COUNT(*) FROM bookings WHERE status = 'confirmed'")[0][0]
        revenue_row = conn.run("SELECT COALESCE(SUM(amount),0) FROM bookings WHERE payment_status = 'paid'")
        revenue     = revenue_row[0][0]
        return {
            "total_users": users,
            "students": students,
            "total_tutors": tutors,
            "approved_tutors": approved,
            "pending_tutors": pending,
            "total_bookings": bookings,
            "confirmed_bookings": confirmed,
            "gross_revenue": int(revenue),
            "platform_profit": int(revenue * 0.05),
        }


@router.get("/tutors")
def list_all_tutors(status: str = "pending", admin=Depends(require_role("admin"))):
    with get_db() as conn:
        rows = conn.run("""
            SELECT t.id, u.name, u.email, u.phone, t.subject, t.experience,
                   t.qualification, t.hourly_rate, t.location, t.status,
                   t.verified, t.rating, t.total_reviews, t.created_at
            FROM tutors t JOIN users u ON u.id = t.user_id
            WHERE t.status = :status
            ORDER BY t.created_at DESC
        """, status=status)
        keys = ["id","name","email","phone","subject","experience","qualification",
                "hourly_rate","location","status","verified","rating","reviews","created_at"]
        return {"tutors": [dict(zip(keys, r)) for r in rows]}


@router.patch("/tutors/{tutor_id}/approve")
def approve_tutor(tutor_id: int, admin=Depends(require_role("admin"))):
    with get_db() as conn:
        conn.run(
            "UPDATE tutors SET status = 'approved', verified = TRUE WHERE id = :tid",
            tid=tutor_id
        )
    return {"message": "Tutor approved ✅"}


@router.patch("/tutors/{tutor_id}/reject")
def reject_tutor(tutor_id: int, admin=Depends(require_role("admin"))):
    with get_db() as conn:
        conn.run(
            "UPDATE tutors SET status = 'rejected' WHERE id = :tid",
            tid=tutor_id
        )
    return {"message": "Tutor rejected"}


@router.get("/users")
def list_users(role: str = "student", admin=Depends(require_role("admin"))):
    with get_db() as conn:
        rows = conn.run("""
            SELECT id, name, email, phone, role, state, created_at
            FROM users WHERE role = :role ORDER BY created_at DESC
        """, role=role)
        keys = ["id","name","email","phone","role","state","created_at"]
        return {"users": [dict(zip(keys, r)) for r in rows]}


@router.get("/bookings")
def list_bookings(admin=Depends(require_role("admin"))):
    with get_db() as conn:
        rows = conn.run("""
            SELECT b.id, s.name as student, tu.name as tutor, t.subject,
                   b.date, b.time, b.amount, b.status, b.payment_status, b.created_at
            FROM bookings b
            JOIN users s ON s.id = b.student_id
            JOIN tutors t ON t.id = b.tutor_id
            JOIN users tu ON tu.id = t.user_id
            ORDER BY b.created_at DESC LIMIT 100
        """)
        keys = ["id","student","tutor","subject","date","time","amount",
                "status","payment_status","created_at"]
        return {"bookings": [dict(zip(keys, r)) for r in rows]}


@router.post("/create-admin")
def create_admin(email: str, name: str, password: str):
    """Bootstrap first admin. Disable this endpoint after use!"""
    from auth_utils import hash_password
    with get_db() as conn:
        existing = conn.run("SELECT id FROM users WHERE email = :e", e=email)
        if existing:
            raise HTTPException(400, "Email already exists")
        conn.run(
            "INSERT INTO users (name, email, phone, password, role) VALUES (:n,:e,'',:pw,'admin')",
            n=name, e=email, pw=hash_password(password)
        )
    return {"message": f"Admin '{name}' created. Disable this endpoint now!"}
