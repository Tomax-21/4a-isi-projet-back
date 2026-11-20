from fastapi import FastAPI
from contextlib import asynccontextmanager


from app.database import create_db_and_tables
from app.routers import auth, users, products, closures, menus


@asynccontextmanager
async def lifespan():
    create_db_and_tables()   # exec au démarrage du serv
    yield                    # serv tourne la
             

app = FastAPI()

#@app.on_event("startup")
#def on_startup():
#    create_db_and_tables()




@app.get("/")
async def root():
    return {"message": "Hello World"}


app.include_router(auth.router) #var router de auth
app.include_router(users.router)
app.include_router(products.router)
app.include_router(closures.router)
app.include_router(menus.router)