from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import check_password, create_token, current_user
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
async def auth_config() -> dict:
    return {"auth_enabled": settings.auth_enabled}


@router.post("/token")
async def login(form: OAuth2PasswordRequestForm = Depends()) -> dict:
    if not check_password(form.username, form.password):
        raise HTTPException(401, "invalid username or password")
    return {"access_token": create_token(form.username), "token_type": "bearer"}


@router.get("/me")
async def me(user: str = Depends(current_user)) -> dict:
    return {"user": user}
