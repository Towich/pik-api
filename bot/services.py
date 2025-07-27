import logging
from typing import Dict, List, Tuple

from bot.models import Flat
from bot.pik_api_client import PIKApiClient
from bot.repository import FlatRepository

logger = logging.getLogger(__name__)


class MonitorService:
    """Отвечает за обновление данных и формирование отчёта."""

    def __init__(self, repo: FlatRepository):
        self._repo = repo

    # --------------------------- utils ---------------------------------

    @staticmethod
    def _is_studio(flat: Flat) -> bool:
        return str(flat.rooms) in {"0", "studio", "студия"}

    @staticmethod
    def _is_one(flat: Flat) -> bool:
        return str(flat.rooms) == "1"

    @staticmethod
    def _price_fmt(price: int) -> str:
        return f"{price / 1_000_000:.2f} млн"

    # -------------------------------------------------------------------

    async def _process_flats(self, new_flats: List[Flat]) -> str:
        """Сравнить `new_flats` с состоянием БД и вернуть отчёт."""

        # Текущее состояние в БД до обновления
        old_flats = await self._repo.get_all_flats()
        old_map: Dict[int, Flat] = {f.id: f for f in old_flats}
        new_map: Dict[int, Flat] = {f.id: f for f in new_flats}

        diff_lines: List[str] = []

        # --- добавленные и удалённые квартиры ----
        added_ids = new_map.keys() - old_map.keys()
        removed_ids = old_map.keys() - new_map.keys()

        for fid in sorted(added_ids):
            f = new_map[fid]
            diff_lines.append(
                f"➕ Добавлена квартира #{f.id}: {self._price_fmt(f.price)}, этаж {f.floor}, статус {f.status}"
            )

        for fid in sorted(removed_ids):
            f = old_map[fid]
            diff_lines.append(
                f"➖ Удалена квартира #{f.id}: была {self._price_fmt(f.price)}, этаж {f.floor}, статус {f.status}"
            )

        # --- изменения параметров ----
        common_ids = new_map.keys() & old_map.keys()
        fields_to_check: Tuple[str, ...] = ("price", "status", "area", "floor")
        for fid in sorted(common_ids):
            old = old_map[fid]
            new = new_map[fid]
            for field in fields_to_check:
                old_val = getattr(old, field)
                new_val = getattr(new, field)
                if old_val != new_val:
                    if field == "price":
                        old_val_fmt = self._price_fmt(old_val)
                        new_val_fmt = self._price_fmt(new_val)
                    else:
                        old_val_fmt = old_val
                        new_val_fmt = new_val
                    diff_lines.append(
                        f"✏️ Квартира #{fid}: {field} {old_val_fmt} → {new_val_fmt}"
                    )

        # --- Обновляем БД свежими данными
        await self._repo.upsert_many(new_flats)

        # --- Статистика для итоговой части
        studio_total = sum(1 for f in new_flats if self._is_studio(f))
        one_total = sum(1 for f in new_flats if self._is_one(f))
        cheapest_prices = sorted(f.price for f in new_flats)[:3]

        summary_lines: List[str] = ["⚡️ Обновление ЖК «Яуза Парк»:"]
        if diff_lines:
            summary_lines.append("Изменения с последней проверки:")
            summary_lines.extend(diff_lines)
        else:
            summary_lines.append("Первая сводка.")

        summary_lines.extend(
            [
                f"Всего студий: {studio_total}",
                f"Всего 1-к.: {one_total}",
                "Три самых дешёвых квартиры:",
                *[
                    f"  #{idx + 1}: {self._price_fmt(price)}"
                    for idx, price in enumerate(cheapest_prices)
                ],
            ]
        )

        return "\n".join(summary_lines)

    # --------------------------- public API ----------------------------

    async def update_from_api(self) -> str:
        """Скачивает данные с API, формирует diff, обновляет БД."""

        async with PIKApiClient() as client:
            new_flats = await client.fetch_flats()
        return await self._process_flats(new_flats)

    async def update_from_list(self, flats: List[Flat]) -> str:
        """То же самое, но принимает готовый список квартир."""

        return await self._process_flats(flats) 