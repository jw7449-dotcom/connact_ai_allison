from copy import deepcopy

# Entirely fictional fixtures. Reserved .example domains; no real people or email addresses.
PEOPLE = [
    (
        "Olivia Chen",
        "Vice President, Investment Banking",
        "Aster Capital",
        "New York, US",
        "Investment Banking",
        "Columbia University",
    ),
    (
        "James Park",
        "Investment Banking Associate",
        "Northstar Partners",
        "New York, US",
        "Investment Banking",
        "New York University",
    ),
    (
        "Sofia Martinez",
        "Director, Private Equity",
        "Cedar Bridge Equity",
        "London, UK",
        "Private Equity",
        "",
    ),
    (
        "Ethan Brooks",
        "Portfolio Manager",
        "Harbor Asset Management",
        "Boston, US",
        "Asset Management",
        "Boston University",
    ),
    (
        "Amelia Wang",
        "Principal, Venture Capital",
        "Lumen Ventures",
        "San Francisco, US",
        "Venture Capital",
        "",
    ),
    (
        "Daniel Kim",
        "Investment Banking Analyst",
        "Aster Capital",
        "Hong Kong",
        "Investment Banking",
        "University of Hong Kong",
    ),
    (
        "Charlotte Evans",
        "Managing Director, M&A",
        "Northstar Partners",
        "London, UK",
        "Investment Banking",
        "",
    ),
    (
        "Noah Patel",
        "Investment Analyst",
        "Cedar Bridge Equity",
        "Singapore",
        "Private Equity",
        "",
    ),
    (
        "Isabella Rossi",
        "Head of Risk Management",
        "Summit Financial",
        "London, UK",
        "Risk Management",
        "",
    ),
    (
        "Lucas Zhang",
        "Equity Research Analyst",
        "Harbor Asset Management",
        "New York, US",
        "Asset Management",
        "",
    ),
    (
        "Mia Thompson",
        "Vice President, Private Equity",
        "Cedar Bridge Equity",
        "New York, US",
        "Private Equity",
        "",
    ),
    (
        "Oliver Lee",
        "Venture Capital Associate",
        "Lumen Ventures",
        "Singapore",
        "Venture Capital",
        "",
    ),
    (
        "Grace Wilson",
        "Credit Risk Analyst",
        "Summit Financial",
        "Hong Kong",
        "Risk Management",
        "",
    ),
    (
        "Leo Davis",
        "Investment Banking Director",
        "Aster Capital",
        "London, UK",
        "Investment Banking",
        "",
    ),
    (
        "Chloe Liu",
        "Investment Strategist",
        "Harbor Asset Management",
        "Singapore",
        "Asset Management",
        "",
    ),
    (
        "Henry Taylor",
        "Partner, Venture Capital",
        "Lumen Ventures",
        "New York, US",
        "Venture Capital",
        "",
    ),
]


def fixtures():
    return [
        dict(
            provider="mock",
            provider_id=f"demo-{i+1}",
            name=p[0],
            title=p[1],
            company=p[2],
            location=p[3],
            sector=p[4],
            school=p[5],
            profile_url="",
            email="",
            email_status="available" if i % 3 else "unknown",
        )
        for i, p in enumerate(PEOPLE)
    ]


class MockPeople:
    def search(self, filters):
        rows = fixtures()
        for field in ("title", "company", "location", "sector"):
            if filters.get(field):
                rows = [r for r in rows if filters[field].lower() in r[field].lower()]
        if filters.get("keywords"):
            words = filters["keywords"].lower().split()
            rows = [
                r for r in rows if all(w in " ".join(r.values()).lower() for w in words)
            ]
        start = (filters["page"] - 1) * filters["per_page"]
        return {
            "people": deepcopy(rows[start : start + filters["per_page"]]),
            "total": len(rows),
        }

    def enrich(self, contact):
        n = int(contact["provider_id"].split("-")[-1])
        email = (
            contact["name"].lower().replace(" ", ".") + "@demo.example" if n % 3 else ""
        )
        return {
            "email": email,
            "email_status": "mock_available" if email else "unavailable",
        }


class MockPublic:
    def search(self, contact):
        return [
            {
                "provider": "mock",
                "url": "",
                "title": "Fictional public-profile example",
                "snippet": f"{contact['name']} — {contact['title']} at {contact['company']}. Demo fixture, not a verified public source.",
                "kind": "unverified_lead",
            }
        ]
