"""Synthetic Lua integration, not X4 or real client networking."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class JobDeliveryHostIntegration(unittest.TestCase):
    def test_waits_for_both_clients_and_source_ack_receipt(self):
        subprocess.run(['luajit', 'tests/authority_job_delivery_host_integration.lua'],
                       cwd=ROOT, check=True, capture_output=True, text=True, timeout=5)

if __name__ == '__main__':
    unittest.main()
