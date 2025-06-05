import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import pyperclip
import subprocess
from pynput import keyboard
import sys
import threading
import logging
from pathlib import Path
import queue # 导入队列模块


# --- 配置区域 ---
# 快捷键组合，例如：'<ctrl>+<alt>+v' 表示 Ctrl + Alt + V
# 您可以根据 pynput 的文档修改：https://pynput.readthedocs.io/en/latest/keyboard.html#global-hotkeys
HOTKEY_STRING = "<ctrl>+<alt>+v"

# 图标文件的路径 (例如 .ico 或 .png 文件)
# 如果找不到该文件，程序会生成一个默认图标。
ICON_PATH = Path(__file__).resolve().parent / "icon.png"
TRAY_ICON_NAME = "bilibili2text"
TRAY_ICON_TITLE = "bilibili2text"
NOTIFICATION_CLIPBOARD_TRUNCATE_LENGTH = 30
# --- 配置区域结束 ---

# 全局变量，用于控制快捷键监听器和托盘图标
hotkey_listener = None
tray_icon = None
task_queue = queue.Queue() # 创建一个全局的任务队列
worker_thread = None # 工作线程的引用

def on_hotkey_activated():
    """当快捷键被按下时调用的回调函数。"""
    logging.info(f"快捷键 {HOTKEY_STRING} 已激活!")
    try:
        clipboard_content = pyperclip.paste()
        if clipboard_content:
            logging.info(f"剪贴板内容: \"{clipboard_content}\"")
            task_queue.put(clipboard_content) # 将剪贴板内容放入队列
            logging.info(f"任务已添加到队列: \"{clipboard_content}\"")
            if tray_icon:
                tray_icon.notify(f"任务已添加到队列。", "信息")
        else:
            logging.info("剪贴板为空。")
            if tray_icon:
                tray_icon.notify("剪贴板为空，未执行操作。", "信息")
    except pyperclip.PyperclipException as e:
        message = f"访问剪贴板时出错: {e}"
        logging.error(message)
        if tray_icon:
            tray_icon.notify(message, "剪贴板错误")
    except Exception as e:
        message = f"发生意外错误: {e}"
        logging.exception(message)
        if tray_icon:
            tray_icon.notify(message, "意外错误")

def worker():
    """工作线程函数，从队列中获取任务并执行。"""
    logging.info("工作线程已启动。")
    convert_script_path = Path(__file__).resolve().parent / "convert.py"
    if not convert_script_path.exists():
        logging.error(f"工作线程错误: 脚本 'convert.py' 未找到于 '{convert_script_path}'。工作线程将无法处理任务。")
        # 可以选择让工作线程在这里退出，或者继续运行但无法处理任务
        return # 如果 convert.py 找不到，工作线程无法工作

    while True:
        try:
            # 等待队列中的任务，设置超时以便能够响应退出信号
            clipboard_content = task_queue.get(timeout=1) 
            if clipboard_content is None: # 收到哨兵值，退出循环
                logging.info("工作线程收到退出信号，准备退出。")
                task_queue.task_done() # 标记哨兵任务完成
                break
            
            logging.info(f"工作线程正在处理任务: \"{clipboard_content}\"")
            try:
                if sys.platform == "win32":
                    creation_flags = subprocess.CREATE_NO_WINDOW
                
                process = subprocess.Popen(
                    [sys.executable, str(convert_script_path), clipboard_content],
                    creationflags=creation_flags
                )
                process.wait()  # 等待 convert.py 进程完成
                logging.info(f"convert.py 进程已完成，剪贴板内容: \"{clipboard_content}\", 返回码: {process.returncode}")
                if tray_icon: # 确保 tray_icon 对象存在
                    if process.returncode == 0:
                        tray_icon.notify(f"处理完成: {clipboard_content[:NOTIFICATION_CLIPBOARD_TRUNCATE_LENGTH]}...", "成功")
                    else:
                        tray_icon.notify(f"处理失败: {clipboard_content[:NOTIFICATION_CLIPBOARD_TRUNCATE_LENGTH]}... (返回码: {process.returncode})", "错误")

            except OSError as oe:
                logging.error(f"工作线程运行 convert.py 时发生OS错误: {oe}")
            except Exception as e:
                logging.exception(f"工作线程运行 convert.py 时发生未知错误:")
            finally:
                task_queue.task_done() # 标记任务完成
        except queue.Empty: # 队列在超时内为空，继续循环
            continue
        except Exception as e: # 捕获 worker 循环中的其他潜在错误
            logging.exception(f"工作线程发生意外错误: {e}")
            # 考虑是否应该在这种情况下中断工作线程

def start_hotkey_listener():
    """在单独的线程中启动全局快捷键监听器。"""
    global hotkey_listener
    # pynput.keyboard.GlobalHotKeys 的回调映射
    hotkey_map = {
        HOTKEY_STRING: on_hotkey_activated
    }
    # GlobalHotKeys 本身是一个线程
    hotkey_listener = keyboard.GlobalHotKeys(hotkey_map)
    logging.info(f"正在启动快捷键监听器: {HOTKEY_STRING}")
    hotkey_listener.start() # 开始监听

