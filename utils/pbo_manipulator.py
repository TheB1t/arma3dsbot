import struct
import os
import shutil
from pathlib import Path

from .log import Log, LogLevel

class PBOManipulator(Log):

    def __init__(self, filename, basedir="./"):
        self.filename = filename
        self.dir = ".".join(self.filename.split(".")[:-1])
        self.basedir = basedir
        self.header = "IIIII"
        self.header_size = struct.calcsize(self.header)

        self.log(f"Header struct: {self.header} Header size: {self.header_size}")

        self.files = []

    def unpack(self):
        with open(f"{self.basedir}/{self.filename}", 'rb') as file:
            self.readHeader(file)

            for f in self.files:
                self.log(f"Reading file: {f['name'].replace(self.dir, '')}, Size: {f['datasize']}")
                f['data'] = file.read(f['datasize'])

                splited_path = f['name'].split("/")
                name = splited_path.pop()
                path = f"{self.basedir}/{self.dir}/{'/'.join(splited_path)}"

                if not os.path.exists(path):
                    os.makedirs(path)

                with open(f"{path}/{name}".replace("\0", ""), 'wb') as t:
                    t.write(f['data'])

            checksum = []
            while True:
                c = file.read(1)
                if not c:
                    break
                checksum.append(int.from_bytes(c, 'big'))
                
            self.log(f"{checksum}")

    def _recursive_update(self, dir, _dir=None):
        directory = Path(_dir if _dir else dir)

        for item in directory.iterdir():
            path = f"{item}".replace(f"{self.basedir}/{self.dir}/", "")
            if item.is_file():
                size = os.path.getsize(item)
                timestamp = os.path.getctime(item)
                self.log(f"Updating -> File: {path}, Size {size}, Timestamp {int(timestamp)}")
                with open(item, 'rb') as file:
                    self.files.append({ 
                        "name": path,
                        "method": 0,
                        "size": size,
                        "timestamp": int(timestamp),
                        "datasize": size,
                        "data": file.read()
                        })
                    
            elif item.is_dir():
                self._recursive_update(dir, item)

    def clean(self):
        if os.path.exists(f"{self.basedir}/{self.dir}"):
            shutil.rmtree(f"{self.basedir}/{self.dir}")

    def update(self):
        self.files.clear()

        self._recursive_update(f"{self.basedir}/{self.dir}")
            
    def pack(self):
        with open(f"{self.basedir}/{self.filename}", 'wb') as file:
            self.writeHeader(file)
            for f in self.files:
                self.log(f"Writing file: {f['name']}, Size: {f['datasize']}")
                file.write(f['data'])

    def readString(self, file):
        string = ""
        while True:
            c = file.read(1)
            string += c.decode("utf8")
            if c == b'\x00':
                break

        return string
    
    def readEntry(self, file):
        name = self.readString(file).replace("\\", "/")
        
        raw = file.read(self.header_size)
        method, size, reserved, timestamp, datasize = struct.unpack(self.header, raw)

        return { 
            "name": name, 
            "method": method,
            "size": size,
            "timestamp": timestamp,
            "datasize": datasize,
            "data": None
            }

    def readHeader(self, file):
        while True:
            entry = self.readEntry(file)

            if (entry["name"] == '\0' and entry["method"] == 0x56657273):
                ext = []

                while True:
                    string = self.readString(file)
                    ext.append(string)
                    if string == '\0':
                        break
                self.log(f"Found start entry (ext {ext})")

            elif (entry["name"] == '\0' and entry["method"] == 0):
                self.log("Found end entry")
                break
            else:
                self.files.append(entry)

    def writeString(self, file, string):
        file.write(f"{string}\0".encode("utf8"))
    
    def writeEntry(self, file, entry):
        self.writeString(file, entry["name"].replace("/", "\\"))
        
        raw = struct.pack(self.header, entry["method"], entry["size"], 0, entry["timestamp"], entry["datasize"])
        file.write(raw)

    def writeHeader(self, file):
        self.log("Writing start entry")
        self.writeEntry(file, { 
            "name": "", 
            "method": 0x56657273,
            "size": 0,
            "timestamp": 0,
            "datasize": 0,
            })
        
        file.write(b'\x00')

        for f in self.files:
            self.writeEntry(file, f)

        self.log("Writing end entry")
        self.writeEntry(file, { 
            "name": "", 
            "method": 0,
            "size": 0,
            "timestamp": 0,
            "datasize": 0,
            })