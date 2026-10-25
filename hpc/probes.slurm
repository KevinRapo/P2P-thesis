#!/bin/bash
# The probe check as a SLURM array: one task per run, each released when its run
# ends, so a short run never waits for a long one. ARGS are probe_ppo.py's options
# (the same in every task); the task's number picks the run (--index).
#
#   N=$(python core/rl/scripts/probe_ppo.py $ARGS --count)
#   sbatch --account=<account> --array=0-$((N-1)) --export=ALL,ARGS="$ARGS" hpc/probes.slurm
#
# Then score them all (afterwards, or with --dependency=afterany:<array job>):
#   python core/rl/scripts/probe_ppo.py $ARGS        (without --index)
#
# Options on the sbatch line override the lines below.
#SBATCH --job-name=probes
#SBATCH --partition=short            # max 4 h per task
#SBATCH --time=03:00:00              # per task
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2            # one training process; Ray's own threads
#SBATCH --mem=3G
#SBATCH --output=probes-%A_%a.out

source ~/miniforge3/etc/profile.d/conda.sh
conda activate marlem
cd "${REPO:-$HOME/marlem-v2}"
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
python -u core/rl/scripts/probe_ppo.py $ARGS --index "$SLURM_ARRAY_TASK_ID"
