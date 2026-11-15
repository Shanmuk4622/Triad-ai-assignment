"""Run Triad's original upload assertion with the assignment's login and a real PDF."""

import argparse
import os
from functools import partial
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from secrets import token_urlsafe
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

import requests

from sample_document import scanned_document


def run_starter(script_path, base_url, report_path):
    script_path = script_path.resolve(strict=True)
    report_path = report_path.resolve()
    spec = spec_from_file_location("triad_starter", script_path)
    starter = module_from_spec(spec)
    spec.loader.exec_module(starter)

    username = f"triad-test-{uuid4().hex[:12]}"
    credentials = {"username": username, "password": token_urlsafe(18)}
    with requests.Session() as client, TemporaryDirectory(prefix="triad-test-") as folder:
        registration = client.post(
            f"{base_url}/auth/register", json={**credentials, "division": "Division A"}, timeout=20
        )
        registration.raise_for_status()
        login = client.post(f"{base_url}/auth/login", json=credentials, timeout=20)
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['token']}"

        # The starter uses requests.post directly. Give it the authenticated session.
        starter.requests = SimpleNamespace(post=partial(client.post, timeout=90), exceptions=requests.exceptions)
        starter.BASE_URL = base_url
        starter.REPORT_FILE = str(report_path)
        original_directory = Path.cwd()
        try:
            os.chdir(folder)
            Path("test_sample.pdf").write_bytes(scanned_document())
            starter.test_document_upload()
            starter.generate_report()
        finally:
            os.chdir(original_directory)

    print(report_path.read_text(), end="")
    return int(starter.results["failed"] > 0 or starter.results["total"] == 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path, help="Path to Triad's downloaded test_api.py")
    parser.add_argument("--base-url", default="http://localhost:7860/api")
    parser.add_argument("--report", type=Path, default=Path("triad_starter_report.txt"))
    args = parser.parse_args()
    raise SystemExit(run_starter(args.script, args.base_url.rstrip("/"), args.report))
