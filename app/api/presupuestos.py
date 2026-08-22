from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
from app.core.database import get_db
from app.models.models import Presupuesto, Categoria, Transaccion, TipoTransaccion, Usuario, Meta, CategoriaEsencial, Cuenta, FondoEmergenciaMovimiento
from app.core.auth import get_current_active_user

router = APIRouter()

class CategoriaEsencialConfig(BaseModel):
    categoria_id: int
    es_esencial: bool

class CategoriaEsencialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    categoria_id: int
    es_esencial: bool
    categoria_nombre: Optional[str] = None
    categoria_icono: Optional[str] = None

class ConfiguracionEsencialesResponse(BaseModel):
    configuraciones: List[CategoriaEsencialResponse]
    categorias_sin_configurar: List[dict]

class GastoEsencial(BaseModel):
    nombre: str
    categoria_id: int
    categoria_nombre: str
    categoria_icono: str
    monto_promedio: float
    meses: int
    es_esencial: bool
    color: str

class AnalisisGastosResponse(BaseModel):
    gastos_por_categoria: List[GastoEsencial]
    total_esenciales: float
    total_flexibles: float
    total_gastos: float
    porcentaje_esenciales: float

class FondoMovimientoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    monto: float
    tipo: str
    fecha: datetime
    nota: Optional[str] = None

class FondoEmergenciaResponse(BaseModel):
    gastos_mensuales_promedio: float
    gastos_esenciales_promedio: float
    gastos_flexibles_promedio: float
    fondo_necesario_minimo: float
    fondo_necesario_3_meses: float
    fondo_necesario_6_meses: float
    fondo_necesario_12_meses: float
    meses_objetivo: int
    sugerencias: List[str]
    analisis_gastos: AnalisisGastosResponse
    que_es_fondo_emergencia: str
    como_construirlo: List[str]
    fondo_actual: float
    total_acumulado: float
    total_retirado: float
    cuenta_nombre: Optional[str] = None
    cuenta_banco: Optional[str] = None
    cuenta_tasa_retorno: float = 0.0
    cuenta_rendimiento_anual: float = 0.0
    progreso_porcentaje: float = 0.0
    meta_completada: bool = False
    movimientos: List[FondoMovimientoResponse] = []
    falta_para_meta: float = 0.0

class PresupuestoCreate(BaseModel):
    limite: float = Field(..., gt=0)
    mes: int = Field(..., ge=1, le=12)
    anio: int = Field(..., ge=2020)
    categoria_id: int

class PresupuestoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    limite: float
    mes: int
    anio: int
    categoria_id: int

