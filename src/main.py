# main.py — 程序入口
#
# 此文件主要负责：
#  - 创建 GameApp 并启动主事件循环

from app import GameApp


def main() -> None:
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
