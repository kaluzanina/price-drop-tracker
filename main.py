
import json
import sqlite3
import sys

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent

GAMES_FILE = BASE_DIR / "games.json"
DATABASE_FILE = BASE_DIR / "prices.db"

STEAM_API_URL = "https://store.steampowered.com/api/appdetails"


def load_games():
    with open(GAMES_FILE, "r", encoding="utf-8") as file:
        config = json.load(file)

    games = config.get("games")

    if not isinstance(games, list) or not games:
        raise ValueError("games.json must contain a list of games.")

    if any(type(game_id) is not int or game_id <= 0 for game_id in games):
        raise ValueError("Game IDs must be positive integers.")

    return list(dict.fromkeys(games))


def fetch_game(app_id):
    response = requests.get(
        STEAM_API_URL,
        params={
            "appids": app_id,
            "cc": "pl",
            "l": "english"
        },
        timeout=15
    )

    response.raise_for_status()
    result = response.json().get(str(app_id), {})

    if not result.get("success"):
        raise ValueError("Game not found.")

    data = result["data"]
    price_info = data.get("price_overview")

    if not price_info:
        raise ValueError("Price is not available.")

    if price_info["currency"] != "PLN":
        raise ValueError("Unexpected currency.")

    return {
        "app_id": app_id,
        "name": data["name"],
        "price": int(price_info["final"]),
        "currency": price_info["currency"],
        "discount": price_info.get("discount_percent", 0)
    }


def init_database(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id INTEGER NOT NULL,
            game_name TEXT NOT NULL,
            price INTEGER NOT NULL,
            currency TEXT NOT NULL,
            checked_at TEXT NOT NULL
        )
    """)
    db.commit()


def get_last_price(db, app_id):
    return db.execute("""
        SELECT price
        FROM price_history
        WHERE app_id = ? AND currency = 'PLN'
        ORDER BY id DESC
        LIMIT 1
    """, (app_id,)).fetchone()


def save_price(db, game):
    db.execute("""
        INSERT INTO price_history
        (app_id, game_name, price, currency, checked_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        game["app_id"],
        game["name"],
        game["price"],
        game["currency"],
        datetime.now(timezone.utc).isoformat(timespec="seconds")
    ))
    db.commit()


def format_price(price):
    return f"{Decimal(price) / 100:.2f} PLN"


def check_prices(db):
    games = load_games()
    errors = 0

    print("\n=== PRICE DROP TRACKER ===")

    for app_id in games:
        try:
            game = fetch_game(app_id)
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            print(f"\nError checking game {app_id}: {error}")
            errors += 1
            continue

        last_record = get_last_price(db, app_id)
        new_price = game["price"]

        print(f"\nGame: {game['name']}")
        print(f"Current price: {format_price(new_price)}")
        print(f"Steam discount: {game['discount']}%")

        if last_record is None:
            print("First price recorded.")

        else:
            old_price = last_record[0]

            if new_price < old_price:
                drop = old_price - new_price
                percentage = Decimal(drop) / Decimal(old_price) * 100

                print("PRICE DROP!")
                print(f"Old price: {format_price(old_price)}")
                print(f"New price: {format_price(new_price)}")
                print(f"Price dropped by: {format_price(drop)}")
                print(f"Percentage drop: {percentage:.2f}%")

            elif new_price > old_price:
                print("PRICE INCREASE!")
                print(f"Old price: {format_price(old_price)}")

            else:
                print("Price unchanged.")

        save_price(db, game)

    return 1 if errors else 0


def show_history(db):
    rows = db.execute("""
        SELECT game_name, price, checked_at
        FROM price_history
        ORDER BY id DESC
        LIMIT 30
    """).fetchall()

    print("\n=== PRICE HISTORY ===")

    if not rows:
        print("No price history found.")
        return

    for name, price, checked_at in rows:
        print(f"{checked_at} | {name} | {format_price(price)}")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("check", "history"):
        print("Usage:")
        print("  py main.py check")
        print("  py main.py history")
        return 2

    try:
        db = sqlite3.connect(DATABASE_FILE)

        try:
            init_database(db)

            if sys.argv[1] == "check":
                return check_prices(db)

            show_history(db)
            return 0

        finally:
            db.close()

    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Application error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
