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

    # --- дополнительные поля ---
    location: Optional[int] = None
    type_id: Optional[int] = None
    guid: Optional[str] = None
    bulk_id: Optional[int] = None
    section_id: Optional[int] = None
    sale_scheme_id: Optional[int] = None
    ceiling_height: Optional[float] = None
    is_pre_sale: Optional[bool] = None
    rooms_fact: Optional[int] = None
    number: Optional[str] = None
    number_bti: Optional[str] = None
    number_stage: Optional[int] = None
    min_month_fee: Optional[int] = None
    discount: Optional[int] = None
    has_advertising_price: Optional[int] = None
    has_new_price: Optional[bool] = None
    area_bti: Optional[float] = None
    area_project: Optional[float] = None
    callback: Optional[bool] = None
    kitchen_furniture: Optional[bool] = None
    booking_cost: Optional[int] = None
    compass_angle: Optional[int] = None
    booking_status: Optional[str] = None
    pdf: Optional[str] = None
    is_resell: Optional[bool] = None 