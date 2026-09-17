"""Explicit, idempotent fictional demo data. Run: python -m app.seed."""

from .db import Session, WorkspaceRepository
from .models import Workspace, Persona, PersonaRevision, Contact, Draft
from .config import settings
from .schemas import PersonaData
from .providers.mock import fixtures
from .providers.ai import MockAI
from .services.contacts import upsert_search, assess


def seed():
    if settings.people_mode != "mock" or settings.ai_mode != "mock":
        raise SystemExit(
            "Demo seed requires PEOPLE_MODE=mock and AI_MODE=mock. No live data is modified."
        )
    with Session() as db:
        if not db.get(Workspace, settings.workspace_id):
            db.add(Workspace(id=settings.workspace_id, name="Personal workspace"))
            db.flush()
        repo = WorkspaceRepository(db)
        existing = repo.all(Persona, Persona.label == "Investment banking · Demo")
        if existing:
            print("Demo already exists; no duplicate data created.")
            return
        data = PersonaData(
            name="Alex Morgan",
            education="New York University · BSc in Finance, 2024",
            experience="Finance intern at a fictional advisory firm. Assisted with valuation models and industry research.",
            skills="Financial modeling, valuation, Excel, Python",
            sectors="Investment Banking",
            career_goals="Build a career in investment banking and learn from professionals working on M&A transactions.",
            target_regions="New York, London",
            target_roles="Investment Banking Analyst",
            contact_purpose="learn about career paths in investment banking",
        ).model_dump()
        p = repo.add(Persona, label="Investment banking · Demo", data=data)
        repo.add(PersonaRevision, persona_id=p.id, version=1, data=data)
        saved = []
        for item in fixtures()[:3]:
            c = upsert_search(repo, item)
            c.saved = True
            c.tags = ["Demo", "Networking"]
            saved.append(c)
            assess(repo, c, p, "en", MockAI(), "mock")
        for c, point in zip(saved[:2], ["Informational Interview", "Networking"]):
            result = MockAI().complete(
                "generate",
                {
                    "persona": data,
                    "contact": {"title": c.title, "company": c.company},
                    "purpose": data["contact_purpose"],
                    "starting_point": point,
                    "language": "en",
                },
            )
            repo.add(
                Draft,
                contact_id=c.id,
                persona_id=p.id,
                persona_version=1,
                language="en",
                purpose=data["contact_purpose"],
                starting_point=point,
                subject=result["subject"],
                body_html=result["body_html"],
                generation_provider="mock",
            )
        db.commit()
        print("Created 1 fictional persona, 3 fictional saved contacts, 2 mock drafts.")


if __name__ == "__main__":
    seed()
