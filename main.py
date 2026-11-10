"""
Mindcode Image Converter for Mindustry 160.7
Главная точка входа.

- Без аргументов: запускает графический интерфейс (GUI).
- С аргументами: запускает интерфейс командной строки (CLI).
"""

import sys


def main():
    if len(sys.argv) > 1:
        import cli
        cli.main()
    else:
        import gui
        gui.main()


if __name__ == "__main__":
    main()

