"""Attach bundled sample photographs to the versioned synthetic demo portfolio."""
import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Property, PropertyImage, RentalUnit
from app.seed import record_id, SeedError

ASSETS = {
    "bologna-living": "Living room with an olive sofa and sunlit windows",
    "milan-living": "Bright living and dining room with warm wood furniture",
    "rome-bedroom": "Double bedroom with a desk and natural light",
    "florence-bedroom": "Bedroom with exposed beams and sage linen",
    "shared-kitchen": "Shared kitchen and dining table",
    "study-bedroom": "Private room with a single bed and study desk",
}
ASSET_DIR = Path(__file__).with_name("demo_assets")


def bundled_image(image: PropertyImage) -> Path | None:
    """Resolve only known bundled assets for an exact, record-specific demo key.

    Called after ordinary database image authorization. Uploads and cleanup keep
    their existing storage paths; deleting metadata never deletes bundled assets.
    """
    prefix = f"demo-v1-{image.id.hex}-"
    if not image.storage_key.startswith(prefix):
        return None
    name = image.storage_key[len(prefix):]
    if name not in {f"{asset}.webp" for asset in ASSETS}:
        return None
    return ASSET_DIR / name


def seed_demo_images(session: Session):
    """Metadata-only import; caller owns the transaction. Preserve existing photos."""
    if session.get_bind().dialect.name != "postgresql":
        raise SeedError("Demo images require PostgreSQL")
    session.execute(text("SELECT pg_advisory_xact_lock(6006001)"))
    if any(not (ASSET_DIR / f"{asset}.webp").is_file() for asset in ASSETS):
        raise SeedError("Bundled demo images are missing; install the complete backend package")
    properties = list(session.scalars(select(Property).where(
        Property.id.in_([record_id("property", i) for i in range(300)])).with_for_update()))
    if len(properties) != 300 or any(not prop.is_synthetic for prop in properties):
        raise SeedError("Run the complete demo data seed before importing sample photos")
    units = set(session.scalars(select(RentalUnit.id).where(
        RentalUnit.id.in_([record_id("unit", i) for i in range(900)]))))
    if len(units) != 900:
        raise SeedError("Demo rental units are incomplete; no images were changed")
    created = 0
    for i in range(300):
        pid = record_id("property", i)
        existing = list(session.scalars(select(PropertyImage).where(PropertyImage.property_id == pid)))
        ids = {image.id for image in existing}
        position = max((image.position for image in existing), default=-1) + 1
        choices = (
            ("bologna-living" if i % 2 == 0 else "milan-living", 0),
            ("rome-bedroom" if i % 3 == 0 else "florence-bedroom", 1),
            ("study-bedroom", 2),
            ("shared-kitchen", None),
        )
        for j, (asset, unit) in enumerate(choices):
            iid = record_id("photo", i * 4 + j)
            if iid in ids:
                continue
            session.add(PropertyImage(id=iid, property_id=pid,
                rental_unit_id=record_id("unit", i * 3 + unit) if unit is not None else None,
                storage_key=f"demo-v1-{iid.hex}-{asset}.webp",
                alt_text=f"AI-generated sample: {ASSETS[asset]}", position=position))
            position += 1
            created += 1
    session.flush()
    return {"created": created, "properties": 300}


def main():
    parser = argparse.ArgumentParser(description="Add AI-generated sample photographs to demo properties")
    parser.add_argument("--demo", required=True, action="store_true")
    parser.parse_args()
    try:
        with Session(get_engine()) as session, session.begin():
            result = seed_demo_images(session)
    except SeedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Demo image import failed; transaction rolled back", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
