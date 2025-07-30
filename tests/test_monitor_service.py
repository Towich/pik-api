import pytest

from bot.models import Flat
from bot.repository import FlatRepository
from bot.services import MonitorService


@pytest.mark.asyncio
async def test_monitor_service_diff_and_db_state(tmp_path):
    """Проверяем формирование diff и итоговое состояние БД."""

    import os

    os.environ.setdefault("telegram_token", "dummy")
    os.environ.setdefault("telegram_chat_id", "dummy")

    db_path = tmp_path / "test.db"

    repo = FlatRepository()
    repo._settings.database_path = str(db_path)
    await repo.init_db()

    # Состояние в БД до обновления
    old_flats = [
        Flat(id=1, rooms="studio", price=9_000_000, status="reserve", url=""),
        Flat(id=3, rooms="1", price=7_600_000, status="free", url=""),
    ]
    await repo.upsert_many(old_flats)

    service = MonitorService(repo)

    # Новые данные: #1 изменилась, #2 добавилась, #3 пропала
    new_flats = [
        Flat(id=1, rooms="studio", price=8_000_000, status="free", url=""),
        Flat(id=2, rooms="1", price=7_000_000, status="free", url=""),
    ]

    diff_text = await service.update_from_list(new_flats)

    # Проверяем, что в отчёте есть строки про добавление, изменение и удаление
    assert "➕ Добавлена квартира #2" in diff_text
    assert "✏️ Квартира #1" in diff_text  # изменение параметров
    assert "➖ Удалена квартира #3" in diff_text

    # Финальное состояние БД должно содержать #1 и #2, но не #3
    final_ids = {f.id for f in await repo.get_all_flats()}

    assert final_ids == {1, 2} 