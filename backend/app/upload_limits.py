from starlette.responses import JSONResponse


class UploadRequestLimit:
    """Bound the whole upload request before multipart parsing/spooling begins."""
    def __init__(self, app, max_bytes):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        path = scope.get('path','').rstrip('/')
        if scope['type'] != 'http' or scope.get('method') != 'POST' or not (
                path.startswith('/api/v1/properties/') and path.endswith('/images')):
            return await self.app(scope, receive, send)
        for name,value in scope.get('headers',[]):
            if name == b'content-length':
                try: length = int(value)
                except ValueError: length = -1
                if length < 0 or length > self.max_bytes:
                    response = self.error(413 if length > self.max_bytes else 400)
                    return await response(scope,receive,send)
        chunks=[]; total=0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect': return
            body=message.get('body',b''); total+=len(body)
            if total > self.max_bytes:
                return await self.error(413)(scope,receive,send)
            chunks.append(body)
            if not message.get('more_body',False): break
        payload=b''.join(chunks)
        delivered=False
        async def bounded_receive():
            nonlocal delivered
            if delivered: return await receive()
            delivered=True
            return {'type':'http.request','body':payload,'more_body':False}
        return await self.app(scope,bounded_receive,send)

    @staticmethod
    def error(status):
        return JSONResponse(status_code=status,content={'error':{
            'code':'upload_request_too_large' if status==413 else 'invalid_request',
            'message':'Upload request exceeds size limit' if status==413 else 'Invalid request size'}})
