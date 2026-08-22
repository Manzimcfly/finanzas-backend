from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.orm import relationship, DeclarativeBase
import enum

class Base(DeclarativeBase):
    pass

class TipoTransaccion(str, enum.Enum):
    INGRESO = "ingreso"
    GASTO = "gasto"

class TipoDeuda(str, enum.Enum):
    TARJETA = "tarjeta"
    PRESTAMO = "prestamo"
    HIPOTECA = "hipoteca"
    OTRO = "otro"

class FrecuenciaSuscripcion(str, enum.Enum):
    SEMANAL = "semanal"
    MENSUAL = "mensual"
    TRIMESTRAL = "trimestral"
    ANUAL = "anual"

class TipoCuenta(str, enum.Enum):
    BANCO = "banco"
    TARJETA = "tarjeta"
    EFECTIVO = "efectivo"
    INVERSION = "inversion"
    CRIPTO = "cripto"
    HIPOTECA = "hipoteca"
    PRESTAMO = "prestamo"
    FONDO_EMERGENCIA = "fondo_emergencia"
    NOMINA = "nomina"

class Categoria(Base):
    __tablename__ = "categorias"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, nullable=False)
    tipo = Column(SQLEnum(TipoTransaccion), nullable=False)
    color = Column(String(7), default="#3498db")
    icono = Column(String(50), default="📦")
    
    transacciones = relationship("Transaccion", back_populates="categoria")
    presupuestos = relationship("Presupuesto", back_populates="categoria")

