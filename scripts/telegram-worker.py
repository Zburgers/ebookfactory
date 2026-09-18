#!/usr/bin/env python3
"""Restart-safe Telegram long poller and durable outbox sender."""

from __future__ import annotations

import logging
import time
from app.database import Database
from app.models import TelegramState
from app.settings import Settings
from app.telegram import (
    TelegramBotClient,
    TelegramConfig,
    claim_outbox,
    config_from_values,
    process_update,
    record_outbox_failure,
    record_outbox_sent,
)

LOG = logging.getLogger("ebook-factory.telegram")
MAX_POLL_RETRIES = 5


def get_next_update_id(session) -> int:
    state = session.get(TelegramState, 1)
    return state.next_update_id if state else 0


def _process_updates(database: Database, config: TelegramConfig, updates: list[dict]) -> None:
    for update in updates:
        session = database.session()
        try:
            process_update(session, config=config, update=update)
        finally:
            session.close()


def drain_outbox(database: Database, bot: TelegramBotClient, *, limit: int = 20) -> int:
    delivered = 0
    for _ in range(limit):
        session = database.session()
        try:
            delivery = claim_outbox(session)
        finally:
            session.close()
        if delivery is None:
            break
        try:
            message_id = bot.send_message(chat_id=delivery.chat_id, text=delivery.text)
        except Exception as exc:  # noqa: BLE001 - delivery state records sanitized error
            session = database.session()
            try:
                record_outbox_failure(session, delivery.outbox_id, type(exc).__name__)
            finally:
                session.close()
        else:
            session = database.session()
            try:
                record_outbox_sent(session, delivery.outbox_id, message_id)
            finally:
                session.close()
            delivered += 1
    return delivered


def poll_once(database: Database, bot: TelegramBotClient, config: TelegramConfig, *, timeout: int = 30) -> int:
    session = database.session()
    try:
        offset = get_next_update_id(session)
    finally:
        session.close()
    updates = bot.get_updates(offset=offset, timeout=timeout)
    _process_updates(database, config, updates)
    drain_outbox(database, bot)
    return len(updates)


def main() -> None:
    settings = Settings()
    config = config_from_values(
        token=settings.telegram_bot_token,
        allowed_chat_ids=settings.telegram_allowed_chat_ids,
        allowed_sender_ids=settings.telegram_allowed_sender_ids,
    )
    if not config.configured:
        raise SystemExit("Telegram is not configured: set token and allowlists")
    database = Database(settings.database_url)
    bot = TelegramBotClient(settings.telegram_bot_token or "")
    retries = 0
    while True:
        try:
            poll_once(database, bot, config)
            retries = 0
        except Exception as exc:  # noqa: BLE001 - supervisor restarts after bounded backoff
            retries += 1
            LOG.error("Telegram polling failed (%s)", type(exc).__name__)
            if retries >= MAX_POLL_RETRIES:
                raise
            time.sleep(min(30, 2**retries))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
