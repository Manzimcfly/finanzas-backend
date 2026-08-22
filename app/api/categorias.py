from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional
from app.core.database import get_db
from app.models.models import Categoria, TipoTransaccion, Usuario
from app.core.auth import get_current_active_user

router = APIRouter()

# Schema Pydantic para crear categoría
class CategoriaCreate(BaseModel):
    nombre: str
    tipo: TipoTransaccion
    color: str = "#3498db"
    icono: str = "📦"

class CategoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    nombre: str
    tipo: TipoTransaccion
    color: str
    icono: str

@router.get("/categorias", response_model=dict)
def listar_categorias(
    tipo: Optional[TipoTransaccion] = Query(None, description="Filtrar por tipo: ingreso/gasto"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    query = db.query(Categoria)
    
    if tipo:
        query = query.filter(Categoria.tipo == tipo)
    
    categorias = query.all()
    
    return {
        "total": len(categorias),
        "categorias": [CategoriaResponse.model_validate(c) for c in categorias]
    }

@router.post("/categorias", response_model=CategoriaResponse, status_code=201)
def crear_categoria(
    categoria: CategoriaCreate, 
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Verificar si ya existe
    existente = db.query(Categoria).filter(Categoria.nombre == categoria.nombre).first()
    if existente:
        raise HTTPException(status_code=400, detail="Ya existe una categoría con ese nombre")
    
    nueva = Categoria(**categoria.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    
    return CategoriaResponse.model_validate(nueva)

class CategoriaUpdate(BaseModel):
    nombre: Optional[str] = None
    color: Optional[str] = None
    icono: Optional[str] = None

@router.put("/categorias/{categoria_id}", response_model=CategoriaResponse)
def actualizar_categoria(
    categoria_id: int,
    categoria: CategoriaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    db_categoria = db.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not db_categoria:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    
    if categoria.nombre is not None:
        db_categoria.nombre = categoria.nombre
    if categoria.color is not None:
        db_categoria.color = categoria.color
    if categoria.icono is not None:
        db_categoria.icono = categoria.icono
    
    db.commit()
    db.refresh(db_categoria)
    
    return CategoriaResponse.model_validate(db_categoria)

@router.delete("/categorias/{categoria_id}")
def eliminar_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    db_categoria = db.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not db_categoria:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    
    db.delete(db_categoria)
    db.commit()
    
    return {"message": "Categoría eliminada"}
