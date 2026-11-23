from fastapi import FastAPI
from contextlib import asynccontextmanager
from pathlib import Path

from app.db.database import create_db_and_tables
from app.routers import auth, users, products, closures, menus, orders
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()   # exec au démarrage du serv
    yield                    # serv tourne la
             
BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(lifespan=lifespan)

#@app.on_event("startup")
#def on_startup():
#    create_db_and_tables()




@app.get("/api")
async def version():
    return {"version": "0.1"}


app.include_router(auth.router) #var router de auth
app.include_router(users.router)
app.include_router(products.router)
app.include_router(closures.router)
app.include_router(menus.router)
app.include_router(orders.router)

@app.get("/")
async def serve_index_page():
    return FileResponse(BASE_DIR / "static" / "index.html")


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
