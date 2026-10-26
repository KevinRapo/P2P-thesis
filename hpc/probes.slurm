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
#SBATCH --mem=6G                 # 3G: about 40 % of the tasks were killed at start
#SBATCH --output=probes-%A_%a.out

source ~/miniforge3/etc/profile.d/conda.sh
conda activate marlem
cd "${REPO:-$HOME/marlem-v2}"
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
# Ray sizes its thread pools by the node's cores (about 175 threads per run): one each,
# so many tasks fit on one node under the 4096 threads per user (core/rl/scripts/
# probe_check.parallel_setup does the same for a shared Ray).
export RAY_num_server_call_thread=1 RAY_gcs_server_rpc_server_thread_num=1
export RAY_gcs_server_rpc_client_thread_num=1 RAY_num_grpc_internal_threads=1
export RAY_worker_num_grpc_internal_threads=1 RAY_object_manager_rpc_threads_num=1
python -u core/rl/scripts/probe_ppo.py $ARGS --index "$SLURM_ARRAY_TASK_ID"
