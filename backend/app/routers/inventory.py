from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select, func
from app.config import get_settings
from app.dependencies import DB, CurrentUser, require_roles, require_property_owner, require_unit_owner, bearer, current_user
from app.errors import ApiError
from app.models import Property, RentalUnit, Listing, User
from app.repositories import inventory as repo
from app.schemas.inventory import (PropertyCreate, PropertyPatch, PropertyRead, PropertyDetail, UnitCreate, UnitPatch,
    UnitRead, ListingCreate, ListingPatch, ListingRead, Moderation, ImageRead, ImagePatch, PublicListing, Availability, Page, Search, ListingStatus)
from app.services import inventory as service, images

router = APIRouter(tags=['inventory'])
Owner = Annotated[User,Depends(require_roles('landlord','admin'))]
Admin = Annotated[User,Depends(require_roles('admin'))]
OwnedProperty = Annotated[Property,Depends(require_property_owner)]
OwnedUnit = Annotated[RentalUnit,Depends(require_unit_owner)]


@router.get('/properties',response_model=Page[PropertyRead])
def properties(db: DB, user: Owner, page: Annotated[int,Query(ge=1)]=1, page_size: Annotated[int,Query(ge=1,le=100)]=20):
    query=select(Property)
    if user.role!='admin': query=query.where(Property.landlord_id==user.id)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    props=db.scalars(query.order_by(Property.created_at.desc(),Property.id).offset((page-1)*page_size).limit(page_size)).all()
    return Page(items=[service.property_view(db,p) for p in props],total=total,page=page,page_size=page_size)


@router.post('/properties',response_model=PropertyDetail,status_code=201)
def create_property(data: PropertyCreate, db: DB, user: Owner):
    return service.create_property(db,user,data)


@router.get('/properties/{property_id}',response_model=PropertyDetail)
def property_detail(db: DB, prop: OwnedProperty):
    return service.property_view(db,prop,True)


@router.patch('/properties/{property_id}',response_model=PropertyDetail)
def update_property(property_id: UUID,data: PropertyPatch,db: DB,user: CurrentUser):
    return service.update_property(db,property_id,user,data)


@router.delete('/properties/{property_id}',status_code=204)
def delete_property(property_id: UUID,db: DB,user: CurrentUser):
    images.cleanup(service.delete_property(db,property_id,user))
    return Response(status_code=204)


@router.get('/properties/{property_id}/units',response_model=Page[UnitRead])
def units(db: DB, prop: OwnedProperty,page: Annotated[int,Query(ge=1)]=1,page_size: Annotated[int,Query(ge=1,le=100)]=20):
    query=select(RentalUnit).where(RentalUnit.property_id==prop.id)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(RentalUnit.name,RentalUnit.id).offset((page-1)*page_size).limit(page_size)).all()
    return Page(items=[service.unit_view(db,u) for u in rows],total=total,page=page,page_size=page_size)


@router.post('/properties/{property_id}/units',response_model=UnitRead,status_code=201)
def create_unit(property_id: UUID,data: UnitCreate,db: DB,user: CurrentUser):
    return service.create_unit(db,property_id,user,data)


@router.get('/units/{unit_id}',response_model=UnitRead)
def unit_detail(db: DB,unit: OwnedUnit): return service.unit_view(db,unit)


@router.patch('/units/{unit_id}',response_model=UnitRead)
def update_unit(unit_id: UUID,data: UnitPatch,db: DB,user: CurrentUser):
    return service.update_unit(db,unit_id,user,data)


@router.delete('/units/{unit_id}',status_code=204)
def delete_unit(unit_id: UUID,db: DB,user: CurrentUser):
    images.cleanup(service.delete_unit(db,unit_id,user)); return Response(status_code=204)


@router.get('/units/{unit_id}/listing',response_model=ListingRead)
def managed_listing(db: DB,unit: OwnedUnit):
    listing=repo.listing_for(db,unit.id)
    if not listing: raise ApiError(404,'not_found','Listing not found')
    return listing


@router.post('/units/{unit_id}/listing',response_model=ListingRead,status_code=201)
def create_listing(unit_id: UUID,data: ListingCreate,db: DB,user: CurrentUser):
    return service.create_listing(db,unit_id,user,data)


@router.patch('/units/{unit_id}/listing',response_model=ListingRead)
def update_listing(unit_id: UUID,data: ListingPatch,db: DB,user: CurrentUser):
    return service.update_listing(db,unit_id,user,data)


