import pytest

from tp.scripts.detail_progress import counts, pipeline


@pytest.mark.mongo
async def test_progress_matches_parser_queue(storage, clock):
    for lot_id in ("new", "fresh", "stale", "missing"):
        await storage.upsert({"source": "bep", "lot_id": lot_id, "lot_url": "x"})
    await storage.save_detail("fresh", {"Описание": "дом"}, clock.now())
    await storage.save_detail("stale", {"Описание": "дом"}, clock.now())
    await storage.upsert({"source": "bep", "lot_id": "stale", "lot_url": "y"})
    await storage.save_detail("missing", None, clock.now())
    await storage.upsert({"source": "other", "lot_id": "foreign", "lot_url": "x"})
    result = counts(await (await storage.collection.aggregate(pipeline("bep"))).to_list())
    assert result == {"total": 4, "pending": 2, "new": 1, "stale": 1, "checked": 2, "not_found": 1}
    assert result["pending"] == len([lot async for lot in storage.pending_detail()])


def test_empty_collection():
    assert counts([]) == {"total": 0, "pending": 0, "new": 0, "stale": 0, "checked": 0, "not_found": 0}
