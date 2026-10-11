from io import BytesIO
import logging
from pathlib import Path
from uuid import uuid4
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, func, or_
from app.config import get_settings
from app.errors import ApiError
from app.models import PropertyImage, RentalUnit, Listing, Property
from app.services import inventory

logger = logging.getLogger(__name__)
FORMATS = {'JPEG': ('image/jpeg','.jpg'), 'PNG': ('image/png','.png'), 'WEBP': ('image/webp','.webp')}


def storage_path(key):
    root = Path(get_settings().upload_dir).resolve()
    if Path(key).name != key:
        raise ApiError(404, 'not_found', 'Image not found')
    path = (root / key).resolve()
    if path.parent != root: raise ApiError(404, 'not_found', 'Image not found')
    return path


def sanitize(data, content_type):
    settings = get_settings()
    if len(data) > settings.max_image_bytes: raise ApiError(413, 'image_too_large', 'Image exceeds upload size limit')
    if content_type not in {v[0] for v in FORMATS.values()}: raise ApiError(415, 'unsupported_image', 'Only JPEG, PNG and WebP images are accepted')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=list(FORMATS)) as candidate:
                fmt = candidate.format
                if candidate.width * candidate.height > settings.max_image_pixels:
                    raise ApiError(413, 'image_dimensions', 'Image exceeds pixel limit')
                if getattr(candidate, 'n_frames', 1) != 1:
                    raise ApiError(415, 'animated_image', 'Animated images are not accepted')
                if content_type != FORMATS[fmt][0]:
                    raise ApiError(415, 'image_type_mismatch', 'Declared image type does not match file contents')
                candidate.verify()
            with Image.open(BytesIO(data), formats=list(FORMATS)) as candidate:
                candidate.load()
                oriented = ImageOps.exif_transpose(candidate)
                mode = 'RGB' if fmt == 'JPEG' else ('RGBA' if 'A' in oriented.getbands() else 'RGB')
                pixels = oriented.convert(mode)
                clean = Image.new(mode, pixels.size)
                clean.paste(pixels)  # New image carries no user-supplied EXIF/text metadata.
                out = BytesIO()
                clean.save(out, format=fmt)
        result = out.getvalue()
        if len(result) > settings.max_image_bytes:
            raise ApiError(413, 'image_too_large', 'Re-encoded image exceeds upload size limit')
        return result, FORMATS[fmt][1]
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ApiError(413, 'image_dimensions', 'Image exceeds pixel limit') from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ApiError(422, 'invalid_image', 'Invalid or damaged image') from None


def upload(session, property_id, user, data, content_type, alt_text, position, rental_unit_id):
    prop = inventory.lock_property(session, property_id, user); inventory.ensure_editable(session, prop)
    if not alt_text.strip(): raise ApiError(422, 'invalid_alt_text', 'Provide nonempty image alt text')
    if rental_unit_id is not None:
        unit = session.scalar(select(RentalUnit).where(RentalUnit.id==rental_unit_id, RentalUnit.property_id==prop.id))
        if unit is None: raise ApiError(422, 'invalid_unit', 'Image unit must belong to this property')
    count = session.scalar(select(func.count()).select_from(PropertyImage).where(PropertyImage.property_id==prop.id))
    if count >= get_settings().max_property_images: raise ApiError(409, 'image_limit', 'Maximum images for this property reached')
    encoded, suffix = sanitize(data, content_type)
    key = uuid4().hex + suffix
    path = storage_path(key)
    created = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f:
            created = True
            f.write(encoded)
    except OSError:
        if created: cleanup([key])
        raise ApiError(503, 'storage_unavailable', 'Image storage unavailable') from None
    record = PropertyImage(property_id=prop.id, rental_unit_id=rental_unit_id, storage_key=key,
                           alt_text=alt_text.strip(), position=position)
    session.add(record)
    try: inventory.commit(session)
    except Exception:
        cleanup([key]); raise
    session.refresh(record)
    return inventory.image_view(record)


def cleanup(keys):
    for key in keys:
        try: storage_path(key).unlink(missing_ok=True)
        except OSError: logger.error('Image cleanup failed; storage reconciliation required')


def owned_image(session, property_id, image_id, user):
    prop = inventory.lock_property(session,property_id,user); inventory.ensure_editable(session,prop)
    image = session.scalar(select(PropertyImage).where(PropertyImage.id==image_id,PropertyImage.property_id==prop.id))
    if image is None: raise ApiError(404,'not_found','Image not found')
    return image


def update(session, property_id, image_id, user, data):
    image = owned_image(session,property_id,image_id,user)
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(image,k,v)
    inventory.commit(session); session.refresh(image)
    return inventory.image_view(image)


def delete(session, property_id, image_id, user):
    image = owned_image(session,property_id,image_id,user)
    key = image.storage_key
    session.delete(image); inventory.commit(session)
    cleanup([key])


def readable_image(session, image_id, user=None):
    image = session.get(PropertyImage,image_id)
    if image is None: raise ApiError(404,'not_found','Image not found')
    owner = session.scalar(select(Property.landlord_id).where(Property.id==image.property_id))
    privileged = user is not None and (user.role=='admin' or (user.role=='landlord' and user.id==owner))
    published = session.scalar(select(Listing.id).join(RentalUnit).where(
        RentalUnit.property_id==image.property_id, Listing.status=='published',
        or_(image.rental_unit_id is None, RentalUnit.id==image.rental_unit_id, RentalUnit.kind=='apartment')).limit(1))
    if not privileged and not published: raise ApiError(404,'not_found','Image not found')
    path = storage_path(image.storage_key)
    if not path.is_file(): raise ApiError(404,'not_found','Image not found')
    return path
