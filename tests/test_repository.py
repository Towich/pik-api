from typing import List

import pytest

from bot.models import Flat
from bot.repository import FlatRepository


@pytest.mark.asyncio
async def test_upsert_and_delete(tmp_path):
    """Проверяем insert/update и удаление квартир."""

    import os

    # Минимальные переменные окружения для Settings
    os.environ.setdefault("telegram_token", "dummy")
    os.environ.setdefault("telegram_chat_id", "dummy")

    db_path = tmp_path / "test.db"

    # Создаём репозиторий с временной БД
    repo = FlatRepository()
    repo._settings.database_path = str(db_path)
    await repo.init_db()

    # --- вставляем две квартиры ---
    flats_initial: List[Flat] = [
        Flat(id=1, rooms="studio", price=9_000_000, status="free", url=""),
        Flat(id=2, rooms="1", price=8_500_000, status="reserve", url=""),
    ]
    await repo.upsert_many(flats_initial)

    all_flats = await repo.get_all_flats()
    assert len(all_flats) == 2

    # --- обновляем цену квартиры #1 ---
    flats_updated: List[Flat] = [
        Flat(id=1, rooms="studio", price=8_800_000, status="free", url=""),
    ]
    await repo.upsert_many(flats_updated)

    all_flats = await repo.get_all_flats()
    # Квартира #1 должна обновиться, #2 остаться
    prices = {f.id: f.price for f in all_flats}
    assert prices == {1: 8_800_000, 2: 8_500_000}

    # --- удаляем квартиру #2 ---
    await repo.delete_by_ids([2])
    all_flats = await repo.get_all_flats()
    assert len(all_flats) == 1
    assert all_flats[0].id == 1 