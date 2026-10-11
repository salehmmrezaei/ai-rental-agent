from datetime import date, timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image, PngImagePlugin
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models import Property, Listing, PropertyImage, RentalRequest, RentalContract, Amenity
from app.repositories.inventory import today
from conftest import application, contract
from test_auth import api, token_for, headers  # shared PostgreSQL-backed authenticated fixture


@pytest.fixture
def actors(api, engine, inventory, monkeypatch, tmp_path):
    monkeypatch.setenv('UPLOAD_DIR',str(tmp_path/'images'))
    get_settings.cache_clear()
    return {role:headers(token_for(api,engine,inventory,role)) for role in ['owner','other_owner','tenant','admin']}


def prop_payload():
    return {'title':'Synthetic Florence apartment','description':'Synthetic rental for development',
            'city':'Florence','address':'Synthetic Via Esempio 20','postal_code':'50100',
            'amenities':['WiFi','Balcony','wifi']}


def draft(api,inventory,actors,unit='room',**values):
    payload={'available_from':str(today()),'available_until':str(today()+timedelta(days=730))}
    payload.update(values)
    response=api.post(f"/api/v1/units/{inventory[unit]}/listing",json=payload,headers=actors['owner'])
    assert response.status_code==201,response.text
    return response.json()['id']


def publish(api,inventory,actors,unit='room',**values):
    lid=draft(api,inventory,actors,unit,**values)
    assert api.post(f'/api/v1/listings/{lid}/submit',headers=actors['owner']).status_code==200
    for status in ['approved','published']:
        response=api.patch(f'/api/v1/admin/listings/{lid}/status',json={'status':status},headers=actors['admin'])
        assert response.status_code==200,response.text
    return lid


def image_bytes(fmt='PNG',metadata=False):
    out=BytesIO(); image=Image.new('RGB',(12,10),'blue')
    options={}
    if metadata:
        info=PngImagePlugin.PngInfo(); info.add_text('PrivateText','synthetic metadata to remove'); options['pnginfo']=info
    image.save(out,format=fmt,**options)
    return out.getvalue()


def upload(api,inventory,actors,role='owner',data=None,mime='image/png',**form):
    return api.post(f"/api/v1/properties/{inventory['property']}/images",headers=actors[role],
        data={'alt_text':'Synthetic property photograph',**form},
        files={'file':('../../user-controlled-name.png',data if data is not None else image_bytes(),mime)})


def test_property_unit_crud_and_amenities(api,engine,inventory,actors):
    response=api.post('/api/v1/properties',json=prop_payload(),headers=actors['owner'])
    assert response.status_code==201,response.text
    prop=response.json(); pid=prop['id']
    assert prop['landlord_id']==str(inventory['owner']) and prop['amenities']==['balcony','wifi']
    assert prop['is_synthetic'] and prop['units']==[]
    response=api.patch(f'/api/v1/properties/{pid}',json={'title':'Synthetic Updated','amenities':['Lift']},headers=actors['owner'])
    assert response.status_code==200 and response.json()['amenities']==['lift']
    response=api.post(f'/api/v1/properties/{pid}/units',json={'kind':'room','name':'Independent room','monthly_rent':'780.50','deposit':'500'},headers=actors['owner'])
    assert response.status_code==201,response.text
    uid=response.json()['id']
    assert response.json()['monthly_rent']=='780.50' and response.json()['occupancy_status']=='available'
    assert api.patch(f'/api/v1/units/{uid}',json={'monthly_rent':'800','area_sqm':'15'},headers=actors['owner']).status_code==200
    assert api.get(f'/api/v1/properties/{pid}/units',headers=actors['owner']).json()['total']==1
    assert api.get(f'/api/v1/units/{uid}',headers=actors['owner']).json()['monthly_rent']=='800.00'
    assert api.delete(f'/api/v1/units/{uid}',headers=actors['owner']).status_code==204
    assert api.delete(f'/api/v1/properties/{pid}',headers=actors['owner']).status_code==204
    assert api.get(f'/api/v1/properties/{pid}',headers=actors['owner']).status_code==404


def test_property_collections_are_scoped(api,inventory,actors):
    assert api.get('/api/v1/properties',headers=actors['owner']).json()['total']==1
    assert api.get('/api/v1/properties',headers=actors['other_owner']).json()['total']==0
    assert api.get('/api/v1/properties',headers=actors['tenant']).status_code==403
    assert api.get('/api/v1/properties').status_code==401
    assert api.get('/api/v1/properties?page_size=101',headers=actors['owner']).status_code==422


