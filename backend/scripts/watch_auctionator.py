"""Foreground local polling, with no game control, settings, DB or network client."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.local_capture.watcher import AuctionatorWatcher, WatchError, WatchEvent, WatchSettings


def _enable_windows_ctrl_c():
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.SetConsoleCtrlHandler.argtypes = (ctypes.c_void_p, ctypes.c_int)  # Win32 BOOL is 32-bit.
        kernel.SetConsoleCtrlHandler.restype = ctypes.c_int
        # A launcher may pass an inherited ignore-Ctrl+C flag to this process.
        # No attached console is also legitimate (e.g. redirected subprocess tests).
        kernel.SetConsoleCtrlHandler(None, False)


@contextmanager
def _console_interrupts():
    signals = [signal.SIGINT]
    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)
    previous = {number: signal.getsignal(number) for number in signals}
    try:
        for number in signals:
            signal.signal(number, signal.default_int_handler)
        _enable_windows_ctrl_c()
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def format_event(event: WatchEvent) -> str:
    messages = {
        "watching": "Observando Auctionator.lua.",
        "waiting": "Archivo detectado o actualizado; esperando estabilidad.",
        "missing": "Archivo ausente; esperando que aparezca.",
        "available": "Archivo disponible nuevamente.",
        "identical": "Archivo idéntico; sin cambios.",
        "unavailable": "No disponible temporalmente; reintentando.",
        "validation_error": "Error de validación; no se archivó ni se marcó como procesado.",
        "archive_error": "Error de archivado; no se marca como procesado y se reintentará.",
        "retry_deferred": "Reintentos agotados; próximo intento después de la pausa de recuperación.",
        "stopped": "Observación detenida.",
    }
    if event.kind == "archived":
        message = {
            "first": "Captura archivada; primer estado de mercado.",
            "changed": "Captura archivada; mercado actualizado.",
            "equivalent": "Archivo diferente, sin cambios económicos; captura archivada.",
        }.get(event.comparison, "Captura archivada.")
    else:
        message = messages.get(event.kind, "Estado actualizado.")
    if event.capture_id is not None:
        message += (f" id={event.capture_id}; mercados={event.market_count}; items={event.item_count};"
                    f" estados_nuevos={event.new_market_states}")
    return message


def main(argv=None):
    parser = argparse.ArgumentParser(description="Observe one configured Auctionator.lua locally (offline polling)")
    parser.add_argument("file", type=Path, help="Real SavedVariables path; parent directory must exist")
    parser.add_argument("--destination", type=Path, help="Private archive outside the project and source directory")
    parser.add_argument("--source-version", choices=["340", "341"])
    parser.add_argument("--serialized-codec", choices=["cbor-definite"])
    parser.add_argument("--origin-id", help="Optional opaque alias, never a path/account name")
    parser.add_argument("--market-rule", action="append", default=[], metavar="KEY=RULESET")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Seconds between probes (0.25..60; default 2)")
    parser.add_argument("--debounce", type=float, default=2.0, help="Quiet seconds after the last detected change")
    parser.add_argument("--stable-seconds", type=float, default=4.0, help="Required unchanged observation period (default 4)")
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--recovery-interval", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        mapping = {}
        for rule in args.market_rule:
            key, separator, value = rule.rpartition("=")
            if not separator or not key or value not in ("PvE", "PvP", "HC", "RP") or key in mapping:
                raise WatchError("invalid_options")
            mapping[key] = value
        settings = WatchSettings(
            poll_interval=args.poll_interval, debounce_seconds=args.debounce, stable_seconds=args.stable_seconds,
            retry_delay=args.retry_delay, max_attempts=args.max_attempts, recovery_interval=args.recovery_interval,
        )
        observer = AuctionatorWatcher(
            args.file, args.destination, settings=settings, origin_id=args.origin_id,
            source_version=args.source_version, serialized_codec=args.serialized_codec, market_mapping=mapping,
            on_event=lambda event: print(format_event(event), flush=True),
        )
        with _console_interrupts():
            observer.run()
        return 0
    except WatchError as error:
        print(f"No se pudo iniciar el watcher ({error.code}). Revisá la configuración en privado.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Observación detenida.", flush=True)
        return 0
    except Exception:
        print("El watcher se detuvo por un error inesperado; detalles omitidos.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
