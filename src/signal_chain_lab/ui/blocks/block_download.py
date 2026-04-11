"""Blocco 1 - Download dati da Telegram."""
from __future__ import annotations

import os
import asyncio
import sqlite3
import sys
from pathlib import Path

from nicegui import ui

from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.file_dialogs import ask_directory
from src.signal_chain_lab.ui.state import UiState

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_PARSER_TEST_DIR = _PROJECT_ROOT / "parser_test"
_ENV_FILE = _PARSER_TEST_DIR / ".env"
_SESSION_NAME = str(_PARSER_TEST_DIR / "parser_test")


class _AuthCtx:
    """Authentication context shared by send_code -> sign_in steps."""

    client: object = None
    phone_code_hash: str | None = None


_auth_ctx = _AuthCtx()


class _DownloadCtx:
    """Mutable state for the currently running Telegram import."""

    process: asyncio.subprocess.Process | None = None
    stop_requested: bool = False


_download_ctx = _DownloadCtx()


def _load_saved_credentials() -> tuple[str, str]:
    api_id, api_hash = "", ""
    if not _ENV_FILE.exists():
        return api_id, api_hash

    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("TELEGRAM_API_ID="):
            api_id = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("TELEGRAM_API_HASH="):
            api_hash = stripped.split("=", 1)[1].strip()
    return api_id, api_hash


def _save_credentials(api_id: str, api_hash: str) -> None:
    _PARSER_TEST_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            if not line.startswith("TELEGRAM_API_ID=") and not line.startswith("TELEGRAM_API_HASH="):
                lines.append(line)
    lines.append(f"TELEGRAM_API_ID={api_id}")
    lines.append(f"TELEGRAM_API_HASH={api_hash}")
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["TELEGRAM_API_ID"] = api_id
    os.environ["TELEGRAM_API_HASH"] = api_hash


def _validate_api_credentials(api_id: str, api_hash: str) -> str | None:
    normalized_id = api_id.strip()
    normalized_hash = api_hash.strip()

    if not normalized_id or not normalized_hash:
        return "Inserisci API_ID e API_HASH"
    if not normalized_id.isdigit():
        return "API_ID deve essere un numero intero"
    if len(normalized_hash) != 32:
        return "API_HASH non valido: deve avere 32 caratteri"
    if not all(char in "0123456789abcdefABCDEF" for char in normalized_hash):
        return "API_HASH non valido: deve contenere solo caratteri esadecimali"
    return None


def _clear_credentials() -> None:
    if _ENV_FILE.exists():
        kept = [
            line for line in _ENV_FILE.read_text(encoding="utf-8").splitlines()
            if not line.startswith("TELEGRAM_API_ID=") and not line.startswith("TELEGRAM_API_HASH=")
        ]
        content = "\n".join(kept).strip()
        _ENV_FILE.write_text((content + "\n") if content else "", encoding="utf-8")
    os.environ.pop("TELEGRAM_API_ID", None)
    os.environ.pop("TELEGRAM_API_HASH", None)


def _session_files() -> list[Path]:
    base = Path(_SESSION_NAME)
    return [
        base.with_suffix(".session"),
        base.with_suffix(".session-journal"),
    ]


def _session_exists() -> bool:
    return any(path.exists() for path in _session_files())


def _reset_auth_state() -> None:
    _auth_ctx.client = None
    _auth_ctx.phone_code_hash = None


def _build_source_id(chat_id: str, topic_id: str) -> str:
    chat = chat_id.strip()
    topic = topic_id.strip()
    if not chat:
        return ""
    return f"{chat}/{topic}" if topic else chat


def _sanitize_path_fragment(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())


def _build_output_db_path(*, chat_id: str, topic_id: str, output_dir: str) -> Path:
    base_dir = Path(output_dir.strip() or "parser_test/db")
    if not base_dir.is_absolute():
        base_dir = (_PROJECT_ROOT / base_dir).resolve()
    chat_fragment = _sanitize_path_fragment(chat_id) or "telegram"
    topic_fragment = _sanitize_path_fragment(topic_id)
    suffix = f"__topic_{topic_fragment}" if topic_fragment else ""
    return base_dir / f"parser_test__chat_{chat_fragment}{suffix}.sqlite3"


