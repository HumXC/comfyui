#!/usr/bin/env python3

import asyncio
import fcntl
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import (
    ServiceInterface,
    dbus_property,
    method,
    signal as dbus_signal,
)

# ============================================================================
# Nix substitutions
# ============================================================================

SETUP_BIN = "__SETUP_BIN__"
XDG_OPEN_BIN = "__XDG_OPEN_BIN__"
ICON_ARGB_PATH = "__ICON_ARGB_PATH__"
LIB_PATH = "__LIB_PATH__"


# ============================================================================
# Configuration
# ============================================================================

WORK_DIR = Path.home() / ".config" / "comfyui"
REPO_DIR = WORK_DIR / "ComfyUI"

VENV_PATH = WORK_DIR / ".venv"
VENV_PYTHON = VENV_PATH / "bin" / "python"

CONSTRAINTS_PATH = WORK_DIR / "constraints.txt"

PID_FILE = WORK_DIR / "comfyui.pid"
LAUNCHER_PID_FILE = WORK_DIR / "launcher.pid"
LOCK_FILE = WORK_DIR / "launcher.lock"

WEBUI_HOST = "127.0.0.1"
WEBUI_PORT = 8188
WEBUI_URL = f"http://{WEBUI_HOST}:{WEBUI_PORT}"

SNI_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"

WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"

DBUS_NAME = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"

ICON_WIDTH = 64
ICON_HEIGHT = 64


ENV_OVERRIDES: Dict[str, str] = {
    "WORK_DIR": str(WORK_DIR),
    "VIRTUAL_ENV": str(VENV_PATH),
    # Intel XPU
    "ONEAPI_DEVICE_SELECTOR": "level_zero:gpu",
    "ZES_ENABLE_SYSMAN": "1",
    "NEOReadDebugKeys": "1",
    "IGC_EnableDPEmulation": "1",
    "OverrideDefaultFP64Settings": "1",
    # uv / ComfyUI Manager
    "UV_TORCH_BACKEND": "xpu",
    "UV_PYTHON_DOWNLOADS": "never",
    "UV_CONSTRAINT": str(CONSTRAINTS_PATH),
}


# ============================================================================
# StatusNotifierItem
# ============================================================================


