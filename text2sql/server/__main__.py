import argparse
import threading
import webbrowser

import uvicorn

from text2sql.server.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description='Serve the Text2SQL web app')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [f'http://{args.host}:{args.port}']).start()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == '__main__':
    main()
