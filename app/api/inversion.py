from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import datetime
from app.core.database import get_db
from app.models.models import Transaccion, TipoTransaccion, Usuario, Cuenta, FondoEmergenciaMovimiento
from app.core.auth import get_current_active_user

router = APIRouter()

class RecomendacionInversion(BaseModel):
    puede_invertir: bool
    nivel_riesgo: str
    fondo_emergencia_meses: float
    fondo_emergencia_necesario: float
    fondo_emergencia_actual: float
    tiene_deudas: bool
    porcentaje_ahorro: float
    cumplen_prerrequisitos: List[str]
    no_cumplen_prerrequisitos: List[str]
    sugerencias: List[str]
    portafolio_sugerido: dict | None

PORTAFOLIO_SWENSEN = {
    "nombre": "Portafolio Swensen",
    "descripcion": "Portafolio diversificado basado en la estrategia de David Swensen",
    "asignaciones": [
        {"activo": "Acciones USA (VOO/VTI)", "porcentaje": 30, "descripcion": "ETF que replica S&P 500 o total US market"},
        {"activo": "Acciones Internacionales (VXUS)", "porcentaje": 30, "descripcion": "ETF de países desarrollados y emergentes"},
        {"activo": "Bonos de Gobierno (BND)", "porcentaje": 20, "descripcion": "Bonos corporativos de EE.UU."},
        {"activo": "Bienes Raíces (VNQ)", "porcentaje": 15, "descripcion": "ETF de bienes raíces (REITs)"},
        {"activo": "Materias Primas", "porcentaje": 5, "descripcion": "ETF de commodities"}
    ],
    "nota": "Este es un ejemplo educativo. Consulta un asesor financiero."
}

