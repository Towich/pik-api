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


@pytest.mark.asyncio
async def test_stats_calculation(tmp_path):
    """Проверяем корректность подсчёта статистики."""

    import os

    os.environ.setdefault("telegram_token", "dummy")
    os.environ.setdefault("telegram_chat_id", "dummy")

    db_path = tmp_path / "test.db"

    repo = FlatRepository()
    repo._settings.database_path = str(db_path)
    await repo.init_db()

    service = MonitorService(repo)

    # Тестовые данные с разными типами квартир и статусами
    test_flats = [
        # Студии
        Flat(id=1, rooms="0", price=8_000_000, status="free", url=""),
        Flat(id=2, rooms="studio", price=8_500_000, status="free", url=""),
        Flat(id=3, rooms="студия", price=9_000_000, status="reserve", url=""),
        # 1-комнатные
        Flat(id=4, rooms="1", price=10_000_000, status="free", url=""),
        Flat(id=5, rooms="1", price=11_000_000, status="free", url=""),
        Flat(id=6, rooms="1", price=12_000_000, status="reserve", url=""),
        # 2-комнатные (не должны учитываться)
        Flat(id=7, rooms="2", price=15_000_000, status="free", url=""),
        Flat(id=8, rooms="2", price=16_000_000, status="reserve", url=""),
    ]

    await repo.upsert_many(test_flats)

    stats_text = await service.stats_text()

    # Проверяем, что статистика корректна
    assert "• 🏠 Студии: <b>2</b> свободно (бронь 1)" in stats_text
    assert "• 🚪 1-к.: <b>2</b> свободно (бронь 1)" in stats_text

    # Проверяем, что 2-комнатные не учитываются в статистике
    assert "2-к." not in stats_text 