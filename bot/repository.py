import datetime
from typing import List

import aiosqlite

from bot.config import get_settings
from bot.models import Flat


class FlatRepository:
    """Слой доступа к базе данных."""

    def __init__(self):
        self._settings = get_settings()

    async def init_db(self) -> None:
        """Создать таблицы при первом запуске."""

        async with aiosqlite.connect(self._settings.database_path) as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS flats (
                    id INTEGER PRIMARY KEY,
                    rooms TEXT,
                    price INTEGER,
                    status TEXT,
                    url TEXT,
                    area REAL,
                    floor INTEGER,
                    location INTEGER,
                    type_id INTEGER,
                    guid TEXT,
                    bulk_id INTEGER,
                    section_id INTEGER,
                    sale_scheme_id INTEGER,
                    ceiling_height REAL,
                    is_pre_sale INTEGER,
                    rooms_fact INTEGER,
                    number TEXT,
                    number_bti TEXT,
                    number_stage INTEGER,
                    min_month_fee INTEGER,
                    discount INTEGER,
                    has_advertising_price INTEGER,
                    has_new_price INTEGER,
                    area_bti REAL,
                    area_project REAL,
                    callback INTEGER,
                    kitchen_furniture INTEGER,
                    booking_cost INTEGER,
                    compass_angle INTEGER,
                    booking_status TEXT,
                    pdf TEXT,
                    is_resell INTEGER,
                    last_seen TEXT NOT NULL
                )
                """
            )
            await conn.commit()

    async def upsert_many(self, flats: List[Flat]) -> None:
        """Обновить информацию о квартирах (insert/update)."""

        now = datetime.datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._settings.database_path) as conn:
            for flat in flats:
                await conn.execute(
                    """
                    INSERT INTO flats(
                        id, rooms, price, status, url, area, floor, location, type_id, guid,
                        bulk_id, section_id, sale_scheme_id, ceiling_height, is_pre_sale, rooms_fact,
                        number, number_bti, number_stage, min_month_fee, discount, has_advertising_price,
                        has_new_price, area_bti, area_project, callback, kitchen_furniture, booking_cost,
                        compass_angle, booking_status, pdf, is_resell, last_seen
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        rooms = excluded.rooms,
                        price = excluded.price,
                        status = excluded.status,
                        url = excluded.url,
                        area = excluded.area,
                        floor = excluded.floor,
                        location = excluded.location,
                        type_id = excluded.type_id,
                        guid = excluded.guid,
                        bulk_id = excluded.bulk_id,
                        section_id = excluded.section_id,
                        sale_scheme_id = excluded.sale_scheme_id,
                        ceiling_height = excluded.ceiling_height,
                        is_pre_sale = excluded.is_pre_sale,
                        rooms_fact = excluded.rooms_fact,
                        number = excluded.number,
                        number_bti = excluded.number_bti,
                        number_stage = excluded.number_stage,
                        min_month_fee = excluded.min_month_fee,
                        discount = excluded.discount,
                        has_advertising_price = excluded.has_advertising_price,
                        has_new_price = excluded.has_new_price,
                        area_bti = excluded.area_bti,
                        area_project = excluded.area_project,
                        callback = excluded.callback,
                        kitchen_furniture = excluded.kitchen_furniture,
                        booking_cost = excluded.booking_cost,
                        compass_angle = excluded.compass_angle,
                        booking_status = excluded.booking_status,
                        pdf = excluded.pdf,
                        is_resell = excluded.is_resell,
                        last_seen = excluded.last_seen
                    """,
                    (
                        flat.id,
                        flat.rooms,
                        flat.price,
                        flat.status,
                        flat.url,
                        flat.area,
                        flat.floor,
                        flat.location,
                        flat.type_id,
                        flat.guid,
                        flat.bulk_id,
                        flat.section_id,
                        flat.sale_scheme_id,
                        flat.ceiling_height,
                        flat.is_pre_sale,
                        flat.rooms_fact,
                        flat.number,
                        flat.number_bti,
                        flat.number_stage,
                        flat.min_month_fee,
                        flat.discount,
                        flat.has_advertising_price,
                        flat.has_new_price,
                        flat.area_bti,
                        flat.area_project,
                        flat.callback,
                        flat.kitchen_furniture,
                        flat.booking_cost,
                        flat.compass_angle,
                        flat.booking_status,
                        flat.pdf,
                        flat.is_resell,
                        now,
                    ),
                )
            await conn.commit()

    async def delete_by_ids(self, ids: List[int]) -> None:
        """Удалить квартиры с заданными id из таблицы flats."""

        if not ids:
            return  # Нечего удалять

        placeholders = ",".join("?" * len(ids))
        query = f"DELETE FROM flats WHERE id IN ({placeholders})"

        async with aiosqlite.connect(self._settings.database_path) as conn:
            await conn.execute(query, ids)
            await conn.commit()

    async def select_cheapest(self, rooms: List[str], limit: int = 10) -> List[Flat]:
        placeholders = ",".join("?" * len(rooms))
        query = (
            f"SELECT id, rooms, price, status, url, area, floor "
            f"FROM flats WHERE rooms IN ({placeholders}) "
            f"ORDER BY price ASC LIMIT ?"
        )
        async with aiosqlite.connect(self._settings.database_path) as conn:
            cursor = await conn.execute(query, (*rooms, limit))
            rows = await cursor.fetchall()

        return [
            Flat(
                id=row[0],
                rooms=row[1],
                price=row[2],
                status=row[3],
                url=row[4],
                area=row[5],
                floor=row[6],
            )
            for row in rows
        ]

    async def count_by_rooms(self, rooms: List[str]) -> int:
        placeholders = ",".join("?" * len(rooms))
        query = f"SELECT COUNT(*) FROM flats WHERE rooms IN ({placeholders})"
        async with aiosqlite.connect(self._settings.database_path) as conn:
            cursor = await conn.execute(query, rooms)
            (count,) = await cursor.fetchone()
        return count

    async def get_min_prices(self, rooms: List[str], limit: int = 3) -> List[int]:
        placeholders = ",".join("?" * len(rooms))
        query = (
            f"SELECT price FROM flats WHERE rooms IN ({placeholders}) "
            f"ORDER BY price ASC LIMIT ?"
        )
        async with aiosqlite.connect(self._settings.database_path) as conn:
            cursor = await conn.execute(query, (*rooms, limit))
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_all_flats(self) -> List[Flat]:
        """Вернуть все квартиры из таблицы со всеми колонками."""

        async with aiosqlite.connect(self._settings.database_path) as conn:
            conn.row_factory = aiosqlite.Row  # позволит обращаться к столбцам по имени
            cursor = await conn.execute("SELECT * FROM flats")
            rows = await cursor.fetchall()

        flats: List[Flat] = []
        for row in rows:
            data = dict(row)
            data.pop("last_seen", None)  # это служебное поле, в модели его нет
            flats.append(Flat(**data))

        return flats 