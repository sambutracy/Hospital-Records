"""Populate fictional accounts in the existing localhost app; no model calls."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ecosystem.client_demo import seed

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-documents',type=int,default=64)
    options=parser.parse_args()
    print(json.dumps(seed(options.max_documents)))