@pytest.mark.parametrize('role', ['tenant','other_owner'])
@pytest.mark.parametrize('operation', ['get_property','patch_property','delete_property','create_unit','get_unit','patch_unit','delete_unit','images'])
def test_owner_checks_on_actual_routes(api,inventory,actors,role,operation):
    p=inventory['property']; u=inventory['room']; h=actors[role]
    actions={
        'get_property':lambda:api.get(f'/api/v1/properties/{p}',headers=h),
        'patch_property':lambda:api.patch(f'/api/v1/properties/{p}',json={'title':'Attempted change'},headers=h),
        'delete_property':lambda:api.delete(f'/api/v1/properties/{p}',headers=h),
        'create_unit':lambda:api.post(f'/api/v1/properties/{p}/units',json={'kind':'room','name':'New','monthly_rent':'650'},headers=h),
        'get_unit':lambda:api.get(f'/api/v1/units/{u}',headers=h),
        'patch_unit':lambda:api.patch(f'/api/v1/units/{u}',json={'monthly_rent':'1'},headers=h),
        'delete_unit':lambda:api.delete(f'/api/v1/units/{u}',headers=h),
        'images':lambda:api.get(f'/api/v1/properties/{p}/images',headers=h)}
    assert actions[operation]().status_code==404
    assert api.get(f'/api/v1/units/{u}',headers=actors['owner']).json()['monthly_rent']=='650.00'


def test_admin_property_creation_preserves_real_owner(api,inventory,actors):
    body=prop_payload()
    assert api.post('/api/v1/properties',json=body,headers=actors['admin']).status_code==422
    body['landlord_id']=str(inventory['owner'])
    response=api.post('/api/v1/properties',json=body,headers=actors['admin'])
    assert response.status_code==201 and response.json()['landlord_id']==str(inventory['owner'])
    body['landlord_id']=str(inventory['tenant'])
    assert api.post('/api/v1/properties',json=body,headers=actors['admin']).status_code==422
    body['landlord_id']=str(inventory['other_owner'])
    assert api.post('/api/v1/properties',json=body,headers=actors['owner']).status_code==403
    assert api.post('/api/v1/properties',json=prop_payload(),headers=actors['tenant']).status_code==403


@pytest.mark.parametrize('data', [{'landlord_id':str(uuid4())},{'is_synthetic':False},{'title':' '},{'postal_code':'abc'},{'amenities':None},{}])
def test_property_patch_validation(api,inventory,actors,data):
    assert api.patch(f"/api/v1/properties/{inventory['property']}",json=data,headers=actors['owner']).status_code==422


@pytest.mark.parametrize('data', [{'monthly_rent':'0'},{'monthly_rent':'NaN'},{'monthly_rent':'650.001'},{'deposit':'-1'},{'bedrooms':0},{'kind':'apartment'},{'property_id':str(uuid4())}])
def test_unit_patch_validation(api,inventory,actors,data):
    assert api.patch(f"/api/v1/units/{inventory['room']}",json=data,headers=actors['owner']).status_code==422


def test_duplicate_apartment_or_room_name_conflicts(api,inventory,actors):
    path=f"/api/v1/properties/{inventory['property']}/units"
    for kind,name in [('apartment','Another entire apartment'),('room','Room A')]:
        assert api.post(path,json={'kind':kind,'name':name,'monthly_rent':'650'},headers=actors['owner']).status_code==409


def test_listing_review_visibility_and_withdrawal(api,inventory,actors):
    lid=draft(api,inventory,actors)
    assert api.get(f'/api/v1/listings/{lid}').status_code==404
    assert api.get('/api/v1/listings').json()['total']==0
    assert api.patch(f'/api/v1/admin/listings/{lid}/status',json={'status':'approved'},headers=actors['owner']).status_code==403
    assert api.post(f'/api/v1/listings/{lid}/submit',headers=actors['other_owner']).status_code==404
    assert api.post(f'/api/v1/listings/{lid}/submit',headers=actors['owner']).status_code==200
    assert api.get('/api/v1/admin/listings?status=submitted',headers=actors['admin']).json()['total']==1
    assert api.post(f'/api/v1/listings/{lid}/withdraw',headers=actors['owner']).json()['status']=='draft'
    assert api.post(f'/api/v1/listings/{lid}/submit',headers=actors['owner']).status_code==200
    assert api.patch(f'/api/v1/admin/listings/{lid}/status',json={'status':'rejected'},headers=actors['admin']).status_code==422
    response=api.patch(f'/api/v1/admin/listings/{lid}/status',json={'status':'rejected','review_note':'Synthetic description needs correction'},headers=actors['admin'])
    assert response.status_code==200 and response.json()['status']=='rejected'
    assert api.patch(f"/api/v1/units/{inventory['room']}/listing",json={'available_until':None},headers=actors['owner']).status_code==200
    assert api.post(f'/api/v1/listings/{lid}/submit',headers=actors['owner']).json()['review_note'] is None
    for status in ['approved','published']:
        assert api.patch(f'/api/v1/admin/listings/{lid}/status',json={'status':status},headers=actors['admin']).status_code==200
    result=api.get(f'/api/v1/listings/{lid}')
    assert result.status_code==200 and result.json()['available_now'] is True
    assert 'landlord_id' not in result.text and 'review_note' not in result.text
    assert api.post(f'/api/v1/listings/{lid}/withdraw',headers=actors['owner']).status_code==409
    assert api.patch(f'/api/v1/admin/listings/{lid}/status',json={'status':'unpublished'},headers=actors['admin']).status_code==200
    assert api.get(f'/api/v1/listings/{lid}').status_code==404
    assert api.post(f'/api/v1/listings/{lid}/withdraw',headers=actors['owner']).status_code==200


