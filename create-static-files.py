from pygments.formatters import HtmlFormatter


def main():
    with open("desktopsearch/static/highlight.css", "w", encoding="ascii", newline="\n") as fw:
        text = HtmlFormatter().get_style_defs(".highlight")
        fw.write(text)


if __name__ == "__main__":
    main()
