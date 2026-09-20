from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_object_ids, get_current_user
from app.core.db import get_db
from app.models.entities import Channel, Object, RiskCase, User
from app.models.enums import RiskCaseStatus
from app.schemas.schemas import ObjectOut

router = APIRouter(prefix="/objects", tags=["objects"], dependencies=[Depends(get_current_user)])

_OPEN_STATUSES = (RiskCaseStatus.new, RiskCaseStatus.observing, RiskCaseStatus.dispatched)
_PRIORITY_RANK_LABEL = {0: "none", 1: "medium", 2: "high"}


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


@router.get("/tree")
def objects_tree(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Иерархическая схема объектов вместо GPS-карты: организаторы подтвердили, что реальные
    координаты объектов предоставлены не будут никогда (только текущие, теряются при
    демонтаже датчика — тема 14, "Город 8. ДЖКХ.xlsx - Вопросы_нормализованные_и_Ответы.csv")
    и сами рекомендуют схематичное/иерархическое представление вместо реальной карты.

    Дерево строится по Object.parent_id; риск на каждом узле — агрегация открытых риск-кейсов
    (статус не resolved/rejected) по каналам самого объекта и всех его потомков.
    """
    accessible = get_accessible_object_ids(user, db)
    objects = list(db.scalars(select(Object)))
    if accessible is not None:
        objects = [o for o in objects if o.id in accessible]

    priority_rank = case(
        (RiskCase.priority == "high", 2),
        (RiskCase.priority == "medium", 1),
        else_=0,
    )
    own_risk_count = dict(
        db.execute(
            select(Channel.object_id, func.count(RiskCase.id))
            .select_from(RiskCase)
            .join(Channel, Channel.id == RiskCase.channel_id)
            .where(RiskCase.status.in_(_OPEN_STATUSES), Channel.object_id.is_not(None))
            .group_by(Channel.object_id)
        ).all()
    )
    own_priority_rank = dict(
        db.execute(
            select(Channel.object_id, func.max(priority_rank))
            .select_from(RiskCase)
            .join(Channel, Channel.id == RiskCase.channel_id)
            .where(RiskCase.status.in_(_OPEN_STATUSES), Channel.object_id.is_not(None))
            .group_by(Channel.object_id)
        ).all()
    )

    nodes = {
        o.id: {
            "id": o.id,
            "external_id": o.external_id,
            "name": o.name,
            "kind": o.kind,
            "hierarchy_level": o.hierarchy_level,
            "parent_id": o.parent_id,
            "own_open_risk_count": own_risk_count.get(o.id, 0),
            "own_max_priority_rank": own_priority_rank.get(o.id, 0),
            "children": [],
        }
        for o in objects
    }
    roots = []
    for node in nodes.values():
        parent = nodes.get(node["parent_id"])
        (parent["children"] if parent is not None else roots).append(node)

    def aggregate(node: dict) -> None:
        total = node["own_open_risk_count"]
        max_rank = node["own_max_priority_rank"]
        for child in node["children"]:
            aggregate(child)
            total += child["aggregated_open_risk_count"]
            max_rank = max(max_rank, child["aggregated_max_priority_rank"])
        node["aggregated_open_risk_count"] = total
        node["aggregated_max_priority_rank"] = max_rank
        node["aggregated_max_priority"] = _PRIORITY_RANK_LABEL[max_rank]

    for root in roots:
        aggregate(root)

    return {"roots": roots}


@router.get("/{object_id}", response_model=ObjectOut)
def get_object(object_id: int, db: Session = Depends(get_db)) -> Object:
    obj = db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Объект не найден")
    return obj
