from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
import csv
import io
from app.core.database import get_db
from app.models.models import Transaccion, Categoria, TipoTransaccion, Usuario
from app.core.auth import get_current_active_user

router = APIRouter()

class TransaccionCreate(BaseModel):
    monto: float = Field(..., gt=0, description="Monto de la transacción")
    descripcion: Optional[str] = None
    tipo: TipoTransaccion
    categoria_id: Optional[int] = None
    fecha: Optional[datetime] = None
    es_reembolso: bool = False

class TransaccionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    monto: float
    descripcion: Optional[str]
    fecha: datetime
    tipo: TipoTransaccion
    categoria_id: Optional[int] = None
    es_reembolso: bool = False

class TransaccionConCategoria(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    monto: float
    descripcion: Optional[str]
    fecha: datetime
    tipo: TipoTransaccion
    categoria_id: Optional[int] = None
    categoria_nombre: Optional[str] = None
    categoria_color: Optional[str] = None
    categoria_icono: Optional[str] = None
    es_reembolso: bool = False

class TransaccionListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    transacciones: List[TransaccionConCategoria]

@router.get("/transacciones", response_model=TransaccionListResponse)
def listar_transacciones(
    skip: int = Query(0, ge=0, description="Cantidad a saltar"),
    limit: int = Query(50, ge=1, le=100, description="Límite de resultados"),
    tipo: Optional[TipoTransaccion] = Query(None, description="Filtrar por tipo"),
    categoria_id: Optional[int] = Query(None, description="Filtrar por categoría"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Filtrar por usuario actual
    query = db.query(Transaccion).filter(Transaccion.usuario_id == current_user.id)
    
    if tipo:
        query = query.filter(Transaccion.tipo == tipo)
    if categoria_id:
        query = query.filter(Transaccion.categoria_id == categoria_id)
    
    total = query.count()
    
    # EAGER LOADING - evita N+1 queries
    transacciones = (
        query
        .options(joinedload(Transaccion.categoria))
        .order_by(Transaccion.fecha.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    # Usar Pydantic para construir respuesta
    from datetime import datetime
    resultados = [
        TransaccionConCategoria(
            id=t.id,
            monto=t.monto,
            descripcion=t.descripcion,
            fecha=t.fecha or datetime.utcnow(),
            tipo=t.tipo,
            categoria_id=t.categoria_id,
            categoria_nombre=t.categoria.nombre if t.categoria else None,
            categoria_color=t.categoria.color if t.categoria else None,
            categoria_icono=t.categoria.icono if t.categoria else None,
            es_reembolso=t.es_reembolso
        )
        for t in transacciones
    ]
    
    return TransaccionListResponse(
        total=total,
        skip=skip,
        limit=limit,
        transacciones=resultados
    )

@router.post("/transacciones", response_model=TransaccionResponse, status_code=201)
def crear_transaccion(
    transaccion: TransaccionCreate, 
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    categoria = None
    if transaccion.categoria_id:
        categoria = db.query(Categoria).filter(Categoria.id == transaccion.categoria_id).first()
        if categoria and transaccion.tipo != categoria.tipo:
            raise HTTPException(
                status_code=400, 
                detail=f"El tipo de transacción '{transaccion.tipo.value}' no coincide con la categoría '{categoria.nombre}' ({categoria.tipo.value})"
            )
    
    nueva = Transaccion(
        monto=transaccion.monto,
        descripcion=transaccion.descripcion,
        tipo=transaccion.tipo,
        categoria_id=transaccion.categoria_id if categoria else None,
        usuario_id=current_user.id,
        fecha=transaccion.fecha or datetime.utcnow(),
        es_reembolso=transaccion.es_reembolso
    )
    
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    
    return TransaccionResponse.model_validate(nueva)

class TransaccionSplit(BaseModel):
    descripcion: str
    tipo: TipoTransaccion = TipoTransaccion.GASTO
    fecha: Optional[datetime] = None
    transacciones: List[TransaccionCreate]

@router.post("/transacciones/dividir", response_model=dict)
def crear_transaccion_dividida(
    transaccion_split: TransaccionSplit,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    if not transaccion_split.transacciones:
        raise HTTPException(status_code=400, detail="Debe incluir al menos una transacción")
    
    resultados = []
    fecha = transaccion_split.fecha or datetime.utcnow()
    
    for t in transaccion_split.transacciones:
        categoria = db.query(Categoria).filter(Categoria.id == t.categoria_id).first()
        if not categoria:
            raise HTTPException(status_code=404, detail=f"Categoría {t.categoria_id} no encontrada")
        
        nueva = Transaccion(
            monto=t.monto,
            descripcion=transaccion_split.descripcion,
            tipo=transaccion_split.tipo,
            categoria_id=t.categoria_id,
            usuario_id=current_user.id,
            fecha=fecha
        )
        db.add(nueva)
        resultados.append(nueva)
    
    db.commit()
    
    return {
        "mensaje": f"Se crearon {len(resultados)} transacciones divididas",
        "transacciones": [TransaccionResponse.model_validate(t).model_dump() for t in resultados]
    }

class TransaccionUpdate(BaseModel):
    monto: Optional[float] = None
    descripcion: Optional[str] = None
    tipo: Optional[TipoTransaccion] = None
    categoria_id: Optional[int] = None
    fecha: Optional[datetime] = None

@router.put("/transacciones/{transaccion_id}", response_model=TransaccionResponse)
def actualizar_transaccion(
    transaccion_id: int,
    transaccion: TransaccionUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    db_transaccion = db.query(Transaccion).filter(
        Transaccion.id == transaccion_id,
        Transaccion.usuario_id == current_user.id
    ).first()
    
    if not db_transaccion:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    if transaccion.monto is not None:
        db_transaccion.monto = transaccion.monto
    if transaccion.descripcion is not None:
        db_transaccion.descripcion = transaccion.descripcion
    if transaccion.tipo is not None:
        db_transaccion.tipo = transaccion.tipo
    if transaccion.categoria_id is not None:
        categoria = db.query(Categoria).filter(Categoria.id == transaccion.categoria_id).first()
        if not categoria:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")
        if transaccion.tipo and transaccion.tipo != categoria.tipo:
            raise HTTPException(
                status_code=400,
                detail=f"El tipo de transacción no coincide con la categoría"
            )
        db_transaccion.categoria_id = transaccion.categoria_id
    if transaccion.fecha is not None:
        db_transaccion.fecha = transaccion.fecha
    
    db.commit()
    db.refresh(db_transaccion)
    
    return TransaccionResponse.model_validate(db_transaccion)

@router.delete("/transacciones/{transaccion_id}")
def eliminar_transaccion(
    transaccion_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    transaccion = db.query(Transaccion).filter(
        Transaccion.id == transaccion_id,
        Transaccion.usuario_id == current_user.id
    ).first()
    
    if not transaccion:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    db.delete(transaccion)
    db.commit()
    
    return {"mensaje": "Transacción eliminada"}

@router.get("/transacciones/resumen", response_model=dict)
def resumen_transacciones(
    mes: Optional[int] = Query(None, ge=1, le=12),
    anio: Optional[int] = Query(None, ge=2020),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Filtrar por usuario actual
    query = db.query(Transaccion).filter(Transaccion.usuario_id == current_user.id)
    
    if mes and anio:
        from datetime import datetime
        fecha_inicio = datetime(anio, mes, 1)
        if mes == 12:
            fecha_fin = datetime(anio + 1, 1, 1)
        else:
            fecha_fin = datetime(anio, mes + 1, 1)
        query = query.filter(Transaccion.fecha >= fecha_inicio, Transaccion.fecha < fecha_fin)
    
    transacciones = query.all()
    
    ingresos = sum(t.monto for t in transacciones if t.tipo == TipoTransaccion.INGRESO)
    gastos = sum(t.monto for t in transacciones if t.tipo == TipoTransaccion.GASTO)
    
    return {
        "periodo": f"{mes}/{anio}" if mes and anio else "total",
        "ingresos": ingresos,
        "gastos": gastos,
        "balance": ingresos - gastos,
        "transacciones_count": len(transacciones)
    }

@router.post("/transacciones/importar")
def importar_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    contenido = file.file.read().decode('utf-8')
    lector = csv.DictReader(io.StringIO(contenido))
    
    resultados = []
    errores = []
    categorias = {c.nombre.lower(): c for c in db.query(Categoria).all()}
    
    for i, fila in enumerate(lector, 1):
        try:
            fecha_str = fila.get('fecha', '').strip()
            monto_str = fila.get('monto', fila.get('amount', '')).strip()
            desc = fila.get('descripcion', fila.get('description', fila.get('concepto', ''))).strip()
            tipo_str = fila.get('tipo', '').strip().lower()
            
            if not monto_str:
                errores.append(f"Fila {i}: Falta monto")
                continue
            
            monto = float(monto_str.replace(',', '').replace('$', ''))
            if monto < 0:
                tipo = TipoTransaccion.GASTO
                monto = abs(monto)
            else:
                tipo = TipoTransaccion.INGRESO
            
            if tipo_str in ['gasto', 'expense', 'debito', 'debit']:
                tipo = TipoTransaccion.GASTO
            elif tipo_str in ['ingreso', 'income', 'credito', 'credit']:
                tipo = TipoTransaccion.INGRESO
            
            fecha = datetime.now()
            if fecha_str:
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']:
                    try:
                        fecha = datetime.strptime(fecha_str, fmt)
                        break
                    except:
                        continue
            
            cat_nombre = desc.lower().split()[0] if desc else 'otro'
            categoria = None
            for cat_nom, cat in categorias.items():
                if cat_nom in cat_nombre or cat_nombre in cat_nom:
                    categoria = cat
                    break
            if not categoria:
                categoria = categorias.get('otro') or categorias.get('general')
            
            if not categoria:
                errores.append(f"Fila {i}: Categoría no encontrada para '{desc}'")
                continue
            
            transaccion = Transaccion(
                monto=monto,
                descripcion=desc,
                tipo=tipo,
                categoria_id=categoria.id,
                usuario_id=current_user.id,
                fecha=fecha
            )
            db.add(transaccion)
            resultados.append(desc)
        except Exception as e:
            errores.append(f"Fila {i}: {str(e)}")
    
    db.commit()
    
    return {
        "importadas": len(resultados),
        "errores": errores[:10],
        "transacciones": resultados[:20]
    }
