from core.parser_app import ParserApp

def main():
    app = ParserApp()
    try:
        app.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()