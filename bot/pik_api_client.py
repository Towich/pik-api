import logging
from typing import List, Optional

import aiohttp

from bot.config import get_settings
from bot.models import Flat

logger = logging.getLogger(__name__)


class PIKApiClient:
    """Клиент для работы с `api.pik.ru`. Используется как async context manager."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            base_url=self._settings.pik_base_url,
            headers={"User-Agent": "PikYauzaBot/1.0"},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_flats(self) -> List[Flat]:
        """Получить список всех квартир в ЖК «Яуза Парк»."""

        if self._session is None:
            raise RuntimeError("PIKApiClient используется вне контекста 'async with'.")

        url = f"/v1/flat?block_id={self._settings.yauza_block_id}"
        logger.info("GET %s", url)
        async with self._session.get(url, timeout=30) as resp:
            logger.info("%s -> %s", url, resp.status)
            resp.raise_for_status()
            data = await resp.json()

        # API иногда оборачивает данные в словарь
        if isinstance(data, dict):
            # Наиболее вероятные ключи
            for key in ("data", "result", "flats"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break

        flats: List[Flat] = []
        for item in data:
            if not isinstance(item, dict):
                logger.warning("Unexpected item type from API: %s", type(item))
                continue
            flats.append(
                Flat(
                    id=item.get("id"),
                    rooms=str(item.get("rooms")),
                    price=item.get("price", 0),
                    status=item.get("status", "unknown"),
                    url=item.get("url", ""),
                    area=item.get("area"),
                    floor=item.get("floor"),
                    # дополнительные поля
                    location=item.get("location"),
                    type_id=item.get("type_id"),
                    guid=item.get("guid"),
                    bulk_id=item.get("bulk_id"),
                    section_id=item.get("section_id"),
                    sale_scheme_id=item.get("saleSchemeId"),
                    ceiling_height=item.get("ceilingHeight"),
                    is_pre_sale=item.get("isPreSale"),
                    rooms_fact=item.get("rooms_fact"),
                    number=item.get("number"),
                    number_bti=item.get("number_bti"),
                    number_stage=item.get("number_stage"),
                    min_month_fee=item.get("minMonthFee"),
                    discount=item.get("discount"),
                    has_advertising_price=item.get("has_advertising_price"),
                    has_new_price=item.get("hasNewPrice"),
                    area_bti=item.get("area_bti"),
                    area_project=item.get("area_project"),
                    callback=item.get("callback"),
                    kitchen_furniture=item.get("kitchenFurniture"),
                    booking_cost=item.get("bookingCost"),
                    compass_angle=item.get("compass_angle"),
                    booking_status=item.get("bookingStatus"),
                    pdf=item.get("pdf"),
                    is_resell=item.get("isResell"),
                )
            )

        return flats 