@router.post('/listings/{listing_id}/submit',response_model=ListingRead)
def submit_listing(listing_id: UUID,db: DB,user: CurrentUser):
    return service.transition_listing(db,listing_id,user,'submitted')


@router.post('/listings/{listing_id}/withdraw',response_model=ListingRead)
def withdraw_listing(listing_id: UUID,db: DB,user: CurrentUser):
    return service.transition_listing(db,listing_id,user,'draft')


@router.get('/admin/listings',response_model=Page[ListingRead])
def moderation_queue(db: DB,admin: Admin,status: ListingStatus|None=None,
                     page: Annotated[int,Query(ge=1)]=1,page_size: Annotated[int,Query(ge=1,le=100)]=20):
    query=select(Listing)
    if status: query=query.where(Listing.status==status)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(Listing.created_at,Listing.id).offset((page-1)*page_size).limit(page_size)).all()
    return Page(items=[ListingRead.model_validate(l) for l in rows],total=total,page=page,page_size=page_size)


@router.patch('/admin/listings/{listing_id}/status',response_model=ListingRead)
def moderate_listing(listing_id: UUID,data: Moderation,db: DB,admin: Admin):
    return service.transition_listing(db,listing_id,admin,data.status,data.review_note)


@router.get('/admin/listings/{listing_id}',response_model=ListingRead)
def moderation_detail(listing_id: UUID,db: DB,admin: Admin):
    listing=db.get(Listing,listing_id)
    if listing is None: raise ApiError(404,'not_found','Listing not found')
    return listing


@router.get('/listings',response_model=Page[PublicListing])
def search_listings(filters: Annotated[Search,Query()],db: DB):
    rows,total=repo.search(db,filters)
    return Page(items=[service.public_view(db,*row) for row in rows],total=total,page=filters.page,page_size=filters.page_size)


@router.get('/listings/{listing_id}',response_model=PublicListing)
def listing_detail(listing_id: UUID,db: DB):
    return service.public_view(db,*service.public_listing(db,listing_id))


@router.get('/listings/{listing_id}/availability',response_model=Availability)
def check_availability(listing_id: UUID,db: DB,start_date: Annotated[str,Query()],end_date: Annotated[str,Query()]):
    try: dates=Search(start_date=start_date,end_date=end_date)
    except ValueError: raise ApiError(422,'invalid_dates','Provide a valid, nonempty date range') from None
    listing,unit,_=service.public_listing(db,listing_id)
    available,reason=service.availability(db,listing,unit,dates.start_date,dates.end_date)
    return Availability(listing_id=listing.id,start_date=dates.start_date,end_date=dates.end_date,available=available,reason=reason)


@router.get('/properties/{property_id}/images',response_model=list[ImageRead])
def list_images(db: DB,prop: OwnedProperty): return [service.image_view(i) for i in repo.images(db,prop.id)]


@router.post('/properties/{property_id}/images',response_model=ImageRead,status_code=201)
def upload_image(property_id: UUID,db: DB,user: CurrentUser,file: Annotated[UploadFile,File()],
                 alt_text: Annotated[str,Form(min_length=1,max_length=255)],
                 position: Annotated[int,Form(ge=0,le=1000)]=0,rental_unit_id: Annotated[UUID|None,Form()]=None):
    data=file.file.read(get_settings().max_image_bytes+1)
    return images.upload(db,property_id,user,data,file.content_type,alt_text,position,rental_unit_id)


@router.patch('/properties/{property_id}/images/{image_id}',response_model=ImageRead)
def update_image(property_id: UUID,image_id: UUID,data: ImagePatch,db: DB,user: CurrentUser):
    return images.update(db,property_id,image_id,user,data)


@router.delete('/properties/{property_id}/images/{image_id}',status_code=204)
def delete_image(property_id: UUID,image_id: UUID,db: DB,user: CurrentUser):
    images.delete(db,property_id,image_id,user); return Response(status_code=204)


def optional_user(db: DB,credentials: Annotated[HTTPAuthorizationCredentials|None,Depends(bearer)]):
    return current_user(db,credentials) if credentials else None


@router.get('/images/{image_id}')
def image_file(image_id: UUID,db: DB,user: Annotated[User|None,Depends(optional_user)]):
    path=images.readable_image(db,image_id,user)
    return FileResponse(path,headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'},content_disposition_type='inline')
