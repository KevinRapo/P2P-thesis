#!/bin/bash
# The probe check as a SLURM array: one task per run, each released when its run
# ends, so a short run never waits for a long one. ARGS are probe_ppo.py's options
# (the same in every task); the task's number picks the run (--index).
#
#   N=$(python core/rl/scripts/probe_ppo.py $ARGS --count)
#   sbatch --account=<account> --array=0-$((N-1))%30 --export=ALL,ARGS="$ARGS" hpc/probes.slurm
#
# Keep the %30: every task starts its own Ray (about 175 threads), and the cluster
# allows 4096 threads per user and node. Uncapped, 396 tasks at once put up to 22
# on one node and most failed to start Ray ("Resource temporarily unavailable").
# A task whose run fails exits with 1.
#
# Then score them all (afterwards, or with --dependency=afterok:<array job>):
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
