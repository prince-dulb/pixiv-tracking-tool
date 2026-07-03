import sys
import traceback

if __name__ == "__main__":
    try:
        from src.tray import run_tray
        run_tray()
    except Exception:
        print("\n启动失败：")
        traceback.print_exc()
        print("\n按 Enter 退出...")
        input()
        sys.exit(1)
