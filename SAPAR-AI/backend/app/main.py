import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.config import Settings
from app.database import Repository, load_dataset
from app.routers.api import router
from app.schemas.contracts import ErrorResponse


def create_app(settings: Settings | None = None, ai_provider=None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        repository = Repository(settings.database_url)
        try:
            repository.initialize(load_dataset(settings.data_dir))
            app.state.repository = repository
            yield
        finally:
            repository.close()

    app = FastAPI(title='SAPAR AI Backend', version='1.0.0', lifespan=lifespan,
                  responses={422: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 500: {'model': ErrorResponse}})
    app.state.settings = settings
    app.state.ai_provider = ai_provider

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Omit input/context: they can contain private text or non-JSON exceptions.
        details = [{'location': list(e['loc']), 'message': e['msg'], 'type': e['type']} for e in exc.errors()]
        return JSONResponse(status_code=422, content={'error': {'code': 'validation_error', 'message': 'Invalid request', 'details': details}})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={'error': {'code': f'http_{exc.status_code}', 'message': str(exc.detail), 'details': []}}, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger('sapar').exception('Unhandled backend failure')
        return JSONResponse(status_code=500, content={'error': {'code': 'internal_error', 'message': 'Internal server error', 'details': []}})

    app.include_router(router)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                       allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
    return app


app = create_app()