class StatusNotifierItem(ServiceInterface):
    def __init__(self, launcher: "ComfyUILauncher") -> None:
        super().__init__("org.kde.StatusNotifierItem")

        self.launcher = launcher

        self._title = "ComfyUI"
        self._status = "Active"

    # ------------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------------

    @dbus_property(access=PropertyAccess.READ)
    def Category(self) -> "s":
        return "ApplicationStatus"

    @dbus_property(access=PropertyAccess.READ)
    def Id(self) -> "s":
        return "comfyui"

    @dbus_property(access=PropertyAccess.READ)
    def Title(self) -> "s":
        return self._title

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return self._status

    @dbus_property(access=PropertyAccess.READ)
    def WindowId(self) -> "u":
        return 0

    @dbus_property(access=PropertyAccess.READ)
    def ItemIsMenu(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def IconName(self) -> "s":
        # IconPixmap is authoritative.
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def IconPixmap(self) -> "a(iiay)":
        return [
            [
                ICON_WIDTH,
                ICON_HEIGHT,
                self.launcher.icon_argb,
            ]
        ]

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconPixmap(self) -> "a(iiay)":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconPixmap(self) -> "a(iiay)":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def AttentionMovieName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def ToolTip(self) -> "(sa(iiay)ss)":
        return [
            "",
            [
                [
                    ICON_WIDTH,
                    ICON_HEIGHT,
                    self.launcher.icon_argb,
                ]
            ],
            "ComfyUI",
            self.launcher.status_text,
        ]

    @dbus_property(access=PropertyAccess.READ)
    def Menu(self) -> "o":
        return MENU_PATH

    # ------------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------------

    @method()
    def Activate(
        self,
        x: "i",
        y: "i",
    ):
        self.launcher.open_webui()

    @method()
    def SecondaryActivate(
        self,
        x: "i",
        y: "i",
    ):
        self.launcher.open_webui()

    @method()
    def ContextMenu(
        self,
        x: "i",
        y: "i",
    ):
        # The tray host reads Menu and displays DBusMenu itself.
        pass

    @method()
    def Scroll(
        self,
        delta: "i",
        orientation: "s",
    ):
        pass

    # ------------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------------

    @dbus_signal()
    def NewTitle(self):
        return None

    @dbus_signal()
    def NewIcon(self):
        return None

    @dbus_signal()
    def NewAttentionIcon(self):
        return None

    @dbus_signal()
    def NewOverlayIcon(self):
        return None

    @dbus_signal()
    def NewToolTip(self):
        return None

    @dbus_signal()
    def NewStatus(self, status: "s") -> "s":
        return status

    # ------------------------------------------------------------------------

    def set_state(
        self,
        *,
        title: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        changed = {}

        if title is not None and title != self._title:
            self._title = title
            changed["Title"] = title

        if status is not None and status != self._status:
            self._status = status
            changed["Status"] = status

        if changed:
            self.emit_properties_changed(changed)

        if "Title" in changed:
            self.NewTitle()

        if "Status" in changed:
            self.NewStatus(self._status)

        self.NewToolTip()


# ============================================================================
# DBusMenu
# ============================================================================


class DBusMenu(ServiceInterface):
    ROOT = 0

    OPEN = 1
    RESTART = 2
    SEPARATOR = 3
    QUIT = 4

    def __init__(self, launcher: "ComfyUILauncher") -> None:
        super().__init__("com.canonical.dbusmenu")

        self.launcher = launcher
        self.revision = 1

    # ------------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------------

    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> "u":
        return 3

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return "normal"

    @dbus_property(access=PropertyAccess.READ)
    def TextDirection(self) -> "s":
        return "ltr"

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "as":
        return []

    # ------------------------------------------------------------------------
    # Menu definitions
    # ------------------------------------------------------------------------

    def item_properties(
        self,
        item_id: int,
    ) -> Dict[str, Variant]:
        if item_id == self.ROOT:
            return {
                "children-display": Variant(
                    "s",
                    "submenu",
                ),
            }

        if item_id == self.OPEN:
            return {
                "label": Variant(
                    "s",
                    "Open WebUI",
                ),
                "enabled": Variant(
                    "b",
                    True,
                ),
                "visible": Variant(
                    "b",
                    True,
                ),
            }

        if item_id == self.RESTART:
            return {
                "label": Variant(
                    "s",
                    "Restart",
                ),
                "enabled": Variant(
                    "b",
                    not self.launcher.shutting_down,
                ),
                "visible": Variant(
                    "b",
                    True,
                ),
            }

        if item_id == self.SEPARATOR:
            return {
                "type": Variant(
                    "s",
                    "separator",
                ),
                "visible": Variant(
                    "b",
                    True,
                ),
            }

        if item_id == self.QUIT:
            return {
                "label": Variant(
                    "s",
                    "Quit",
                ),
                "enabled": Variant(
                    "b",
                    True,
                ),
                "visible": Variant(
                    "b",
                    True,
                ),
            }

        return {}

    def filtered_properties(
        self,
        item_id: int,
        property_names: list[str],
    ) -> Dict[str, Variant]:
        properties = self.item_properties(item_id)

        if not property_names:
            return properties

        return {
            name: value for name, value in properties.items() if name in property_names
        }

    def build_item(
        self,
        item_id: int,
        property_names: list[str],
        recursion_depth: int,
    ):
        properties = self.filtered_properties(
            item_id,
            property_names,
        )

        children = []

        if item_id == self.ROOT and recursion_depth != 0:
            if recursion_depth > 0:
                next_depth = recursion_depth - 1
            else:
                next_depth = recursion_depth

            for child_id in (
                self.OPEN,
                self.RESTART,
                self.SEPARATOR,
                self.QUIT,
            ):
                child = self.build_item(
                    child_id,
                    property_names,
                    next_depth,
                )

                children.append(
                    Variant(
                        "(ia{sv}av)",
                        child,
                    )
                )

        return [
            item_id,
            properties,
            children,
        ]

    # ------------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------------

    @method()
    def GetLayout(
        self,
        parent_id: "i",
        recursion_depth: "i",
        property_names: "as",
    ) -> "u(ia{sv}av)":
        layout = self.build_item(
            parent_id,
            property_names,
            recursion_depth,
        )

        return [
            self.revision,
            layout,
        ]

    @method()
    def GetGroupProperties(
        self,
        ids: "ai",
        property_names: "as",
    ) -> "a(ia{sv})":
        if not ids:
            ids = [
                self.ROOT,
                self.OPEN,
                self.RESTART,
                self.SEPARATOR,
                self.QUIT,
            ]

        result = []

        for item_id in ids:
            result.append(
                [
                    item_id,
                    self.filtered_properties(
                        item_id,
                        property_names,
                    ),
                ]
            )

        return result

    @method()
    def GetProperty(
        self,
        item_id: "i",
        name: "s",
    ) -> "v":
        properties = self.item_properties(item_id)

        value = properties.get(name)

        if value is not None:
            return value

        return Variant(
            "s",
            "",
        )

    @method()
    def Event(
        self,
        item_id: "i",
        event_id: "s",
        data: "v",
        timestamp: "u",
    ):
        if event_id != "clicked":
            return

        if item_id == self.OPEN:
            self.launcher.open_webui()

        elif item_id == self.RESTART:
            asyncio.create_task(self.launcher.restart_comfyui())

        elif item_id == self.QUIT:
            asyncio.create_task(self.launcher.shutdown())

    @method()
    def EventGroup(
        self,
        events: "a(isvu)",
    ) -> "ai":
        failed = []

        for event in events:
            (
                item_id,
                event_id,
                data,
                timestamp,
            ) = event

            try:
                self.Event(
                    item_id,
                    event_id,
                    data,
                    timestamp,
                )
            except Exception:
                failed.append(item_id)

        return failed

    @method()
    def AboutToShow(
        self,
        item_id: "i",
    ) -> "b":
        return False

    @method()
    def AboutToShowGroup(
        self,
        ids: "ai",
    ) -> "aiai":
        # No dynamic menu reconstruction needed.
        return [
            [],
            [],
        ]

    # ------------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------------

    @dbus_signal()
    def LayoutUpdated(
        self,
        revision: "u",
        parent: "i",
    ) -> "ui":
        return [
            revision,
            parent,
        ]

    @dbus_signal()
    def ItemsPropertiesUpdated(
        self,
        updated: "a(ia{sv})",
        removed: "a(ias)",
    ) -> "a(ia{sv})a(ias)":
        return [
            updated,
            removed,
        ]


# ============================================================================
# Launcher
# ============================================================================


class ComfyUILauncher:
    def __init__(self) -> None:
        self.env = self.build_env()

        self.process: Optional[subprocess.Popen] = None
        self.process_lock = asyncio.Lock()

        self.shutdown_event = asyncio.Event()

        self.shutting_down = False

        self.lock_fd = None

        self.bus: Optional[MessageBus] = None
        self.sni: Optional[StatusNotifierItem] = None
        self.menu: Optional[DBusMenu] = None

        self.status_text = "Starting"

        self.icon_argb = self.load_icon()

    # ------------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------------

    def build_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env.update(ENV_OVERRIDES)

        env["LD_LIBRARY_PATH"] = f"{LIB_PATH}:" + env.get(
            "LD_LIBRARY_PATH",
            "",
        )

        env["PATH"] = (
            str(VENV_PATH / "bin")
            + os.pathsep
            + env.get(
                "PATH",
                "",
            )
        )

        return env

    def check_environment(self) -> bool:
        try:
            result = subprocess.run(
                [
                    SETUP_BIN,
                    "--check",
                ],
                env=self.env,
            )

        except OSError as exc:
            print(
                f"Failed to run environment checker: {exc}",
                file=sys.stderr,
            )

            return False

        if result.returncode == 0:
            return True

        print(
            "\nComfyUI environment is not ready.",
            file=sys.stderr,
        )

        print(
            "Run `comfyui-setup` to initialize or repair it.",
            file=sys.stderr,
        )

        return False

    # ------------------------------------------------------------------------
    # Icon
    # ------------------------------------------------------------------------

    def load_icon(self) -> bytes:
        path = Path(ICON_ARGB_PATH)

        try:
            data = path.read_bytes()

        except OSError as exc:
            raise RuntimeError(f"Unable to load tray icon: {path}: {exc}") from exc

        expected_size = ICON_WIDTH * ICON_HEIGHT * 4

        if len(data) != expected_size:
            raise RuntimeError(
                f"Invalid tray icon size: {path}\n"
                f"Expected {expected_size} bytes "
                f"({ICON_WIDTH}x{ICON_HEIGHT} ARGB32), "
                f"got {len(data)} bytes."
            )

        return data

    # ------------------------------------------------------------------------
    # Single instance
    # ------------------------------------------------------------------------

    def acquire_instance_lock(self) -> bool:
        try:
            self.lock_fd = LOCK_FILE.open("a+")

            fcntl.flock(
                self.lock_fd.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

            return True

        except BlockingIOError:
            return False

    def write_launcher_pid(self) -> None:
        LAUNCHER_PID_FILE.write_text(
            str(os.getpid()),
            encoding="utf-8",
        )

    def remove_launcher_pid(self) -> None:
        try:
            LAUNCHER_PID_FILE.unlink()

        except OSError:
            pass

    # ------------------------------------------------------------------------
    # WebUI
    # ------------------------------------------------------------------------

    def open_webui(self) -> None:
        try:
            subprocess.Popen(
                [
                    XDG_OPEN_BIN,
                    WEBUI_URL,
                ],
                env=self.env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        except OSError as exc:
            print(
                f"Failed to open WebUI: {exc}",
                file=sys.stderr,
            )

    async def webui_ready(self) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    WEBUI_HOST,
                    WEBUI_PORT,
                ),
                timeout=1.0,
            )

            writer.close()

            try:
                await writer.wait_closed()

            except Exception:
                pass

            return True

        except (
            OSError,
            asyncio.TimeoutError,
        ):
            return False

    async def open_webui_when_ready(
        self,
        process: subprocess.Popen,
        timeout: float = 30.0,
    ) -> None:
        loop = asyncio.get_running_loop()

        deadline = loop.time() + timeout

        while not self.shutting_down and loop.time() < deadline:
            if process.poll() is not None:
                return

            if await self.webui_ready():
                self.open_webui()
                return

            await asyncio.sleep(0.5)

        if not self.shutting_down:
            print(
                "ComfyUI WebUI did not become ready " f"within {timeout:.0f} seconds.",
                file=sys.stderr,
            )

    # ------------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------------

    def set_status(
        self,
        text: str,
        *,
        sni_status: str = "Active",
    ) -> None:
        self.status_text = text

        if self.sni is not None:
            self.sni.set_state(
                title=f"ComfyUI - {text}",
                status=sni_status,
            )

    # ------------------------------------------------------------------------
    # ComfyUI PID
    # ------------------------------------------------------------------------

    def write_comfyui_pid(
        self,
        pid: int,
    ) -> None:
        PID_FILE.write_text(
            str(pid),
            encoding="utf-8",
        )

    def remove_comfyui_pid(
        self,
    ) -> None:
        try:
            PID_FILE.unlink()

        except OSError:
            pass

    # ------------------------------------------------------------------------
    # ComfyUI process
    # ------------------------------------------------------------------------

    async def start_comfyui(
        self,
        *,
        open_when_ready: bool = False,
    ) -> bool:
        async with self.process_lock:
            if self.shutting_down:
                return False

            if self.process is not None and self.process.poll() is None:
                return True

            self.set_status("Starting")

            print("Starting ComfyUI...")

            try:
                process = subprocess.Popen(
                    [
                        str(VENV_PYTHON),
                        "main.py",
                        "--enable-manager",
                    ],
                    cwd=REPO_DIR,
                    env=self.env,
                    # ComfyUI gets an independent process group.
                    start_new_session=True,
                )

            except OSError as exc:
                print(
                    f"Failed to start ComfyUI: {exc}",
                    file=sys.stderr,
                )

                self.set_status(
                    "Stopped",
                    sni_status="NeedsAttention",
                )

                return False

            self.process = process

            self.write_comfyui_pid(process.pid)

            print(f"ComfyUI started with pid {process.pid}.")

            self.set_status("Running")

            asyncio.create_task(self.monitor_process(process))

            if open_when_ready:
                asyncio.create_task(self.open_webui_when_ready(process))

            return True

    async def monitor_process(
        self,
        process: subprocess.Popen,
    ) -> None:
        return_code = await asyncio.to_thread(process.wait)

        async with self.process_lock:
            # A restart may already have installed another process.
            if self.process is not process:
                return

            self.process = None

            self.remove_comfyui_pid()

        if self.shutting_down:
            return

        print(
            f"ComfyUI exited with code {return_code}.",
            file=sys.stderr,
        )

        self.set_status(
            "Stopped",
            sni_status="NeedsAttention",
        )

    async def stop_comfyui(
        self,
        timeout: float = 10.0,
    ) -> None:
        async with self.process_lock:
            process = self.process

            if process is None:
                self.remove_comfyui_pid()
                return

            if process.poll() is not None:
                self.process = None
                self.remove_comfyui_pid()
                return

            pid = process.pid

        if not self.shutting_down:
            self.set_status("Stopping")

        print(f"Stopping ComfyUI (pid {pid})...")

        try:
            os.killpg(
                pid,
                signal.SIGTERM,
            )

        except ProcessLookupError:
            pass

        except PermissionError as exc:
            print(
                f"Cannot terminate ComfyUI: {exc}",
                file=sys.stderr,
            )

        try:
            await asyncio.wait_for(
                asyncio.to_thread(process.wait),
                timeout=timeout,
            )

        except asyncio.TimeoutError:
            print(
                "ComfyUI did not stop gracefully; " "sending SIGKILL...",
                file=sys.stderr,
            )

            try:
                os.killpg(
                    pid,
                    signal.SIGKILL,
                )

            except ProcessLookupError:
                pass

            await asyncio.to_thread(process.wait)

        async with self.process_lock:
            if self.process is process:
                self.process = None

            self.remove_comfyui_pid()

        if not self.shutting_down:
            self.set_status(
                "Stopped",
                sni_status="NeedsAttention",
            )

    async def restart_comfyui(
        self,
    ) -> None:
        if self.shutting_down:
            return

        print("Restarting ComfyUI...")

        self.set_status("Restarting")

        await self.stop_comfyui()

        if self.shutting_down:
            return

        await self.start_comfyui(
            open_when_ready=False,
        )

    # ------------------------------------------------------------------------
    # D-Bus
    # ------------------------------------------------------------------------

    async def register_status_notifier_item(
        self,
    ) -> None:
        if self.bus is None:
            return

        try:
            introspection = await self.bus.introspect(
                WATCHER_NAME,
                WATCHER_PATH,
            )

            obj = self.bus.get_proxy_object(
                WATCHER_NAME,
                WATCHER_PATH,
                introspection,
            )

            watcher = obj.get_interface("org.kde.StatusNotifierWatcher")

            # Important:
            #
            # Register the object path instead of a well-known service name.
            # The watcher associates it with this connection's unique D-Bus
            # name, e.g. :1.123/StatusNotifierItem.
            await watcher.call_register_status_notifier_item(SNI_PATH)

            print("StatusNotifierItem registered.")

        except Exception as exc:
            print(
                f"StatusNotifierWatcher unavailable: {exc}",
                file=sys.stderr,
            )

    async def watch_status_notifier_watcher(
        self,
    ) -> None:
        if self.bus is None:
            return

        try:
            introspection = await self.bus.introspect(
                DBUS_NAME,
                DBUS_PATH,
            )

            obj = self.bus.get_proxy_object(
                DBUS_NAME,
                DBUS_PATH,
                introspection,
            )

            dbus = obj.get_interface("org.freedesktop.DBus")

            def owner_changed(
                name: str,
                old_owner: str,
                new_owner: str,
            ) -> None:
                if name == WATCHER_NAME and new_owner:
                    asyncio.create_task(self.register_status_notifier_item())

            dbus.on_name_owner_changed(owner_changed)

        except Exception as exc:
            print(
                "Unable to watch " f"StatusNotifierWatcher: {exc}",
                file=sys.stderr,
            )

    async def setup_dbus(
        self,
    ) -> None:
        self.bus = await MessageBus().connect()

        self.sni = StatusNotifierItem(self)

        self.menu = DBusMenu(self)

        self.bus.export(
            SNI_PATH,
            self.sni,
        )

        self.bus.export(
            MENU_PATH,
            self.menu,
        )

        await self.watch_status_notifier_watcher()

        await self.register_status_notifier_item()

    # ------------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------------

    async def shutdown(
        self,
    ) -> None:
        if self.shutting_down:
            return

        self.shutting_down = True

        print("Shutting down ComfyUI launcher...")

        await self.stop_comfyui()

        self.remove_launcher_pid()

        if self.bus is not None:
            try:
                self.bus.disconnect()

            except Exception:
                pass

        self.shutdown_event.set()

    # ------------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------------

    async def run(
        self,
    ) -> int:
        if not self.check_environment():
            return 1

        if not self.acquire_instance_lock():
            # An existing launcher owns the lock.
            # Treat another invocation as "open WebUI".
            self.open_webui()
            return 0

        self.write_launcher_pid()

        loop = asyncio.get_running_loop()

        def request_shutdown() -> None:
            asyncio.create_task(self.shutdown())

        for sig in (
            signal.SIGTERM,
            signal.SIGINT,
        ):
            loop.add_signal_handler(
                sig,
                request_shutdown,
            )

        try:
            await self.setup_dbus()

        except Exception as exc:
            print(
                f"Failed to initialize tray D-Bus service: {exc}",
                file=sys.stderr,
            )

            self.remove_launcher_pid()

            return 1

        if not await self.start_comfyui(
            open_when_ready=False,
        ):
            self.remove_launcher_pid()

            if self.bus is not None:
                self.bus.disconnect()

            return 1

        await self.shutdown_event.wait()

        return 0


# ============================================================================
# Entry point
# ============================================================================


async def async_main() -> int:
    try:
        launcher = ComfyUILauncher()

    except RuntimeError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    return await launcher.run()


def main() -> int:
    try:
        return asyncio.run(async_main())

    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
