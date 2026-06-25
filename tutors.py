from fastapi import APIRouter, Query, Depends, HTTPException
from database import get_db
from auth_utils import get_current_user, require_role
from typing import Optional

router = APIRouter()

# ── LIST / SEARCH ─────────────────────────────────────────────────────────────

@router.get("/")
def list_tutors(
    subject: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    min_price: Optional[int] = Query(None),
    max_price: Optional[int] = Query(None),
    verified: Optional[bool] = Query(None),
    online: Optional[bool] = Query(None),
    sort: str = Query("rating"),   # rating | price_asc | price_desc | reviews
    page: int = Query(1, ge=1),
    limit: int = Query(12, le=50),
):
    filters = ["t.status = 'approved'"]
    params  = {}

    if subject and subject != "All":
        filters.append("t.subject = :subject")
        params["subject"] = subject
    if location and location not in ("All Locations", "All"):
        filters.append("t.location = :location")
        params["location"] = location
    if min_price is not None:
        filters.append("t.hourly_rate >= :min_price")
        params["min_price"] = min_price
    if max_price is not None:
        filters.append("t.hourly_rate <= :max_price")
        params["max_price"] = max_price
    if verified is not None:
        filters.append("t.verified = :verified")
        params["verified"] = verified
    if online is not None:
        filters.append("t.online = :online")
        params["online"] = online

    order = {
        "rating":     "t.rating DESC, t.total_reviews DESC",
        "price_asc":  "t.hourly_rate ASC",
        "price_desc": "t.hourly_rate DESC",
        "reviews":    "t.total_reviews DESC",
    }.get(sort, "t.rating DESC")

    where = " AND ".join(filters)
    offset = (page - 1) * limit
    params.update({"limit": limit, "offset": offset})

    with get_db() as conn:
        rows = conn.run(f"""
            SELECT t.id, u.name, t.subject, t.rating, t.total_reviews,
                   t.hourly_rate, t.location, t.verified, t.online,
                   t.experience, t.tags, t.bio, t.availability,
                   t.total_sessions, t.total_students
            FROM tutors t
            JOIN users u ON u.id = t.user_id
            WHERE {where}
            ORDER BY {order}
            LIMIT :limit OFFSET :offset
        """, **params)

        count_row = conn.run(f"""
            SELECT COUNT(*) FROM tutors t
            JOIN users u ON u.id = t.user_id
            WHERE {where}
        """, **{k: v for k, v in params.items() if k not in ("limit","offset")})

    keys = ["id","name","subject","rating","reviews","price","location","verified",
            "online","experience","tags","bio","availability","sessions","students"]
    tutors = [dict(zip(keys, r)) for r in rows]
    return {"tutors": tutors, "total": count_row[0][0], "page": page, "limit": limit}


@router.get("/{tutor_id}")
def get_tutor(tutor_id: int):
    with get_db() as conn:
        rows = conn.run("""
            SELECT t.id, u.name, u.email, t.subject, t.rating, t.total_reviews,
                   t.hourly_rate, t.location, t.verified, t.online,
                   t.experience, t.tags, t.bio, t.availability,
                   t.total_sessions, t.total_students, t.qualification
            FROM tutors t
            JOIN users u ON u.id = t.user_id
            WHERE t.id = :tid AND t.status = 'approved'
        """, tid=tutor_id)

        if not rows:
            raise HTTPException(404, "Tutor not found")

        keys = ["id","name","email","subject","rating","reviews","price","location",
                "verified","online","experience","tags","bio","availability",
                "sessions","students","qualification"]
        tutor = dict(zip(keys, rows[0]))

        # Fetch reviews
        rev_rows = conn.run("""
            SELECT u.name, r.rating, r.comment, r.created_at
            FROM reviews r JOIN users u ON u.id = r.student_id
            WHERE r.tutor_id = :tid
            ORDER BY r.created_at DESC LIMIT 10
        """, tid=tutor_id)
        tutor["recent_reviews"] = [
            {"name": r[0], "rating": r[1], "comment": r[2], "date": str(r[3])}
            for r in rev_rows
        ]
        return tutor


# ── SEED DEMO TUTORS (run once) ───────────────────────────────────────────────

