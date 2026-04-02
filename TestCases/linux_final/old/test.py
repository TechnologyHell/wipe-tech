import sys
import time

for i in range(101):
    sys.stdout.write(f"\rProgress: {i}%")
    sys.stdout.flush()
    time.sleep(0.1)
print()

