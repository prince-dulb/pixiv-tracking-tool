import sys
import traceback
import webbrowser

if __name__ == "__main__":
    try:
        from src.web import main
        # 启动后自动打开浏览器访问画廊
        def open_browser():
            import time
            time.sleep(2)
            webbrowser.open("http://localhost:8000")

        import threading
        threading.Thread(target=open_browser, daemon=True).start()

        main()
    except Exception:
        print("\n启动失败：")
        traceback.print_exc()
        print("\n按 Enter 退出...")
        input()
        sys.exit(1)
