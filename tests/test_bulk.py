import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient

import app as lector
import db


@pytest.fixture
def lib(tmp_path, monkeypatch):
    database = db.get_db(tmp_path / "test.db")
    # db.get_articles_table() only builds the row dataclass for the first
    # database it sees; give this one its own so rows aren't plain dicts.
    database.t.articles.dataclass()
    monkeypatch.setattr(lector, "DB", database)
    # Not entered as a context manager, so startup (TTS model load) never runs.
    client = TestClient(lector.app, follow_redirects=False)

    def add(title, folder=None):
        return db.create_article(database, title=title, markdown=f"# {title}", source_type="paste", folder=folder).id

    def folders():
        return {a.title: a.folder for a in db.list_articles(database)}

    return client, add, folders


def test_move_articles_and_folder_into_target(lib):
    client, add, folders = lib
    a = add("A")
    b = add("B", "Old")
    add("C", "Notes")
    add("D", "Notes/Sub")
    r = client.post("/library/bulk", data={"action": "move", "article_id": [a, b], "folder": ["Notes"], "target": "Archive"})
    assert r.status_code == 303
    assert folders() == {"A": "Archive", "B": "Archive", "C": "Archive/Notes", "D": "Archive/Notes/Sub"}


def test_move_to_no_folder(lib):
    client, add, folders = lib
    a = add("A", "X")
    add("B", "X/Y")
    client.post("/library/bulk", data={"action": "move", "article_id": [a], "folder": ["X/Y"], "target": ""})
    assert folders() == {"A": None, "B": "Y"}


def test_article_inside_selected_folder_keeps_its_place(lib):
    client, add, folders = lib
    c = add("C", "Notes/Sub")
    client.post("/library/bulk", data={"action": "move", "article_id": [c], "folder": ["Notes"], "target": "Archive"})
    assert folders() == {"C": "Archive/Notes/Sub"}


def test_folder_not_moved_into_itself(lib):
    client, add, folders = lib
    add("C", "Notes")
    r = client.post("/library/bulk", data={"action": "move", "folder": ["Notes"], "target": "Notes/Sub"})
    assert "skipped" in r.headers["location"]
    assert folders() == {"C": "Notes"}


def test_delete_articles_and_folders(lib):
    client, add, folders = lib
    a = add("A")
    add("B")
    add("C", "Notes")
    add("D", "Notes/Sub")
    r = client.post("/library/bulk", data={"action": "delete", "article_id": [a], "folder": ["Notes"]})
    assert "Deleted%203%20articles" in r.headers["location"]
    assert folders() == {"B": None}


def test_unknown_action_rejected(lib):
    client, _, _ = lib
    assert client.post("/library/bulk", data={"action": "nope"}).status_code == 400
