"""
webview_app.py — 用 pywebview 将 Flask Web UI 包装为原生桌面窗口
无需打开浏览器，体验接近原版 WPF。

依赖：
    pip install flask pywebview

启动：
    python webview_app.py
"""
import threading
import webbrowser
import time

from app import app


def start_flask() -> None:
    """在后台线程启动 Flask，关闭 reloader 避免多进程冲突。"""
    app.run(port=5000, use_reloader=False, debug=False)


def main() -> None:
    # 尝试用 pywebview 嵌入原生窗口
    try:
        import webview  # type: ignore

        t = threading.Thread(target=start_flask, daemon=True)
        t.start()
        time.sleep(0.8)  # 等 Flask 就绪

        webview.create_window(
            "TraceLogic",
            "http://localhost:5000",
            width=1280,
            height=800,
            resizable=True,
        )
        webview.start()

    except ImportError:
        # pywebview 未安装时，fallback 到浏览器模式
        print("pywebview 未安装，使用浏览器模式")
        print("访问 http://localhost:5000")
        t = threading.Thread(target=start_flask, daemon=True)
        t.start()
        time.sleep(0.8)
        webbrowser.open("http://localhost:5000")
        # 保持主线程存活
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n已退出")


if __name__ == "__main__":
    main()
