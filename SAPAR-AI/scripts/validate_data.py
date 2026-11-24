"""Backend contract validation; does not verify factual truth of sources."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.database import load_dataset


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path,nargs='?',default=ROOT/'data')
    args=parser.parse_args()
    dataset=load_dataset(args.directory)
    print(f'Valid structure: {len(dataset.destinations)} destinations, {len(dataset.transport.routes)} routes.')
    if not dataset.transport.routes:
        print('NOT READY for travel planning: no route templates.')
