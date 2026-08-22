from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import timedelta
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.core.auth import create_access_token, get_current_active_user
from app.core.config import settings
from app.models.models import Usuario

router = APIRouter(prefix="/auth", tags=["Autenticación"])

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    nombre_completo: str | None = None

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    email: str
    username: str
    nombre_completo: str | None
    activo: bool

class Token(BaseModel):
    access_token: str
    token_type: str

@router.post("/register", response_model=UserResponse, status_code=201)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # Verificar si email ya existe
    if db.query(Usuario).filter(Usuario.email == user.email).first():
        raise HTTPException(
            status_code=400,
            detail="El email ya está registrado"
        )
    
    # Verificar si username ya existe
    if db.query(Usuario).filter(Usuario.username == user.username).first():
        raise HTTPException(
            status_code=400,
            detail="El username ya está en uso"
        )
    
    # Crear usuario
    hashed_pw = hash_password(user.password)
    nuevo_usuario = Usuario(
        email=user.email,
        username=user.username,
        hashed_password=hashed_pw,
        nombre_completo=user.nombre_completo,
        activo=True
    )
    
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    
    return UserResponse.model_validate(nuevo_usuario)

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # Buscar usuario por username
    user = db.query(Usuario).filter(Usuario.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.activo:
        raise HTTPException(
            status_code=400,
            detail="Usuario inactivo"
        )
    
    # Crear token
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: Usuario = Depends(get_current_active_user)):
    return UserResponse.model_validate(current_user)
