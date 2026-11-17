import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.database import get_session
from app.main import app

#copy paste from doc : 
#https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/#client-fixture
#Client Fixture


@pytest.fixture(name="session")
def session_fixture():
    #nouvelle bd differente de celle de prod
    engine = create_engine(
        "sqlite://", #uniquement en memoire, pas de fichier
        connect_args={"check_same_thread": False}, # ok pour plusieurs thread
        poolclass=StaticPool, #tt le monde sur la meme base. snn, tous les tests auraient une nouvelle bdd vide
    )
    SQLModel.metadata.create_all(engine) #cree table
    with Session(engine) as session: #nouvelle session
        yield session  #"yield" = on donne la session au test, puis le test s'exécute.
                        # Quand il est fini, le code reprend ici et ferme la session.


#faux client
@pytest.fixture(name="client")
def client_fixture(session):
    #on change le get sessison, snn il ouvrirait la vrai db
    app.dependency_overrides[get_session] = lambda: session

    #pareil
    #def get_test_session():
    #   return session
    #app.dependency_overrides[get_session] = get_test_session
    
    
    #nouveau client
    #yield = on attend
    yield TestClient(app)

    #on suppr notre override pour reprendre comme avant qd on a fini
    app.dependency_overrides.clear()