import os
import time
import datetime
import tarfile
import argparse
from ftplib import FTP
from loguru import logger
import sys
import json
import yaml

fmt = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{message}</level>"
config = {
    "handlers": [
        {"sink": sys.stderr, "format": fmt},
    ],
}
logger.configure(**config)


class FTPSync:
    """An Server class to listen for requests on normal device

    Based on FTP and both device should be able to connect the same FTP host.

    Example:

    >>> import server
    >>> server = FTPSync(server_name='my_server', ftp_host='114.51.4.191', ftp_username='xxx', ftp_password='xxx')
    >>> server.listen()


    Usage for client side:
    >>> import server
    >>> server = FTPSync(server_name='my_server', ftp_host='114.51.4.191', ftp_username='xxx', ftp_password='xxx')
    >>> server.push('path/to/my.file')  # push files to the server
    >>> server.pull('path/to/local.file')  # pull files from the server
    >>> server.exec('make -C path/to')  # run command on the server

    """

    def __init__(self, server_name, ftp_host, ftp_username, ftp_password, ftp_encoding) -> None:
        """Initializing method,
        set attributes for self & ftp.
        server_name: name of the server, use to distinguish between different servers
        ftp_host: host for FTP
        ftp_username: username for FTP
        ftp_password: password for FTP
        ftp_encoding: encoding for FTP
        """
        self.server_name = server_name
        self.ftp_host = ftp_host
        self.ftp_username = ftp_username
        self.ftp_password = ftp_password
        self.ftp_encoding = ftp_encoding
        self.interval = 2
        self.cwd = os.getcwd()
        self.exec_root = os.getcwd()
        self.verbose = True

    def connect_to_ftp(self):
        """Create connection to FTP."""
        if self.verbose:
            logger.success("connect to ftp")
        conn = FTP(self.ftp_host, encoding=self.ftp_encoding)
        conn.login(self.ftp_username, self.ftp_password)
        return conn

    def download_from_ftp(self, conn: FTP, name):
        """Download file from FTP,
        files will be downloaded to current path,
        if file exists, it will be removed first.
        """
        self.remove_if_exists(name)
        if self.verbose:
            logger.success(f"download ftp:{name}")
        with open(name, "wb") as f:
            conn.retrbinary("RETR " + name, lambda data: f.write(data))

    def delete_from_ftp(self, conn: FTP, name):
        """Delete file from FTP."""
        if self.verbose:
            logger.success(f"delete ftp:{name}")
        if name in conn.nlst():
            conn.delete(name)

    def upload_to_ftp(self, conn: FTP, path):
        """Upload local file to FTP,
        during transfer, the file will be locked as xxx.transfer until it is completely uploaded.
        """
        filename = os.path.basename(path)
        if self.verbose:
            logger.success(f"upload ftp:{filename} ({(os.stat(path).st_size) / 1e6:.3f}MB) ...")
        with open(path, "rb") as f:
            if filename in conn.nlst():
                conn.delete(filename)
            if (filename + ".transfer") in conn.nlst():
                conn.delete(filename + ".transfer")
            conn.storbinary("STOR " + filename + ".transfer", f)
        conn.rename(filename + ".transfer", filename)
        assert filename in conn.nlst()
        if self.verbose:
            logger.success("upload finished")

    def remove_if_exists(self, path):
        """Remove local file."""
        if os.path.exists(path):
            if self.verbose:
                logger.success(f"remove exist {path}")
            os.system(f"rm -r {path}")

    def parse_action_push(self, conn, name: str):
        """Use suffix=.servername.push as PUSH mode
        This action will push files from ftp to server side
        files: ftp -> server
        """
        if self.verbose:
            logger.success(f"> PUSH {name}")
        self.download_from_ftp(conn, name)
        self.delete_from_ftp(conn, name)
        package_name = name.split(f".{self.server_name}.push")[0]
        self.remove_if_exists(package_name)
        if self.verbose:
            logger.success(f"extract {name}")
        with tarfile.open(name, "r") as tf:
            tf.extractall(".")
        self.remove_if_exists(name)

    def parse_action_pull(self, conn, name: str):
        """Use suffix=.servername.pull as PULL mode
        This action will download files from server side to ftp
        files: server -> ftp
        """
        if self.verbose:
            logger.success(f"> PULL {name}")
        self.download_from_ftp(conn, name)
        if self.verbose:
            logger.success(f"archive {name}.recv")
        with tarfile.open(f"{name}.recv", "w") as tf:
            with open(name, "r") as f:
                for line in f.readlines():
                    tf.add(line.strip())
        self.upload_to_ftp(conn, f"{name}.recv")
        self.remove_if_exists(f"{name}.recv")
        self.remove_if_exists(name)
        self.delete_from_ftp(conn, name)

    def parse_action_exec(self, conn, name: str):
        """Use suffix=.servername.exec as EXEC mode
        This action will execute commands on server side and generate a log file
        commands: server(run)
        log file: server -> ftp
        """
        if self.verbose:
            logger.success(f"> EXEC {name}")
        os.chdir(self.exec_root)
        self.download_from_ftp(conn, name)
        self.delete_from_ftp(conn, name)
        os.system(f"sh {name} 2>&1 | tee {name}.log")
        self.upload_to_ftp(conn, f"{name}.log")
        self.remove_if_exists(f"{name}.log")
        self.remove_if_exists(name)
        os.chdir(self.cwd)

    def parse_action_conf(self, conn, name: str):
        """Use suffix=.servername.conf as CONF mode
        This action will edit configure by the input dict
        commands: server(config)
        log file: server -> ftp
        """
        if self.verbose:
            logger.success(f"> CONF {name}")
        self.download_from_ftp(conn, name)
        self.delete_from_ftp(conn, name)
        with open(name, "r") as f:
            config = json.load(f)
        chdir = None
        with open(f"{name}.log", "w") as f:
            for k, v in config.items():
                if k == "exec_root":
                    v = os.path.abspath(os.path.join(self.cwd, v))
                    chdir = v
                self.__dict__[k] = v
                if self.verbose:
                    logger.success(f"> SET {k}={v}")
        self.upload_to_ftp(conn, f"{name}.log")
        self.remove_if_exists(f"{name}.log")
        self.remove_if_exists(name)
        if chdir is not None:
            if self.verbose:
                logger.success(f"clean {chdir}")
                os.system(f"mkdir -p {chdir}")
                os.system(f"rm -rf {chdir}/*")
            os.chdir(chdir)

    def listen(self):
        """Set self as a server and listening forever,
        response to 3 types of requests:
            1. xxx.servername.push
            2. xxx.servername.pull
            3. xxx.servername.exec
        """
        while True:  # loop forever
            with self.connect_to_ftp() as conn:
                if self.verbose:
                    logger.success("listening on ftp://" + self.ftp_host + " ...")
                has_req = False
                while not has_req:
                    try:
                        for name in conn.nlst():
                            if name.endswith(f".{self.server_name}.push"):
                                self.parse_action_push(conn, name)
                                has_req = True
                            if name.endswith(f".{self.server_name}.pull"):
                                self.parse_action_pull(conn, name)
                                has_req = True
                            elif name.endswith(f".{self.server_name}.exec"):
                                self.parse_action_exec(conn, name)
                                has_req = True
                            elif name.endswith(f".{self.server_name}.conf"):
                                self.parse_action_conf(conn, name)
                                has_req = True
                    except Exception as e:
                        logger.error(f"{e}")
                    time.sleep(self.interval)  # query interval

    @staticmethod
    def gen_package_name():
        return datetime.datetime.now().strftime(r"%Y%m%dT%H%M%S")

    # Client functions
    def push(self, *path_list):
        """Push local files to server,
        files will be compressed and extract on server side.
        """
        package_name = self.gen_package_name()
        package_name += f".{self.server_name}.push"
        with tarfile.open(package_name, "w") as tf:
            for path in path_list:
                if self.verbose:
                    logger.success("> PUSH " + path)
                tf.add(path)
        with self.connect_to_ftp() as conn:
            self.upload_to_ftp(conn, package_name)
        self.remove_if_exists(package_name)

    def pull(self, *path_list):
        """Pull files from server,
        files will be compressed and be extracted on the other side.
        """
        package_name = self.gen_package_name()
        package_name += f".{self.server_name}.pull"
        with open(package_name, "w") as f:
            for path in path_list:
                if self.verbose:
                    logger.success("> PULL " + path)
                f.write(f"{path}\n")
        with self.connect_to_ftp() as conn:
            self.upload_to_ftp(conn, package_name)
            self.remove_if_exists(package_name)
            if self.verbose:
                logger.success(f"listening for {package_name}.recv ...")
            while f"{package_name}.recv" not in conn.nlst():  # Wait for response
                time.sleep(self.interval)
            self.download_from_ftp(conn, f"{package_name}.recv")
            self.delete_from_ftp(conn, f"{package_name}.recv")
        with tarfile.open(f"{package_name}.recv", "r") as tf:
            tf.extractall(".")
        self.remove_if_exists(f"{package_name}.recv")

    def exec(self, *commands):
        """Execute commands on server,
        NOTE: all commands will be excuted in ONE shell file!
        """
        package_name = self.gen_package_name()
        package_name += f".{self.server_name}.exec"
        with open(package_name, "w") as f:
            for command in commands:
                f.write(f"{command}\n")
                if self.verbose:
                    logger.success(f'> EXEC "{command}"')
        with self.connect_to_ftp() as conn:
            self.upload_to_ftp(conn, package_name)
            self.remove_if_exists(package_name)
            if self.verbose:
                logger.success(f"listening for {package_name}.log ...")
            while f"{package_name}.log" not in conn.nlst():  # Wait for response
                time.sleep(self.interval)
            self.download_from_ftp(conn, f"{package_name}.log")
            self.delete_from_ftp(conn, f"{package_name}.log")
        # display logs
        with open(f"{package_name}.log", "r") as f:
            ret = f.readlines()
        os.system(f"rm {package_name}.log")
        if self.verbose:
            for line in ret:
                print(line, end="")
        return ret

    def conf(self, **kwargs):
        """Set configurations on server by json"""
        package_name = self.gen_package_name()
        package_name += f".{self.server_name}.conf"
        with open(package_name, "w") as f:
            json.dump(kwargs, f)
        for k, v in kwargs.items():  # sync locally too
            self.__dict__[k] = v
        if self.verbose:
            logger.success(f'> CONF "{kwargs}"')
        with self.connect_to_ftp() as conn:
            self.upload_to_ftp(conn, package_name)
            self.remove_if_exists(package_name)
            if self.verbose:
                logger.success(f"listening for {package_name}.log ...")
            while f"{package_name}.log" not in conn.nlst():  # Wait for response
                time.sleep(self.interval)
            self.download_from_ftp(conn, f"{package_name}.log")
            self.delete_from_ftp(conn, f"{package_name}.log")
        # display logs
        with open(f"{package_name}.log", "r") as f:
            for line in f.readlines():
                print(line, end="")
        os.system(f"rm {package_name}.log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None, help="configuration file, see example_config.yml")
    parser.add_argument("--listen", action="store_true", help="use this as a server")
    parser.add_argument("--ssh", action="store_true", help="use this as a ssh connection")
    parser.add_argument("--push", type=str, default=None, nargs="+", help="paths to push")
    parser.add_argument("--pull", type=str, default=None, nargs="+", help="paths to pull")
    parser.add_argument("--exec", type=str, default=None, nargs="+", help="commands to execute")
    parser.add_argument("--interval", type=float, default=None, help="interval of query")
    parser.add_argument("--root", type=str, default=None, help="root of self")

    args = parser.parse_args()

    yaml_file = args.config
    if yaml_file is None:
        raise Exception("Must specify config file, use --config MY_CONFIG.yml")
    if not os.path.exists(yaml_file):
        raise Exception("Config file path does not exist: %s" % yaml_file)

    with open(yaml_file, "r") as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)
        server = FTPSync(
            server_name=config["server_name"],
            ftp_host=config["ftp_host"],
            ftp_username=config["ftp_username"],
            ftp_password=config["ftp_password"],
            ftp_encoding=config["ftp_encoding"],
        )

    if args.listen:  # Server mode
        server.listen()
    elif args.ssh:  # SSH mode
        server.conf(interval=0.05)
        server.verbose = False
        root = server.exec("pwd")[0].strip()
        print("(Enter 'exit' to quit)\n")
        print(f"{root}> ", end="")
        command = input()
        while command != "exit":
            if command.startswith("cd "):
                root = command.split("cd ")[-1]
                server.conf(exec_root=root)
                root = server.exec("pwd")[0].strip()
            else:
                server.exec(command)
            print(f"{root}> ", end="")
            command = input()
        server.conf(interval=4)
    else:  # Sync mode
        for x in sys.argv[1:]:
            if x == "--exec":
                server.exec(*args.exec)
            elif x == "--push":
                server.push(*args.push)
            elif x == "--pull":
                server.pull(*args.pull)
            elif x == "--interval":
                server.conf(interval=args.interval)
            elif x == "--root":
                server.conf(exec_root=args.root)
