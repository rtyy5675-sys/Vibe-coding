"""Command-line entry point for the local evaluation MVP."""

import argparse

from mvp.app import create_app


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8766, type=int)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    create_app().run(host=arguments.host, port=arguments.port)
