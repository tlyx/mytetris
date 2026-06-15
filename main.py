from tetris import TetrisApp

__version__ = "0.8.5"

def main() -> None:
    # 启动时在控制台显示版本号
    print(f"Tetris v{__version__} (macOS Lab)")
    app = TetrisApp()
    app.run()

if __name__ == "__main__":
    main()
