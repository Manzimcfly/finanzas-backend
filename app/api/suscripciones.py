from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime, timedelta
from app.core.database import get_db
from app.models.models import Suscripcion, FrecuenciaSuscripcion, Usuario
from app.core.auth import get_current_active_user

router = APIRouter()

class SuscripcionCreate(BaseModel):
    nombre: str
    proveedor: Optional[str] = None
    monto: float
    frecuencia: FrecuenciaSuscripcion
    categoria: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    notas: Optional[str] = None

class SuscripcionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    proveedor: Optional[str]
    monto: float
    frecuencia: FrecuenciaSuscripcion
    categoria: Optional[str]
    fecha_inicio: Optional[datetime]
    proximo_pago: Optional[datetime]
    esta_activa: bool

@router.get("/suscripciones", response_model=dict)
def listar_suscripciones(
    solo_activas: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    query = db.query(Suscripcion).filter(Suscripcion.usuario_id == current_user.id)
    
    if solo_activas:
        query = query.filter(Suscripcion.esta_activa == True)
    
    suscripciones = query.all()
    
    # Calcular próximo pago para cada una
    resultados = []
    for s in suscripciones:
        if not s.proximo_pago and s.esta_activa:
            s.proximo_pago = calcular_proximo_pago(s)
            db.commit()
        
        resultados.append(SuscripcionResponse.model_validate(s))
    
    return {
        "total": len(resultados),
        "suscripciones": resultados
    }

def calcular_proximo_pago(suscripcion: Suscripcion) -> datetime:
    """Calcula el próximo pago basándose en la frecuencia"""
    hoy = datetime.now()
    
    if suscripcion.fecha_inicio:
        ultimo = suscripcion.fecha_inicio
    else:
        ultimo = hoy
    
    while ultimo < hoy:
        if suscripcion.frecuencia == FrecuenciaSuscripcion.SEMANAL:
            ultimo += timedelta(weeks=1)
        elif suscripcion.frecuencia == FrecuenciaSuscripcion.MENSUAL:
            ultimo = agregar_meses(ultimo, 1)
        elif suscripcion.frecuencia == FrecuenciaSuscripcion.TRIMESTRAL:
            ultimo = agregar_meses(ultimo, 3)
        elif suscripcion.frecuencia == FrecuenciaSuscripcion.ANUAL:
            ultimo = agregar_meses(ultimo, 12)
    
    return ultimo

def agregar_meses(fecha: datetime, meses: int) -> datetime:
    mes = fecha.month + meses
    anio = fecha.year
    while mes > 12:
        mes -= 12
        anio += 1
    return fecha.replace(month=mes, year=anio)

@router.post("/suscripciones", response_model=SuscripcionResponse, status_code=201)
def crear_suscripcion(
    suscripcion: SuscripcionCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Calcular primer próximo pago
    fecha_inicio = suscripcion.fecha_inicio or datetime.now()
    proximo = calcular_proximo_pago_desde(suscripcion.frecuencia, fecha_inicio)
    
    nueva = Suscripcion(
        nombre=suscripcion.nombre,
        proveedor=suscripcion.proveedor,
        monto=suscripcion.monto,
        frecuencia=suscripcion.frecuencia,
        categoria=suscripcion.categoria,
        fecha_inicio=fecha_inicio,
        proximo_pago=proximo,
        esta_activa=True,
        notas=suscripcion.notas,
        usuario_id=current_user.id
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return SuscripcionResponse.model_validate(nueva)

def calcular_proximo_pago_desde(frecuencia: FrecuenciaSuscripcion, desde: datetime) -> datetime:
    hoy = datetime.now()
    proximo = desde
    
    while proximo <= hoy:
        if frecuencia == FrecuenciaSuscripcion.SEMANAL:
            proximo += timedelta(weeks=1)
        elif frecuencia == FrecuenciaSuscripcion.MENSUAL:
            proximo = agregar_meses(proximo, 1)
        elif frecuencia == FrecuenciaSuscripcion.TRIMESTRAL:
            proximo = agregar_meses(proximo, 3)
        elif frecuencia == FrecuenciaSuscripcion.ANUAL:
            proximo = agregar_meses(proximo, 12)
    
    return proximo

@router.get("/suscripciones/resumen", response_model=dict)
def resumen_suscripciones(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    suscripciones = db.query(Suscripcion).filter(
        Suscripcion.usuario_id == current_user.id,
        Suscripcion.esta_activa == True
    ).all()
    
    total_mensual = 0
    por_categoria = {}
    proximas_a_vencer = []
    
    for s in suscripciones:
        # Convertir a mensual
        if s.frecuencia == FrecuenciaSuscripcion.SEMANAL:
            total_mensual += s.monto * 4.33
        elif s.frecuencia == FrecuenciaSuscripcion.MENSUAL:
            total_mensual += s.monto
        elif s.frecuencia == FrecuenciaSuscripcion.TRIMESTRAL:
            total_mensual += s.monto / 3
        elif s.frecuencia == FrecuenciaSuscripcion.ANUAL:
            total_mensual += s.monto / 12
        
        # Por categoría
        cat = s.categoria or "Otros"
        por_categoria[cat] = por_categoria.get(cat, 0) + s.monto
        
        # Próximas a vencer (en los próximos 7 días)
        if s.proximo_pago:
            dias_hasta = (s.proximo_pago - datetime.now()).days
            if 0 <= dias_hasta <= 7:
                proximas_a_vencer.append({
                    "nombre": s.nombre,
                    "monto": s.monto,
                    "proximo_pago": s.proximo_pago.isoformat(),
                    "dias": dias_hasta
                })
    
    return {
        "total_mensual": total_mensual,
        "total_anual": total_mensual * 12,
        "cantidad": len(suscripciones),
        "por_categoria": por_categoria,
        "proximas_a_vencer": proximas_a_vencer
    }

@router.patch("/suscripciones/{suscripcion_id}")
def actualizar_suscripcion(
    suscripcion_id: int,
    esta_activa: bool = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    suscripcion = db.query(Suscripcion).filter(
        Suscripcion.id == suscripcion_id,
        Suscripcion.usuario_id == current_user.id
    ).first()
    
    if not suscripcion:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    
    if esta_activa is not None:
        suscripcion.esta_activa = esta_activa
    
    db.commit()
    return {"mensaje": "Suscripción actualizada"}
