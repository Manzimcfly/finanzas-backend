from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    from app.models.models import Base
    Base.metadata.create_all(bind=engine)

    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if 'usuarios' in inspector.get_table_names():
        cols = {c['name'] for c in inspector.get_columns('usuarios')}
        if 'cuenta_nomina_id' not in cols:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE usuarios ADD COLUMN cuenta_nomina_id INTEGER REFERENCES cuentas(id) ON DELETE SET NULL'))
