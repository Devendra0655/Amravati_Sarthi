import os
from pathlib import Path
from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)

_pool: AsyncConnectionPool | None = None


def _build_conninfo() -> str:
    """
    Supabase transaction pooler URL looks like:
    postgresql://postgres.xxxx:PASSWORD@aws-0-ap-south-1.pooler.supabase.com:6543/postgres

    We append sslmode=require and options to make it work with psycopg3 + Render.
    Also disables prepared statements — required for Supabase transaction pooler mode.
    """
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise ValueError("DATABASE_URL environment variable is not set")

    # Supabase pooler requires sslmode=require
    if "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"

    return url


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        conninfo = _build_conninfo()
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            open=False,
            min_size=1,
            max_size=5,               # Supabase free tier: max 15 connections via pooler
            max_idle=300,             # close idle connections after 5 min
            reconnect_timeout=10,
            kwargs={
                "prepare_threshold": None,  # REQUIRED for Supabase transaction pooler
                "autocommit": True,         # better for async read-heavy workloads
            },
        )
        await _pool.open(wait=True, timeout=10)   # wait=True ensures it's ready before returning
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_government_schemes(query: str) -> list[dict]:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT name, description, eligibility, documents, apply_at, timeline
                FROM schemes
                WHERE name        ILIKE %(q)s
                   OR description ILIKE %(q)s
                   OR eligibility ILIKE %(q)s
                LIMIT 5
                """,
                {"q": f"%{query}%"},
            )
            rows = await cur.fetchall()
    return [
        {
            "name":        r[0],
            "description": r[1],
            "eligibility": r[2],
            "documents":   r[3],
            "apply_at":    r[4],
            "timeline":    r[5],
        }
        for r in rows
    ]


async def get_nearby_businesses(
    query: str,
    user_lat: float,
    user_lng: float,
    radius_km: float = 3.0,
) -> list[dict]:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    name, category, address, lat, lng, phone, opening_hours,
                    ROUND(CAST(
                        6371 * 2 * ASIN(SQRT(
                            POWER(SIN(RADIANS(lat - %(ulat)s) / 2), 2) +
                            COS(RADIANS(%(ulat)s)) * COS(RADIANS(lat)) *
                            POWER(SIN(RADIANS(lng - %(ulng)s) / 2), 2)
                        ))
                    AS NUMERIC), 2) AS distance_km
                FROM businesses
                WHERE (
                    name     ILIKE %(q)s
                    OR category ILIKE %(q)s
                )
                AND (
                    6371 * 2 * ASIN(SQRT(
                        POWER(SIN(RADIANS(lat - %(ulat)s) / 2), 2) +
                        COS(RADIANS(%(ulat)s)) * COS(RADIANS(lat)) *
                        POWER(SIN(RADIANS(lng - %(ulng)s) / 2), 2)
                    ))
                ) <= %(radius)s
                ORDER BY distance_km ASC
                LIMIT 8
                """,
                {
                    "q":      f"%{query}%",
                    "ulat":   user_lat,
                    "ulng":   user_lng,
                    "radius": radius_km,
                },
            )
            rows = await cur.fetchall()
    return [
        {
            "name":          r[0],
            "category":      r[1],
            "address":       r[2],
            "lat":           float(r[3]),
            "lng":           float(r[4]),
            "phone":         r[5] or "",
            "opening_hours": r[6] or "",
            "distance_km":   float(r[7]),
        }
        for r in rows
    ]