# Molchip FTP Synchronizer
Python FTP远程同步

## 设备要求
两台设备均能够访问同一台ftp服务器，并且均具有读写权限

## 使用方法
### 1. 配置yaml文件
```shell
cp example_config.yaml my_config.yaml && vim my_config.yaml
```

### 2. 远程设备启动监听
```shell
# 启动服务器
python ftp_sync.py --config my_config.yaml  --listen
```

### 3. 本地设备操作
```shell
# 上传文件
python ftp_sync.py --config my_config.yaml --push foo/my_file.abc foo/dictionary

# 执行命令
python ftp_sync.py --config my_config.yaml --exec "echo hello world"

# 下载文件
python ftp_sync.py --config my_config.yaml --pull foo/my_result.abc

# 以上操作组合（顺序执行）
python ftp_sync.py --config my_config.yaml --push foo/my_file.abc foo/dictionary --exec "echo hello world" --pull foo/my_result.abc

# 伪SSH模式
python ftp_sync.py --config my_config.yaml --ssh
```