class Transaccion(Base):
    __tablename__ = "transacciones"
    
    id = Column(Integer, primary_key=True, index=True)
    monto = Column(Float, nullable=False)
    descripcion = Column(String(255))
    fecha = Column(DateTime, default=datetime.utcnow)
    tipo = Column(SQLEnum(TipoTransaccion), nullable=False)
    
    categoria_id = Column(Integer, ForeignKey("categorias.id"))
    cuenta_id = Column(Integer, ForeignKey("cuentas.id"), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    es_reembolso = Column(Boolean, default=False)
    
    categoria = relationship("Categoria", back_populates="transacciones")
    cuenta = relationship("Cuenta", back_populates="transacciones")
    usuario = relationship("Usuario", back_populates="transacciones")

class Usuario(Base):
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    nombre_completo = Column(String(200))
    creado_en = Column(DateTime, default=datetime.utcnow)
    activo = Column(Boolean, default=True)
    
    transacciones = relationship("Transaccion", back_populates="usuario")
    presupuestos = relationship("Presupuesto", back_populates="usuario")
    cuentas = relationship("Cuenta", back_populates="usuario", foreign_keys="Cuenta.usuario_id")
    metas = relationship("Meta", back_populates="usuario")
    deudas = relationship("Deuda", back_populates="usuario")
    suscripciones = relationship("Suscripcion", back_populates="usuario")
    alertas = relationship("Alerta", back_populates="usuario")
    tarjetas = relationship("TarjetaCredito", back_populates="usuario")
    categorias_esenciales = relationship("CategoriaEsencial", back_populates="usuario", cascade="all, delete-orphan")
    fondo_movimientos = relationship("FondoEmergenciaMovimiento", back_populates="usuario", cascade="all, delete-orphan")
    cuenta_nomina_id = Column(Integer, ForeignKey("cuentas.id", use_alter=True, ondelete="SET NULL"), nullable=True)

class Presupuesto(Base):
    __tablename__ = "presupuestos"
    
    id = Column(Integer, primary_key=True, index=True)
    limite = Column(Float, nullable=False)
    mes = Column(Integer, nullable=False)
    anio = Column(Integer, nullable=False)
    
    categoria_id = Column(Integer, ForeignKey("categorias.id"))
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    
    categoria = relationship("Categoria", back_populates="presupuestos")
    usuario = relationship("Usuario", back_populates="presupuestos")

class Cuenta(Base):
    __tablename__ = "cuentas"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(SQLEnum(TipoCuenta), nullable=False)
    saldo_actual = Column(Float, default=0.0)
    saldo_inicial = Column(Float, default=0.0)
    tasa_retorno = Column(Float, default=0.0)  # Tasa de retorno anual en %
    moneda = Column(String(3), default="USD")
    banco = Column(String(100), nullable=True)
    ultimo_actualizacion = Column(DateTime, default=datetime.utcnow)
    
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    es_fondo_emergencia = Column(Boolean, default=False)
    usuario = relationship("Usuario", back_populates="cuentas", foreign_keys=[usuario_id])
    transacciones = relationship("Transaccion", back_populates="cuenta")

class Meta(Base):
    __tablename__ = "metas"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    objetivo = Column(Float, nullable=False)
    actual = Column(Float, default=0.0)
    fecha_limite = Column(DateTime, nullable=True)
    completado = Column(Boolean, default=False)
    icono = Column(String(50), default="🎯")
    color = Column(String(7), default="#3498db")
    categoria = Column(String(50), default="general")  # general, emergencia, viaje, vivienda, educacion, otro
    
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    usuario = relationship("Usuario", back_populates="metas")
    movimientos = relationship("MetaMovimiento", back_populates="meta", cascade="all, delete-orphan")

class MetaMovimiento(Base):
    __tablename__ = "meta_movimientos"
    
    id = Column(Integer, primary_key=True, index=True)
    monto = Column(Float, nullable=False)
    tipo = Column(String(20), nullable=False)  # 'agregado' o 'reembolso'
    fecha = Column(DateTime, default=datetime.utcnow)
    
    meta_id = Column(Integer, ForeignKey("metas.id", ondelete="CASCADE"))
    meta = relationship("Meta", back_populates="movimientos")

class FondoEmergenciaMovimiento(Base):
    __tablename__ = "fondo_emergencia_movimientos"
    
    id = Column(Integer, primary_key=True, index=True)
    monto = Column(Float, nullable=False)
    tipo = Column(String(20), nullable=False)  # 'aportacion' o 'retiro'
    fecha = Column(DateTime, default=datetime.utcnow)
    nota = Column(String(255), nullable=True)
    
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    usuario = relationship("Usuario", back_populates="fondo_movimientos")

class Deuda(Base):
    __tablename__ = "deudas"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    tipo = Column(SQLEnum(TipoDeuda), nullable=False)
    monto_original = Column(Float, nullable=False)
    monto_actual = Column(Float, nullable=False)
    tasa_interes = Column(Float, default=0.0)  # Porcentaje anual
    cuota_mensual = Column(Float, nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    esta_pagada = Column(Boolean, default=False)
    
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    usuario = relationship("Usuario", back_populates="deudas")

class Suscripcion(Base):
    __tablename__ = "suscripciones"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    proveedor = Column(String(100), nullable=True)
    monto = Column(Float, nullable=False)
    frecuencia = Column(SQLEnum(FrecuenciaSuscripcion), nullable=False)
    categoria = Column(String(50), nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    proximo_pago = Column(DateTime, nullable=True)
    esta_activa = Column(Boolean, default=True)
    notas = Column(Text, nullable=True)
    
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    usuario = relationship("Usuario", back_populates="suscripciones")

class TarjetaCredito(Base):
    __tablename__ = "tarjetas_credito"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    banco = Column(String(100), nullable=True)
    limite_credito = Column(Float, nullable=False)
    saldo_actual = Column(Float, default=0.0)
    fecha_corte = Column(Integer, default=15)  # Día del mes
    tasa_interes = Column(Float, default=0.0)  # Tasa de interés mensual
    color = Column(String(7), default="#8B5CF6")
    ultimo_actualizacion = Column(DateTime, default=datetime.utcnow)
    
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    usuario = relationship("Usuario", back_populates="tarjetas")

class Alerta(Base):
    __tablename__ = "alertas"
    
    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String(50), nullable=False)  # presupuesto_excedido, suscripcion_proxima, deuda_vencida, gasto_inusual
    titulo = Column(String(200), nullable=False)
    mensaje = Column(Text, nullable=False)
    leida = Column(Boolean, default=False)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    datos_extra = Column(Text, nullable=True)  # JSON con datos adicionales
    
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    usuario = relationship("Usuario", back_populates="alertas")

class CategoriaEsencial(Base):
    __tablename__ = "categorias_esenciales"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=False)
    es_esencial = Column(Boolean, default=False)
    
    usuario = relationship("Usuario")
    categoria = relationship("Categoria")