def stop_hotkey_listener():
    """停止全局快捷键监听器。"""
    global hotkey_listener
    if hotkey_listener and hotkey_listener.is_alive():
        logging.info("正在停止快捷键监听器...")
        try:
            hotkey_listener.stop()
            # hotkey_listener.join(timeout=1) # 等待线程结束，可选
        except Exception as e:
            logging.error(f"停止监听器时发生错误: {e}")
        hotkey_listener = None
        logging.info("快捷键监听器已停止。")
    elif hotkey_listener:  # Listener exists but not alive
        hotkey_listener = None # Just clear it
        logging.info("快捷键监听器已清理 (之前未在运行)。")


def exit_action(icon, item):
    """托盘菜单“退出”选项的回调函数。"""
    global worker_thread
    logging.info("触发退出操作。")
    stop_hotkey_listener() # 首先停止监听器
    
    # 向工作线程发送退出信号
    logging.info("正在向工作线程发送退出信号...")
    task_queue.put(None) # 放入哨兵值
    if worker_thread and worker_thread.is_alive():
        worker_thread.join(timeout=5) # 等待工作线程结束，设置超时
        logging.info(f"工作线程已 {'结束' if not worker_thread.is_alive() else '仍在运行 (超时)'}。")

    if tray_icon: # 使用全局 tray_icon 变量
        tray_icon.stop()  # 然后停止托盘图标的事件循环

def setup_tray_icon():
    """设置并运行系统托盘图标。"""
    global tray_icon # 声明我们要修改全局变量
    loaded_icon = None
    try:
        loaded_icon = Image.open(ICON_PATH)
        logging.info(f"已从 '{ICON_PATH}' 加载图标。")
    except Exception as e: # 捕获所有图标加载错误 (FileNotFoundError 是 Exception 的子类)
        logging.warning(f"加载主图标 '{ICON_PATH}' 失败: {e}。尝试使用回退图标。")
        try:
            # 创建一个最小的64x64透明图像作为回退
            loaded_icon = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            logging.info("已创建并使用透明的回退图标。")
        except Exception as fallback_e:
            logging.error(f"创建回退图标也失败: {fallback_e}。托盘图标可能无法显示。")
            loaded_icon = None # 如果连回退图标都创建失败

    # 定义托盘菜单项
    menu = (
        item('使用剪贴板内容运行程序 (手动)', on_hotkey_activated), # 用于测试或手动触发
        item('退出', exit_action)
    )
    
    tray_icon = pystray.Icon(TRAY_ICON_NAME, loaded_icon, TRAY_ICON_TITLE, menu)
    
    # 在托盘图标运行之前启动快捷键监听器
    # pynput.keyboard.GlobalHotKeys().start() 会在自己的线程中运行
    global worker_thread
    worker_thread = threading.Thread(target=worker, daemon=True) # 将工作线程设置为守护线程
    worker_thread.name = "TaskWorkerThread" # 给线程命名，方便日志查看
    worker_thread.start()

    start_hotkey_listener()
    
    logging.info("托盘图标和快捷键监听器已启动。程序正在系统托盘中运行。")
    # tray_icon.run() 是一个阻塞调用，它会运行pystray的事件循环
    # 直到调用 tray_icon.stop()
    tray_icon.run() 
    
    # 当 tray_icon.run() 结束后 (即 tray_icon.stop() 被调用后)
    logging.info("托盘图标事件循环已结束。")
    # 确保监听器也已停止 (尽管 exit_action 应该已经处理了)
    stop_hotkey_listener()
    # 确保工作线程也已停止 (exit_action 应该处理了，但作为双重检查)
    if worker_thread and worker_thread.is_alive():
        logging.info("尝试再次停止工作线程 (如果仍在运行)...")
        task_queue.put(None) # 再次尝试发送哨兵
        worker_thread.join(timeout=2)
        if worker_thread.is_alive():
            logging.warning("工作线程在最终尝试后仍未停止。")

if __name__ == "__main__":
    # --- Logging Setup ---
    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) # Set the logging level

    # Create a formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(module)s - %(funcName)s - %(message)s')

    # Create a handler for stdout
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Create a handler for logging to a file
    log_file_path = Path(__file__).resolve().parent / "daemon.log"
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8') # 'a' for append
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    # --- End Logging Setup ---

    logging.info("Daemon application starting...")
    try:
        convert_script_path = Path(__file__).resolve().parent / "convert.py"
        if not convert_script_path.exists():
            logging.error(f"无法找到 convert.py 文件于 '{convert_script_path}'。程序将退出。")
            # Consider exiting if convert.py is critical and not found
            sys.exit(1) # Exiting if convert.py is essential
        else:
            setup_tray_icon()
    except Exception:
        logging.exception("在主程序设置过程中发生严重错误。")
        stop_hotkey_listener()  # 确保清理监听器
    logging.info("Daemon application has shut down.")
