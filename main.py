import os
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncGenerator, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import ASupabaseAuthClient, AuthApiError, AuthError
from supabase_auth.types import AuthResponse, Session, User

SUPABASE_KEY_ENV_NAMES = (
    "SUPABASE_ANON_KEY",
    "SUPABASE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
)


def _read_supabase_key() -> str | None:
    for env_name in SUPABASE_KEY_ENV_NAMES:
        env_value = os.getenv(env_name)
        if env_value:
            return env_value
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = _read_supabase_key()

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing Supabase configuration. Set SUPABASE_URL and "
            "SUPABASE_ANON_KEY (or SUPABASE_KEY / SUPABASE_SERVICE_ROLE_KEY)."
        )

    app.state.supabase_url = supabase_url.rstrip("/")
    app.state.supabase_key = supabase_key
    yield


app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://smolib.com",          # Production
        "https://www.smolib.com",      # Production wwg
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Hi, this is smolib"}


class SignUpPayload(BaseModel):
    email: str
    password: str = Field(min_length=8)
    metadata: dict[str, Any] | None = None


class SignInPayload(BaseModel):
    email: str
    password: str


class RefreshPayload(BaseModel):
    refresh_token: str = Field(min_length=1)


class SignOutPayload(BaseModel):
    scope: Literal["global", "local", "others"] = "global"


def _build_auth_client(request: Request) -> ASupabaseAuthClient:
    supabase_url = request.app.state.supabase_url
    supabase_key = request.app.state.supabase_key

    return ASupabaseAuthClient(
        url=f"{supabase_url}/auth/v1",
        headers={
            "apiKey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        auto_refresh_token=False,
        persist_session=False,
    )


async def get_auth_client(
    request: Request,
) -> AsyncGenerator[ASupabaseAuthClient, None]:
    auth_client = _build_auth_client(request)
    try:
        yield auth_client
    finally:
        await auth_client.close()


def _read_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be: Bearer <token>.",
        )

    return token.strip()


def _serialize_session(session: Session | None) -> dict[str, Any] | None:
    if session is None:
        return None

    return session.model_dump(
        mode="json",
        include={
            "access_token",
            "refresh_token",
            "expires_in",
            "expires_at",
            "token_type",
        },
    )


def _serialize_user(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return user.model_dump(mode="json")


def _serialize_auth_response(response: AuthResponse) -> dict[str, Any]:
    return {
        "user": _serialize_user(response.user),
        "session": _serialize_session(response.session),
    }


def _map_auth_error(error: AuthError) -> HTTPException:
    if isinstance(error, AuthApiError):
        return HTTPException(status_code=error.status, detail=error.message)

    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@app.post("/auth/sign-up")
async def sign_up(
    payload: SignUpPayload,
    auth_client: Annotated[ASupabaseAuthClient, Depends(get_auth_client)],
):
    credentials: dict[str, Any] = {
        "email": payload.email,
        "password": payload.password,
    }
    if payload.metadata is not None:
        credentials["options"] = {"data": payload.metadata}

    try:
        auth_response = await auth_client.sign_up(credentials)
    except AuthError as error:
        raise _map_auth_error(error) from error

    return _serialize_auth_response(auth_response)


@app.post("/auth/sign-in")
async def sign_in(
    payload: SignInPayload,
    auth_client: Annotated[ASupabaseAuthClient, Depends(get_auth_client)],
):
    try:
        auth_response = await auth_client.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
    except AuthError as error:
        raise _map_auth_error(error) from error

    return _serialize_auth_response(auth_response)


@app.post("/auth/refresh")
async def refresh(
    payload: RefreshPayload,
    auth_client: Annotated[ASupabaseAuthClient, Depends(get_auth_client)],
):
    try:
        auth_response = await auth_client.refresh_session(payload.refresh_token)
    except AuthError as error:
        raise _map_auth_error(error) from error

    return _serialize_auth_response(auth_response)


@app.get("/auth/me")
async def me(
    auth_client: Annotated[ASupabaseAuthClient, Depends(get_auth_client)],
    authorization: Annotated[str | None, Header()] = None,
):
    access_token = _read_bearer_token(authorization)

    try:
        user_response = await auth_client.get_user(access_token)
    except AuthError as error:
        raise _map_auth_error(error) from error

    if not user_response or not user_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
        )

    return {"user": _serialize_user(user_response.user)}


@app.post("/auth/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    auth_client: Annotated[ASupabaseAuthClient, Depends(get_auth_client)],
    payload: SignOutPayload | None = None,
    authorization: Annotated[str | None, Header()] = None,
):
    access_token = _read_bearer_token(authorization)
    scope = payload.scope if payload else "global"

    try:
        await auth_client.admin.sign_out(access_token, scope)
    except AuthError as error:
        raise _map_auth_error(error) from error


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=443)
