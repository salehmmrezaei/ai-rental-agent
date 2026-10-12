import pytest
from test_auth import api, token_for, headers
from test_inventory import actors, publish
from test_operations import apply, visit_request

@pytest.mark.parametrize('kind',['application','visit'])
def test_rental_display_context_preserves_tenant_privacy(api,engine,inventory,actors,kind):
    lid=publish(api,inventory,actors)
    actors['other']=headers(token_for(api,engine,inventory,'other'))
    rid=apply(api,actors,lid)['id'] if kind=='application' else visit_request(api,actors,lid)
    path=f"/api/v1/{'applications' if kind=='application' else 'visits'}/{rid}"
    response=api.get(path,headers=actors['tenant'])
    assert response.status_code==200
    data=response.json()
    assert data['property_title']=='Synthetic Bologna apartment'
    assert data['unit_name']=='Room A' and data['property_id']==str(inventory['property'])
    assert 'landlord_id' not in data and 'email' not in data
    assert api.get(path,headers=actors['other']).status_code==404
    assert api.get(path,headers=actors['owner']).status_code==403
    directory=api.get(path.rsplit('/',1)[0],headers=actors['tenant']).json()
    assert directory['items'][0]['unit_name']=='Room A'