def _delete_downloaded_db(*, state: UiState, log_panel: LogPanel, db_output_label) -> None:
    if _download_ctx.process is not None:
        ui.notify("Ferma prima il download in corso", color="warning")
        return

    db_path = state.downloaded_db_path.strip()
    if not db_path:
        ui.notify("Nessun DB scaricato da eliminare", color="warning")
        return

    target = Path(db_path)
    if not target.exists():
        log_panel.push(f"DB non trovato sul filesystem: {target}")
        state.downloaded_db_path = ""
        db_output_label.set_text("DB: -")
        ui.notify("DB già assente", color="warning")
        return

    target.unlink()
    log_panel.push(f"DB eliminato: {target}")
    state.downloaded_db_path = ""
    if state.parsed_db_path == db_path:
        state.parsed_db_path = ""
    db_output_label.set_text("DB: -")
    ui.notify("DB scaricato eliminato", color="positive")


def _stop_download(log_panel: LogPanel) -> None:
    process = _download_ctx.process
    if process is None:
        ui.notify("Nessun download in corso", color="warning")
        return

    _download_ctx.stop_requested = True
    log_panel.push("Richiesta arresto download...")
    try:
        process.terminate()
    except ProcessLookupError:
        pass
    ui.notify("Arresto download richiesto", color="warning")


