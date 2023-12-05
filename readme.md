# Molchip FTP Synchronizer
Python FTP远程同步

## Requirements
两台设备均能够访问同一台ftp服务器，并且均具有读写权限

## Usage
### Remote device:
```shell
# 启动服务器
python ftp_sync.py --listen
```

### Client:
```shell
# 上传文件
python ftp_sync.py --push foo/my_file.abc foo/dictionary

# 执行命令
python ftp_sync.py --exec "echo hello world"

# 下载文件
python ftp_sync.py --pull foo/my_result.abc

# 以上操作组合（顺序执行）
python ftp_sync.py --push foo/my_file.abc foo/dictionary --exec "echo hello world" --pull foo/my_result.abc

# 伪SSH模式
python ftp_sync.py --ssh
```