@pytest.mark.parametrize('state', ['submitted','approved','published','unpublished'])
def test_reviewed_property_content_is_frozen(api,inventory,actors,state):
    lid=draft(api,inventory,actors)
    assert api.post(f'/api/v1/listings/{lid}/submit',headers=actors['owner']).status_code==200
    transitions={'submitted':[],'approved':['approved'],'published':['approved','published'],'unpublished':['approved','published','unpublished']}
    for status in transitions[state]:
        assert api.patch(f'/api/v1/admin/listings/{lid}/status',json={'status':status},headers=actors['admin']).status_code==200
    assert api.patch(f"/api/v1/properties/{inventory['property']}",json={'description':'Changed'},headers=actors['owner']).status_code==409
    assert api.patch(f"/api/v1/units/{inventory['room']}",json={'monthly_rent':'999'},headers=actors['owner']).status_code==409
    assert api.patch(f"/api/v1/units/{inventory['room']}/listing",json={'available_until':None},headers=actors['owner']).status_code==409
    assert upload(api,inventory,actors).status_code==409
    assert api.delete(f"/api/v1/units/{inventory['room_b']}",headers=actors['owner']).status_code==409


def test_draft_listing_constraints(api,inventory,actors):
    path=f"/api/v1/units/{inventory['room']}/listing"
    assert api.post(path,json={'available_from':'2027-03-01','available_until':'2027-01-01'},headers=actors['owner']).status_code==422
    lid=draft(api,inventory,actors)
    assert api.post(path,json={'available_from':str(today())},headers=actors['owner']).status_code==409
    assert api.patch(path,json={'status':'published'},headers=actors['owner']).status_code==422
    assert api.patch(path,json={'available_until':str(today())},headers=actors['owner']).status_code==422
    assert api.patch(f'/api/v1/admin/listings/{lid}/status',json={'status':'published'},headers=actors['admin']).status_code==409


def test_expired_listing_cannot_be_submitted(api,inventory,actors):
    lid=draft(api,inventory,actors,available_from=str(today()-timedelta(days=30)),available_until=str(today()-timedelta(days=1)))
    assert api.post(f'/api/v1/listings/{lid}/submit',headers=actors['owner']).status_code==409


def test_search_filters_sort_pagination_and_no_private_metadata(api,inventory,actors):
    for key in ['room','room_b','apartment']: publish(api,inventory,actors,key)
    response=api.get('/api/v1/listings?city=BOLOGNA&property_type=room&min_price=600&max_price=650&min_rooms=1&sort=price_asc&page_size=1')
    assert response.status_code==200,response.text
    result=response.json(); assert result['total']==2 and len(result['items'])==1
    assert result['items'][0]['monthly_rent']=='600.00'
    assert api.get('/api/v1/listings?sort=price_desc').json()['items'][0]['kind']=='apartment'
    assert api.get('/api/v1/listings?city=Rome').json()['total']==0
    assert api.get('/api/v1/listings?min_rooms=2').json()['total']==0
    assert 'landlord_id' not in response.text and 'storage_key' not in response.text
    assert api.get('/api/v1/listings?page=2&page_size=1').json()['total']==3


@pytest.mark.parametrize('query', ['min_price=1000&max_price=1','start_date=2027-01-01','start_date=2027-03-01&end_date=2027-01-01','sort=invalid','page_size=101','property_type=castle'])
def test_search_validation(api,query):
    assert api.get('/api/v1/listings?'+query).status_code==422


