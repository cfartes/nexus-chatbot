from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.schemas.auth import LoginRequest, Operator
from src.services.auth import SESSION_SECONDS, AuthService, InvalidLogin, LoginLimited, csrf_token, valid_csrf

router = APIRouter(prefix="/auth")
SESSION_COOKIE = "nexus_atende_session"
CSRF_COOKIE = "nexus_atende_csrf"


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin != request.app.state.public_origin:
        raise HTTPException(403, "Origem inválida")


def _service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth_service
    return service


async def authenticated_operator(request: Request) -> Operator:
    try:
        return await _service(request).authenticate(request.cookies.get(SESSION_COOKIE, ""))
    except InvalidLogin:
        raise HTTPException(401, "Sessão inválida") from None


async def mutation_operator(request: Request) -> Operator:
    _check_origin(request)
    operator = await authenticated_operator(request)
    if not valid_csrf(request.cookies.get(SESSION_COOKIE, ""), request.headers.get("X-CSRF-Token", "")):
        raise HTTPException(403, "Token CSRF inválido")
    return operator


async def administrator(actor: Annotated[Operator, Depends(authenticated_operator)]) -> Operator:
    if actor.role != "admin":
        raise HTTPException(403, "Acesso restrito a administradores")
    return actor


async def administrator_mutation(actor: Annotated[Operator, Depends(mutation_operator)]) -> Operator:
    return await administrator(actor)


@router.post("/login", response_model=Operator)
async def login(credentials: LoginRequest, request: Request, response: Response) -> Operator:
    _check_origin(request)
    try:
        operator, session = await _service(request).login(
            credentials, request.client.host if request.client else "unknown",
        )
    except InvalidLogin:
        raise HTTPException(401, "Credenciais inválidas") from None
    except LoginLimited:
        raise HTTPException(429, "Muitas tentativas", headers={"Retry-After": "900"}) from None
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(SESSION_COOKIE, session, max_age=SESSION_SECONDS, httponly=True, secure=True)
    response.set_cookie(CSRF_COOKIE, csrf_token(session), max_age=SESSION_SECONDS, secure=True)
    return operator


@router.get("/me", response_model=Operator)
async def current_operator(request: Request, response: Response) -> Operator:
    response.headers["Cache-Control"] = "no-store"
    return await authenticated_operator(request)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    _check_origin(request)
    try:
        await _service(request).logout(
            request.cookies.get(SESSION_COOKIE, ""), request.headers.get("X-CSRF-Token", ""),
        )
    except InvalidLogin:
        raise HTTPException(401, "Sessão inválida") from None
    except PermissionError:
        raise HTTPException(403, "Token CSRF inválido") from None
    response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True)
    response.delete_cookie(CSRF_COOKIE, secure=True)
