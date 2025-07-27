import logging
from typing import Any, Dict, List

from bot.models import Flat
from bot.pik_api_client import PIKApiClient
from bot.repository import FlatRepository

logger = logging.getLogger(__name__)


class MonitorService:
    """Отвечает за обновление данных и формирование отчёта."""

    def __init__(self, repo: FlatRepository):
        self._repo = repo
        self._last_snapshot: Dict[str, Any] | None = None

    # --------------------------- utils ---------------------------------

    @staticmethod
    def _is_studio(flat: Flat) -> bool:
        return str(flat.rooms) in {"0", "studio", "студия"}

    @staticmethod
    def _is_one(flat: Flat) -> bool:
        return str(flat.rooms) == "1"

    async def _build_snapshot(self) -> Dict[str, Any]:
        studio_total = await self._repo.count_by_rooms(["0", "studio"])
        one_total = await self._repo.count_by_rooms(["1"])
        cheapest = await self._repo.get_min_prices(["0", "studio", "1"], limit=3)
        return {
            "studio_total": studio_total,
            "one_total": one_total,
            "cheapest": cheapest,
        }

    # --------------------------- public API ----------------------------

    async def refresh_and_diff(self) -> str:
        """Обновить данные и вернуть отчёт с изменениями."""

        # 1. Скачиваем свежие данные
        async with PIKApiClient() as client:
            flats = await client.fetch_flats()

        studios: List[Flat] = [f for f in flats if self._is_studio(f)]
        ones: List[Flat] = [f for f in flats if self._is_one(f)]

        await self._repo.upsert_many(studios + ones)

        # 2. Формируем snapshot
        current = await self._build_snapshot()
        diff_lines: List[str] = []

        if self._last_snapshot is None:
            diff_lines.append("Первая сводка.")
        else:
            # сравниваем значения
            if current["studio_total"] != self._last_snapshot["studio_total"]:
                diff_lines.append(
                    f"Изменилось количество студий: {self._last_snapshot['studio_total']} → {current['studio_total']}"
                )
            if current["one_total"] != self._last_snapshot["one_total"]:
                diff_lines.append(
                    f"Изменилось количество 1-к.: {self._last_snapshot['one_total']} → {current['one_total']}"
                )
            # цены
            for idx, (old, new) in enumerate(
                zip(self._last_snapshot["cheapest"], current["cheapest"])
            ):
                if old != new:
                    diff_lines.append(
                        f"Цена #{idx + 1} изменилась: {old / 1_000_000:.2f} → {new / 1_000_000:.2f} млн"
                    )

        self._last_snapshot = current

        # 3. Итоговая сводка
        summary_lines = [
            "\n⚡️ Обновление ЖК «Яуза Парк»:",
            f"Всего студий: {current['studio_total']}",
            f"Всего 1-к.: {current['one_total']}",
            "Три самых дешёвых квартиры:",
            *[
                f"  #{idx + 1}: {price / 1_000_000:.2f} млн"
                for idx, price in enumerate(current["cheapest"])
            ],
        ]

        if diff_lines:
            summary_lines.insert(1, "Изменения с последней проверки:")
            summary_lines[2:2] = diff_lines  # вставка сразу после заголовка

        return "\n".join(summary_lines) 