@pytest.mark.parametrize('booked,target,available', [('room','room',False),('room','apartment',False),('apartment','room',False),('apartment','apartment',False),('room','room_b',True)])
def test_availability_and_search_use_room_apartment_conflicts(api,engine,inventory,actors,booked,target,available):
    lid=publish(api,inventory,actors,target)
    with Session(engine) as s,s.begin():
        r=application(s,inventory,booked); contract(s,inventory,r,booked)
    params={'start_date':'2027-01-01','end_date':'2027-03-01'}
    result=api.get(f'/api/v1/listings/{lid}/availability',params=params)
    assert result.status_code==200,result.text
    assert result.json()['available']==available
    assert api.get('/api/v1/listings',params=params).json()['total']==(1 if available else 0)
    assert 'tenant' not in result.text


def test_adjacent_date_and_window_boundaries(api,engine,inventory,actors):
    lid=publish(api,inventory,actors,available_from='2027-01-01',available_until='2027-06-01')
    with Session(engine) as s,s.begin():
        r=application(s,inventory); contract(s,inventory,r)
    path=f'/api/v1/listings/{lid}/availability'
    assert api.get(path,params={'start_date':'2027-03-01','end_date':'2027-06-01'}).json()['available']
    result=api.get(path,params={'start_date':'2027-06-01','end_date':'2027-07-01'}).json()
    assert result['reason']=='outside_listing_window' and not result['available']
    assert api.get(path,params={'start_date':'2027-01-01','end_date':'2027-01-01'}).status_code==422


def test_live_occupancy_and_cancelled_release(api,engine,inventory,actors):
    day=today()
    with Session(engine) as s,s.begin():
        r=application(s,inventory,start=day,end=day+timedelta(days=30)); cid=contract(s,inventory,r,start=day,end=day+timedelta(days=30))
    assert api.get(f"/api/v1/units/{inventory['room']}",headers=actors['owner']).json()['occupancy_status']=='occupied'
    assert api.get(f"/api/v1/units/{inventory['apartment']}",headers=actors['owner']).json()['occupancy_status']=='occupied'
    assert api.get(f"/api/v1/units/{inventory['room_b']}",headers=actors['owner']).json()['occupancy_status']=='available'
    with Session(engine) as s,s.begin(): s.get(RentalContract,cid).status='cancelled'
    assert api.get(f"/api/v1/units/{inventory['room']}",headers=actors['owner']).json()['occupancy_status']=='available'


@pytest.mark.parametrize('resource', ['unit','property'])
def test_delete_preserves_rental_history_and_rolls_back(api,engine,inventory,actors,resource):
    with Session(engine) as s,s.begin(): application(s,inventory)
    image=upload(api,inventory,actors).json()
    path=f"/api/v1/units/{inventory['room']}" if resource=='unit' else f"/api/v1/properties/{inventory['property']}"
    assert api.delete(path,headers=actors['owner']).status_code==409
    assert api.get(f"/api/v1/properties/{inventory['property']}",headers=actors['owner']).status_code==200
    assert api.get(image['url'],headers=actors['owner']).status_code==200


@pytest.mark.parametrize('fmt,mime', [('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp')])
def test_image_upload_serve_delete_and_filename_safety(api,engine,inventory,actors,fmt,mime):
    response=upload(api,inventory,actors,data=image_bytes(fmt),mime=mime)
    assert response.status_code==201,response.text
    image=response.json(); assert 'storage_key' not in image
    assert api.get(image['url']).status_code==404
    assert api.get(image['url'],headers=actors['tenant']).status_code==404
    served=api.get(image['url'],headers=actors['owner'])
    assert served.status_code==200 and served.headers['content-type']==mime
    assert served.headers['x-content-type-options']=='nosniff'
    with Session(engine) as s:
        key=s.get(PropertyImage,image['id']).storage_key
        assert '..' not in key and '/' not in key
    assert api.patch(f"/api/v1/properties/{inventory['property']}/images/{image['id']}",json={'alt_text':'Updated synthetic view','position':2},headers=actors['owner']).status_code==200
    assert api.delete(f"/api/v1/properties/{inventory['property']}/images/{image['id']}",headers=actors['owner']).status_code==204
    assert api.get(image['url'],headers=actors['owner']).status_code==404
    assert not (get_settings().upload_dir and __import__('pathlib').Path(get_settings().upload_dir,key).exists())


