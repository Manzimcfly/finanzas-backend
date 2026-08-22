from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.core.database import create_tables
from app.api.categorias import router as router_categorias
from app.api.transacciones import router as router_transacciones
from app.api.auth import router as router_auth
from app.api.presupuestos import router as router_presupuestos
from app.api.inversion import router as router_inversion
from app.api.dashboard import router as router_dashboard
from app.api.deudas import router as router_deudas
from app.api.suscripciones import router as router_suscripciones
from app.api.cuentas_metas import router_cuentas, router_metas
from app.api.exportar_alertas import router as router_exportar
from app.api.tarjetas import router as router_tarjetas

app = FastAPI(
    title="Finanzas App",
    description="Tu asistente personal de finanzas",
    version="1.0.0"
)

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router_auth, prefix="/api", tags=["Autenticación"])
app.include_router(router_categorias, prefix="/api", tags=["Categorias"])
app.include_router(router_transacciones, prefix="/api", tags=["Transacciones"])
app.include_router(router_presupuestos, prefix="/api", tags=["Presupuestos"])
app.include_router(router_inversion, prefix="/api", tags=["Inversión"])
app.include_router(router_dashboard, prefix="/api", tags=["Dashboard"])
app.include_router(router_deudas, prefix="/api", tags=["Deudas"])
app.include_router(router_suscripciones, prefix="/api", tags=["Suscripciones"])
app.include_router(router_cuentas, prefix="/api", tags=["Cuentas"])
app.include_router(router_metas, prefix="/api", tags=["Metas"])
app.include_router(router_exportar, prefix="/api", tags=["Exportar"])
app.include_router(router_tarjetas, prefix="/api", tags=["Tarjetas"])

@app.on_event("startup")
def iniciar_app():
    create_tables()
    print("✓ Base de datos inicializada")

@app.get("/")
def raiz():
    return {
        "mensaje": "Hola, finanzas",
        "app": settings.PROJECT_NAME,
        "version": "1.0.0"
    }

@app.get("/saludo/{nombre}")
def saludar(nombre: str):
    return {"hola": nombre, "mensaje": "Bienvenido a tu app de finanzas"}

@app.get("/doble/{numero}")
def calcular_doble(numero: int):
    return {"numero": numero, "doble": numero * 2}
