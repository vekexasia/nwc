"""Run with: python -m unittest discover -s Tools/nw_capture -p 'test_*.py'."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

# These tests never connect to Frida, even when it is installed.
sys.modules.setdefault("frida", types.SimpleNamespace())
import _runner
import nw_capture
import extract_https_pairs


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("CAPTURES_ROOT", "LOGS_DIR"):
            p = patch.object(_runner, name, self.root / name)
            p.start()
            self.addCleanup(p.stop)
        self.frida = Mock()
        self.frida.ProcessNotFoundError = ProcessLookupError
        p = patch.object(_runner, "frida", self.frida)
        p.start()
        self.addCleanup(p.stop)
        self.device = self.frida.get_device_manager.return_value.add_remote_device.return_value
        self.device.query_system_parameters.return_value = {"platform": "windows", "arch": "x64"}
        self.session = self.device.attach.return_value
        del self.session.unload  # A real Frida Session only has detach().
        self.script = self.session.create_script.return_value
        self.order = []
        self.runner = _runner.FridaRunner(None, ["nw_https_tap.js"],
                                         host="127.0.0.1:27943", pid=123, timeout_s=0.001)
        self.script.exports_sync.stop.side_effect = self.stop
        self.script.unload.side_effect = lambda: self.check_open("unload")
        self.session.detach.side_effect = lambda: self.check_open("detach")

    def check_open(self, step):
        self.assertFalse(self.runner._ledger_f.closed)
        self.assertFalse(self.runner._keylog_f.closed)
        self.assertFalse(self.runner._log_file.closed)
        self.order.append(step)

    def stop(self):
        self.check_open("stop")
        # Deliver final messages on another thread, not through the RPC return.
        def deliver():
            self.runner._on_message({"type": "send", "payload": {"type": "dtls_ledger"}}, b"last")
            self.order.append("received")
            self.runner._on_message({"type": "send", "payload": {
                "type": "capture_stopped", "dtls": {"bytes": 4, "flushes": 1, "keylog": 0}}}, None)
        t = threading.Thread(target=deliver)
        t.start()
        self.addCleanup(t.join)

    def run_capture(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.runner.run()

    def assert_attach_only(self):
        self.frida.get_local_device.assert_not_called()
        for obj in (self.frida, self.device):
            obj.spawn.assert_not_called()
            obj.resume.assert_not_called()
            obj.kill.assert_not_called()
        self.assertFalse(list(self.root.rglob("steam_appid.txt")))

    def test_timeout_flush_before_detach_and_close(self):
        original = Path.write_text
        writes = []
        def write(path, *args, **kwargs):
            writes.append(path.name)
            return original(path, *args, **kwargs)
        with patch.object(Path, "write_text", write):
            self.assertEqual(self.run_capture(), 0)
        self.assertNotIn("steam_appid.txt", writes)
        self.assert_attach_only()
        self.device.attach.assert_called_once_with(123)
        self.assertEqual(self.order, ["stop", "received", "unload", "detach"])
        self.assertEqual(self.runner._ledger_path.read_bytes(), b"last")
        self.assertTrue(self.runner._ledger_f.closed)
        self.assertTrue(json.loads(self.runner._meta_path.read_text())["final_flush_acknowledged"])

    def test_ctrl_c_does_not_control_attached_process(self):
        self.runner._wait_for_exit = Mock(side_effect=KeyboardInterrupt)
        self.assertEqual(self.run_capture(), 0)
        self.assert_attach_only()
        self.assertEqual(self.order[-2:], ["unload", "detach"])

    def test_install_failure_still_detaches(self):
        self.script.exports_sync.install.side_effect = RuntimeError("unsupported build")
        with self.assertRaisesRegex(RuntimeError, "unsupported build"):
            self.run_capture()
        self.assert_attach_only()
        self.session.detach.assert_called_once()

    def test_wrong_remote_server_rejected_before_attach(self):
        for params in ({"platform": "linux", "arch": "x64"},
                       {"platform": "windows", "arch": "ia32"}, {}):
            self.device.query_system_parameters.return_value = params
            with self.assertRaisesRegex(RuntimeError, "refusing attach"):
                self.run_capture()
            self.device.attach.assert_not_called()
            self.assert_attach_only()

    def test_remote_failure_has_no_local_fallback(self):
        self.frida.get_device_manager.return_value.add_remote_device.side_effect = RuntimeError("offline")
        with self.assertRaisesRegex(RuntimeError, "offline"):
            self.run_capture()
        self.assert_attach_only()

    def test_missing_ack_is_incomplete(self):
        self.script.exports_sync.stop.side_effect = lambda: None
        self.runner._stopped = Mock()
        self.runner._stopped.wait.return_value = False
        self.runner._stopped.is_set.return_value = False
        self.assertEqual(self.run_capture(), 2)
        self.assertFalse(json.loads(self.runner._meta_path.read_text())["final_flush_acknowledged"])
        self.assert_attach_only()

    def test_count_mismatch_is_not_acknowledged(self):
        self.runner._on_message({"type": "send", "payload": {
            "type": "capture_stopped", "dtls": {"bytes": 1, "flushes": 1, "keylog": 0}}}, None)
        self.assertFalse(self.runner._stopped.is_set())
        self.assertEqual(self.runner.exit_code, 2)

    def test_invalid_stop_stats_are_not_acknowledged(self):
        for stats in (None, {}, [], {"bytes": False, "flushes": 0, "keylog": 0}):
            with self.subTest(stats=stats):
                self.runner._on_message({"type": "send", "payload": {
                    "type": "capture_stopped", "dtls": stats}}, None)
                self.assertFalse(self.runner._stopped.is_set())
                self.assertEqual(self.runner.exit_code, 2)
        self.runner._on_message({"type": "send", "payload": {"type": "capture_stopped"}}, None)
        self.assertFalse(self.runner._stopped.is_set())

    def test_final_flush_failure_is_incomplete(self):
        open_sinks = self.runner._open_dtls_sinks
        def failing_sink():
            open_sinks()
            real = self.runner._ledger_f
            self.runner._ledger_f = Mock(wraps=real)
            self.runner._ledger_f.flush.side_effect = OSError("disk full")
            self.runner._ledger_f.closed = False
        self.runner._open_dtls_sinks = failing_sink
        self.assertEqual(self.run_capture(), 2)
        self.assertFalse(json.loads(self.runner._meta_path.read_text())["sink_write_succeeded"])
        self.runner._ledger_f.close.assert_called_once()
        self.assert_attach_only()

    def test_unlimited_capture_manual_stop(self):
        _runner.validate_mode(None, "server:123", 42, 0)
        self.runner.timeout_s = 0
        self.runner._detached = Mock()
        self.runner._detached.wait.side_effect = KeyboardInterrupt
        self.assertEqual(self.run_capture(), 0)
        self.runner._detached.wait.assert_called_once_with(timeout=None)
        self.assertEqual(self.order, ["stop", "received", "unload", "detach"])
        self.assertTrue(json.loads(self.runner._meta_path.read_text())["final_flush_acknowledged"])
        self.assert_attach_only()

    def test_proton_launcher_cleanup_order(self):
        game = types.SimpleNamespace(name="NewWorld.exe", pid=123)
        server = types.SimpleNamespace(name="frida-server.exe", pid=456)
        self.device.enumerate_processes.return_value = [game, server]
        runner = Mock(log_path=self.root / "capture.log")
        runner.run.side_effect = lambda: self.order.append("capture_stopped") or 0
        self.device.kill.side_effect = lambda pid: self.order.append("server_stopped")
        source = (_runner.HERE / "capture_proton.py").read_text()
        with patch.dict(sys.modules, {"frida": self.frida}), \
             patch.object(sys, 'argv', ['capture_proton.py', '--launch', '--timeout', '120', '--steam-dir', '/home/gamer/.steam/debian-installation']), \
             patch('subprocess.run', side_effect=[Mock(returncode=1), Mock(returncode=1), Mock(returncode=0)]) as detect, \
             patch('time.sleep'), \
             patch.object(nw_capture, "HttpsTapRunner", return_value=runner) as factory, \
             patch.object(nw_capture, "run_extractor", return_value=0), \
             patch("subprocess.Popen") as process, patch("socket.create_connection"), \
             patch("os.umask"), contextlib.redirect_stdout(io.StringIO()), \
             self.assertRaises(SystemExit) as cm:
            exec(compile(source, "capture_proton.py", "exec"),
                 {"__file__": str(self.root / "capture_proton.py")})
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(factory.call_args.args[1], 120)
        server_call = process.call_args_list[1]
        steamapps = '/home/gamer/.steam/debian-installation/steamapps'
        self.assertEqual(server_call.args[0][0], steamapps + '/common/SteamLinuxRuntime_4/run')
        self.assertEqual(server_call.args[0][2], steamapps + '/common/Proton 11.0/files/bin/wine')
        self.assertEqual(server_call.kwargs['env']['WINEPREFIX'], steamapps + '/compatdata/1063730/pfx')
        self.assertEqual(self.order, ["capture_stopped", "server_stopped"])
        self.device.kill.assert_called_once_with(456)
        process.return_value.wait.assert_called_once_with(timeout=10)
        self.assertEqual(detect.call_count, 3)
        self.assertEqual(process.call_args_list[0].args[0], ['steam', '-applaunch', '1063730'])
        self.assertIn('frida-server.exe', process.call_args_list[1].args[0][3])

    def test_validation(self):
        for target, host, pid, timeout in [
            (None, None, 1, 1), (None, "server", None, 1),
            ("game.exe", "server", 1, 1), (None, "", 1, 1),
            (None, "server", 0, 1), (None, "server", -1, 1),
            (None, "server", 1, -1), (None, "server", 1, float("nan")),
            (None, "server", 1, float("inf")), (None, None, None, 1),
        ]:
            with self.subTest(target=target, host=host, pid=pid, timeout=timeout):
                with self.assertRaises(ValueError):
                    _runner.validate_mode(target, host, pid, timeout)
        _runner.validate_mode("game.exe", None, None, 600)
        _runner.validate_mode(None, "server:123", 42, 600)
        with patch.object(sys, "argv", ["nw_capture.py", "--pid", "12"]), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            nw_capture.main()
        self.assertEqual(cm.exception.code, 2)

    def test_native_linux_spawn_refused(self):
        self.runner.attach_pid = None
        self.runner.target_path = "NewWorld.exe"
        with patch.object(sys, "platform", "linux"), self.assertRaisesRegex(RuntimeError, "requires Windows"):
            self.run_capture()
        self.frida.get_local_device.assert_not_called()

    def test_windows_spawn_preserved(self):
        target = self.root / "NewWorld.exe"
        target.touch()
        self.runner.attach_pid = None
        self.runner.target_path = str(target)
        self.frida.get_local_device.return_value = self.device
        self.device.spawn.return_value = 456
        with patch.object(sys, "platform", "win32"):
            self.assertEqual(self.run_capture(), 0)
        self.assertEqual(target.with_name("steam_appid.txt").read_text(), "1063730\n")
        self.device.spawn.assert_called_once_with(str(target))
        self.device.resume.assert_called_once_with(456)
        self.device.kill.assert_called_once_with(456)

    def test_js_and_offline_formats(self):
        ledger = self.root / "ledger.bin"
        events = self.root / "events.jsonl"
        subprocess.run(["node", str(_runner.HERE / "test_agent.js"), str(ledger), str(events)], check=True)
        requests = extract_https_pairs.parse(events)
        self.assertEqual(len(requests), 2)
        self.assertEqual([r.response_body.joined_text for r in requests], ["hello", "hello"])
        try:
            import decode_dtls_ledger
        except SystemExit:
            self.skipTest("lz4 not installed; JS and extractor checks passed")
        records = list(decode_dtls_ledger.iter_ledger(ledger))
        self.assertEqual(len(records), 1)
        decoded = decode_dtls_ledger.decode_record(*records[0])
        self.assertIsNone(decoded.error)
        self.assertEqual(decoded.messages[0].payload, b"hi")


if __name__ == "__main__":
    unittest.main()