class PresupuestoConGasto(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    limite: float
    mes: int
    anio: int
    categoria_id: int
    categoria_nombre: Optional[str] = None
    categoria_color: Optional[str] = None
    categoria_icono: Optional[str] = None
    gastado: float = 0.0
    restante: float = 0.0
    porcentaje_usado: float = 0.0

class Resumen502030(BaseModel):
    ingreso_total: float
    necesidades_limite: float
    deseos_limite: float
    ahorro_limite: float
    necesidades_actual: float
    deseos_actual: float
    ahorro_actual: float
    necesidades_restante: float
    deseos_restante: float
    ahorro_restante: float
    recomendaciones: List[str]

@router.get("/presupuestos", response_model=dict)
def listar_presupuestos(
    mes: Optional[int] = Query(None, ge=1, le=12),
    anio: Optional[int] = Query(None, ge=2020),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    query = db.query(Presupuesto).filter(Presupuesto.usuario_id == current_user.id)
    
    if mes:
        query = query.filter(Presupuesto.mes == mes)
    if anio:
        query = query.filter(Presupuesto.anio == anio)
    
    presupuestos = query.all()
    
    resultados = []
    for p in presupuestos:
        # Calcular gasto real en esa categoría
        fecha_inicio = datetime(p.anio, p.mes, 1)
        if p.mes == 12:
            fecha_fin = datetime(p.anio + 1, 1, 1)
        else:
            fecha_fin = datetime(p.anio, p.mes + 1, 1)
        
        gastos = db.query(Transaccion).filter(
            Transaccion.usuario_id == current_user.id,
            Transaccion.categoria_id == p.categoria_id,
            Transaccion.tipo == TipoTransaccion.GASTO,
            Transaccion.fecha >= fecha_inicio,
            Transaccion.fecha < fecha_fin
        ).all()
        
        gastado = sum(g.monto for g in gastos)
        
        resultados.append({
            "id": p.id,
            "limite": p.limite,
            "mes": p.mes,
            "anio": p.anio,
            "categoria_id": p.categoria_id,
            "categoria_nombre": p.categoria.nombre if p.categoria else None,
            "categoria_color": p.categoria.color if p.categoria else None,
            "categoria_icono": p.categoria.icono if p.categoria else None,
            "gastado": gastado,
            "restante": p.limite - gastado,
            "porcentaje_usado": (gastado / p.limite * 100) if p.limite > 0 else 0
        })
    
    return {
        "total": len(resultados),
        "presupuestos": resultados
    }

@router.post("/presupuestos", response_model=PresupuestoResponse, status_code=201)
def crear_presupuesto(
    presupuesto: PresupuestoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Verificar que la categoría existe
    categoria = db.query(Categoria).filter(Categoria.id == presupuesto.categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    
    # Verificar que no exista presupuesto para esa categoría/mes/año
    existente = db.query(Presupuesto).filter(
        Presupuesto.usuario_id == current_user.id,
        Presupuesto.categoria_id == presupuesto.categoria_id,
        Presupuesto.mes == presupuesto.mes,
        Presupuesto.anio == presupuesto.anio
    ).first()
    
    if existente:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un presupuesto para esta categoría en ese mes"
        )
    
    nuevo = Presupuesto(
        limite=presupuesto.limite,
        mes=presupuesto.mes,
        anio=presupuesto.anio,
        categoria_id=presupuesto.categoria_id,
        usuario_id=current_user.id
    )
    
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    
    return PresupuestoResponse.model_validate(nuevo)

@router.get("/presupuestos/resumen-50-30-20", response_model=Resumen502030)
def resumen_50_30_20(
    mes: int = Query(..., ge=1, le=12),
    anio: int = Query(..., ge=2020),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Obtener ingresos del mes
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
    
    # Calcular límites 50/30/20
    necesidades_limite = ingreso_total * 0.50
    deseos_limite = ingreso_total * 0.30
    ahorro_limite = ingreso_total * 0.20
    
    # Obtener categorías del usuario
    categorias_gasto = db.query(Categoria).filter(
        Categoria.tipo == TipoTransaccion.GASTO
    ).all()
    
    # Clasificar gastos por categoría
    gastos_por_categoria = {}
    for t in transacciones:
        if t.tipo == TipoTransaccion.GASTO:
            if t.categoria_id not in gastos_por_categoria:
                gastos_por_categoria[t.categoria_id] = 0
            gastos_por_categoria[t.categoria_id] += t.monto
    
    # Calcular necesidades, deseos y ahorro basado en categorías
    # Necesidades: comida, renta, transporte, servicios
    # Deseos: ocio, entretenimiento, restaurantes
    # Ahorro: lo que sobre o categorías de ahorro
    
    necesidades_categorias = ["comida", "renta", "transporte", "servicio", "luz", "agua", "internet"]
    deseos_categorias = ["ocio", "entretenimiento", "restaurante", "cine", "netflix", "suscripcion"]
    
    necesidades_actual = 0
    deseos_actual = 0
    
    for cat in categorias_gasto:
        if cat.id in gastos_por_categoria:
            monto = gastos_por_categoria[cat.id]
            cat_nombre = cat.nombre.lower()
            
            # Clasificar por nombre de categoría
            if any(n in cat_nombre for n in necesidades_categorias):
                necesidades_actual += monto
            elif any(d in cat_nombre for d in deseos_categorias):
                deseos_actual += monto
    
    # El resto se considera "otros gastos" o falta clasificar
    otros_gastos = sum(gastos_por_categoria.values()) - necesidades_actual - deseos_actual
    if otros_gastos < 0:
        otros_gastos = 0
    
    # Calcular ahorro real (ingreso - todos los gastos)
    gasto_total = sum(gastos_por_categoria.values())
    ahorro_actual = ingreso_total - gasto_total
    
    # Recomendaciones
    recomendaciones = []
    
    if necesidades_actual > necesidades_limite:
        recomendaciones.append(
            f"⚠️ Has gastado ${necesidades_actual:.0f} en necesidades (límite: ${necesidades_limite:.0f}). "
            "Considera reducir gastos en servicios o buscar alternativas más económicas."
        )
    else:
        recomendaciones.append(
            f"✅ Bien! Gastaste ${necesidades_actual:.0f} en necesidades (presupuesto: ${necesidades_limite:.0f})"
        )
    
    if deseos_actual > deseos_limite:
        recomendaciones.append(
            f"⚠️ Has gastado ${deseos_actual:.0f} en deseos (límite: ${deseos_limite:.0f}). "
            "Considera reducir suscripciones o entretenimiento."
        )
    else:
        recomendaciones.append(
            f"✅ Bien! Gastaste ${deseos_actual:.0f} en deseos (presupuesto: ${deseos_limite:.0f})"
        )
    
    if ahorro_actual < ahorro_limite:
        recomendaciones.append(
            f"⚠️ Solo has ahorrado ${ahorro_actual:.0f}. "
            f"El objetivo es ${ahorro_limite:.0f} (20% de tus ingresos). "
            "Intenta reducir gastos discrecionales."
        )
    else:
        recomendaciones.append(
            f"🎉 Excelente! Has ahorrado ${ahorro_actual:.0f} (objetivo: ${ahorro_limite:.0f})"
        )
    
    return Resumen502030(
        ingreso_total=ingreso_total,
        necesidades_limite=necesidades_limite,
        deseos_limite=deseos_limite,
        ahorro_limite=ahorro_limite,
        necesidades_actual=necesidades_actual,
        deseos_actual=deseos_actual,
        ahorro_actual=ahorro_actual,
        necesidades_restante=necesidades_limite - necesidades_actual,
        deseos_restante=deseos_limite - deseos_actual,
        ahorro_restante=ahorro_actual - ahorro_limite,
        recomendaciones=recomendaciones
    )

@router.get("/presupuestos/fondo-emergencia", response_model=FondoEmergenciaResponse)
def calcular_fondo_emergencia(
    mes: Optional[int] = Query(None, ge=1, le=12),
    anio: Optional[int] = Query(None, ge=2020),
    meses_objetivo: int = Query(6, ge=3, le=12),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    if not mes:
        mes = datetime.now().month
    if not anio:
        anio = datetime.now().year
    
    esenciales_keywords = [
        "renta", "hipoteca", "alquiler", "servicio", "luz", "agua", "gas", "internet", 
        "telefono", "comida", "supermercado", "mantenimiento", "salud", "medicamento",
        "transporte", "gasolina", "seguro", "educacion", "prestamo", "deuda"
    ]
    
    flexibles_keywords = [
        "ocio", "entretenimiento", "restaurante", "café", "netflix", "spotify", 
        "amazon", "compras", "ropa", "zapato", "viaje", "vacaciones", "gimnasio",
        "suscripcion", "membresia", "dota", "videojuego", "juego", "hobby"
    ]
    
    prefs_usuario = db.query(CategoriaEsencial).filter(
        CategoriaEsencial.usuario_id == current_user.id
    ).all()
    prefs_dict = {p.categoria_id: p.es_esencial for p in prefs_usuario}
    
    configured_cat_ids = set(prefs_dict.keys())
    
    all_cats = db.query(Categoria).filter(Categoria.tipo == TipoTransaccion.GASTO).all()
    all_cats_dict = {c.id: c for c in all_cats}
    
    gastos_por_categoria = {}
    
    meses_con_datos = set()
    
    for m in range(1, 7):
        mes_calculo = mes - m
        anio_calculo = anio
        if mes_calculo <= 0:
            mes_calculo += 12
            anio_calculo -= 1
        
        fecha_inicio = datetime(anio_calculo, mes_calculo, 1)
        if mes_calculo == 12:
            fecha_fin = datetime(anio_calculo + 1, 1, 1)
        else:
            fecha_fin = datetime(anio_calculo, mes_calculo + 1, 1)
        
        transacciones = db.query(Transaccion).filter(
            Transaccion.usuario_id == current_user.id,
            Transaccion.fecha >= fecha_inicio,
            Transaccion.fecha < fecha_fin,
            Transaccion.tipo == TipoTransaccion.GASTO
        ).all()
        
        if transacciones:
            meses_con_datos.add((anio_calculo, mes_calculo))
        
        for t in transacciones:
            cat_id = t.categoria_id
            if cat_id not in gastos_por_categoria:
                gastos_por_categoria[cat_id] = {
                    "monto": 0,
                    "meses_count": set(),
                    "categoria_nombre": t.categoria.nombre if t.categoria else "Sin categoría",
                    "categoria_icono": t.categoria.icono if t.categoria else "📦",
                    "categoria_color": t.categoria.color if t.categoria else "#888888"
                }
            gastos_por_categoria[cat_id]["monto"] += t.monto
            gastos_por_categoria[cat_id]["meses_count"].add((anio_calculo, mes_calculo))
    
    for cat_id in configured_cat_ids:
        if cat_id not in gastos_por_categoria and cat_id in all_cats_dict:
            cat = all_cats_dict[cat_id]
            gastos_por_categoria[cat_id] = {
                "monto": 0,
                "meses_count": set(),
                "categoria_nombre": cat.nombre,
                "categoria_icono": cat.icono,
                "categoria_color": cat.color
            }
    
    num_meses = len(meses_con_datos) if meses_con_datos else 1
    
    gastos_lista = []
    total_esenciales = 0
    total_flexibles = 0
    total_gastos = 0
    
    for cat_id, data in gastos_por_categoria.items():
        meses_con_gasto = len(data["meses_count"]) if data["meses_count"] else 1
        monto_promedio = data["monto"] / meses_con_gasto if meses_con_gasto > 0 else data["monto"]
        cat_nombre_lower = data["categoria_nombre"].lower()
        
        if cat_id in prefs_dict:
            es_esencial = prefs_dict[cat_id]
        else:
            es_esencial = any(kw in cat_nombre_lower for kw in esenciales_keywords)
        
        es_flexible = any(kw in cat_nombre_lower for kw in flexibles_keywords) and not es_esencial
        
        if es_esencial:
            total_esenciales += monto_promedio
        elif es_flexible:
            total_flexibles += monto_promedio
        else:
            if monto_promedio > 0:
                total_esenciales += monto_promedio * 0.5
                total_flexibles += monto_promedio * 0.5
        
        total_gastos += monto_promedio
        
        gastos_lista.append(GastoEsencial(
            nombre=data["categoria_nombre"],
            categoria_id=cat_id,
            categoria_nombre=data["categoria_nombre"],
            categoria_icono=data["categoria_icono"],
            monto_promedio=monto_promedio,
            meses=meses_con_gasto,
            es_esencial=es_esencial,
            color=data["categoria_color"]
        ))
    
    gastos_lista.sort(key=lambda x: x.monto_promedio, reverse=True)
    
    analisis_gastos = AnalisisGastosResponse(
        gastos_por_categoria=gastos_lista,
        total_esenciales=total_esenciales,
        total_flexibles=total_flexibles,
        total_gastos=total_gastos,
        porcentaje_esenciales=(total_esenciales / total_gastos * 100) if total_gastos > 0 else 0
    )
    
    gastos_esenciales_promedio = total_esenciales
    fondo_3_meses = gastos_esenciales_promedio * 3
    fondo_6_meses = gastos_esenciales_promedio * 6
    fondo_12_meses = gastos_esenciales_promedio * 12
    
    sugerencias = []
    
    if gastos_lista:
        top_gastos = sorted(gastos_lista, key=lambda x: x.monto_promedio, reverse=True)[:5]
        sugerencias.append("📊 Tus gastos más importantes son:")
        for g in top_gastos:
            if g.es_esencial:
                sugerencias.append(f"   {g.categoria_icono} {g.categoria_nombre}: ${g.monto_promedio:,.0f}/mes (Esencial)")
            else:
                sugerencias.append(f"   {g.categoria_icono} {g.categoria_nombre}: ${g.monto_promedio:,.0f}/mes")
    
    sugerencias.append("")
    sugerencias.append(f"💡 Para cubrir {meses_objetivo} meses sin empleo, necesitas ${gastos_esenciales_promedio * meses_objetivo:,.0f}")
    sugerencias.append(f"   Esto equivale a ahorrar ${gastos_esenciales_promedio:,.0f} al mes durante {meses_objetivo} meses")
    
    if total_flexibles > 0:
        reduccion = total_flexibles * 0.5
        sugerencias.append("")
        sugerencias.append(f"✂️ Reduciendo gastos no esenciales a la mitad (${reduccion:,.0f}/mes),")
        sugerencias.append(f"   podrías destinar ${reduccion:,.0f} extra al fondo de emergencia")
    
    sugerencias.append("")
    sugerencias.append("🎯 Estrategia sugerida:")
    sugerencias.append("   1. Primero identifica gastos esenciales que puedas reducir")
    sugerencias.append("   2. Cancela suscripciones no esenciales")
    sugerencias.append("   3. Busca alternativas más económicas para gastos fijos")
    sugerencias.append("   4. Automatiza transferencias a tu cuenta de emergencia")
    
    que_es = (
        "Un fondo de emergencia es dinero que apartas para cubrir tus gastos esenciales "
        "si pierdes tu fuente de ingresos. Debe cubrir: vivienda, servicios básicos, "
        "comida, salud y transporte. NO incluye gastos de entretenimiento, suscripciones "
        "o hobbies. La recomendación estándar es tener 3-6 meses de gastos esenciales."
    )
    
    como_construirlo = [
        "1️⃣ Calcula tus gastos esenciales mensuales (los de abajo marcados como Esencial)",
        f"2️⃣ Multiplica por 3 (mínimo), 6 (recomendado) o 12 meses",
        f"3️⃣ Tu meta: ${gastos_esenciales_promedio * 3:,.0f} (3 meses) / ${gastos_esenciales_promedio * 6:,.0f} (6 meses) / ${gastos_esenciales_promedio * 12:,.0f} (12 meses)",
        "4️⃣ Automatiza transferencias el día de pago",
        "5️⃣ Solo usa el fondo en emergencias reales",
        "6️⃣ Reabastece inmediatamente después de usarlo"
    ]
    
    cuenta_fondo = db.query(Cuenta).filter(
        Cuenta.usuario_id == current_user.id,
        Cuenta.es_fondo_emergencia == True
    ).first()
    
    movimientos = db.query(FondoEmergenciaMovimiento).filter(
        FondoEmergenciaMovimiento.usuario_id == current_user.id
    ).order_by(FondoEmergenciaMovimiento.fecha.desc()).limit(20).all()
    
    total_acumulado = sum(m.monto for m in movimientos if m.tipo == 'aportacion')
    total_retirado = sum(m.monto for m in movimientos if m.tipo == 'retiro')
    
    fondo_actual = cuenta_fondo.saldo_actual if cuenta_fondo else 0.0
    cuenta_nombre = cuenta_fondo.nombre if cuenta_fondo else None
    cuenta_banco = cuenta_fondo.banco if cuenta_fondo else None
    cuenta_tasa = cuenta_fondo.tasa_retorno if cuenta_fondo else 0.0
    cuenta_rendimiento = fondo_actual * (cuenta_tasa / 100) if cuenta_fondo else 0.0
    
    fondo_meta = gastos_esenciales_promedio * meses_objetivo
    progreso_porcentaje = (fondo_actual / fondo_meta * 100) if fondo_meta > 0 else 0.0
    meta_completada = fondo_actual >= fondo_meta
    falta_para_meta = max(0, fondo_meta - fondo_actual)
    
    if meta_completada:
        sugerencias.append("🎉 ¡Felicidades! Has alcanzado tu meta del fondo de emergencia")
        sugerencias.append("💡 Considera invertir este dinero extra en inversiones de largo plazo")
    elif fondo_actual > 0:
        sugerencias.append(f"💰 Ahorrado: ${fondo_actual:,.0f} de ${fondo_meta:,.0f} (necesitas ${falta_para_meta:,.0f} más)")
    
    if total_acumulado > 0:
        sugerencias.append(f"📊 Total aportado: ${total_acumulado:,.0f} en {len([m for m in movimientos if m.tipo == 'aportacion'])} aportaciones")
    
    return FondoEmergenciaResponse(
        gastos_mensuales_promedio=total_gastos,
        gastos_esenciales_promedio=gastos_esenciales_promedio,
        gastos_flexibles_promedio=total_flexibles,
        fondo_necesario_minimo=fondo_3_meses,
        fondo_necesario_3_meses=fondo_3_meses,
        fondo_necesario_6_meses=fondo_6_meses,
        fondo_necesario_12_meses=fondo_12_meses,
        meses_objetivo=meses_objetivo,
        sugerencias=sugerencias,
        analisis_gastos=analisis_gastos,
        que_es_fondo_emergencia=que_es,
        como_construirlo=como_construirlo,
        fondo_actual=fondo_actual,
        total_acumulado=total_acumulado,
        total_retirado=total_retirado,
        cuenta_nombre=cuenta_nombre,
        cuenta_banco=cuenta_banco,
        cuenta_tasa_retorno=cuenta_tasa,
        cuenta_rendimiento_anual=cuenta_rendimiento,
        progreso_porcentaje=min(progreso_porcentaje, 100.0),
        meta_completada=meta_completada,
        movimientos=movimientos,
        falta_para_meta=falta_para_meta
    )

@router.get("/presupuestos/configuracion-esenciales", response_model=ConfiguracionEsencialesResponse)
def get_configuracion_esenciales(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    configs_db = db.query(CategoriaEsencial).filter(
        CategoriaEsencial.usuario_id == current_user.id
    ).all()
    
    configs_dict = {c.categoria_id: c for c in configs_db}
    
    categorias = db.query(Categoria).filter(
        Categoria.tipo == TipoTransaccion.GASTO
    ).all()
    
    configuraciones_resp = []
    categorias_sin_configurar = []
    
    for cat in categorias:
        if cat.id in configs_dict:
            configuraciones_resp.append(CategoriaEsencialResponse(
                id=configs_dict[cat.id].id,
                categoria_id=cat.id,
                es_esencial=configs_dict[cat.id].es_esencial,
                categoria_nombre=cat.nombre,
                categoria_icono=cat.icono
            ))
        else:
            categorias_sin_configurar.append({
                "categoria_id": cat.id,
                "categoria_nombre": cat.nombre,
                "categoria_icono": cat.icono,
                "color": cat.color
            })
    
    return ConfiguracionEsencialesResponse(
        configuraciones=configuraciones_resp,
        categorias_sin_configurar=categorias_sin_configurar
    )

@router.post("/presupuestos/configuracion-esenciales")
def guardar_configuracion_esenciales(
    configuraciones: List[CategoriaEsencialConfig],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    for config in configuraciones:
        existente = db.query(CategoriaEsencial).filter(
            CategoriaEsencial.usuario_id == current_user.id,
            CategoriaEsencial.categoria_id == config.categoria_id
        ).first()
        
        if existente:
            existente.es_esencial = config.es_esencial
        else:
            nueva = CategoriaEsencial(
                usuario_id=current_user.id,
                categoria_id=config.categoria_id,
                es_esencial=config.es_esencial
            )
            db.add(nueva)
    
    db.commit()
    return {"message": "Configuración guardada correctamente"}

class FondoMovimientoCreate(BaseModel):
    monto: float = Field(..., gt=0)
    tipo: str = Field(..., pattern="^(aportacion|retiro)$")
    nota: Optional[str] = None

FondoEmergenciaResponse.model_rebuild()

@router.get("/presupuestos/fondo-emergencia/movimientos", response_model=List[FondoMovimientoResponse])
def listar_movimientos_fondo(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    movimientos = db.query(FondoEmergenciaMovimiento).filter(
        FondoEmergenciaMovimiento.usuario_id == current_user.id
    ).order_by(FondoEmergenciaMovimiento.fecha.desc()).all()
    return movimientos

@router.post("/presupuestos/fondo-emergencia/movimientos", response_model=FondoMovimientoResponse, status_code=201)
def agregar_movimiento_fondo(
    movimiento: FondoMovimientoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    nuevo = FondoEmergenciaMovimiento(
        monto=movimiento.monto,
        tipo=movimiento.tipo,
        nota=movimiento.nota,
        usuario_id=current_user.id
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.delete("/presupuestos/fondo-emergencia/movimientos/{movimiento_id}")
def eliminar_movimiento_fondo(
    movimiento_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    movimiento = db.query(FondoEmergenciaMovimiento).filter(
        FondoEmergenciaMovimiento.id == movimiento_id,
        FondoEmergenciaMovimiento.usuario_id == current_user.id
    ).first()
    
    if not movimiento:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    
    db.delete(movimiento)
    db.commit()
    return {"message": "Movimiento eliminado"}
