from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.user import User, ConnectorProfile  # noqa: E402, F401
from app.models.company import Company  # noqa: E402, F401
from app.models.contact import Contact, ContactCompany, CsvUpload  # noqa: E402, F401
from app.models.search_request import SearchRequest  # noqa: E402, F401
from app.models.match_result import (  # noqa: E402, F401
    IntroMessage,
    IntroRequest,
    MatchResult,
    WarmScore,
)
from app.models.enrichment import EnrichmentCache, UsageLog  # noqa: E402, F401
