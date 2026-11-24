import sys
import asyncio
import threading
from typing import Optional, Coroutine, TypeVar, Any

T = TypeVar("T")


class ProactorLoopThread:
    """Quản lý một Event Loop Proactor riêng biệt trên Windows cho Playwright.
    
    Khắc phục triệt để lỗi NotImplementedError khi Uvicorn chạy SelectorEventLoop
    hoặc chế độ --reload trên Windows.
    """
    _instance: Optional["ProactorLoopThread"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    @classmethod
    def get_instance(cls) -> "ProactorLoopThread":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ProactorLoopThread()
                cls._instance.start()
            return cls._instance

    def start(self):
        def _run():
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self._ready.set()
            self.loop.run_forever()

        self.thread = threading.Thread(
            target=_run, daemon=True, name="ProactorPlaywrightWorkerLoop"
        )
        self.thread.start()
        self._ready.wait()

    def submit(self, coro: Coroutine[Any, Any, T]) -> asyncio.Future:
        """Đưa coroutine vào chạy trên loop Proactor và trả về Future có thể await từ bất kỳ loop nào."""
        if self.loop is None or not self.loop.is_running():
            raise RuntimeError("Proactor loop chưa được khởi động.")
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return asyncio.wrap_future(fut)

