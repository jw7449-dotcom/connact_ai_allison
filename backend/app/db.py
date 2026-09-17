from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from fastapi import HTTPException, Request
from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=(
        {"check_same_thread": False}
        if settings.database_url.startswith("sqlite")
        else {}
    ),
)
if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def foreign_keys(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")


Session = sessionmaker(engine, expire_on_commit=False)


class WorkspaceRepository:
    """The only business-data access boundary. Workspace never comes from a request."""

    def __init__(self, session, workspace_id=settings.workspace_id):
        self.session, self.workspace_id = session, workspace_id

    def query(self, model):
        return select(model).where(model.workspace_id == self.workspace_id)

    def all(self, model, *conditions):
        return self.session.scalars(self.query(model).where(*conditions)).all()

    def get(self, model, id):
        obj = self.session.scalar(self.query(model).where(model.id == id))
        if obj is None:
            raise HTTPException(404, "Record not found in this workspace.")
        return obj

    def add(self, model_cls, **values):
        obj = model_cls(workspace_id=self.workspace_id, **values)
        self.session.add(obj)
        self.session.flush()
        return obj


def get_repo(request: Request):
    from .routers.auth import workspace_for_request
    with Session() as session:
        try:
            yield WorkspaceRepository(session, workspace_for_request(session, request))
            session.commit()
        except Exception:
            session.rollback()
            raise
