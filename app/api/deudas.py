from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime, timedelta
from app.core.database import get_db
from app.models.models import Deuda, TipoDeuda, Usuario
from app.core.auth import get_current_active_user

router = APIRouter()

class DeudaCreate(BaseModel):
    nombre: str
    tipo: TipoDeuda
    monto_original: float
    monto_actual: float
    tasa_interes: float = 0.0
    cuota_mensual: Optional[float] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None

class DeudaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    tipo: TipoDeuda
    monto_original: float
    monto_actual: float
    tasa_interes: float
    cuota_mensual: Optional[float]
    fecha_inicio: Optional[datetime]
    fecha_fin: Optional[datetime]
    esta_pagada: bool

class SimulacionPagoAnticipado(BaseModel):
    meses_ahorrados: int
    intereses_ahorrados: float
    nuevo_fecha_fin: datetime
    ahorro_total: float

@router.get("/deudas", response_model=dict)
def listar_deudas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    deudas = db.query(Deuda).filter(Deuda.usuario_id == current_user.id).all()
    return {
        "total": len(deudas),
        "deudas": [DeudaResponse.model_validate(d) for d in deudas]
    }

@router.post("/deudas", response_model=DeudaResponse, status_code=201)
def crear_deuda(
    deuda: DeudaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    nueva = Deuda(
        nombre=deuda.nombre,
        tipo=deuda.tipo,
        monto_original=deuda.monto_original,
        monto_actual=deuda.monto_actual,
        tasa_interes=deuda.tasa_interes,
        cuota_mensual=deuda.cuota_mensual,
        fecha_inicio=deuda.fecha_inicio,
        fecha_fin=deuda.fecha_fin,
        usuario_id=current_user.id
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return DeudaResponse.model_validate(nueva)

@router.get("/deudas/resumen", response_model=dict)
def resumen_deudas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    deudas = db.query(Deuda).filter(
        Deuda.usuario_id == current_user.id,
        Deuda.esta_pagada == False
    ).all()
    
    total_deuda = sum(d.monto_actual for d in deudas)
    deuda_mayor = max(deudas, key=lambda d: d.monto_actual, default=None)
    
    # Calcular interés mensual estimado
    interes_mensual = sum(d.monto_actual * (d.tasa_interes / 100 / 12) for d in deudas)
    
    return {
        "total_deuda": total_deuda,
        "cantidad_deudas": len(deudas),
        "deuda_mayor": {
            "nombre": deuda_mayor.nombre if deuda_mayor else None,
            "monto": deuda_mayor.monto_actual if deuda_mayor else 0
        },
        "interes_mensual_estimado": interes_mensual,
        "deudas_por_tipo": {
            t.value: len([d for d in deudas if d.tipo == t]) 
            for t in TipoDeuda
        }
    }

@router.get("/deudas/{deuda_id}/simular-pago-anticipado", response_model=SimulacionPagoAnticipado)
def simular_pago_anticipado(
    deuda_id: int,
    monto_extra: float = Query(..., gt=0, description="Monto adicional a pagar"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    deuda = db.query(Deuda).filter(
        Deuda.id == deuda_id,
        Deuda.usuario_id == current_user.id
    ).first()
    
    if not deuda:
        raise HTTPException(status_code=404, detail="Deuda no encontrada")
    
    if deuda.esta_pagada:
        raise HTTPException(status_code=400, detail="La deuda ya está pagada")
    
    # Simulación simple (método avalancha - pagar deuda con mayor tasa de interés)
    tasa_mensual = deuda.tasa_interes / 100 / 12
    saldo = deuda.monto_actual
    pago_mensual = deuda.cuota_mensual or saldo / 24  # Default 24 meses
    pago_total = pago_mensual + monto_extra
    
    meses = 0
    intereses_pagados = 0
    
    while saldo > 0 and meses < 120:  # Max 10 años
        intereses = saldo * tasa_mensual
        intereses_pagados += intereses
        saldo = saldo + intereses - pago_total
        meses += 1
        if saldo <= 0:
            break
    
    # Calcular fecha original vs nueva
    fecha_original = datetime.now() + timedelta(days=30 * (deuda.meses_originales or 24))
    nueva_fecha = datetime.now() + timedelta(days=30 * meses)
    
    # Original
    meses_originales = 24
    intereses_originales = 0
    saldo_orig = deuda.monto_actual
    for _ in range(meses_originales):
        intereses_originales += saldo_orig * tasa_mensual
        saldo_orig = saldo_orig + saldo_orig * tasa_mensual - pago_mensual
    
    return SimulacionPagoAnticipado(
        meses_ahorrados=meses_originales - meses,
        intereses_ahorrados=intereses_originales - intereses_pagados,
        nuevo_fecha_fin=nueva_fecha,
        ahorro_total=(intereses_originales - intereses_pagados)
    )

@router.patch("/deudas/{deuda_id}/marcar-pagada")
def marcar_deuda_pagada(
    deuda_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    deuda = db.query(Deuda).filter(
        Deuda.id == deuda_id,
        Deuda.usuario_id == current_user.id
    ).first()
    
    if not deuda:
        raise HTTPException(status_code=404, detail="Deuda no encontrada")
    
    deuda.esta_pagada = True
    db.commit()
    
    return {"mensaje": "Deuda marcada como pagada"}
