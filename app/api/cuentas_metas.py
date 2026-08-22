from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.core.database import get_db
from app.models.models import Cuenta, TipoCuenta, Meta, MetaMovimiento, Usuario
from app.core.auth import get_current_active_user

router_cuentas = APIRouter()
router_metas = APIRouter()

# ============ CUENTAS ============

class CuentaCreate(BaseModel):
    nombre: str
    tipo: TipoCuenta
    saldo_inicial: float = 0.0
    tasa_retorno: float = 0.0
    moneda: str = "USD"
    banco: Optional[str] = None
    es_fondo_emergencia: bool = False

class CuentaUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[TipoCuenta] = None
    banco: Optional[str] = None
    saldo_actual: Optional[float] = None
    saldo_inicial: Optional[float] = None
    tasa_retorno: Optional[float] = None
    es_fondo_emergencia: Optional[bool] = None
    moneda: Optional[str] = None

class CuentaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    tipo: TipoCuenta
    saldo_actual: float
    saldo_inicial: float
    tasa_retorno: float
    moneda: str
    banco: Optional[str]
    ultimo_actualizacion: datetime
    rendimiento_anual: Optional[float] = None
    es_fondo_emergencia: bool = False

@router_cuentas.get("/cuentas", response_model=dict)
def listar_cuentas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    cuentas = db.query(Cuenta).filter(Cuenta.usuario_id == current_user.id).all()
    cuentas_con_rendimiento = []
    for c in cuentas:
        cuenta_data = CuentaResponse.model_validate(c)
        cuenta_data.rendimiento_anual = c.saldo_actual * (c.tasa_retorno / 100)
        cuentas_con_rendimiento.append(cuenta_data)
    return {
        "total": len(cuentas),
        "cuentas": cuentas_con_rendimiento
    }

