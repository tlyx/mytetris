from tetris import TetrisApp

# 🎯 动态引入打包引擎生成的版本号，开发环境（无该文件）时自动回退
try:
    from _version import __version__
except ImportError:
    __version__ = "0.8.5"

def main() -> None:
    # 启动时在控制台显示版本号
    print(f"Tetris v{__version__} (macOS Lab)")
    app = TetrisApp()
    app.run()

if __name__ == "__main__":
    main()
