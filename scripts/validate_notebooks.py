"""Execute selected notebooks in fresh kernels and retain executed artifacts."""
import argparse
import os
from pathlib import Path
import sys
import nbformat
from nbclient import NotebookClient
from jupyter_client import AsyncKernelManager
from jupyter_client.kernelspec import KernelSpec

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('patterns',nargs='+')
    parser.add_argument('--training',action='store_true')
    parser.add_argument('--episodes',type=int,default=1)
    parser.add_argument('--iterations',type=int,default=2)
    parser.add_argument('--timeout',type=int,default=14400,
                        help='Maximum seconds per cell; the full 54-run scalability comparison is one cell.')
    args=parser.parse_args()
    os.environ.update(MARLEM_NOTEBOOK_TRAIN=str(int(args.training)),
                      MARLEM_NOTEBOOK_EPISODES=str(args.episodes),
                      MARLEM_NOTEBOOK_ITERATIONS=str(args.iterations),
                      MARLEM_NOTEBOOK_BATCH='32',MPLBACKEND='Agg',
                      PYTHONPATH=str(ROOT),PYTHONUTF8='1')
    target=ROOT/'tmp/executed_notebooks'/('training' if args.training else 'simulation')
    target.mkdir(parents=True,exist_ok=True)
    for pattern in args.patterns:
        paths=list(ROOT.glob(pattern))
        if not paths: raise FileNotFoundError(pattern)
        for path in paths:
            print('EXECUTING',path,flush=True)
            book=nbformat.read(path,4)
            nbformat.validate(book)
            manager=AsyncKernelManager()
            manager._kernel_spec=KernelSpec(argv=[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],display_name='MARLEM validation',language='python')
            client=NotebookClient(book,km=manager,timeout=args.timeout,resources={'metadata':{'path':str(path.parent)}})
            # Use the interpreter running this validator, independent of named kernels.
            try:
                client.execute(cleanup_kc=True)
            finally:
                nbformat.write(book,target/path.name)
            has_plots = any(c.cell_type == 'code' and ('plot_results(' in c.source or 'plt.subplots(' in c.source)
                            for c in book.cells)
            figure_count = sum('image/png' in output.get('data', {})
                               for cell in book.cells for output in cell.get('outputs', []))
            if has_plots and not figure_count:
                raise AssertionError(f'{path.name} executed plotting code without embedding any figures.')
            print('PASSED',path,flush=True)