def _summarize_download_db(db_path: Path) -> dict[str, int]:
    summary = {
        "raw_messages": 0,
        "rows_with_media": 0,
        "rows_with_media_blob": 0,
        "photo_rows": 0,
        "image_blob_rows": 0,
    }
    with sqlite3.connect(str(db_path)) as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(raw_messages)")}
        summary["raw_messages"] = int(conn.execute("SELECT COUNT(*) FROM raw_messages").fetchone()[0])
        if "has_media" in columns:
            summary["rows_with_media"] = int(
                conn.execute("SELECT COUNT(*) FROM raw_messages WHERE COALESCE(has_media, 0) = 1").fetchone()[0]
            )
        if "media_blob" in columns:
            summary["rows_with_media_blob"] = int(
                conn.execute("SELECT COUNT(*) FROM raw_messages WHERE media_blob IS NOT NULL").fetchone()[0]
            )
        if "media_kind" in columns:
            summary["photo_rows"] = int(
                conn.execute("SELECT COUNT(*) FROM raw_messages WHERE LOWER(COALESCE(media_kind, '')) = 'photo'").fetchone()[0]
            )
        if "media_mime_type" in columns and "media_blob" in columns:
            summary["image_blob_rows"] = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM raw_messages
                    WHERE media_blob IS NOT NULL
                      AND LOWER(COALESCE(media_mime_type, '')) LIKE 'image/%'
                    """
                ).fetchone()[0]
            )
    return summary


async def _browse_output_dir(output_input) -> None:
    selected = ask_directory(
        initialdir=_PROJECT_ROOT,
        title="Seleziona la cartella dove salvare il DB",
        mustexist=False,
    )
    if not selected:
        ui.notify("Selezione cartella annullata.", color="warning")
        return
    output_input.value = selected
    output_input.update()


async def _send_otp(
    *,
    api_id: str,
    api_hash: str,
    phone: str,
    log_panel: LogPanel,
    otp_row,
    auth_status_label,
) -> None:
    try:
        from telethon import TelegramClient
        from telethon.errors import ApiIdInvalidError, PhoneNumberInvalidError
    except ImportError:
        ui.notify("telethon non installato", color="negative")
        return

    validation_error = _validate_api_credentials(api_id, api_hash)
    if validation_error:
        ui.notify(validation_error, color="negative")
        log_panel.push(f"ERRORE: {validation_error}")
        return
    if not phone.strip():
        ui.notify("Inserisci il numero di telefono", color="negative")
        return

    _save_credentials(api_id.strip(), api_hash.strip())
    log_panel.push("Credenziali salvate in parser_test/.env")
    log_panel.push(f"Connessione a Telegram con sessione: {_SESSION_NAME}")

    try:
        client = TelegramClient(_SESSION_NAME, int(api_id.strip()), api_hash.strip())
        await client.connect()
        result = await client.send_code_request(phone.strip())
        _auth_ctx.client = client
        _auth_ctx.phone_code_hash = result.phone_code_hash
        log_panel.push(f"Codice OTP inviato al numero {phone.strip()}")
        auth_status_label.set_text("Inserisci il codice OTP ricevuto sul telefono")
        otp_row.set_visibility(True)
        ui.notify("Codice OTP inviato", color="positive")
    except ApiIdInvalidError:
        ui.notify("API_ID o API_HASH non validi", color="negative")
        log_panel.push("ERRORE: API_ID o API_HASH non validi")
    except PhoneNumberInvalidError:
        ui.notify("Numero di telefono non valido", color="negative")
        log_panel.push("ERRORE: Numero di telefono non valido")
    except Exception as exc:
        ui.notify(f"Errore: {exc}", color="negative")
        log_panel.push(f"ERRORE: {exc}")


async def _confirm_otp(
    *,
    phone: str,
    otp_code: str,
    log_panel: LogPanel,
    auth_status_label,
    otp_row,
) -> None:
    if _auth_ctx.client is None or _auth_ctx.phone_code_hash is None:
        ui.notify("Prima invia il codice OTP", color="negative")
        return
    if not otp_code.strip():
        ui.notify("Inserisci il codice OTP", color="negative")
        return

    try:
        from telethon.errors import SessionPasswordNeededError

        await _auth_ctx.client.sign_in(
            phone.strip(),
            otp_code.strip(),
            phone_code_hash=_auth_ctx.phone_code_hash,
        )
        await _auth_ctx.client.disconnect()
        _reset_auth_state()
        log_panel.push("Autenticazione completata")
        log_panel.push(f"Sessione salvata in: {_SESSION_NAME}.session")
        auth_status_label.set_text("Autenticato - sessione salvata")
        otp_row.set_visibility(False)
        ui.notify("Autenticazione completata", color="positive")
    except SessionPasswordNeededError:
        ui.notify("Account con 2FA attivo: password cloud non ancora gestita dalla UI", color="warning")
        log_panel.push("ERRORE: 2FA abilitato - usare il terminale per completare la sessione")
    except Exception as exc:
        ui.notify(f"OTP errato o scaduto: {exc}", color="negative")
        log_panel.push(f"ERRORE OTP: {exc}")


def _reset_telegram_session(
    *,
    api_id_input,
    api_hash_input,
    auth_status_label,
    log_panel: LogPanel,
    otp_row,
) -> None:
    removed_any = False
    for path in _session_files():
        if path.exists():
            path.unlink()
            removed_any = True
    _clear_credentials()
    _reset_auth_state()
    api_id_input.value = ""
    api_hash_input.value = ""
    api_id_input.update()
    api_hash_input.update()
    auth_status_label.set_text("Sessione e credenziali azzerate")
    otp_row.set_visibility(False)
    log_panel.push("Sessione Telegram rimossa")
    log_panel.push("Credenziali TELEGRAM_API_ID / TELEGRAM_API_HASH rimosse da parser_test/.env")
    ui.notify(
        "Sessione e credenziali azzerate" if removed_any else "Credenziali azzerate",
        color="positive",
    )


async def _handle_download(
    *,
    state: UiState,
    chat_id: str,
    topic_id: str,
    date_from: str,
    date_to: str,
    full_history: bool,
    download_mode: str,
    output_dir: str,
    log_panel: LogPanel,
    source_id_label,
    db_output_label,
    run_streaming_command,
) -> None:
    state.chat_id = chat_id.strip()
    state.topic_id = topic_id.strip()
    state.full_history = full_history
    state.download_media = download_mode == "text_images"
    state.date_from = "" if full_history else date_from.strip()
    state.date_to = "" if full_history else date_to.strip()
    state.db_output_dir = output_dir.strip() or "parser_test/db"
    log_panel.clear()
    _download_ctx.stop_requested = False

    source_id = _build_source_id(state.chat_id, state.topic_id)
    source_id_label.set_text(f"ID sorgente: {source_id or '-'}")

    if not state.chat_id:
        ui.notify("Inserisci il chat_id Telegram", color="negative")
        return
    if not _session_exists():
        ui.notify("Sessione Telegram non trovata: autentica prima con API_ID/HASH + OTP", color="negative")
        return
    if not state.full_history and not (state.date_from or state.date_to):
        ui.notify("Se scegli periodo personalizzato inserisci almeno una data", color="negative")
        return

    output_db_path = _build_output_db_path(
        chat_id=state.chat_id,
        topic_id=state.topic_id,
        output_dir=state.db_output_dir,
    )
    output_db_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "parser_test/scripts/import_history.py",
        "--chat-id",
        state.chat_id,
        "--session",
        _SESSION_NAME,
        "--db-path",
        str(output_db_path),
    ]
    if state.topic_id:
        command += ["--topic-id", state.topic_id]
    if state.date_from:
        command += ["--from-date", state.date_from]
    if state.date_to:
        command += ["--to-date", state.date_to]
    if state.download_media:
        command += ["--download-media"]

    log_panel.push(f"Avvio download da {source_id or state.chat_id}")
    log_panel.push("Periodo: tutto" if state.full_history else f"Periodo: {state.date_from or '-'} -> {state.date_to or '-'}")
    log_panel.push("Contenuto: testo + immagini" if state.download_media else "Contenuto: solo testo")
    log_panel.push(f"Sessione Telegram: {_SESSION_NAME}.session")
    log_panel.push(f"DB destinazione: {output_db_path}")
    log_panel.push("Download in esecuzione...")

    def _bind_process(process) -> None:
        _download_ctx.process = process

    try:
        rc = await run_streaming_command(command, log_panel, process_started=_bind_process)
    finally:
        _download_ctx.process = None

    if _download_ctx.stop_requested:
        _download_ctx.stop_requested = False
        ui.notify("Download arrestato", color="warning")
        return
    if rc != 0:
        ui.notify("Download fallito: controlla log", color="negative")
        return

    state.downloaded_db_path = str(output_db_path)
    db_output_label.set_text(f"DB: {state.downloaded_db_path}")
    summary = _summarize_download_db(output_db_path)
    log_panel.push(
        "Verifica DB: "
        f"messaggi={summary['raw_messages']}, "
        f"righe_con_media={summary['rows_with_media']}, "
        f"blob_media={summary['rows_with_media_blob']}, "
        f"foto={summary['photo_rows']}, "
        f"blob_immagine={summary['image_blob_rows']}"
    )
    if state.download_media:
        if summary["rows_with_media_blob"] > 0:
            log_panel.push("Controllo immagini: OK, il DB contiene media scaricati.")
        elif summary["rows_with_media"] > 0:
            log_panel.push("Controllo immagini: presenti messaggi con media, ma nessun blob salvato.")
        else:
            log_panel.push("Controllo immagini: nessun messaggio con media trovato nel periodo selezionato.")
    ui.notify("Download completato", color="positive")


def render_block_download(state: UiState, *, run_streaming_command) -> None:
    """Render block 1 - Telegram history download."""
    saved_api_id, saved_api_hash = _load_saved_credentials()

    with ui.card().classes("w-full"):
        ui.label("Blocco 1 - Download dati").classes("text-h6")
        ui.label("Sorgente fissa: Telegram").classes("text-body2 text-grey-7")
        block1_log = LogPanel(title="Log Download")

        session_ok = _session_exists()
        auth_status_label = ui.label(
            "Sessione attiva" if session_ok else "Nessuna sessione - inserisci le credenziali"
        ).classes("text-caption text-grey-6" if session_ok else "text-caption text-orange-7")

        with ui.expansion("Credenziali Telegram / Autenticazione", icon="lock", value=not session_ok).classes("w-full"):
            api_id_input = ui.input("API_ID (da my.telegram.org)", value=saved_api_id).classes("w-full")
            api_hash_input = ui.input(
                "API_HASH (da my.telegram.org)",
                value=saved_api_hash,
                password=True,
                password_toggle_button=True,
            ).classes("w-full")
            phone_input = ui.input("Numero telefono (es. +39...)", value="").classes("w-full")

            with ui.row().classes("w-full items-center gap-2") as otp_row:
                otp_input = ui.input("Codice OTP ricevuto sul telefono").classes("flex-1")

                async def _on_confirm_otp() -> None:
                    await _confirm_otp(
                        phone=phone_input.value,
                        otp_code=otp_input.value,
                        log_panel=block1_log,
                        auth_status_label=auth_status_label,
                        otp_row=otp_row,
                    )

                ui.button("Conferma OTP", on_click=_on_confirm_otp, color="positive")

            otp_row.set_visibility(False)

            async def _on_send_otp() -> None:
                await _send_otp(
                    api_id=api_id_input.value,
                    api_hash=api_hash_input.value,
                    phone=phone_input.value,
                    log_panel=block1_log,
                    otp_row=otp_row,
                    auth_status_label=auth_status_label,
                )

            with ui.row().classes("gap-2"):
                ui.button("Invia OTP", on_click=_on_send_otp, icon="send")
                ui.button(
                    "Azzera sessione e credenziali",
                    on_click=lambda: _reset_telegram_session(
                        api_id_input=api_id_input,
                        api_hash_input=api_hash_input,
                        auth_status_label=auth_status_label,
                        log_panel=block1_log,
                        otp_row=otp_row,
                    ),
                    color="warning",
                    icon="delete",
                )

        source_id_label = ui.label(f"ID sorgente: {_build_source_id(state.chat_id, state.topic_id) or '-'}")
        chat_id_input = ui.input("Chat ID Telegram", value=state.chat_id, placeholder="-1001234567890").classes("w-full")
        topic_id_input = ui.input("Topic ID opzionale", value=state.topic_id, placeholder="es. 8").classes("w-full")
        ui.label('Se inserisci il topic, l\'ID logico diventa ad esempio "3722628653/8".').classes(
            "text-caption text-grey-7"
        )

        def _refresh_source_id(*_) -> None:
            source_id_label.set_text(f"ID sorgente: {_build_source_id(chat_id_input.value, topic_id_input.value) or '-'}")

        chat_id_input.on("update:model-value", _refresh_source_id)
        topic_id_input.on("update:model-value", _refresh_source_id)

        full_history_toggle = ui.checkbox("Scarica tutto lo storico", value=state.full_history)
        with ui.row().classes("w-full gap-4") as date_row:
            date_from = ui.input("Dal", value=state.date_from).props("type=date").classes("flex-1")
            date_to = ui.input("Al", value=state.date_to).props("type=date").classes("flex-1")

        def _toggle_date_row(*_) -> None:
            date_row.set_visibility(not full_history_toggle.value)

        full_history_toggle.on("update:model-value", _toggle_date_row)
        date_row.set_visibility(not state.full_history)

        download_mode = ui.radio(
            {
                "text": "Solo testo",
                "text_images": "Testo + immagini",
            },
            value="text_images" if state.download_media else "text",
        ).props("inline")

        with ui.row().classes("w-full items-end gap-2"):
            db_output_dir = ui.input("Cartella dove salvare il DB", value=state.db_output_dir).classes("flex-1")

            async def _on_browse_output_dir() -> None:
                await _browse_output_dir(db_output_dir)

            ui.button("Sfoglia", on_click=_on_browse_output_dir, icon="folder_open")

        db_output_label = ui.label(f"DB: {state.downloaded_db_path or '-'}")

        async def _on_download_click() -> None:
            if _download_ctx.process is not None:
                ui.notify("Download già in corso", color="warning")
                return
            await _handle_download(
                state=state,
                chat_id=chat_id_input.value,
                topic_id=topic_id_input.value,
                date_from=date_from.value,
                date_to=date_to.value,
                full_history=bool(full_history_toggle.value),
                download_mode=download_mode.value,
                output_dir=db_output_dir.value,
                log_panel=block1_log,
                source_id_label=source_id_label,
                db_output_label=db_output_label,
                run_streaming_command=run_streaming_command,
            )

        with ui.row().classes("gap-2"):
            ui.button("Esegui Download", on_click=_on_download_click)
            ui.button("Arresta Download", on_click=lambda: _stop_download(block1_log), color="warning", icon="stop")
            ui.button(
                "Elimina DB scaricato",
                on_click=lambda: _delete_downloaded_db(
                    state=state,
                    log_panel=block1_log,
                    db_output_label=db_output_label,
                ),
                color="negative",
                icon="delete",
            )
