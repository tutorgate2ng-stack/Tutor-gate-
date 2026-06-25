from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_db
from auth_utils import get_current_user
import httpx
import os

router = APIRouter()

PAYSTACK_SECRET = os.environ.get("PAYSTACK_SECRET_KEY", "")

# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class BookingCreate(BaseModel):
    tutor_id: int
    date: str
    time: str
    duration: float = 1.0
    session_type: str = "Online (Video Call)"
    payment_method: str = "card"

class PaymentVerify(BaseModel):
    booking_id: int
    paystack_reference: str

class ReviewCreate(BaseModel):
    booking_id: int
    rating: int
    comment: str = ""

# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
def create_booking(body: BookingCreate, current_user: dict = Depends(get_current_user)):
    student_id = int(current_user["sub"])

    with get_db() as conn:
        # Get tutor rate
        t = conn.run("SELECT hourly_rate FROM tutors WHERE id = :tid AND status = 'approved'", tid=body.tutor_id)
        if not t:
            raise HTTPException(404, "Tutor not found or not approved")

        hourly_rate = t[0][0]
        amount      = int(hourly_rate * body.duration)
        platform_fee = round(amount * 0.05)
        tutor_earns  = amount - platform_fee

        rows = conn.run("""
            INSERT INTO bookings
              (student_id, tutor_id, date, time, duration, session_type,
               amount, platform_fee, tutor_earns, payment_method, status)
            VALUES (:sid, :tid, :date, :time, :dur, :stype,
                    :amt, :fee, :earn, :pmethod, 'pending')
            RETURNING id
        """, sid=student_id, tid=body.tutor_id, date=body.date, time=body.time,
             dur=body.duration, stype=body.session_type,
             amt=amount, fee=platform_fee, earn=tutor_earns,
             pmethod=body.payment_method)

        booking_id = rows[0][0]
        return {
            "booking_id": booking_id,
            "amount": amount,
            "platform_fee": platform_fee,
            "tutor_earns": tutor_earns,
            "amount_kobo": amount * 100,   # for Paystack
        }


@router.post("/verify-payment")
async def verify_payment(body: PaymentVerify, current_user: dict = Depends(get_current_user)):
    """Call after Paystack callback to confirm payment and activate booking."""
    if not PAYSTACK_SECRET:
        raise HTTPException(500, "Paystack secret key not configured")

    # Verify with Paystack
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.paystack.co/transaction/verify/{body.paystack_reference}",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"}
        )
    data = resp.json()

    if not data.get("status") or data["data"]["status"] != "success":
        raise HTTPException(400, "Payment not successful")

    paid_amount_kobo = data["data"]["amount"]

    with get_db() as conn:
        booking = conn.run(
            "SELECT id, amount, student_id FROM bookings WHERE id = :bid",
            bid=body.booking_id
        )
        if not booking:
            raise HTTPException(404, "Booking not found")

        bid, amount, student_id = booking[0]
        if int(current_user["sub"]) != student_id:
            raise HTTPException(403, "Not your booking")

        # Verify amount matches (within ₦1 tolerance for rounding)
        if abs(paid_amount_kobo - amount * 100) > 100:
            raise HTTPException(400, "Amount mismatch")

        conn.run("""
            UPDATE bookings
            SET payment_status = 'paid', payment_ref = :ref, status = 'confirmed'
            WHERE id = :bid
        """, ref=body.paystack_reference, bid=bid)

        # Increment tutor session count
        conn.run("""
            UPDATE tutors SET total_sessions = total_sessions + 1
            WHERE id = (SELECT tutor_id FROM bookings WHERE id = :bid)
        """, bid=bid)

    return {"message": "Payment verified. Session confirmed! 🎉"}


@router.get("/my")
def my_bookings(current_user: dict = Depends(get_current_user)):
    uid = int(current_user["sub"])
    role = current_user.get("role")

    with get_db() as conn:
        if role == "student":
            rows = conn.run("""
                SELECT b.id, u.name as tutor_name, t.subject,
                       b.date, b.time, b.duration, b.session_type,
                       b.amount, b.status, b.payment_status, b.created_at
                FROM bookings b
                JOIN tutors t ON t.id = b.tutor_id
                JOIN users u ON u.id = t.user_id
                WHERE b.student_id = :uid
                ORDER BY b.created_at DESC
            """, uid=uid)
            keys = ["id","tutor_name","subject","date","time","duration",
                    "session_type","amount","status","payment_status","created_at"]
        else:
            tutor_row = conn.run("SELECT id FROM tutors WHERE user_id = :uid", uid=uid)
            if not tutor_row:
                return {"bookings": []}
            tid = tutor_row[0][0]
            rows = conn.run("""
                SELECT b.id, u.name as student_name, t.subject,
                       b.date, b.time, b.duration, b.session_type,
                       b.amount, b.tutor_earns, b.status, b.payment_status, b.created_at
                FROM bookings b
                JOIN users u ON u.id = b.student_id
                JOIN tutors t ON t.id = b.tutor_id
                WHERE b.tutor_id = :tid
                ORDER BY b.created_at DESC
            """, tid=tid)
            keys = ["id","student_name","subject","date","time","duration",
                    "session_type","amount","tutor_earns","status","payment_status","created_at"]

        bookings = []
        for r in rows:
            d = dict(zip(keys, r))
            d["created_at"] = str(d["created_at"])
            bookings.append(d)
        return {"bookings": bookings}


@router.post("/review", status_code=201)
def leave_review(body: ReviewCreate, current_user: dict = Depends(get_current_user)):
    student_id = int(current_user["sub"])

    with get_db() as conn:
        booking = conn.run(
            "SELECT tutor_id, status FROM bookings WHERE id = :bid AND student_id = :sid",
            bid=body.booking_id, sid=student_id
        )
        if not booking:
            raise HTTPException(404, "Booking not found")
        tutor_id, bstatus = booking[0]
        if bstatus != "confirmed":
            raise HTTPException(400, "Can only review completed sessions")

        # Check not already reviewed
        existing = conn.run(
            "SELECT id FROM reviews WHERE booking_id = :bid", bid=body.booking_id
        )
        if existing:
            raise HTTPException(400, "Already reviewed this session")

        conn.run("""
            INSERT INTO reviews (booking_id, student_id, tutor_id, rating, comment)
            VALUES (:bid, :sid, :tid, :rating, :comment)
        """, bid=body.booking_id, sid=student_id, tid=tutor_id,
             rating=body.rating, comment=body.comment)

        # Recalculate tutor average rating
        conn.run("""
            UPDATE tutors SET
                rating = (SELECT ROUND(AVG(rating)::numeric, 1) FROM reviews WHERE tutor_id = :tid),
                total_reviews = (SELECT COUNT(*) FROM reviews WHERE tutor_id = :tid)
            WHERE id = :tid
        """, tid=tutor_id)

    return {"message": "Review submitted. Thank you! ⭐"}
