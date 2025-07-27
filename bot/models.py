from typing import Optional

from pydantic import BaseModel


class Flat(BaseModel):
    """Модель квартиры для внутреннего использования."""

    id: int
    rooms: str
    price: int  # цена в рублях
    status: str
    url: str

    area: Optional[float] = None
    floor: Optional[int] = None 