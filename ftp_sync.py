import os
import time
import tarfile
import argparse
from ftplib import FTP
from loguru import logger
import sys
import yaml

logger.configure(handlers=[{"sink": sys.stderr, "format": "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{message}</level>"}])


class FTPSync:
    def __init__(self, yaml_file) -> None:
        self.sync_id = None
        self.sync_mode = None
        self.ftp_host = None
        self.ftp_username = None
        self.ftp_password = None
        self.ftp_encoding = None
        self.workdir = os.getcwd()
        with open(yaml_file, "r") as f:
            config = yaml.load(f, Loader=yaml.SafeLoader)
        self.parse_settings(config)
        self.interval = 4.0

    def task(self, yaml_file):
        request_file = f"{yaml_file}.{self.sync_id}_request"
        os.system(f"cp {yaml_file} {request_file}")
        self.upload_to_ftp(request_file)
        with open(request_file, "r") as f:
            config = yaml.load(f, Loader=yaml.SafeLoader)
        self.remove_if_exists(request_file)
        self.parse_actions(config)

    def listen(self):
        while True:
            logger.success(f"listening on {self.ftp_host} ...")
            try:
                with self.connect_to_ftp() as conn:
                    found_task = False
                    while not found_task:
                        for fname in conn.nlst():
                            if fname.endswith(f".{self.sync_id}_request"):
                                found_task = True
                                self.download_from_ftp(conn, fname)
                                self.delete_from_ftp(conn, fname)
                                with open(fname, "r") as f:
                                    config = yaml.load(f, Loader=yaml.SafeLoader)
                                self.remove_if_exists(fname)
                                try:
                                    self.parse_actions(config)
                                except Exception as e:
                                    logger.error(f"{e}")
                        time.sleep(self.interval)
            except Exception as e:
                logger.error(f"{e}")

    def parse_settings(self, config: dict):
        self.sync_id = config.get("sync_id")
        self.sync_mode = config.get("sync_mode")
        self.ftp_host = config.get("ftp_host")
        self.ftp_username = config.get("ftp_username")
        self.ftp_password = config.get("ftp_password")
        self.ftp_encoding = config.get("ftp_encoding")

    def parse_actions(self, config: dict):
        actions = config.get("actions")
        if actions is None:
            raise Exception("actions not available")
        for action in actions:
            action: dict
            action_type = action.get("type")
            action_root = action.get("root")
            device = action.get("device")
            action_args = action.get("args")
            if action_type == "pack":
                if (device == "local" and self.sync_mode == "client") or (device == "remote" and self.sync_mode == "server"):
                    self.action_pack(action_root, action_args)
                else:
                    self.listen_pack(action_args)
            if action_type == "shell":
                if (device == "local" and self.sync_mode == "client") or (device == "remote" and self.sync_mode == "server"):
                    self.action_shell(action_root, action_args)
                else:
                    self.listen_shell(action_args)

    def action_shell(self, root, args: dict):
        log_file = args.get("log_file")
        command_list = args.get("command_list")
        os.chdir(self.workdir)
        os.chdir(os.path.abspath(root))
        self.remove_if_exists(log_file)
        abs_log_file = os.path.abspath(log_file)
        for command in command_list:
            print(f"> {command}")
            os.system(f'echo "> {command}" >> {abs_log_file}')
            os.system(f"{command} 2>&1 | tee -a {abs_log_file}")
        self.upload_to_ftp(log_file)
        self.remove_if_exists(log_file)

    def listen_shell(self, args: dict):
        log_file = args.get("log_file")
        logger.success(f"listening for {log_file} ...")
        os.chdir(self.workdir)
        with self.connect_to_ftp() as conn:
            while log_file not in conn.nlst():  # Wait for response
                time.sleep(self.interval)
            self.download_from_ftp(conn, log_file)
            self.delete_from_ftp(conn, log_file)
        with open(log_file, "r") as f:
            for line in f.readlines():
                print(line, end="")
        self.remove_if_exists(log_file)

    def action_pack(self, root, args: dict):
        send_tar = args.get("send_tar")
        send_list = args.get("send_list")
        os.chdir(self.workdir)
        os.chdir(os.path.abspath(root))
        with tarfile.open(send_tar, "w") as tf:
            for file in send_list:
                tf.add(file)
                logger.success(f"add file: {file}")
        self.upload_to_ftp(send_tar)
        self.remove_if_exists(send_tar)

    def listen_pack(self, args: dict):
        send_tar = args.get("send_tar")
        send_path = args.get("send_path")
        logger.success(f"listening for {send_tar} ...")
        os.chdir(self.workdir)
        with self.connect_to_ftp() as conn:
            while send_tar not in conn.nlst():  # Wait for response
                time.sleep(self.interval)
            self.download_from_ftp(conn, send_tar)
            self.delete_from_ftp(conn, send_tar)
        with tarfile.open(send_tar, "r") as tf:
            tf.extractall(send_path)
        self.remove_if_exists(send_tar)

    def remove_if_exists(self, path):
        """Remove local file."""
        if os.path.exists(path):
            logger.success(f"remove exist {path}")
            os.system(f"rm -r {path}")

    def connect_to_ftp(self):
        conn = FTP(self.ftp_host, encoding=self.ftp_encoding)
        conn.login(self.ftp_username, self.ftp_password)
        return conn

    def download_from_ftp(self, conn: FTP, name):
        """Download file from FTP,
        files will be downloaded to current path,
        if file exists, it will be removed first.
        """
        self.remove_if_exists(name)
        logger.success(f"download ftp:{name}")
        with open(name, "wb") as f:
            conn.retrbinary("RETR " + name, lambda data: f.write(data))

    def delete_from_ftp(self, conn: FTP, name):
        """Delete file from FTP."""
        logger.success(f"delete ftp:{name}")
        if name in conn.nlst():
            conn.delete(name)

    def upload_to_ftp(self, path):
        """Upload local file to FTP,
        during transfer, the file will be locked as xxx.transfer until it is completely uploaded.
        """
        filename = os.path.basename(path)
        logger.success(f"upload ftp:{filename} ({(os.stat(path).st_size) / 1e6:.3f}MB) ...")
        with self.connect_to_ftp() as conn:
            with open(path, "rb") as f:
                if filename in conn.nlst():
                    conn.delete(filename)
                if (filename + ".transfer") in conn.nlst():
                    conn.delete(filename + ".transfer")
                conn.storbinary("STOR " + filename + ".transfer", f)
            conn.rename(filename + ".transfer", filename)
            assert filename in conn.nlst()
        logger.success("upload finished")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, default=None, help="configuration file, see example_config.yml")
    args = parser.parse_args()

    sync = FTPSync(args.config)
    if sync.sync_mode == "client":
        sync.task(args.config)
    elif sync.sync_mode == "server":
        sync.listen()
