import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock


class WorkerTests(unittest.TestCase):
    def test_failed_start_does_not_publish_running(self):
        source = ast.parse(Path(__file__).with_name('worker.py').read_text())
        definition = next(node for node in source.body if isinstance(node, ast.ClassDef))
        cleanup = Mock()
        base = type('Base', (), {'_cleanup': cleanup})
        namespace = {'nw_capture': types.SimpleNamespace(HttpsTapRunner=base)}
        exec(compile(ast.Module(body=[definition], type_ignores=[]), 'worker.py', 'exec'), namespace)
        runner = namespace['ManagedRunner']()
        runner.publish = Mock()
        runner._cleanup()
        runner.publish.assert_not_called()
        cleanup.assert_called_once()
        runner._web_ready = True
        runner._cleanup()
        runner.publish.assert_called_once()


if __name__ == '__main__':
    unittest.main()