def test_images_public_only_while_published_and_metadata_stripped(api,inventory,actors):
    image=upload(api,inventory,actors,data=image_bytes(metadata=True)).json()
    assert api.get(image['url']).status_code==404
    lid=publish(api,inventory,actors)
    response=api.get(image['url']); assert response.status_code==200
    with Image.open(BytesIO(response.content)) as decoded: assert 'PrivateText' not in decoded.info
    assert len(api.get(f'/api/v1/listings/{lid}').json()['images'])==1
    assert api.patch(f'/api/v1/admin/listings/{lid}/status',json={'status':'unpublished'},headers=actors['admin']).status_code==200
    assert api.get(image['url']).status_code==404


@pytest.mark.parametrize('data,mime,expected', [(b'<svg>script</svg>','image/svg+xml',415),(b'not an image','image/png',422),(image_bytes(),'image/jpeg',415)])
def test_upload_content_validation(api,inventory,actors,data,mime,expected):
    assert upload(api,inventory,actors,data=data,mime=mime).status_code==expected


def test_image_limits_unit_membership_and_owner_protection(api,inventory,actors,monkeypatch):
    assert upload(api,inventory,actors,role='other_owner').status_code==404
    assert upload(api,inventory,actors,rental_unit_id=str(uuid4())).status_code==422
    monkeypatch.setenv('MAX_IMAGE_PIXELS','10'); get_settings.cache_clear()
    assert upload(api,inventory,actors).status_code==413
    monkeypatch.setenv('MAX_IMAGE_PIXELS','20000000')
    monkeypatch.setenv('MAX_PROPERTY_IMAGES','1'); get_settings.cache_clear()
    assert upload(api,inventory,actors).status_code==201
    assert upload(api,inventory,actors).status_code==409


def test_entire_upload_request_limit(api,inventory,actors):
    response=api.post(f"/api/v1/properties/{inventory['property']}/images",headers={**actors['owner'],'Content-Length':'999999999'},content=b'')
    assert response.status_code==413
    # No Content-Length: count actual streamed bytes before multipart parsing.
    def chunks():
        for _ in range(90): yield b'x'*65536
    response=api.post(f"/api/v1/properties/{inventory['property']}/images",headers=actors['owner'],content=chunks())
    assert response.status_code==413


def test_room_images_not_leaked_to_unrelated_published_room(api,inventory,actors):
    image=upload(api,inventory,actors,rental_unit_id=str(inventory['room_b'])).json()
    lid=publish(api,inventory,actors,'room')
    assert api.get(f'/api/v1/listings/{lid}').json()['images']==[]
    assert api.get(image['url']).status_code==404


def test_foreign_and_missing_unit_listing_errors_are_indistinguishable(api,inventory,actors):
    for uid in [inventory['room'],uuid4()]:
        response=api.patch(f'/api/v1/units/{uid}',json={'monthly_rent':'700'},headers=actors['other_owner'])
        assert response.status_code==404
        assert response.json()['error']['message']=='Rental unit not found'
    lid=draft(api,inventory,actors)
    for target in [lid,uuid4()]:
        response=api.post(f'/api/v1/listings/{target}/submit',headers=actors['other_owner'])
        assert response.status_code==404
        assert response.json()['error']['message']=='Listing not found'


def test_future_reservation_and_available_now_from_dates(api,engine,inventory,actors):
    lid=publish(api,inventory,actors)
    day=today()
    with Session(engine) as s,s.begin():
        start,end=day+timedelta(days=10),day+timedelta(days=40)
        req=application(s,inventory,start=start,end=end)
        contract(s,inventory,req,start=start,end=end)
    assert api.get(f"/api/v1/units/{inventory['room']}",headers=actors['owner']).json()['occupancy_status']=='reserved'
    assert api.get(f'/api/v1/listings/{lid}').json()['available_now']
    assert api.get('/api/v1/listings',params={'start_date':str(start),'end_date':str(end)}).json()['total']==0


def test_delete_property_cleans_image_files(api,inventory,actors):
    from pathlib import Path
    image=upload(api,inventory,actors).json()
    root=Path(get_settings().upload_dir)
    assert list(root.iterdir())
    assert api.delete(f"/api/v1/properties/{inventory['property']}",headers=actors['owner']).status_code==204
    assert list(root.iterdir())==[]
    assert api.get(image['url'],headers=actors['owner']).status_code==404


def test_jpeg_private_exif_removed(api,inventory,actors):
    out=BytesIO(); img=Image.new('RGB',(10,10),'red'); exif=Image.Exif(); exif[0x010E]='Synthetic private image metadata'
    img.save(out,format='JPEG',exif=exif)
    response=upload(api,inventory,actors,data=out.getvalue(),mime='image/jpeg')
    assert response.status_code==201
    served=api.get(response.json()['url'],headers=actors['owner'])
    with Image.open(BytesIO(served.content)) as decoded: assert not decoded.getexif()
