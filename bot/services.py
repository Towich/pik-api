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

    def _build_stats_lines(self, flats: List[Flat], *, include_links: bool = False) -> List[str]:
        """Сформировать блок статистики и топ-3 цен."""

        studio_free = sum(1 for f in flats if self._is_studio(f) and f.status == "free")
        studio_reserved = sum(1 for f in flats if self._is_studio(f) and f.status != "free")

        one_free = sum(1 for f in flats if self._is_one(f) and f.status == "free")
        one_reserved = sum(1 for f in flats if self._is_one(f) and f.status != "free")

        # Берём объекты, чтобы можно было использовать ссылки при необходимости
        cheapest_studios = (
            sorted(
                (f for f in flats if self._is_studio(f) and f.status == "free"),
                key=lambda x: x.price,
            )[:3]
        )
        cheapest_ones = (
            sorted(
                (f for f in flats if self._is_one(f) and f.status == "free"),
                key=lambda x: x.price,
            )[:3]
        )

        number_emojis = ["1️⃣", "2️⃣", "3️⃣"]

        lines: List[str] = ["\n📊 <b>Статистика</b>"]
        lines.extend(
            [
                f"• 🏠 Студии: <b>{studio_free}</b> свободно (бронь {studio_reserved})",
                f"• 🚪 1-к.: <b>{one_free}</b> свободно (бронь {one_reserved})",
            ]
        )

        if cheapest_studios:
            lines.append("\n💸 <b>Топ-3 дешёвых студий (свободные)</b>")
            for idx, flat in enumerate(cheapest_studios):
                price_part = (
                    f"<a href=\"{flat.url}\">{self._price_fmt(flat.price)}</a>"
                    if include_links and flat.url
                    else self._price_fmt(flat.price)
                )
                lines.append(f"{number_emojis[idx]} {price_part}")

        if cheapest_ones:
            lines.append("\n💸 <b>Топ-3 дешёвых 1-к. (свободные)</b>")
            for idx, flat in enumerate(cheapest_ones):
                price_part = (
                    f"<a href=\"{flat.url}\">{self._price_fmt(flat.price)}</a>"
                    if include_links and flat.url
                    else self._price_fmt(flat.price)
                )
                lines.append(f"{number_emojis[idx]} {price_part}")

        return lines

    async def stats_text(self, *, include_links: bool = False) -> str:
        """Публичный метод: вернуть текст статистики по данным в БД."""

        flats = await self._repo.get_all_flats()
        return "\n".join(self._build_stats_lines(flats, include_links=include_links))

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
            apartment_link = f"<a href=\"{f.url}\">#{f.id}</a>" if f.url else f"#{f.id}"
            room_type = "студия" if self._is_studio(f) else "1-к."
            diff_lines.append(
                f"➕ Добавлена квартира {apartment_link} ({room_type}): {self._price_fmt(f.price)}, этаж {f.floor}, статус {f.status}"
            )

        for fid in sorted(removed_ids):
            f = old_map[fid]
            apartment_link = f"<a href=\"{f.url}\">#{f.id}</a>" if f.url else f"#{f.id}"
            room_type = "студия" if self._is_studio(f) else "1-к."
            diff_lines.append(
                f"➖ Удалена квартира {apartment_link} ({room_type}): была {self._price_fmt(f.price)}, этаж {f.floor}, статус {f.status}"
            )

        # --- физически удаляем отсутствующие квартиры из БД ----
        if removed_ids:
            await self._repo.delete_by_ids(list(removed_ids))

        # --- изменения параметров ----
        common_ids = new_map.keys() & old_map.keys()
        # Проверяем некоторые поля модели Flat
        fields_to_check: Tuple[str, ...] = (
            "price",
            "status",
            "area",
            "floor",
            "rooms",
            "url",
            "location",
            "type_id",
            "guid",
            "bulk_id",
            "section_id",
            "sale_scheme_id",
            "ceiling_height",
            "is_pre_sale",
            "rooms_fact",
            "number",
            "number_bti",
            "number_stage",
            "min_month_fee",
            "discount",
            "has_advertising_price",
            "has_new_price",
            "area_bti",
            "area_project",
            "callback",
            "kitchen_furniture",
            "compass_angle",
            "is_resell",
        )
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
                    
                    # Создаём ссылку на квартиру
                    apartment_link = f"<a href=\"{new.url}\">#{fid}</a>" if new.url else f"#{fid}"
                    room_type = "студия" if self._is_studio(new) else "1-к."
                    diff_lines.append(
                        f"✏️ Квартира {apartment_link} ({room_type}): {field} {old_val_fmt} → {new_val_fmt}"
                    )

        # --- Обновляем БД свежими данными (insert/update)
        await self._repo.upsert_many(new_flats)

        # Если изменений нет – краткое сообщение
        if not diff_lines:
            return "📝 Изменений нет"

        # Иначе формируем подробный отчёт с ссылками
        summary_lines: List[str] = ["⚡️ <b>ЖК «Яуза Парк»</b>"]
        summary_lines.append("\n📝 <b>Изменения с последней проверки:</b>")
        summary_lines.extend(diff_lines)

        # добавляем статистику и топ с ссылками
        summary_lines.extend(self._build_stats_lines(new_flats, include_links=True))

        return "\n".join(summary_lines)

    # --------------------------- public API ----------------------------

    async def update_from_api(self) -> str:
        """Скачивает данные с API, формирует diff, обновляет БД."""

        async with PIKApiClient() as client:
            all_flats = await client.fetch_flats()
            # Фильтруем только студии и 1-комнатные
            new_flats = [f for f in all_flats if self._is_studio(f) or self._is_one(f)]
        return await self._process_flats(new_flats)

    async def update_from_list(self, flats: List[Flat]) -> str:
        """То же самое, но принимает готовый список квартир."""

        # Фильтруем только студии и 1-комнатные
        filtered_flats = [f for f in flats if self._is_studio(f) or self._is_one(f)]
        return await self._process_flats(filtered_flats) 