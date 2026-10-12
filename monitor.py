
import json
import os

from decimal import Decimal
from pathlib import Path

import requests

from main import fetch_game, format_price, load_games


STATE_FILE = Path(__file__).resolve().parent / "price_state.json"


def load_state():
    if not STATE_FILE.exists():
        return {}

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        state = json.load(file)

    if not isinstance(state, dict):
        raise ValueError("Invalid price state file.")

    return state


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2, ensure_ascii=False)
        file.write("\n")


def main():
    games = load_games()
    state = load_state()

    messages = []
    errors = 0
    successful_checks = 0

    print("=== AUTOMATIC PRICE MONITOR ===")

    for app_id in games:
        try:
            game = fetch_game(app_id)

        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            message = f"API ERROR [{app_id}]: {error}"
            print(message)
            messages.append(message)
            errors += 1
            continue

        key = str(app_id)
        previous = state.get(key)
        current_price = game["price"]

        if previous is None:
            message = (
                f"FIRST CHECK: {game['name']} - "
                f"{format_price(current_price)}"
            )

        elif previous["currency"] != game["currency"]:
            message = f"CURRENCY CHANGED: {game['name']}"

        else:
            old_price = previous["price"]

            if current_price < old_price:
                drop = old_price - current_price
                percentage = Decimal(drop) / Decimal(old_price) * 100

                message = (
                    f"PRICE DROP! {game['name']}: "
                    f"{format_price(old_price)} -> "
                    f"{format_price(current_price)} "
                    f"(-{percentage:.2f}%)"
                )

            elif current_price > old_price:
                message = (
                    f"PRICE INCREASE: {game['name']}: "
                    f"{format_price(old_price)} -> "
                    f"{format_price(current_price)}"
                )

            else:
                message = (
                    f"UNCHANGED: {game['name']} - "
                    f"{format_price(current_price)}"
                )

        print(message)
        messages.append(message)

        state[key] = {
            "name": game["name"],
            "price": current_price,
            "currency": game["currency"]
        }

        successful_checks += 1

    if successful_checks:
        save_state(state)

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")

    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as file:
            file.write("## Steam Price Monitor\n\n")

            for message in messages:
                file.write(f"- {message}\n")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
