from pygments.formatters import HtmlFormatter

with open("static/highlight.css", "w", encoding="ascii", newline="\n") as fw:
    text = HtmlFormatter().get_style_defs(".highlight")
    fw.write(text)
