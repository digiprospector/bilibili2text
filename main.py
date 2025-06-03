from config import config
import sys
import argparse
import subprocess
from pathlib import Path # pathlib for path operations

if __name__ == '__main__':
    # Setup argument parser
    parser = argparse.ArgumentParser(description="处理B站视频URL并将其转换为文本。")
    parser.add_argument("url", help="需要处理的B站视频URL") # Positional, required by default
    
    # Parse arguments (handles errors/help automatically)
    args = parser.parse_args()
    url = args.url

    # Convert config paths to Path objects early for consistent handling
    temp_dir_path_str = config.get("temp_dir")
    if not temp_dir_path_str:
        print("错误：配置中未提供 'temp_dir'。", file=sys.stderr)
        sys.exit(1)
    temp_dir_path = Path(temp_dir_path_str)

    BVID = ""
    if "www.bilibili.com" in url:
        BVID = url.split("/")[-1].split("?")[0]
    elif url.startswith("BV"):
        BVID = url

    if BVID:
        url = f"https://www.bilibili.com/video/{BVID}"
        
        # 下载
        print(f"准备使用标准化 URL 下载: {url}")

        # 构建下载命令
        # 示例：假设您有一个名为 'my_downloader.exe' 的下载工具
        # 并且它接受 URL 作为第一个参数，可能还需要一个输出路径
        # 您需要根据您的实际下载工具和参数进行调整
        download_command = [
            "python.exe",
            config.get("downloader"),
            "-a",
            url,
            "-p",
            str(temp_dir_path) # Pass temp_dir as a string argument
        ]
        
        download_result = False
        try:
            print(f"执行下载命令: {' '.join(download_command)}")
            # 执行命令
            # check=True 会在命令返回非零退出码时抛出 CalledProcessError
            result = subprocess.run(download_command, check=True, capture_output=True, text=True)
            print("下载命令成功执行。")
            print("输出:", result.stdout)
            download_result = True
        except subprocess.CalledProcessError as e:
            print(f"下载命令执行失败，返回码: {e.returncode}", file=sys.stderr)
            print("错误输出:", e.stderr, file=sys.stderr)
        except FileNotFoundError:
            print(f"错误：找不到下载命令 '{download_command[0]}'. 请确保它在您的 PATH 中或提供了完整路径。", file=sys.stderr)
        except Exception as e:
            print(f"执行下载命令时发生未知错误: {e}", file=sys.stderr)
            
        if download_result:
            # 检查下载文件是否存在且以 [BVID] 开头
            if not temp_dir_path.is_dir():
                print(f"错误：指定的临时目录 '{temp_dir_path}' 不存在或不是一个目录。", file=sys.stderr)
            else:
                found_matching_file_path = None
                # Iterate through items in the temp directory
                excluded_suffixes = {'.json', '.srt', '.lrc', '.txt', '.text', '.vtt', '.tsv'}
                for item_path in temp_dir_path.iterdir():
                    # Check if it's a file and its name starts with the BVID pattern
                    # 同时排除指定后缀集合中的文件
                    if item_path.is_file() and item_path.name.startswith(f"[{BVID}]") \
                       and item_path.suffix not in excluded_suffixes:
                        found_matching_file_path = item_path
                        print(f"在目录 '{temp_dir_path}' 中找到以 '[{BVID}]' 开头的文件: {item_path.name}")
                        break # 找到一个即可
                
                if not found_matching_file_path:
                    print(f"在目录 '{temp_dir_path}' 中未找到以 '[{BVID}]' 开头的文件。")
                else:
                    # 转换 (STT - Speech To Text)
                    stt_command = [
                        config.get("stt"),
                        "-l",
                        "Chinese",
                        f"--output_dir={str(temp_dir_path)}", # Use Path object, converted to string
                        "--output_format=all",
                        "--model=small",
                        str(found_matching_file_path) # Pass the full path of the found file
                    ]
                    
                    try:
                        print(f"执行 STT 转换命令: {' '.join(stt_command)}")
                        # 执行命令
                        # check=True 会在命令返回非零退出码时抛出 CalledProcessError
                        result = subprocess.run(stt_command, check=True, capture_output=True, text=True, encoding='utf-8')
                        print("STT 转换命令成功执行。")
                        print("输出:", result.stdout)
                    except subprocess.CalledProcessError as e:
                        print(f"STT 转换命令执行失败，返回码: {e.returncode}", file=sys.stderr)
                        print("错误输出:", e.stderr, file=sys.stderr)
                    except FileNotFoundError:
                        print(f"错误：找不到 STT 命令 '{stt_command[0]}'. 请确保它在您的 PATH 中或提供了完整路径，并且在 config 中配置正确。", file=sys.stderr)
                    except Exception as e:
                        print(f"执行 STT 转换命令时发生未知错误: {e}", file=sys.stderr)
