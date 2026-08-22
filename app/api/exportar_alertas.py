from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime, timedelta
import csv
import io
from app.core.database import get_db
from app.models.models import Transaccion, Categoria, TipoTransaccion, Usuario, Alerta
from app.core.auth import get_current_active_user
from fastapi.responses import StreamingResponse

router = APIRouter()

# ============ EXPORTACIÓN ============

@router.get("/exportar/csv")
def exportar_csv(
    anio: Optional[int] = Query(None),
    mes: Optional[int] = Query(None),
    tipo: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    query = db.query(Transaccion).filter(Transaccion.usuario_id == current_user.id)
    
    if anio and mes:
        fecha_inicio = datetime(anio, mes, 1)
        if mes == 12:
            fecha_fin = datetime(anio + 1, 1, 1)
        else:
            fecha_fin = datetime(anio, mes + 1, 1)
        query = query.filter(Transaccion.fecha >= fecha_inicio, Transaccion.fecha < fecha_fin)
    
    if tipo:
        query = query.filter(Transaccion.tipo == tipo)
    
    transacciones = query.order_by(Transaccion.fecha.desc()).all()
    
    # Crear CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Fecha", "Tipo", "Monto", "Descripción", "Categoría", "Cuenta"])
    
    for t in transacciones:
        writer.writerow([
            t.id,
            t.fecha.strftime("%Y-%m-%d %H:%M:%S") if t.fecha else "",
            t.tipo.value if t.tipo else "",
            t.monto,
            t.descripcion or "",
            t.categoria.nombre if t.categoria else "",
            t.cuenta.nombre if t.cuenta else ""
        ])
    
    output.seek(0)
    
    filename = f"transacciones_{anio or 'all'}_{mes or 'all'}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/exportar/resumen-mensual")
def exportar_resumen_mensual(
    anio: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Mes", "Ingresos", "Gastos", "Balance", "Ahorro %"])
    
    for mes in range(1, 13):
        fecha_inicio = datetime(anio, mes, 1)
        if mes == 12:
            fecha_fin = datetime(anio + 1, 1, 1)
        else:
            fecha_fin = datetime(anio, mes + 1, 1)
        
        transacciones = db.query(Transaccion).filter(
            Transaccion.usuario_id == current_user.id,
            Transaccion.fecha >= fecha_inicio,
            Transaccion.fecha < fecha_fin
        ).all()
        
        ingresos = sum(t.monto for t in transacciones if t.tipo == TipoTransaccion.INGRESO)
        gastos = sum(t.monto for t in transacciones if t.tipo == TipoTransaccion.GASTO)
        balance = ingresos - gastos
        ahorro_pct = (balance / ingresos * 100) if ingresos > 0 else 0
        
        writer.writerow([
            f"{mes}/{anio}",
            ingresos,
            gastos,
            balance,
            f"{ahorro_pct:.1f}%"
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=resumen_{anio}.csv"}
    )

# ============ ALERTAS ============

class AlertaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo: str
    titulo: str
    mensaje: str
    leida: bool
    fecha_creacion: datetime

@router.get("/alertas", response_model=dict)
def listar_alertas(
    solo_no_leidas: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    query = db.query(Alerta).filter(Alerta.usuario_id == current_user.id)
    
    if solo_no_leidas:
        query = query.filter(Alerta.leida == False)
    
    alertas = query.order_by(Alerta.fecha_creacion.desc()).all()
    
    return {
        "total": len(alertas),
        "no_leidas": len([a for a in alertas if not a.leida]),
        "alertas": [AlertaResponse.model_validate(a) for a in alertas]
    }

@router.patch("/alertas/{alerta_id}/leer")
def marcar_alerta_leida(
    alerta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    alerta = db.query(Alerta).filter(
        Alerta.id == alerta_id,
        Alerta.usuario_id == current_user.id
    ).first()
    
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    
    alerta.leida = True
    db.commit()
    
    return {"mensaje": "Alerta marcada como leída"}

@router.post("/alertas/generar")
def generar_alertas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    from app.models.models import Presupuesto, Suscripcion
    alertas_creadas = []
    
    # 1. Verificar presupuestos excedidos del mes actual
    mes_actual = datetime.now().month
    anio_actual = datetime.now().year
    
    presupuestos = db.query(Presupuesto).filter(
        Presupuesto.usuario_id == current_user.id,
        Presupuesto.mes == mes_actual,
        Presupuesto.anio == anio_actual
    ).all()
    
    for p in presupuestos:
        # Calcular gastado
        fecha_inicio = datetime(anio_actual, mes_actual, 1)
        if mes_actual == 12:
            fecha_fin = datetime(anio_actual + 1, 1, 1)
        else:
            fecha_fin = datetime(anio_actual, mes_actual + 1, 1)
        
        transacciones = db.query(Transaccion).filter(
            Transaccion.usuario_id == current_user.id,
            Transaccion.categoria_id == p.categoria_id,
            Transaccion.tipo == TipoTransaccion.GASTO,
            Transaccion.fecha >= fecha_inicio,
            Transaccion.fecha < fecha_fin
        ).all()
        
        gastado = sum(t.monto for t in transacciones)
        
        if gastado > p.limite:
            # Verificar si ya existe alerta
            existente = db.query(Alerta).filter(
                Alerta.usuario_id == current_user.id,
                Alerta.tipo == "presupuesto_excedido",
                Alerta.datos_extra.contains(str(p.id))
            ).first()
            
            if not existente:
                nueva_alerta = Alerta(
                    tipo="presupuesto_excedido",
                    titulo=f"Presupuesto excedido en {p.categoria.nombre}",
                    mensaje=f"Has gastado ${gastado:.0f} de ${p.limite:.0f}预算",
                    datos_extra=f'{{"presupuesto_id": {p.id}, "gastado": {gastado}, "limite": {p.limite}}}',
                    usuario_id=current_user.id
                )
                db.add(nueva_alerta)
                alertas_creadas.append(nueva_alerta)
    
    # 2. Verificar suscripciones próximas a vencer
    suscripciones = db.query(Suscripcion).filter(
        Suscripcion.usuario_id == current_user.id,
        Suscripcion.esta_activa == True,
        Suscripcion.proximo_pago != None
    ).all()
    
    for s in suscripciones:
        dias_proximo = (s.proximo_pago - datetime.now()).days if s.proximo_pago else 999
        
        if 0 <= dias_proximo <= 7:
            existente = db.query(Alerta).filter(
                Alerta.usuario_id == current_user.id,
                Alerta.tipo == "suscripcion_proxima",
                Alerta.datos_extra.contains(str(s.id))
            ).first()
            
            if not existente:
                nueva_alerta = Alerta(
                    tipo="suscripcion_proxima",
                    titulo=f"Suscripción próxima: {s.nombre}",
                    mensaje=f"${s.monto} se cobrará el {s.proximo_pago.strftime('%d/%m/%Y')}",
                    datos_extra=f'{{"suscripcion_id": {s.id}, "monto": {s.monto}}}',
                    usuario_id=current_user.id
                )
                db.add(nueva_alerta)
                alertas_creadas.append(nueva_alerta)
    
    db.commit()
    
    return {
        "mensaje": f"Se generaron {len(alertas_creadas)} alertas",
        "alertas": [{"tipo": a.tipo, "titulo": a.titulo} for a in alertas_creadas]
    }
