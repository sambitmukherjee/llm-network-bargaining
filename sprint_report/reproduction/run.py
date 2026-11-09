"""Offline saved-evidence reproduction; no model requests or paper typesetting."""
import argparse
import runpy
from pathlib import Path
import context
from verification import verify_inputs

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['replay','analyse','figures','tables','verify','all'])
    parser.add_argument('--verify-git',action='store_true',help='Also recheck saved historical version evidence using local Git objects')
    args=parser.parse_args()
    verify_inputs()
    if args.stage in ['replay','all']:
        from replay_saved import replay
        replay()
    if args.stage in ['analyse','all']:
        from selected_analysis import analyse
        analyse()
    if args.stage in ['figures','all']:
        runpy.run_path(str(context.ROOT/'reproduction/figures.py'),run_name='__main__')
    if args.stage in ['tables','all']:
        runpy.run_path(str(context.ROOT/'reproduction/tables.py'),run_name='__main__')
    if args.stage in ['verify','all']:
        from provenance import verify as verify_provenance
        verify_provenance()
        from verification import verify
        verify()

if __name__=='__main__':
    main()
