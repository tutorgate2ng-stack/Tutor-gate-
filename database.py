import pg8000.native
import os
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_conn_params():
    """Parse Supabase SESSION POOLER connection string."""
    import re
    url = DATABASE_URL
    # postgresql://user:password@host:port/dbname
    pattern = r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
    m = re.match(pattern, url)
    if not m:
        raise ValueError(f"Invalid DATABASE_URL: {url}")
    user, password, host, port, dbname = m.groups()
    # Strip query params from dbname if present
    dbname = dbname.split("?")[0]
    return dict(user=user, password=password, host=host, port=int(port), database=dbname)

@contextmanager
def get_db():
    params = get_conn_params()
    conn = pg8000.native.Connection(**params, ssl_context=True)
    try:
        yield conn
        conn.run("COMMIT")
    except Exception:
        conn.run("ROLLBACK")
        raise
    finally:
        conn.close()

def create_tables():
    with get_db() as conn:
        conn.run("""
        CREATE TABLE IF NOT EXISTS users (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            phone       TEXT,
            password    TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'student',
            state       TEXT,
            level       TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
        """)

        conn.run("""
        CREATE TABLE IF NOT EXISTS tutors (
            id              SERIAL PRIMARY KEY,
            user_id         INT REFERENCES users(id) ON DELETE CASCADE,
            subject         TEXT NOT NULL,
            experience      INT DEFAULT 0,
            qualification   TEXT,
            hourly_rate     INT NOT NULL,
            bio             TEXT,
            availability    TEXT,
            location        TEXT,
            tags            TEXT[],
            online          BOOLEAN DEFAULT TRUE,
            verified        BOOLEAN DEFAULT FALSE,
            rating          NUMERIC(3,1) DEFAULT 0,
            total_reviews   INT DEFAULT 0,
            total_sessions  INT DEFAULT 0,
            total_students  INT DEFAULT 0,
            id_type         TEXT,
            id_number       TEXT,
            status          TEXT DEFAULT 'pending',
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
        """)

        conn.run("""
        CREATE TABLE IF NOT EXISTS bookings (
            id              SERIAL PRIMARY KEY,
            student_id      INT REFERENCES users(id) ON DELETE CASCADE,
            tutor_id        INT REFERENCES tutors(id) ON DELETE CASCADE,
            date            TEXT NOT NULL,
            time            TEXT NOT NULL,
            duration        NUMERIC(3,1) NOT NULL DEFAULT 1,
            session_type    TEXT DEFAULT 'Online (Video Call)',
            amount          INT NOT NULL,
            platform_fee    INT NOT NULL,
            tutor_earns     INT NOT NULL,
            payment_method  TEXT DEFAULT 'card',
            payment_ref     TEXT,
            payment_status  TEXT DEFAULT 'pending',
            status          TEXT DEFAULT 'pending',
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
        """)

        conn.run("""
        CREATE TABLE IF NOT EXISTS reviews (
            id          SERIAL PRIMARY KEY,
            booking_id  INT REFERENCES bookings(id) ON DELETE CASCADE,
            student_id  INT REFERENCES users(id) ON DELETE CASCADE,
            tutor_id    INT REFERENCES tutors(id) ON DELETE CASCADE,
            rating      INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment     TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
        """)

    print("✅ Tables created / verified")
