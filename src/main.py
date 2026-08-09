# main.py — 程序入口
#
# 此文件主要负责：
#  - 创建 TetrisApp 并启动主事件循环

from tetris import TetrisApp


def main() -> None:
    app = TetrisApp()
    app.run()


if __name__ == "__main__":
    main()
