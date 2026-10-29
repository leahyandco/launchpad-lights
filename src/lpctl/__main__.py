"""Entry point: arg parsing, logging setup."""
import sys

sys.coinit_flags = 0  # COM multithreaded apartment; must be set before anything imports comtypes

import argparse  # noqa: E402
import logging  # noqa: E402
import signal  # noqa: E402
from logging.handlers import RotatingFileHandler  # noqa: E402

from lpctl.config import Config, app_dir

log = logging.getLogger("lpctl")


def setup_logging(verbose: bool, console: bool) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_dir = app_dir() / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_dir / "lpctl.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as e:
        print(f"Could not open log file in {log_dir}: {e}", file=sys.stderr)
    if console and sys.stderr:  # sys.stderr is None under pythonw
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", "%H:%M:%S"))
        root.addHandler(sh)


def list_ports() -> None:
    import mido

    print("MIDI outputs:")
    for n in mido.get_output_names():
        print(f"  {n}")
    print("MIDI inputs:")
    for n in mido.get_input_names():
        print(f"  {n}")
    try:
        import pyaudiowpatch as pyaudio
    except ImportError as e:
        print(f"Audio: pyaudiowpatch unavailable ({e})")
        return
    pa = pyaudio.PyAudio()
    try:
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default = wasapi["defaultOutputDevice"]
        print("WASAPI output devices (* = default):")
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            if d["hostApi"] == wasapi["index"] and d["maxOutputChannels"] > 0:
                print(f"  {'*' if i == default else ' '} {d['name']} ({int(d['defaultSampleRate'])} Hz)")
        print("Loopback capture devices:")
        for d in pa.get_loopback_device_info_generator():
            print(f"    {d['name']} ({int(d['defaultSampleRate'])} Hz, {d['maxInputChannels']} ch)")
    finally:
        pa.terminate()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="lpctl", description="Launchpad Mini controller")
    p.add_argument("--test", action="store_true", help="hardware smoke test: walk every LED, cycle colours, echo presses")
    p.add_argument("--simulate", action="store_true", help="render to the terminal instead of the device")
    p.add_argument("--list-ports", action="store_true", help="list MIDI ports and audio devices")
    p.add_argument("--no-gui", action="store_true", help="run headless: no window or tray icon")
    p.add_argument("--hidden", action="store_true", help="start with the window hidden (tray icon only)")
    p.add_argument("--mode", help="start in this mode instead of the configured one")
    p.add_argument("--config", help="config file path (default %%APPDATA%%\\lpctl\\config.toml)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    if args.list_ports:
        list_ports()
        return

    config = Config.load(args.config)
    setup_logging(args.verbose, console=not args.simulate)
    log.info("Starting lpctl (config %s)", config.path)

    if args.simulate:
        from lpctl.launchpad.simulator import TerminalDevice
        device = TerminalDevice()
    else:
        from lpctl.launchpad.device import LaunchpadDevice
        dev_cfg = config.section("device")
        device = LaunchpadDevice(dev_cfg.get("port_name", "Launchpad Mini"), bool(dev_cfg.get("rapid_update", True)),
                                 float(dev_cfg.get("retry_seconds", 2.0)))

    from lpctl.app import App
    app = App(config, device, locked_mode="test_pattern" if args.test else None, start_mode=args.mode)
    for sig in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), lambda *_: app.stop())
    if args.test:
        print("Smoke test running: watch the LEDs, press every button. Ctrl+C to stop.")
    if args.test or args.simulate or args.no_gui:
        app.run()
    else:
        from lpctl.gui import run_gui
        run_gui(app, start_hidden=args.hidden)


if __name__ == "__main__":
    main()
