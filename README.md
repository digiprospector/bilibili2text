# bilibili2text
download bilibili video then convert to text

需要 https://github.com/digiprospector/BilibiliDownloader 和 https://github.com/Purfview/whisper-standalone-win

在 config.py 文件里配置
- downloader: BilibiliDownloader的src/main.py文件
- stt: whisper-standalone-win的faster-whisper-xxl.exe文件
- temp_dir: 临时目录,下载的音频文件和生成的文件都放在这里