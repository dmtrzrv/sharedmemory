Some task requested functionality for shared memory on old python versions. Technically it can be used even on python 2.7, but annotations since python 3.5, also PyMemoryView_FromMemory introduced in Python 3.3, so for Windows on Python 2.7 this has to be a little changed.

Linux version (after removing annotations) suits for Python 2.7.

USAGE

```python
#1 process
from sharedmemory import SharedMemory
shm = SharedMemory('test', True, 1024)
shm.write(b'test message')

#2 process
from sharedmemory import SharedMemory
shm = SharedMemory('test', False, 1024)
print(shm.read(len('test message')))
#OR
print(bytes(shm.memory[:len('test message')]))
```