from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from app.core.database import get_db
from app.models.models import Transaccion, Categoria, TipoTransaccion, Usuario, Suscripcion, Meta, Cuenta
from app.core.auth import get_current_active_user

router = APIRouter()

class IndicadorFinanciero(BaseModel):
    label: str
    valor: float
    cambio_porcentual: Optional[float] = None
    estado: str  # positivo, negativo, neutro

class GastoPorCategoria(BaseModel):
    categoria: str
    categoria_color: str
    categoria_icono: str
    total: float
    porcentaje: float

class DatosGrafico(BaseModel):
    etiquetas: List[str]
    valores: List[float]
    colores: List[str]
    iconos: List[str]

class TendenciaMensual(BaseModel):
    mes: str
    ingreso: float
    gasto: float
    balance: float

class DashboardResponse(BaseModel):
    indicadores: List[IndicadorFinanciero]
    gastos_por_categoria: List[GastoPorCategoria]
    grafico_pie: DatosGrafico
    tendencia_mensual: List[TendenciaMensual]
    ultimos_gastos: List[dict]
    cuenta_nomina: Optional[dict] = None

@router.get("/dashboard", response_model=DashboardResponse)
def obtener_dashboard(
    mes: Optional[int] = Query(None, ge=1, le=12),
    anio: Optional[int] = Query(None, ge=2020),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Usar mes/año actual si no se especifica
    if not mes:
        mes = datetime.now().month
    if not anio:
        anio = datetime.now().year
    
    # Obtener transacciones del mes actual
    fecha_inicio = datetime(anio, mes, 1)
    if mes == 12:
        fecha_fin = datetime(anio + 1, 1, 1)
    else:
        fecha_fin = datetime(anio, mes + 1, 1)
    
    transacciones_mes = db.query(Transaccion).filter(
        Transaccion.usuario_id == current_user.id,
        Transaccion.fecha >= fecha_inicio,
        Transaccion.fecha < fecha_fin
    ).all()
    
    # Calcular ingreso, gasto y balance
    # Los reembolsos RESTAN de los gastos (como descuento)
    ingreso_mes = sum(t.monto for t in transacciones_mes if t.tipo == TipoTransaccion.INGRESO)
    
    # Obtener el ID de la categoría "Metas" para excluirla de los gastos
    categoria_metas = db.query(Categoria).filter(Categoria.nombre == "Metas").first()
    categoria_metas_id = categoria_metas.id if categoria_metas else None
    
    # Calcular gastos excluirando transacciones en categoría "Metas" (son ahorros, no gastos reales)
    gasto_mes = sum(t.monto for t in transacciones_mes if t.tipo == TipoTransaccion.GASTO and t.categoria_id != categoria_metas_id)
    # Los reembolsos también reducen los gastos
    gasto_mes -= sum(t.monto for t in transacciones_mes if t.es_reembolso == True)
    
    reembolso_mes = sum(t.monto for t in transacciones_mes if t.es_reembolso == True)
    # Balance incluye los reembolsos como dinero disponible
    balance_mes = ingreso_mes - gasto_mes + reembolso_mes
    
    # Agregar suscripciones activas a los gastos mensuales
    suscripciones_activas = db.query(Suscripcion).filter(
        Suscripcion.usuario_id == current_user.id,
        Suscripcion.esta_activa == True
    ).all()
    
    gasto_suscripciones = 0
    for s in suscripciones_activas:
        if s.frecuencia == 'mensual':
            gasto_suscripciones += s.monto
        elif s.frecuencia == 'anual':
            gasto_suscripciones += s.monto / 12
        elif s.frecuencia == 'semanal':
            gasto_suscripciones += s.monto * 4
    
    # Incluir suscripciones en el total de gastos
    gasto_mes_total = gasto_mes + gasto_suscripciones
    
    # Obtener total ahorrado en metas (no como gasto, pero resta del balance disponible)
    metas = db.query(Meta).filter(Meta.usuario_id == current_user.id).all()
    total_ahorrado_metas = sum(m.actual for m in metas)
    
    # Balance = Ingresos - Gastos (normales) - Suscripciones - Ahorros en metas + Reembolsos
    balance_mes = ingreso_mes - gasto_mes_total - total_ahorrado_metas + reembolso_mes
    
    # Calcular mismo mes del año anterior para comparar
    fecha_inicio_anterior = datetime(anio - 1, mes, 1)
    if mes == 12:
        fecha_fin_anterior = datetime(anio, 1, 1)
    else:
        fecha_fin_anterior = datetime(anio - 1, mes + 1, 1)
    
    transacciones_anterior = db.query(Transaccion).filter(
        Transaccion.usuario_id == current_user.id,
        Transaccion.fecha >= fecha_inicio_anterior,
        Transaccion.fecha < fecha_fin_anterior
    ).all()
    
    ingreso_anterior = sum(t.monto for t in transacciones_anterior if t.tipo == TipoTransaccion.INGRESO)
    reembolso_anterior = sum(t.monto for t in transacciones_anterior if t.es_reembolso == True)
    gasto_anterior = sum(t.monto for t in transacciones_anterior if t.tipo == TipoTransaccion.GASTO) - reembolso_anterior
    
    # Calcular cambios porcentuales
    cambio_ingreso = ((ingreso_mes - ingreso_anterior) / ingreso_anterior * 100) if ingreso_anterior > 0 else None
    cambio_gasto = ((gasto_mes - gasto_anterior) / gasto_anterior * 100) if gasto_anterior > 0 else None
    
    # Indicadores
    indicadores = [
        IndicadorFinanciero(
            label="Ingresos",
            valor=ingreso_mes,
            cambio_porcentual=cambio_ingreso,
            estado="positivo" if cambio_ingreso and cambio_ingreso > 0 else "neutro"
        ),
        IndicadorFinanciero(
            label="Gastos",
            valor=gasto_mes_total,
            cambio_porcentual=cambio_gasto,
            estado="negativo" if cambio_gasto and cambio_gasto > 0 else "positivo"
        ),
        IndicadorFinanciero(
            label="Suscripciones",
            valor=gasto_suscripciones,
            cambio_porcentual=None,
            estado="neutro"
        ),
        IndicadorFinanciero(
            label="Ahorros en Metas",
            valor=total_ahorrado_metas,
            cambio_porcentual=None,
            estado="positivo"
        ),
        IndicadorFinanciero(
            label="Balance",
            valor=balance_mes,
            cambio_porcentual=None,
            estado="positivo" if balance_mes > 0 else "negativo"
        )
    ]
    
    # Gastos por categoría (solo gastos normales, sin reembolsos, sin categoría "Metas")
    gastos_por_categoria = {}
    for t in transacciones_mes:
        if t.tipo == TipoTransaccion.GASTO and not t.es_reembolso and t.categoria_id != categoria_metas_id:
            cat_id = t.categoria_id
            if cat_id not in gastos_por_categoria:
                gastos_por_categoria[cat_id] = {
                    "total": 0,
                    "nombre": t.categoria.nombre if t.categoria else "Sin categoría",
                    "color": t.categoria.color if t.categoria else "#888",
                    "icono": t.categoria.icono if t.categoria else "📦"
                }
            gastos_por_categoria[cat_id]["total"] += t.monto
    
    # Agregar suscripciones como categoría
    if gasto_suscripciones > 0:
        gastos_por_categoria["suscripciones"] = {
            "total": gasto_suscripciones,
            "nombre": "Suscripciones",
            "color": "#8B5CF6",
            "icono": "📱"
        }
    
    # Calcular porcentajes
    resultados_categorias = []
    for cat_id, data in gastos_por_categoria.items():
        porcentaje = (data["total"] / gasto_mes_total * 100) if gasto_mes_total > 0 else 0
        resultados_categorias.append(
            GastoPorCategoria(
                categoria=data["nombre"],
                categoria_color=data["color"],
                categoria_icono=data["icono"],
                total=data["total"],
                porcentaje=porcentaje
            )
        )
    
    # Ordenar por total
    resultados_categorias.sort(key=lambda x: x.total, reverse=True)
    
    # Datos para gráfico de pie
    grafico_pie = DatosGrafico(
        etiquetas=[c.categoria for c in resultados_categorias],
        valores=[c.total for c in resultados_categorias],
        colores=[c.categoria_color for c in resultados_categorias],
        iconos=[c.categoria_icono for c in resultados_categorias]
    )
    
    # Tendencia de los últimos 6 meses
    tendencia_mensual = []
    for m in range(6, 0, -1):
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
        
        trans = db.query(Transaccion).filter(
            Transaccion.usuario_id == current_user.id,
            Transaccion.fecha >= fi,
            Transaccion.fecha < ff
        ).all()
        
        ingreso = sum(t.monto for t in trans if t.tipo == TipoTransaccion.INGRESO)
        reembolsos = sum(t.monto for t in trans if t.es_reembolso == True)
        gasto = sum(t.monto for t in trans if t.tipo == TipoTransaccion.GASTO and t.categoria_id != categoria_metas_id) - reembolsos
        
        tendencia_mensual.append(
            TendenciaMensual(
                mes=f"{mes_anterior}/{anio_anterior}",
                ingreso=ingreso,
                gasto=gasto,
                balance=ingreso - gasto
            )
        )
    
    # Últimos gastos
    ultimos_gastos = []
    gastos_recientes = db.query(Transaccion).filter(
        Transaccion.usuario_id == current_user.id
    ).order_by(Transaccion.fecha.desc()).limit(5).all()
    
    for g in gastos_recientes:
        ultimos_gastos.append({
            "id": g.id,
            "descripcion": g.descripcion or "Sin descripción",
            "monto": g.monto,
            "tipo": g.tipo.value,
            "categoria_id": g.categoria_id,
            "categoria": g.categoria.nombre if g.categoria else "Sin categoría",
            "categoria_icono": g.categoria.icono if g.categoria else "📦",
            "fecha": g.fecha.isoformat() if g.fecha else None
        })
    
    cuenta_nomina_data = None
    if current_user.cuenta_nomina_id:
        cn = db.query(Cuenta).filter(Cuenta.id == current_user.cuenta_nomina_id).first()
        if cn:
            cuenta_nomina_data = {
                "id": cn.id,
                "nombre": cn.nombre,
                "banco": cn.banco,
                "saldo_actual": cn.saldo_actual,
                "moneda": cn.moneda,
            }

    return DashboardResponse(
        indicadores=indicadores,
        gastos_por_categoria=resultados_categorias,
        grafico_pie=grafico_pie,
        tendencia_mensual=tendencia_mensual,
        ultimos_gastos=ultimos_gastos,
        cuenta_nomina=cuenta_nomina_data
    )
