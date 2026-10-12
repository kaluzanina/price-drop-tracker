
import json
import sqlite3

import pytest
import requests

import main


def test_load_games(tmp_path, monkeypatch):
    config_file = tmp_path / "games.json"
    config_file.write_text(
        json.dumps({"games": [620, 1091500, 620]}),
        encoding="utf-8"
    )

    monkeypatch.setattr(main, "GAMES_FILE", config_file)

    assert main.load_games() == [620, 1091500]


def test_format_price():
    assert main.format_price(1999) == "19.99 PLN"
    assert main.format_price(0) == "0.00 PLN"


def test_fetch_game(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "620": {
                    "success": True,
                    "data": {
                        "name": "Portal 2",
                        "price_overview": {
                            "final": 3999,
                            "currency": "PLN",
                            "discount_percent": 20
                        }
                    }
                }
            }

    def fake_get(url, params, timeout):
        assert params["appids"] == 620
        assert timeout == 15
        return FakeResponse()

    monkeypatch.setattr(main.requests, "get", fake_get)

    game = main.fetch_game(620)

    assert game["name"] == "Portal 2"
    assert game["price"] == 3999
    assert game["currency"] == "PLN"
    assert game["discount"] == 20


def test_fetch_game_missing_price(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "620": {
                    "success": True,
                    "data": {
                        "name": "Portal 2"
                    }
                }
            }

    monkeypatch.setattr(
        main.requests,
        "get",
        lambda *args, **kwargs: FakeResponse()
    )

    with pytest.raises(ValueError, match="Price is not available"):
        main.fetch_game(620)


def test_price_drop_detection(monkeypatch, capsys):
    db = sqlite3.connect(":memory:")
    main.init_database(db)

    monkeypatch.setattr(main, "load_games", lambda: [620])

    prices = iter([4000, 3200])

    def fake_fetch_game(app_id):
        return {
            "app_id": app_id,
            "name": "Portal 2",
            "price": next(prices),
            "currency": "PLN",
            "discount": 20
        }

    monkeypatch.setattr(main, "fetch_game", fake_fetch_game)

    assert main.check_prices(db) == 0
    assert main.check_prices(db) == 0

    output = capsys.readouterr().out

    assert "PRICE DROP!" in output
    assert "20.00%" in output

    rows = db.execute(
        "SELECT price FROM price_history ORDER BY id"
    ).fetchall()

    assert rows == [(4000,), (3200,)]

    db.close()


def test_api_error_handling(monkeypatch):
    db = sqlite3.connect(":memory:")
    main.init_database(db)

    monkeypatch.setattr(main, "load_games", lambda: [620])

    def fake_fetch_game(app_id):
        raise requests.Timeout("API timeout")

    monkeypatch.setattr(main, "fetch_game", fake_fetch_game)

    assert main.check_prices(db) == 1

    db.close()