@router_cuentas.post("/cuentas", response_model=CuentaResponse, status_code=201)
def crear_cuenta(
    cuenta: CuentaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    if cuenta.es_fondo_emergencia:
        db.query(Cuenta).filter(
            Cuenta.usuario_id == current_user.id,
            Cuenta.es_fondo_emergencia == True
        ).update({"es_fondo_emergencia": False})
    
    nueva = Cuenta(
        nombre=cuenta.nombre,
        tipo=cuenta.tipo,
        saldo_inicial=cuenta.saldo_inicial,
        saldo_actual=cuenta.saldo_inicial,
        tasa_retorno=cuenta.tasa_retorno,
        moneda=cuenta.moneda,
        banco=cuenta.banco,
        es_fondo_emergencia=cuenta.es_fondo_emergencia,
        usuario_id=current_user.id
    )
    db.add(nueva)
    db.flush()

    if cuenta.tipo == TipoCuenta.NOMINA:
        current_user.cuenta_nomina_id = nueva.id
        db.commit()
    else:
        db.commit()
    db.refresh(nueva)
    return CuentaResponse.model_validate(nueva)

@router_cuentas.get("/cuentas/resumen", response_model=dict)
def resumen_cuentas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    cuentas = db.query(Cuenta).filter(Cuenta.usuario_id == current_user.id).all()
    
    total = sum(c.saldo_actual for c in cuentas)
    por_tipo = {}
    por_moneda = {}
    rendimiento_total = sum(c.saldo_actual * (c.tasa_retorno / 100) for c in cuentas)
    
    for c in cuentas:
        por_tipo[c.tipo.value] = por_tipo.get(c.tipo.value, 0) + c.saldo_actual
        por_moneda[c.moneda] = por_moneda.get(c.moneda, 0) + c.saldo_actual
    
    return {
        "total": total,
        "cantidad_cuentas": len(cuentas),
        "por_tipo": por_tipo,
        "por_moneda": por_moneda,
        "rendimiento_anual_total": rendimiento_total,
        "rendimiento_mensual_total": rendimiento_total / 12
    }

@router_cuentas.patch("/cuentas/{cuenta_id}", response_model=CuentaResponse)
def actualizar_saldo_cuenta(
    cuenta_id: int,
    cambios: CuentaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    cuenta = db.query(Cuenta).filter(
        Cuenta.id == cuenta_id,
        Cuenta.usuario_id == current_user.id
    ).first()

    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")

    datos = cambios.model_dump(exclude_unset=True)
    saldo_anterior = float(cuenta.saldo_actual or 0)

    if datos.get("es_fondo_emergencia") is True:
        db.query(Cuenta).filter(
            Cuenta.usuario_id == current_user.id,
            Cuenta.es_fondo_emergencia == True,
            Cuenta.id != cuenta_id
        ).update({"es_fondo_emergencia": False})

    for campo, valor in datos.items():
        setattr(cuenta, campo, valor)

    if cuenta.tipo == TipoCuenta.NOMINA and current_user.cuenta_nomina_id != cuenta_id:
        current_user.cuenta_nomina_id = cuenta_id

    cuenta.ultimo_actualizacion = datetime.now()
    db.flush()

    delta = cuenta.saldo_actual - saldo_anterior
    if cuenta.tipo == TipoCuenta.NOMINA and abs(delta) > 0.005:
        from app.models.models import Transaccion, TipoTransaccion
        txn = Transaccion(
            usuario_id=current_user.id,
            cuenta_id=cuenta_id,
            categoria_id=None,
            tipo=TipoTransaccion.INGRESO if delta > 0 else TipoTransaccion.GASTO,
            monto=abs(delta),
            descripcion='Ajuste nomina',
            fecha=datetime.now(),
        )
        db.add(txn)

    db.commit()
    db.refresh(cuenta)

    respuesta = CuentaResponse.model_validate(cuenta)
    respuesta.rendimiento_anual = cuenta.saldo_actual * (cuenta.tasa_retorno / 100)
    return respuesta

@router_cuentas.delete("/cuentas/{cuenta_id}")
def eliminar_cuenta(
    cuenta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    cuenta = db.query(Cuenta).filter(
        Cuenta.id == cuenta_id,
        Cuenta.usuario_id == current_user.id
    ).first()
    
    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    
    if current_user.cuenta_nomina_id == cuenta_id:
        current_user.cuenta_nomina_id = None

    db.delete(cuenta)
    db.commit()

    return {"mensaje": "Cuenta eliminada"}

class TransferenciaCreate(BaseModel):
    cuenta_origen_id: int
    cuenta_destino_id: int
    monto: float
    descripcion: Optional[str] = None

@router_cuentas.post("/cuentas/transferir")
def transferir_entre_cuentas(
    transferencia: TransferenciaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    cuenta_origen = db.query(Cuenta).filter(
        Cuenta.id == transferencia.cuenta_origen_id,
        Cuenta.usuario_id == current_user.id
    ).first()
    
    cuenta_destino = db.query(Cuenta).filter(
        Cuenta.id == transferencia.cuenta_destino_id,
        Cuenta.usuario_id == current_user.id
    ).first()
    
    if not cuenta_origen:
        raise HTTPException(status_code=404, detail="Cuenta de origen no encontrada")
    if not cuenta_destino:
        raise HTTPException(status_code=404, detail="Cuenta de destino no encontrada")
    if cuenta_origen.saldo_actual < transferencia.monto:
        raise HTTPException(status_code=400, detail="Saldo insuficiente")
    
    cuenta_origen.saldo_actual -= transferencia.monto
    cuenta_destino.saldo_actual += transferencia.monto
    cuenta_origen.ultimo_actualizacion = datetime.now()
    cuenta_destino.ultimo_actualizacion = datetime.now()
    
    db.commit()
    
    return {
        "mensaje": "Transferencia exitosa",
        "cuenta_origen": cuenta_origen.nombre,
        "cuenta_destino": cuenta_destino.nombre,
        "monto": transferencia.monto,
        "nuevo_saldo_origen": cuenta_origen.saldo_actual,
        "nuevo_saldo_destino": cuenta_destino.saldo_actual
    }

# ============ METAS ============

class MetaCreate(BaseModel):
    nombre: str
    objetivo: float
    fecha_limite: Optional[datetime] = None
    icono: str = "🎯"
    color: str = "#3498db"
    categoria: str = "general"

class MetaUpdate(BaseModel):
    nombre: Optional[str] = None
    objetivo: Optional[float] = None
    fecha_limite: Optional[datetime] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    categoria: Optional[str] = None

class MetaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    objetivo: float
    actual: float
    fecha_limite: Optional[datetime]
    completado: bool
    icono: str
    color: str
    categoria: str = "general"

@router_metas.get("/metas", response_model=dict)
def listar_metas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    metas = db.query(Meta).filter(Meta.usuario_id == current_user.id).all()
    
    resultados = []
    for m in metas:
        porcentaje = (m.actual / m.objetivo * 100) if m.objetivo > 0 else 0
        resultados.append({
            **MetaResponse.model_validate(m).model_dump(),
            "porcentaje": porcentaje,
            "restante": m.objetivo - m.actual if not m.completado else 0
        })
    
    return {
        "total": len(resultados),
        "metas": resultados
    }

@router_metas.post("/metas", response_model=MetaResponse, status_code=201)
def crear_meta(
    meta: MetaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    nueva = Meta(
        nombre=meta.nombre,
        objetivo=meta.objetivo,
        actual=0,
        fecha_limite=meta.fecha_limite,
        icono=meta.icono,
        color=meta.color,
        categoria=meta.categoria,
        usuario_id=current_user.id
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return MetaResponse.model_validate(nueva)

@router_metas.put("/metas/{meta_id}", response_model=MetaResponse)
def actualizar_meta(
    meta_id: int,
    meta: MetaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    db_meta = db.query(Meta).filter(
        Meta.id == meta_id,
        Meta.usuario_id == current_user.id
    ).first()
    
    if not db_meta:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    
    if meta.nombre is not None:
        db_meta.nombre = meta.nombre
    if meta.objetivo is not None:
        db_meta.objetivo = meta.objetivo
    if meta.fecha_limite is not None:
        db_meta.fecha_limite = meta.fecha_limite
    if meta.icono is not None:
        db_meta.icono = meta.icono
    if meta.color is not None:
        db_meta.color = meta.color
    if meta.categoria is not None:
        db_meta.categoria = meta.categoria
    
    db.commit()
    db.refresh(db_meta)
    return MetaResponse.model_validate(db_meta)

@router_metas.delete("/metas/{meta_id}")
def eliminar_meta(
    meta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    meta = db.query(Meta).filter(
        Meta.id == meta_id,
        Meta.usuario_id == current_user.id
    ).first()
    
    if not meta:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    
    db.delete(meta)
    db.commit()
    
    return {"mensaje": "Meta eliminada"}

@router_metas.patch("/metas/{meta_id}/agregar-ahorro")
def agregar_a_meta(
    meta_id: int,
    monto: float,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    meta = db.query(Meta).filter(
        Meta.id == meta_id,
        Meta.usuario_id == current_user.id
    ).first()
    
    if not meta:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    
    tipo_movimiento = "agregado" if monto > 0 else "reembolso"
    
    meta.actual += monto
    
    if meta.actual >= meta.objetivo:
        meta.completado = True
    else:
        meta.completado = False
    
    movimiento = MetaMovimiento(
        monto=abs(monto),
        tipo=tipo_movimiento,
        meta_id=meta_id
    )
    db.add(movimiento)
    db.commit()
    db.refresh(movimiento)
    
    return {
        "mensaje": "Ahorro agregado",
        "meta_actual": meta.actual,
        "meta_objetivo": meta.objetivo,
        "completado": meta.completado,
        "movimiento": {
            "id": movimiento.id,
            "monto": movimiento.monto,
            "tipo": movimiento.tipo,
            "fecha": movimiento.fecha
        }
    }

@router_metas.get("/metas/{meta_id}/movimientos", response_model=dict)
def listar_movimientos(
    meta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    meta = db.query(Meta).filter(
        Meta.id == meta_id,
        Meta.usuario_id == current_user.id
    ).first()
    
    if not meta:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    
    movimientos = db.query(MetaMovimiento).filter(
        MetaMovimiento.meta_id == meta_id
    ).order_by(MetaMovimiento.fecha.desc()).all()
    
    return {
        "movimientos": [
            {
                "id": m.id,
                "monto": m.monto,
                "tipo": m.tipo,
                "fecha": m.fecha.isoformat() if m.fecha else None
            }
            for m in movimientos
        ]
    }

@router_metas.get("/metas/progreso", response_model=dict)
def progreso_metas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    metas = db.query(Meta).filter(
        Meta.usuario_id == current_user.id,
        Meta.completado == False
    ).all()
    
    total_objetivo = sum(m.objetivo for m in metas)
    total_actual = sum(m.actual for m in metas)
    progreso_global = (total_actual / total_objetivo * 100) if total_objetivo > 0 else 0
    
    return {
        "total_objetivo": total_objetivo,
        "total_actual": total_actual,
        "progreso_global": progreso_global,
        "metas_por_completar": len(metas)
    }
