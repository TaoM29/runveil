import errno
import os
import socket
import unittest
from pathlib import Path


class BoundaryTests(unittest.TestCase):
    def test_isolation(self) -> None:
        self.assertEqual((os.getuid(), os.getgid()), (65532, 65532))
        self.assertFalse(Path("/var/run/docker.sock").exists())
        self.assertEqual(set(os.environ), {"PATH", "HOME", "LANG"})
        status = Path("/proc/self/status").read_text()
        self.assertIn("CapEff:\t0000000000000000", status)
        self.assertIn("NoNewPrivs:\t1", status)
        self.assertIn("Seccomp:\t2", status)
        self.assertEqual(Path("/sys/fs/cgroup/memory.max").read_text().strip(), "134217728")
        self.assertEqual(Path("/sys/fs/cgroup/pids.max").read_text().strip(), "32")
        self.assertEqual(Path("/sys/fs/cgroup/cpu.max").read_text().split(), ["50000", "100000"])
        with self.assertRaises(OSError) as denied:
            Path("/opt/forbidden").write_text("x")
        self.assertEqual(denied.exception.errno, errno.EROFS)
        Path("disposable.txt").write_text("workspace writable")
        with socket.socket() as sock:
            sock.settimeout(0.5)
            with self.assertRaises(OSError):
                sock.connect(("192.0.2.1", 80))
