import pytest
from app import create_app
from app.db import get_db, migrate


@pytest.fixture()
def app(tmp_path):
    app=create_app({"TESTING":True,"SECRET_KEY":"test-secret","DATABASE":str(tmp_path/"test.sqlite3")})
    with app.app_context(): migrate()
    yield app


@pytest.fixture()
def client(app): return app.test_client()


def register(client,email="one@example.com",password="very-secure-password",language="en"):
    with client.session_transaction() as s: s["csrf_token"]="test-csrf"
    response=client.post("/auth/register",data={"csrf_token":"test-csrf","email":email,"password":password,"language":language})
    with client.session_transaction() as s: s["csrf_token"]="test-csrf"
    return response


def api(client,method,path,json=None):
    return client.open(path,method=method,json=json,headers={"X-CSRF-Token":"test-csrf"})


@pytest.fixture()
def user(client):
    register(client)
    return client
