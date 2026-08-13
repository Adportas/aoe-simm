#!/usr/bin/env python3
"""Serve the local Web export with Apple's required USDZ media type."""

from __future__ import annotations

import argparse
import mimetypes
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> int:
	project_path = Path(__file__).resolve().parents[1]
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		"--directory",
		type=Path,
		default=project_path / "exports/web-preview",
	)
	parser.add_argument("--host", default="127.0.0.1")
	parser.add_argument("--port", type=int, default=8060)
	args = parser.parse_args()

	mimetypes.add_type("model/vnd.usdz+zip", ".usdz")
	handler = partial(SimpleHTTPRequestHandler, directory=str(args.directory.resolve()))
	server = ThreadingHTTPServer((args.host, args.port), handler)
	print(f"Serving {args.directory.resolve()} at http://{args.host}:{args.port}")
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		pass
	finally:
		server.server_close()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