@router.post("/seed", status_code=201)
def seed_tutors():
    """Populate the DB with the 8 demo tutors. Call once after deployment."""
    demo = [
        ("John Okafor",    "john@tutorgate.demo",    "Lagos",         "Mathematics",      6, "B.Sc",  5000, "6 years teaching experience. I help students understand Maths in a simple and practical way.",  "Mon–Sat 8AM–8PM",  True,  True,  4.8, 120, 340, 89,  ["WAEC","JAMB","NECO"]),
        ("Adaeze Mbah",    "adaeze@tutorgate.demo",  "Abuja",         "English Language", 8, "M.Sc",  4500, "Passionate English tutor with a flair for literature and grammar.",                              "Mon–Fri 9AM–6PM",  True,  True,  4.9, 98,  280, 72,  ["WAEC","NECO","Undergraduate"]),
        ("Emeka Nwosu",    "emeka@tutorgate.demo",   "Port Harcourt", "Physics",          5, "B.Sc",  5500, "Physics made easy! I break down complex concepts into digestible lessons.",                      "Tue–Sun 10AM–7PM", False, True,  4.7, 74,  190, 51,  ["JAMB","Undergraduate"]),
        ("Fatima Bello",   "fatima@tutorgate.demo",  "Kano",          "Chemistry",        4, "B.Sc",  4800, "Chemistry specialist covering organic, inorganic, and physical chemistry.",                      "Mon–Sat 7AM–5PM",  True,  True,  4.6, 55,  145, 40,  ["WAEC","JAMB"]),
        ("Chidi Eze",      "chidi@tutorgate.demo",   "Enugu",         "Biology",          9, "M.Sc",  5200, "Top-rated Biology tutor. I prepare students for national exams with past question drills.",       "Mon–Fri 8AM–8PM",  True,  True,  4.9, 143, 420, 112, ["WAEC","NECO","JAMB"]),
        ("Ngozi Obi",      "ngozi@tutorgate.demo",   "Lagos",         "Computer Science", 7, "B.Sc",  6000, "Software engineer turned educator. I teach Python, web dev, databases and data science.",        "Weekends & Evenings", True, False, 4.8, 87, 210, 63, ["Coding","Undergraduate"]),
        ("Suleiman Yusuf", "suleiman@tutorgate.demo","Abuja",         "Economics",        6, "B.Sc",  4200, "Economics made simple — macro, micro, and development economics.",                               "Mon–Sat 9AM–7PM",  True,  True,  4.7, 62,  160, 44,  ["WAEC","JAMB","Undergraduate"]),
        ("Ifeoma Chukwu",  "ifeoma@tutorgate.demo",  "Lagos",         "Literature",       3, "B.Sc",  3800, "Literature in English specialist. I cover drama, prose and poetry thoroughly.",                   "Mon–Thu 10AM–6PM", True,  False, 4.5, 39,  95,  28,  ["WAEC","NECO"]),
    ]
    from auth_utils import hash_password
    created = 0
    with get_db() as conn:
        for (name, email, loc, subj, exp, qual, rate, bio, avail, online, verified, rating, reviews, sessions, students, tags) in demo:
            existing = conn.run("SELECT id FROM users WHERE email = :e", e=email)
            if existing:
                continue
            user_rows = conn.run(
                "INSERT INTO users (name, email, phone, password, role, state) VALUES (:n,:e,'',:pw,'tutor',:s) RETURNING id",
                n=name, e=email, pw=hash_password("Demo@12345"), s=loc
            )
            uid = user_rows[0][0]
            conn.run("""
                INSERT INTO tutors (user_id, subject, experience, qualification, hourly_rate, bio,
                    availability, location, tags, online, verified, rating, total_reviews,
                    total_sessions, total_students, status)
                VALUES (:uid,:sub,:exp,:qual,:rate,:bio,:avail,:loc,:tags,:online,:verified,
                        :rating,:reviews,:sessions,:students,'approved')
            """, uid=uid, sub=subj, exp=exp, qual=qual, rate=rate, bio=bio,
                 avail=avail, loc=loc, tags=tags, online=online, verified=verified,
                 rating=rating, reviews=reviews, sessions=sessions, students=students)
            created += 1

    return {"message": f"Seeded {created} tutors successfully"}
