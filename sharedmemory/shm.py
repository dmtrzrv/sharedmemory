import sys
from abc import ABC, abstractmethod


class SharedMemoryInterface(ABC):
    _memory: memoryview = None

    def write(self, data: bytes, offset: int = 0) -> None:
        self._memory[offset:offset + len(data)] = data

    def read(self, size: int, offset: int = 0) -> bytes:
        return bytes(self._memory[offset:offset + size])

    @property
    def memory(self) -> memoryview:
        return self._memory

    @abstractmethod
    def close(self) -> None:
        pass


if sys.version_info.major == 3 and sys.version_info.minor >= 8:
    from multiprocessing import shared_memory

    class SharedMemory(SharedMemoryInterface):
        def __init__(self, name: str, create: bool = False, buff_size: int = 0):
            self._is_closed: bool = False
            self._is_creator: bool = create
            self._shm: shared_memory.SharedMemory = shared_memory.SharedMemory(name=name, create=create, size=buff_size)
            self._memory = self._shm.buf

        def close(self) -> None:
            if not self._is_closed:
                self._memory.release()
                self._shm.close()
                if self._is_creator:
                    self._shm.unlink()
                self._is_closed = True

        def __del__(self):
            self.close()

else:
    if sys.platform == 'win32' and sys.version_info.major == 3 and sys.version_info.minor >= 3:  # 5 cuz of annotations
        import ctypes.wintypes
        from ctypes import pythonapi

        class SecurityAttributes(ctypes.Structure):
            _fields_ = [
                ('nLength', ctypes.wintypes.DWORD),
                ('lpSecurityDescriptor', ctypes.wintypes.LPVOID),
                ('bInheritHandle', ctypes.wintypes.BOOL)
            ]

        create_file_mapping = ctypes.windll.kernel32.CreateFileMappingA
        create_file_mapping.restype = ctypes.wintypes.HANDLE
        create_file_mapping.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(SecurityAttributes),
                                        ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
                                        ctypes.wintypes.LPCSTR]
        open_file_mapping = ctypes.windll.kernel32.OpenFileMappingA
        open_file_mapping.restype = ctypes.wintypes.HANDLE
        open_file_mapping.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.LPCSTR]
        map_view_of_file = ctypes.windll.kernel32.MapViewOfFile
        map_view_of_file.restype = ctypes.wintypes.LPVOID
        map_view_of_file.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
                                     ctypes.wintypes.DWORD, ctypes.c_size_t]
        unmap_view_of_file = ctypes.windll.kernel32.UnmapViewOfFile
        unmap_view_of_file.restype = ctypes.wintypes.BOOL
        unmap_view_of_file.argtypes = [ctypes.wintypes.LPVOID]
        close_handle = ctypes.windll.kernel32.CloseHandle
        close_handle.restype = ctypes.wintypes.BOOL
        close_handle.argtypes = [ctypes.wintypes.HANDLE]
        pythonapi.PyMemoryView_FromMemory.restype = ctypes.py_object
        pythonapi.PyMemoryView_FromMemory.argtypes = (ctypes.c_char_p, ctypes.c_ssize_t, ctypes.c_int)

        class SharedMemory(SharedMemoryInterface):
            INVALID_HANDLE_VALUE: int = -0x1
            PAGE_READWRITE: int = 0x4
            FILE_MAP_ALL_ACCESS: int = 0xf001f
            PyBUF_WRITE: int = 0x200

            def __init__(self, name: str, create: bool = False, buff_size: int = 0):
                self._is_closed: bool = False
                if create:
                    self._handle = create_file_mapping(SharedMemory.INVALID_HANDLE_VALUE,
                                                       ctypes.POINTER(SecurityAttributes)(),
                                                       SharedMemory.PAGE_READWRITE, 0, buff_size,
                                                       ctypes.create_string_buffer(name.encode(), len(name)))
                else:
                    self._handle = open_file_mapping(SharedMemory.FILE_MAP_ALL_ACCESS, False,
                                                     ctypes.create_string_buffer(name.encode(), len(name)))

                self._buff_address = map_view_of_file(self._handle, SharedMemory.FILE_MAP_ALL_ACCESS, 0, 0,
                                                      buff_size)

                self._memory = pythonapi.PyMemoryView_FromMemory(
                    (ctypes.c_char * buff_size).from_address(self._buff_address),
                    buff_size, SharedMemory.PyBUF_WRITE)

            def close(self) -> None:
                if not self._is_closed:
                    self._memory.release()
                    unmap_view_of_file(self._buff_address)
                    close_handle(self._handle)
                    self._is_closed = True

            def __del__(self):
                self.close()

    elif sys.platform == 'linux':
        import ctypes
        import os
        import stat
        import mmap
        from ctypes.util import find_library
        rt = ctypes.cdll.LoadLibrary(find_library('rt'))
        shm_open = rt.shm_open
        shm_open.restype = ctypes.c_int
        shm_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_uint32]
        shm_unlink = rt.shm_unlink
        shm_unlink.restype = ctypes.c_int
        shm_unlink.argtypes = [ctypes.c_char_p, ]

        class SharedMemory(SharedMemoryInterface):
            def __init__(self, name: str, create: bool = False, buff_size: int = 0):
                self._is_creator: bool = create
                self._is_closed: bool = False
                self._name: str = name
                if create:
                    fd = shm_open(ctypes.create_string_buffer(name.encode(), len(name)), os.O_CREAT | os.O_RDWR,
                                  stat.S_IRUSR | stat.S_IWUSR)
                else:
                    fd = shm_open(ctypes.create_string_buffer(name.encode(), len(name)), os.O_RDWR,
                                  stat.S_IRUSR | stat.S_IWUSR)
                os.ftruncate(fd, buff_size)
                self._mmap = mmap.mmap(fd, buff_size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                                       mmap.ACCESS_WRITE)
                self._memory = memoryview(self._mmap)

            def close(self) -> None:
                if not self._is_closed:
                    self._memory.release()
                    self._mmap.close()
                    if self._is_creator:
                        shm_unlink(ctypes.create_string_buffer(self._name.encode(), len(self._name)))
                    self._is_closed = True

            def __del__(self):
                self.close()
    else:
        raise ImportError("SharedMemory is not available")
