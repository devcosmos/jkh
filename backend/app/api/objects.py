from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.entities import Object
from app.schemas.schemas import ObjectOut

router = APIRouter(prefix="/objects", tags=["objects"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ObjectOut])
def list_objects(
    district: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[Object]:
    stmt = select(Object)
    if district:
        stmt = stmt.where(Object.district == district)
    return list(db.scalars(stmt.offset(offset).limit(limit)))


@router.get("/geojson")
def objects_geojson(db: Session = Depends(get_db)) -> dict:
    """Только объекты с проверенной геометрией — раздел 3.2 плана: без выдуманных координат."""
    objects = db.scalars(select(Object).where(Object.geometry_wkt.is_not(None)))
    features = [
        {
            "type": "Feature",
            "properties": {"id": o.id, "name": o.name, "kind": o.kind},
            "geometry_wkt": o.geometry_wkt,
        }
        for o in objects
    ]
    n_total = len(list(db.scalars(select(Object.id))))
    return {
        "type": "FeatureCollection",
        "features": features,
        "n_with_geometry": len(features),
        "n_total_objects": n_total,
    }


@router.get("/{object_id}", response_model=ObjectOut)
def get_object(object_id: int, db: Session = Depends(get_db)) -> Object:
    obj = db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Объект не найден")
    return obj
