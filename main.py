from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlite3
import json
import datetime
import os
from typing import List

app = FastAPI(
    title="Painel de Despacho API",
    description="API avançada com controle financeiro por perfil",
    version="3.6.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

def init_db():
    conn = sqlite3.connect("database.db", timeout=10)
    cursor = conn.cursor()
    
    # Cria a tabela base caso não exista
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_os TEXT,
            team_viewer TEXT,
            cliente TEXT,
            servico_prestado TEXT,
            observacoes TEXT,
            tecnico TEXT,
            status TEXT,
            data_registro TEXT
        )
    """)
    
    # Migração automática: Adiciona colunas financeiras se a tabela for antiga
    colunas_necessarias = [
        ("valor", "REAL DEFAULT 0.0"),
        ("forma_pagamento", "TEXT DEFAULT ''"),
        ("faturado", "INTEGER DEFAULT 0")
    ]
    
    cursor.execute("PRAGMA table_info(servicos)")
    colunas_existentes = [col[1] for col in cursor.fetchall()]
    
    for col_nome, col_tipo in colunas_necessarias:
        if col_nome not in colunas_existentes:
            cursor.execute(f"ALTER TABLE servicos ADD COLUMN {col_nome} {col_tipo}")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            acao TEXT,
            data_hora TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def registrar_log(acao: str):
    try:
        conn = sqlite3.connect("database.db", timeout=10)
        cursor = conn.cursor()
        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        cursor.execute("INSERT INTO historico (acao, data_hora) VALUES (?, ?)", (acao, agora))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Erro ao registrar log:", e)

class ServicoCreate(BaseModel):
    numero_os: str = None
    team_viewer: str
    cliente: str
    servico_prestado: str
    observacoes: str = None
    data_registro: str
    valor: float = 0.0
    forma_pagamento: str = "Pix"
    faturado: int = 0

class UpdateStatus(BaseModel):
    status: str

class UpdateObs(BaseModel):
    observacoes: str

class UpdateFaturamento(BaseModel):
    faturado: int


# ==========================================
# WEBSOCKET (Mantido em /ws)
# ==========================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ==========================================
# ROTAS DA API (Agora com prefixo /api)
# ==========================================
@app.get("/api/status")
def read_root():
    return {"Status": "API Operacional com Módulo Financeiro online!"}

@app.get("/api/servicos")
def listar_servicos():
    conn = sqlite3.connect("database.db", timeout=10)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM servicos ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/historico")
def listar_historico():
    conn = sqlite3.connect("database.db", timeout=10)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM historico ORDER BY id DESC LIMIT 50")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/servicos")
async def criar_servico(servico: ServicoCreate):
    conn = sqlite3.connect("database.db", timeout=10)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO servicos (numero_os, team_viewer, cliente, servico_prestado, observacoes, tecnico, status, data_registro, valor, forma_pagamento, faturado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        servico.numero_os or "S/N",
        servico.team_viewer,
        servico.cliente,
        servico.servico_prestado,
        servico.observacoes or "",
        None,
        "Em Andamento",
        servico.data_registro,
        servico.valor,
        servico.forma_pagamento,
        servico.faturado
    ))
    conn.commit()
    conn.close()
    
    registrar_log(f"Nova OS #{servico.numero_os or 'S/N'} criada (R$ {servico.valor:.2f})")
    await manager.broadcast(json.dumps({"acao": "atualizar"}))
    return {"message": "Serviço criado com sucesso!"}

@app.put("/api/servicos/{id}/assumir")
async def assumir_servico(id: int, tecnico: str):
    conn = sqlite3.connect("database.db", timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT numero_os FROM servicos WHERE id = ?", (id,))
    res = cursor.fetchone()
    num_os = res[0] if res else id

    cursor.execute("UPDATE servicos SET tecnico = ?, status = 'Em Andamento' WHERE id = ?", (tecnico, id))
    conn.commit()
    conn.close()
    
    registrar_log(f"{tecnico} assumiu a OS #{num_os}")
    await manager.broadcast(json.dumps({"acao": "atualizar"}))
    return {"message": "Atendimento assumido"}

@app.put("/api/servicos/{id}/status")
async def atualizar_status(id: int, data: UpdateStatus):
    conn = sqlite3.connect("database.db", timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE servicos SET status = ? WHERE id = ?", (data.status, id))
    conn.commit()
    conn.close()
    await manager.broadcast(json.dumps({"acao": "atualizar"}))
    return {"message": "Status atualizado"}

@app.put("/api/servicos/{id}/faturamento")
async def atualizar_faturamento(id: int, data: UpdateFaturamento):
    conn = sqlite3.connect("database.db", timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE servicos SET faturado = ? WHERE id = ?", (data.faturado, id))
    conn.commit()
    conn.close()
    await manager.broadcast(json.dumps({"acao": "atualizar"}))
    return {"message": "Status de faturamento atualizado"}

@app.put("/api/servicos/{id}/observacao")
async def atualizar_observacao(id: int, data: UpdateObs):
    conn = sqlite3.connect("database.db", timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE servicos SET observacoes = ? WHERE id = ?", (data.observacoes, id))
    conn.commit()
    conn.close()
    await manager.broadcast(json.dumps({"acao": "atualizar"}))
    return {"message": "Observação atualizada"}

@app.delete("/api/servicos/{id}")
async def deletar_servico(id: int):
    conn = sqlite3.connect("database.db", timeout=10)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM servicos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    
    registrar_log("Uma Ordem de Serviço foi excluída")
    await manager.broadcast(json.dumps({"acao": "atualizar"}))
    return {"message": "Serviço deletado"}


# ==========================================
# MONTAGEM DA INTERFACE VISUAL (FRONTEND)
# ==========================================
# Garante que a pasta frontend exista para o app não quebrar
os.makedirs("frontend", exist_ok=True)

# Serve os arquivos estáticos na raiz ("/"). DEVE SER A ÚLTIMA ROTA DO CÓDIGO.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")