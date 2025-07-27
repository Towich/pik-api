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
                    INSERT INTO flats(id, rooms, price, status, url, area, floor, last_seen)
                    VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        price = excluded.price,
                        status = excluded.status,
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
                        now,
                    ),
                )
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
        """Вернуть все квартиры из таблицы."""

        query = "SELECT id, rooms, price, status, url, area, floor FROM flats"
        async with aiosqlite.connect(self._settings.database_path) as conn:
            cursor = await conn.execute(query)
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