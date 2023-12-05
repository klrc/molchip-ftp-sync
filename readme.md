# Molchip FTP Synchronizer
Python FTP远程同步

## 设备要求
两台设备均能够访问同一台ftp服务器，并且均具有读写权限

## 使用方法
### 1. 配置yaml文件
```shell
cp server.yaml.example server.yaml 
cp task.yaml.example task.yaml 
vim server.yaml
vim task.yaml
```

### 2. 远程设备启动监听
```shell
# 启动服务器
python ftp_sync.py -c server.yaml
```

### 3. 本地设备操作
```shell
#
# 上传文件/执行命令/下载文件（任意组合顺序执行）
python ftp_sync.py -c task.yaml
```

