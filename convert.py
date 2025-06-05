from config import config
import sys
import argparse
import subprocess
from pathlib import Path # pathlib for path operations
import logging # Import the logging module

def run_subprocess_with_hidden_window(command_list, check=True, capture_output=True, text=True, encoding=None):
    """
    Executes a subprocess command, hiding the console window on Windows.
    Wraps subprocess.run with common parameters and creationflags logic.
    """
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW
    
    logging.info(f"执行命令: {' '.join(command_list)}")
    return subprocess.run(
        command_list,
        check=check,
        capture_output=capture_output,
        text=text,
        encoding=encoding,
        creationflags=creation_flags
    )


if __name__ == '__main__':
    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) # Set the logging level

    # Create a formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Create a handler for stdout
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Create a handler for logging to a file
    # __file__ is the path to the current script. Path(__file__).resolve().parent gives the directory.
    log_file_path = Path(__file__).resolve().parent / "convert.log"
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8') # 'a' for append
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Setup argument parser
    parser = argparse.ArgumentParser(description="处理B站视频URL并将其转换为文本。日志将输出到标准输出。")
    parser.add_argument("url", help="需要处理的B站视频URL") # Positional, required by default
    
    # Parse arguments (handles errors/help automatically)
    args = parser.parse_args()
    url = args.url

    # Convert config paths to Path objects early for consistent handling
    temp_dir_path_str = config.get("temp_dir")
    if not temp_dir_path_str:
        logging.error("配置中未提供 'temp_dir'。")
        sys.exit(1)
    temp_dir_path = Path(temp_dir_path_str)

    downloader_path_str = config.get("downloader")
    if not downloader_path_str or not Path(downloader_path_str).is_file():
        logging.error(f"配置中的 'downloader' 路径 '{downloader_path_str}' 无效或文件不存在。")
        sys.exit(1)
    downloader_path = Path(downloader_path_str)

    stt_executable_path_str = config.get("stt")
    if not stt_executable_path_str or not Path(stt_executable_path_str).is_file():
        logging.error(f"配置中的 'stt' 路径 '{stt_executable_path_str}' 无效或文件不存在。")
        sys.exit(1)
    stt_executable_path = Path(stt_executable_path_str)



    BVID = ""
    if "www.bilibili.com" in url:
        BVID = url.split("/")[-1].split("?")[0]
    elif url.startswith("BV"):
        BVID = url

    if BVID:
        url = f"https://www.bilibili.com/video/{BVID}"
        
        # 下载
        logging.info(f"准备使用标准化 URL 下载: {url}")

        # 构建下载命令
        # 示例：假设您有一个名为 'my_downloader.exe' 的下载工具
        # 并且它接受 URL 作为第一个参数，可能还需要一个输出路径
        # 您需要根据您的实际下载工具和参数进行调整
        download_command = [
            sys.executable, # 使用当前Python解释器
            str(downloader_path),
            "-a",
            url,
            "-p",
            str(temp_dir_path) # Pass temp_dir as a string argument
        ]
        
        download_result = False
        try:
            result = run_subprocess_with_hidden_window(
                download_command
            )
            logging.info("下载命令成功执行。")
            if result.stdout:
                logging.info(f"下载命令输出:\n{result.stdout}")
            download_result = True
        except subprocess.CalledProcessError as e:
            logging.error(f"下载命令执行失败，返回码: {e.returncode}")
            if e.stderr:
                logging.error(f"下载命令错误输出:\n{e.stderr}")
            if e.stdout: # Log stdout as well, as it might contain useful info
                logging.info(f"下载命令标准输出 (即使失败):\n{e.stdout}")
        except FileNotFoundError:
            logging.error(f"找不到命令 '{download_command[0]}'. 请确保Python解释器路径正确，且脚本路径 '{downloader_path}' 有效。")
        except Exception as e:
            logging.exception("执行下载命令时发生未知错误:")
            
        if download_result:
            # 检查下载文件是否存在且以 [BVID] 开头
            if not temp_dir_path.is_dir():
                logging.error(f"指定的临时目录 '{temp_dir_path}' 不存在或不是一个目录。")
            else:
                found_matching_file_path = None
                # Iterate through items in the temp directory
                excluded_suffixes = {'.json', '.srt', '.lrc', '.txt', '.text', '.vtt', '.tsv'}
                for item_path in temp_dir_path.iterdir():
                    if item_path.is_file() and item_path.name.startswith(f"[{BVID}]") \
                       and item_path.suffix not in excluded_suffixes:
                        found_matching_file_path = item_path
                        logging.info(f"在目录 '{temp_dir_path}' 中找到以 '[{BVID}]' 开头的文件: {item_path.name}")
                        break # 找到一个即可
                
                if not found_matching_file_path:
                    logging.warning(f"在目录 '{temp_dir_path}' 中未找到以 '[{BVID}]' 开头且符合后缀要求的文件。")
                else:
                    # 转换 (STT - Speech To Text)
                    stt_command = [
                        str(stt_executable_path),
                        "-l",
                        "Chinese",
                        f"--output_dir={str(temp_dir_path)}", # Use Path object, converted to string
                        "--output_format=all",
                        "--model=small",
                        str(found_matching_file_path) # Pass the full path of the found file
                    ]
                    
                    try:
                        result = run_subprocess_with_hidden_window(
                            stt_command,
                            encoding='utf-8' # STT可能需要指定编码
                        )
                        logging.info("STT 转换命令成功执行。")
                        if result.stdout:
                            logging.info(f"STT 命令输出:\n{result.stdout}")

                        # STT成功后，删除指定的临时文件
                        files_to_delete_suffixes = {'.tsv', '.json', '.lrc', '.vtt'}
                        logging.info(f"准备删除以下类型的临时文件: {files_to_delete_suffixes}")
                        for item_path in temp_dir_path.iterdir():
                            if item_path.is_file() and \
                               item_path.name.startswith(f"[{BVID}]") and \
                               item_path.suffix.lower() in files_to_delete_suffixes:
                                try:
                                    item_path.unlink() # 删除文件
                                    logging.info(f"已删除临时文件: {item_path.name}")
                                except OSError as e:
                                    logging.error(f"删除临时文件 {item_path.name} 失败: {e}")

                    except subprocess.CalledProcessError as e:
                        logging.error(f"STT 转换命令执行失败，返回码: {e.returncode}")
                        if e.stderr:
                            logging.error(f"STT 命令错误输出:\n{e.stderr}")
                        if e.stdout:
                            logging.info(f"STT 命令标准输出 (即使失败):\n{e.stdout}")
                    except FileNotFoundError:
                        logging.error(f"找不到 STT 命令 '{stt_command[0]}'. 请确保路径 '{stt_executable_path}' 配置正确且文件存在。")
                    except Exception as e:
                        logging.exception("执行 STT 转换命令时发生未知错误:")
    else:
        logging.warning(f"未能从输入URL/ID '{url}' 中提取有效的BVID。")