@router.get("/inversion/recomendaciones", response_model=RecomendacionInversion)
def recomendaciones_inversion(
    mes: int = Query(..., ge=1, le=12),
    anio: int = Query(..., ge=2020),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Calcular gastos mensuales promedio
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
    
    ingreso_total = sum(t.monto for t in transacciones if t.tipo == TipoTransaccion.INGRESO)
    gasto_total = sum(t.monto for t in transacciones if t.tipo == TipoTransaccion.GASTO)
    
    # Calcular promedio de gastos de los últimos 3 meses
    meses_pasados = []
    for m in range(1, 4):
        mes_anterior = mes - m
        anio_anterior = anio
        if mes_anterior <= 0:
            mes_anterior += 12
            anio_anterior -= 1
        
        fi = datetime(anio_anterior, mes_anterior, 1)
        if mes_anterior == 12:
            ff = datetime(anio_anterior + 1, 1, 1)
        else:
            ff = datetime(anio_anterior, mes_anterior + 1, 1)
        
        trans_anterior = db.query(Transaccion).filter(
            Transaccion.usuario_id == current_user.id,
            Transaccion.fecha >= fi,
            Transaccion.fecha < ff
        ).all()
        
        gasto_mes = sum(t.monto for t in trans_anterior if t.tipo == TipoTransaccion.GASTO)
        meses_pasados.append(gasto_mes)
    
    gasto_promedio = sum(meses_pasados) / len(meses_pasados) if meses_pasados and sum(meses_pasados) > 0 else gasto_total
    
    # Si no hay gastos registrados, usar el gasto del mes actual como referencia
    if gasto_promedio == 0 and gasto_total > 0:
        gasto_promedio = gasto_total
    
    # Fondo de emergencia necesario (3-6 meses de gastos)
    fondo_emergencia_necesario_min = gasto_promedio * 3
    fondo_emergencia_necesario_max = gasto_promedio * 6
    
    # Calcular ahorro actual (diferencia entre ingreso y gasto)
    ahorro_mensual = ingreso_total - gasto_total
    porcentaje_ahorro = (ahorro_mensual / ingreso_total * 100) if ingreso_total > 0 else 0
    
    # Calcular fondo de emergencia actual:
    # Prioridad 1: cuenta marcada como es_fondo_emergencia
    # Prioridad 2: suma de movimientos de FondoEmergenciaMovimiento
    # Fallback: ahorro acumulado de transacciones
    cuenta_fondo = db.query(Cuenta).filter(
        Cuenta.usuario_id == current_user.id,
        Cuenta.es_fondo_emergencia == True
    ).first()

    if cuenta_fondo:
        fondo_emergencia_actual = cuenta_fondo.saldo_actual
    else:
        movimientos_fondo = db.query(FondoEmergenciaMovimiento).filter(
            FondoEmergenciaMovimiento.usuario_id == current_user.id
        ).all()
        aportaciones = sum(m.monto for m in movimientos_fondo if m.tipo == "aportacion")
        retiros = sum(m.monto for m in movimientos_fondo if m.tipo == "retiro")
        fondo_emergencia_actual = max(0, aportaciones - retiros)

    fondo_emergencia_meses = fondo_emergencia_actual / gasto_promedio if gasto_promedio > 0 else 0
    
    # Evaluar prerrequisitos
    cumplen = []
    no_cumplen = []
    sugerencias = []
    
    # 1. Fondo de emergencia
    if fondo_emergencia_meses >= 3:
        cumple_fondo = True
        cumplen.append(f"Fondo de emergencia: {fondo_emergencia_meses:.1f} meses ✅")
    else:
        cumple_fondo = False
        meses_faltan = 3 - fondo_emergencia_meses
        no_cumplen.append(f"Fondo de emergencia: solo {fondo_emergencia_meses:.1f} meses (necesitas 3-6) ❌")
        sugerencias.append(
            f"💰 Ahorra ${gasto_promedio * 3 - fondo_emergencia_actual:.0f} más para tener 3 meses de emergencia. "
            f"Considera reducir gastos discrecionales."
        )
    
    # 2. Sin deudas (simplificado - en una app real you'd tener modelo Deuda)
    tiene_deudas = False  # Por ahora假设没有债务
    if tiene_deudas:
        no_cumplen.append("Tienes deudas pendientes ❌")
        sugerencias.append("💳 Antes de invertir, enfócate en pagar deudas de alto interés.")
    else:
        cumple_deudas = True
        cumple_deudas_str = "Sin deudas de alto interés ✅"
        if "Sin deudas" not in str(cumplen):
            cumplen.append(cumple_deudas_str)
    
    # 3. Ahorro 20%
    if porcentaje_ahorro >= 20:
        cumple_ahorro = True
        cumplen.append(f"Ahorro: {porcentaje_ahorro:.1f}% ✅")
    else:
        cumple_ahorro = False
        no_cumplen.append(f"Ahorro: solo {porcentaje_ahorro:.1f}% (necesitas 20%+) ❌")
        ahorro_necesario = ingreso_total * 0.20 - ahorro_mensual
        if ahorro_necesario > 0:
            sugerencias.append(
                f"📊 Para alcanzar el 20% de ahorro, necesitas ${ahorro_necesario:.0f} más al mes. "
                f"Reduce gastos en deseos/entretenimiento."
            )
    
    # Determinar si puede invertir
    puede_invertir = cumple_fondo and not tiene_deudas and cumple_ahorro
    
    # Generar recomendaciones
    if puede_invertir:
        nivel_riesgo = "moderado"
        portafolio = PORTAFOLIO_SWENSEN
        sugerencias.append(
            "🎉 ¡Felicidades! Cumples todos los prerrequisitos para comenzar a invertir."
        )
        sugerencias.append(
            "📈 Considera el portafolio Swensen como punto de partida. "
            "Invierte regularmente (dollar-cost averaging) y diversifica."
        )
    else:
        nivel_riesgo = "no recomendado"
        portafolio = None
        if not cumple_fondo:
            sugerencias.append(
                "⚠️ Prioriza construir tu fondo de emergencia antes de pensar en inversiones."
            )
        if tiene_deudas:
            sugerencias.append(
                "💳 Paga tus deudas de alto interés antes de invertir para maximizar retornos."
            )
        if not cumple_ahorro:
            sugerencias.append(
                "💵 Aumenta tu tasa de ahorro al 20% antes de comenzar a invertir."
            )
    
    return RecomendacionInversion(
        puede_invertir=puede_invertir,
        nivel_riesgo=nivel_riesgo,
        fondo_emergencia_meses=fondo_emergencia_meses,
        fondo_emergencia_necesario=fondo_emergencia_necesario_min,
        fondo_emergencia_actual=fondo_emergencia_actual,
        tiene_deudas=tiene_deudas,
        porcentaje_ahorro=porcentaje_ahorro,
        cumplen_prerrequisitos=cumplen,
        no_cumplen_prerrequisitos=no_cumplen,
        sugerencias=sugerencias,
        portafolio_sugerido=portafolio
    )
