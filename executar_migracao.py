from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, String
import uuid

# Configuração direta do SQLite sem depender de imports externos complexos
SQLALCHEMY_DATABASE_URL = "sqlite:///./painel_despacho.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modelo da Tabela do Painel de Despacho
class ServicoDB(Base):
    __tablename__ = "servicos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    data_registro = Column(String, nullable=False)
    team_viewer = Column(String, nullable=False)
    cliente = Column(String, nullable=False, index=True)
    servico_prestado = Column(String, nullable=False)
    status = Column(String, default="Pendente") 
    tecnico = Column(String, nullable=True)
    observacoes = Column(String, nullable=True)
    numero_os = Column(String, nullable=True)
    status_pagamento = Column(String, nullable=True)
    status_os = Column(String, nullable=True)
    forma_pagamento = Column(String, nullable=True)

print("Iniciando a criação do banco SQLite...")

try:
    Base.metadata.create_all(bind=engine)
    print("[SUCESSO] Banco de dados e tabelas criados com sucesso!")
except Exception as e:
    print(f"[ERRO] Falha ao criar tabelas: {e}")