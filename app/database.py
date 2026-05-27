import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Sem DATABASE_URL → usa SQLite local (desenvolvimento)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./pgmei.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Railway provê postgres://, SQLAlchemy exige postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
