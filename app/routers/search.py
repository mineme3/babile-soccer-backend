from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.search import SearchService

router = APIRouter(prefix="/api/v1/search", tags=["Search"])


@router.get("")
async def search(
    q: str = Query("", min_length=2),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db),
):
    svc = SearchService(db)
    return await svc.search_all(q, limit)
