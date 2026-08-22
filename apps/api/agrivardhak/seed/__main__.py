"""``python -m agrivardhak.seed`` — load the synthetic Prayagraj FPO."""

from __future__ import annotations

import argparse

from sqlalchemy import text

from agrivardhak.db.session import engine, session_scope
from agrivardhak.domain.units import sqm_to_acres
from agrivardhak.seed import seed_all

#: Never truncated — Alembic's bookkeeping and PostGIS's reference table.
PRESERVE = ("alembic_version", "spatial_ref_sys")


def reset() -> None:
    """Truncate every data table, keeping the schema.

    Faster than `make db-reset`, which destroys the volume. Disables replication role for
    the duration because the append-only triggers (DR-04) would otherwise refuse the
    DELETE — which is the correct behaviour for the application and merely inconvenient
    for a developer resetting their machine.
    """
    with engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))
        tables = [
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            if row[0] not in PRESERVE
        ]
        if tables:
            conn.execute(text("TRUNCATE " + ", ".join(tables) + " CASCADE"))
        conn.execute(text("SET session_replication_role = 'origin'"))
    print(f"Truncated {len(tables)} tables.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="truncate all data before seeding")
    args = parser.parse_args()

    if args.reset:
        reset()

    with session_scope() as session:
        result = seed_all(session)

    acres = sqm_to_acres(result.total_area_sqm)
    print("Seeded Prayagraj Kisan Producer Company Limited  [SYNTHETIC — DEMO DATA]")
    print(f"  organization   {result.organization_id}")
    print(f"  farmers        {result.farmers:,}")
    print(f"  plots          {result.plots:,}")
    print(f"  crop cycles    {result.crop_cycles:,}")
    print(f"  observations   {result.observations:,}")
    print(f"  discrepancies  {result.discrepancies:,}  (deliberate — the demo needs them)")
    print(f"  total area     {acres:,.0f} acres ({result.total_area_sqm / 10_000:,.1f} ha)")
    print(f"  price records  {result.price_records:,}  (real Agmarknet, not synthetic)")
    print(f"  weather days   {result.weather_records:,}  (real Open-Meteo, 3 tracts)")
    print(f"  lots           {result.lots:,}")
    print(f"  buyer offers   {result.offers:,}  (anchored to real modal prices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
