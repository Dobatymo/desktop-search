from cheroot.wsgi import Server

from wsgi import app

if __name__ == "__main__":

    from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser

    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    args = parser.parse_args()

    server = Server((args.host, args.port), app)
    app.config["close"] = server.stop

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
