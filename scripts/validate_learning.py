"""Run a small real training/checkpoint/inference case; writes validation evidence."""
import argparse
import json
import pickle
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from src.agent.battery import Battery
from src.agent.der import DERAgent
from src.environment.train import RLTrainer
from src.environment.base import RLAlgorithm, TrainingMode
from src.environment.inference import RLInference
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.dso import DSOAgent
from src.market.matching import MarketConfig


def capture_initial_weights(*, algorithm, **kwargs):
    """Validation-only snapshot; ordinary notebook training does not save this."""
    destination = Path(algorithm.config.env_config['_validation_state_path'])
    with destination.open('wb') as stream:
        pickle.dump(algorithm.learner_group.get_weights(), stream)


class ValidationTrainer(RLTrainer):
    def _setup_config(self, embeddings_dim=128):
        config, mutations = super()._setup_config(embeddings_dim)
        return config.callbacks(on_algorithm_init=capture_initial_weights), mutations


def config(steps=8):
    grid=GridNetwork(GridTopology.LINE,2,100.,seed=7)
    agents=[DERAgent('seller',10.,Battery(4.,initial_soc=.5),node_id='0',
                     generation_profile=[4.]*steps,demand_profile=[1.]*steps),
            DERAgent('buyer',10.,Battery(4.,initial_soc=.5),node_id='1',
                     generation_profile=[1.]*steps,demand_profile=[3.]*steps)]
    dso=DSOAgent('DSO',[.1]*steps,[.8]*steps,grid)
    return dict(max_steps=steps,agents=agents,grid_network=grid,dso=dso,seed=7,
                market_config=MarketConfig(min_price=0.,max_price=1.,min_quantity=0.,max_quantity=10.,
                                           enable_partner_preference=True))


def leaves(value,prefix=''):
    if isinstance(value,dict):
        for key,item in value.items():
            yield from leaves(item,prefix+'/'+str(key))
    else:
        if hasattr(value,'detach'):
            value=value.detach().cpu().numpy()
        yield prefix,np.asarray(value)


def run(algorithm,mode,iterations,batch):
    cfg=config()
    initial_path=ROOT/'tmp/learning'/f'initial_module_state_{uuid4().hex}.pkl'
    initial_path.parent.mkdir(parents=True,exist_ok=True)
    cfg['_validation_state_path']=str(initial_path)
    trainer=ValidationTrainer(cfg,algorithm=RLAlgorithm(algorithm),training=TrainingMode(mode),
                      iters=iterations,checkpoint_freq=1,cpus=1,gpus=0,train_batch_size=batch,
                      storage_path=str(ROOT/'tmp/learning'))
    results,metrics=trainer.train(embeddings_dim=32)
    checkpoint=trainer.get_best_checkpoint(results)['train']
    with initial_path.open('rb') as stream:
        initial=dict(leaves(pickle.load(stream)))
    inference=RLInference(cfg,checkpoint_path=checkpoint.path)
    try:
        learned = inference.algorithm.learner_group.get_weights()
        final=dict(leaves(learned))
        changed=[key for key,value in initial.items() if key in final and value.shape==final[key].shape
                 and not np.array_equal(value,final[key])]
        policy_changed=[key for key in changed if any(part in key for part in ('pi','actor')) and 'target' not in key]
        if not policy_changed:
            raise AssertionError(f'No executed actor weights changed; changed keys: {changed}')
        executed = dict(leaves({module_id: inference.algorithm.get_module(module_id).get_state()
                                for module_id in learned}))
        for key in policy_changed:
            if key not in executed:
                raise AssertionError(f'Trained actor parameter is absent from inference: {key}')
            np.testing.assert_array_equal(final[key], executed[key], err_msg=key)
        observations,_=inference.env.reset(seed=19)
        controls=inference._compute_actions(observations)
        if mode=='dtde':
            assert all(inference.env.action_spaces[id].contains(action) for id,action in controls.items())
        else:
            assert inference.env.action_space.contains(controls)
        evaluation=inference.inference(iters=1)
        evidence=dict(algorithm=algorithm,mode=mode,iterations=iterations,batch=batch,
                      checkpoint=checkpoint.path,changed_actor_parameters=policy_changed,
                      restored_actor_parameters_match=True,
                      evaluation=evaluation,trial_errors=results.num_errors)
    finally:
        inference.close()
    destination=ROOT/'tmp/learning'/f'{algorithm}-{mode}-validation.json'
    destination.write_text(json.dumps(evidence,indent=2,default=str),encoding='utf-8')
    print('VALIDATION PASSED:',destination,flush=True)
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--algorithm',choices=['ppo','appo','sac'],default='ppo')
    parser.add_argument('--mode',choices=['dtde','ctde','ctce'],default='dtde')
    parser.add_argument('--iterations',type=int,default=2)
    parser.add_argument('--batch',type=int,default=32)
    args=parser.parse_args()
    run(args.algorithm,args.mode,args.iterations,args.batch)
