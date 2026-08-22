from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.core.database import get_db
from app.models.models import TarjetaCredito, Usuario
from app.core.auth import get_current_active_user

router = APIRouter()

class TarjetaCreate(BaseModel):
    nombre: str
    banco: Optional[str] = None
    limite_credito: float
    saldo_actual: float = 0.0
    fecha_corte: int = 15
    tasa_interes: float = 0.0
    color: str = "#8B5CF6"

class TarjetaUpdate(BaseModel):
    saldo_actual: Optional[float] = None
    limite_credito: Optional[float] = None
    fecha_corte: Optional[int] = None
    tasa_interes: Optional[float] = None

class TarjetaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    banco: Optional[str]
    limite_credito: float
    saldo_actual: float
    fecha_corte: int
    tasa_interes: float
    color: str
    ultimo_actualizacion: datetime
    disponible: Optional[float] = None
    porcentaje_usado: Optional[float] = None

@router.get("/tarjetas", response_model=dict)
def listar_tarjetas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    tarjetas = db.query(TarjetaCredito).filter(TarjetaCredito.usuario_id == current_user.id).all()
    resultados = []
    for t in tarjetas:
        disponible = t.limite_credito - t.saldo_actual
        porcentaje = (t.saldo_actual / t.limite_credito * 100) if t.limite_credito > 0 else 0
        data = TarjetaResponse.model_validate(t)
        data.disponible = disponible
        data.porcentaje_usado = porcentaje
        resultados.append(data)
    return {
        "total": len(resultados),
        "tarjetas": resultados
    }

@router.post("/tarjetas", response_model=TarjetaResponse, status_code=201)
def crear_tarjeta(
    tarjeta: TarjetaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    nueva = TarjetaCredito(
        nombre=tarjeta.nombre,
        banco=tarjeta.banco,
        limite_credito=tarjeta.limite_credito,
        saldo_actual=tarjeta.saldo_actual,
        fecha_corte=tarjeta.fecha_corte,
        tasa_interes=tarjeta.tasa_interes,
        color=tarjeta.color,
        usuario_id=current_user.id
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return TarjetaResponse.model_validate(nueva)

@router.patch("/tarjetas/{tarjeta_id}")
def actualizar_tarjeta(
    tarjeta_id: int,
    tarjeta: TarjetaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    db_tarjeta = db.query(TarjetaCredito).filter(
        TarjetaCredito.id == tarjeta_id,
        TarjetaCredito.usuario_id == current_user.id
    ).first()
    
    if not db_tarjeta:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")
    
    if tarjeta.saldo_actual is not None:
        db_tarjeta.saldo_actual = tarjeta.saldo_actual
    if tarjeta.limite_credito is not None:
        db_tarjeta.limite_credito = tarjeta.limite_credito
    if tarjeta.fecha_corte is not None:
        db_tarjeta.fecha_corte = tarjeta.fecha_corte
    if tarjeta.tasa_interes is not None:
        db_tarjeta.tasa_interes = tarjeta.tasa_interes
    db_tarjeta.ultimo_actualizacion = datetime.now()
    db.commit()
    
    return {
        "mensaje": "Tarjeta actualizada",
        "disponible": db_tarjeta.limite_credito - db_tarjeta.saldo_actual
    }

@router.delete("/tarjetas/{tarjeta_id}")
def eliminar_tarjeta(
    tarjeta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    tarjeta = db.query(TarjetaCredito).filter(
        TarjetaCredito.id == tarjeta_id,
        TarjetaCredito.usuario_id == current_user.id
    ).first()
    
    if not tarjeta:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")
    
    db.delete(tarjeta)
    db.commit()
    
    return {"mensaje": "Tarjeta eliminada"}
