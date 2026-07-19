import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rules import parse_frequency

print(f"parse_frequency('1-1-1') = {parse_frequency('1-1-1')}")
print(f"parse_frequency('1-0-1') = {parse_frequency('1-0-1')}")
print(f"parse_frequency('1-0-0') = {parse_frequency('1-0-0')}")
print(f"parse_frequency('TDS') = {parse_frequency('TDS')}")
