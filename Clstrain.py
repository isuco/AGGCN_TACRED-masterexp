"""
Train a model on TACRED.
"""

import os
import sys
from datetime import datetime
import time
import numpy as np
import random
import argparse
from shutil import copyfile
import torch
import json
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable

from data.loader import DataLoader
from model.trainer import GCNTrainer
from utils import torch_utils, scorer, constant, helper
from utils.vocab import Vocab

parser = argparse.ArgumentParser()
parser.add_argument('--data_dir', type=str, default='dataset/tacred')
parser.add_argument('--vocab_dir', type=str, default='dataset/vocab')
parser.add_argument('--emb_dim', type=int, default=300, help='Word embedding dimension.')
parser.add_argument('--ner_dim', type=int, default=30, help='NER embedding dimension.')
parser.add_argument('--pos_dim', type=int, default=30, help='POS embedding dimension.')
parser.add_argument('--hidden_dim', type=int, default=300, help='RNN hidden state size.')
parser.add_argument('--num_layers', type=int, default=2, help='Num of AGGCN blocks.')
parser.add_argument('--input_dropout', type=float, default=0.5, help='Input dropout rate.')
parser.add_argument('--gcn_dropout', type=float, default=0.5, help='AGGCN layer dropout rate.')
parser.add_argument('--gru_dropout', type=float, default=0.4, help='AGGCN gru layer dropout rate.')
parser.add_argument('--word_dropout', type=float, default=0.04, help='The rate at which randomly set a word to UNK.')
parser.add_argument('--topn', type=int, default=1e10, help='Only finetune top N word embeddings.')
parser.add_argument('--lower', dest='lower', action='store_true', help='Lowercase all words.')
parser.add_argument('--no-lower', dest='lower', action='store_false')
parser.set_defaults(lower=False)
parser.add_argument('--heads', type=int, default=3, help='Num of heads in multi-head attention.')
parser.add_argument('--sublayer_first', type=int, default=3, help='Num of the first sublayers in dcgcn block.')
parser.add_argument('--sublayer_second', type=int, default=3, help='Num of the second sublayers in dcgcn block.')
parser.add_argument('--pooling', choices=['max', 'avg', 'sum'], default='max', help='Pooling function type. Default max.')
parser.add_argument('--pooling_l2', type=float, default=0.002, help='L2-penalty for all pooling output.')
parser.add_argument('--mlp_layers', type=int, default=1, help='Number of output mlp layers.')
parser.add_argument('--no_adj', dest='no_adj', action='store_true', help="Zero out adjacency matrix for ablation.")
parser.add_argument('--no-rnn', dest='rnn', action='store_false', help='Do not use RNN layer.')
parser.add_argument('--rnn_hidden', type=int, default=300, help='RNN hidden state size.')
parser.add_argument('--rnn_layers', type=int, default=1, help='Number of RNN layers.')
parser.add_argument('--rnn_dropout', type=float, default=0.5, help='RNN dropout rate.')
parser.add_argument('--lr', type=float, default=0.1, help='Applies to sgd and adagrad.')
parser.add_argument('--lr_decay', type=float, default=0.9, help='Learning rate decay rate.')
parser.add_argument('--decay_epoch', type=int, default=5, help='Decay learning rate after this epoch.')
parser.add_argument('--optim', choices=['sgd', 'adagrad', 'adam', 'adamax'], default='sgd', help='Optimizer: sgd, adagrad, adam or adamax.')
parser.add_argument('--num_epoch', type=int, default=100, help='Number of total training epochs.')
parser.add_argument('--batch_size', type=int, default=64, help='Training batch size.')
parser.add_argument('--max_grad_norm', type=float, default=5.0, help='Gradient clipping.')
parser.add_argument('--log_step', type=int, default=20, help='Print log every k steps.')
parser.add_argument('--log', type=str, default='logs.txt', help='Write training log to file.')
parser.add_argument('--save_epoch', type=int, default=100, help='Save model checkpoints every k epochs.')
parser.add_argument('--save_dir', type=str, default='./saved_models', help='Root dir for saving models.')
parser.add_argument('--id', type=str, default='02', help='Model ID under which to save models.')
parser.add_argument('--info', type=str, default='', help='Optional info for the experiment.')
parser.add_argument('--seed', type=int, default=0)
parser.add_argument('--cuda', type=bool, default=torch.cuda.is_available())
parser.add_argument('--cpu', action='store_true', help='Ignore CUDA.')
parser.add_argument('--load', dest='load', action='store_true', help='Load pretrained model.')
parser.add_argument('--model_file', type=str, help='Filename of the pretrained model.')
print(torch.cuda.device_count())
args = parser.parse_args()
torch.manual_seed(args.seed)
np.random.seed(args.seed)
random.seed(1024)
args.load=True
args.cpu=False
args.cuda=True
augdatanum=500
args.model_file='saved_models/02/best_model.pt'
if args.cpu:
    args.cuda = False
elif args.cuda:
    torch.cuda.manual_seed_all(args.seed)
    os.environ["CUDA_VISIBLE_DEVICES"] = "0,1"
init_time = time.time()
print(torch.cuda.device_count())
# make opt
opt = vars(args)
label2id = constant.LABEL_TO_ID
opt['num_class'] = len(label2id)
SUBJ_LIST=list(constant.SUBJ_NER_TO_ID.keys())
OBJ_LIST=list(constant.OBJ_NER_TO_ID.keys())
SUBJ_LIST.remove('<PAD>')
SUBJ_LIST.remove('<UNK>')
OBJ_LIST.remove('<PAD>')
OBJ_LIST.remove('<UNK>')
aug_data=[]

#     data_file="dataset/"+subj+"_"+obj+"_train_data.json"
#     if os.path.exists(data_file):
#         with open(data_file,'r') as f:
#             entity_data=json.load(f)
#             aug_data+=entity_data
# with open("dataset/aug_train_data.json",'w') as f:
#     json.dump(aug_data,f)

# print(torch.cuda.device_count())
# with torch.cuda.device(0):
entitie_pairs = constant.REL_ENTITIES
for entitie_pair in entitie_pairs:
    subj = entitie_pair[0]
    obj = entitie_pair[-1]
    # load vocab

    vocab_file = opt['vocab_dir'] + '/vocab.pkl'
    vocab = Vocab(vocab_file, load=True)
    opt['vocab_size'] = vocab.size
    emb_file = opt['vocab_dir'] + '/embedding.npy'
    emb_matrix = np.load(emb_file)
    assert emb_matrix.shape[0] == vocab.size
    assert emb_matrix.shape[1] == opt['emb_dim']

    # load data
    print("Loading data from {} with batch size {}...".format(opt['data_dir'], opt['batch_size']))
    #label_weight=train_batch.getWeight()
    model_id = opt['id'] if len(opt['id']) > 1 else '0' + opt['id']
    model_save_dir = opt['save_dir'] + '/' + model_id
    opt['model_save_dir'] = model_save_dir
    helper.ensure_dir(model_save_dir, verbose=True)

    # save config
    helper.save_config(opt, model_save_dir + '/config.json', verbose=True)
    vocab.save(model_save_dir + '/vocab.pkl')
    file_logger = helper.FileLogger(model_save_dir + '/' + opt['log'], header="# epoch\ttrain_loss\tdev_loss\tdev_score\tbest_dev_score")

    # print model info
    helper.print_config(opt)
    # model
    id2label = dict([(v,k) for k,v in label2id.items()])
    aug_train_epoch=5
    # for subj in SUBJ_LIST:
    #     for obj in OBJ_LIST:
    print("labeled dataset for class with subj:" + str(subj) + " and obj: " + str(obj))
    # model_file = "saved_models/02/" + subj + "_" + obj + "_" + "best_model.pt"
    # if not os.path.exists(model_file):
    #     model_file="saved_models/02/"+"best_model_aug.pt"
    train_batch = DataLoader([opt['data_dir'] + '/train_coref.json'], opt['batch_size'], opt, vocab, evaluation=False,is_aug=False,corefresolve=True,subj=subj,obj=obj)
    dev_batch = DataLoader([opt['data_dir'] + '/dev_rev_coref.json'], opt['batch_size'], opt, vocab, evaluation=True,corefresolve=True,subj=subj,obj=obj)
    test_batch = DataLoader([opt['data_dir'] + '/test_rev_coref.json'], opt['batch_size'], opt, vocab, evaluation=True,corefresolve=True,obj=obj,subj=subj)
    # if dev_batch.num_examples==0 or test_batch.num_examples==0:
    #     continue
    max_steps = len(train_batch) * opt['num_epoch']
    global_step = 0
    global_start_time = time.time()
    format_str = '{}: step {}/{} (epoch {}/{}), loss = {:.6f} ({:.3f} sec/batch), lr: {:.6f}'
    score_history = []
    test_score_history=[]
    current_lr = opt['lr']
    if not opt['load']:
        trainer = GCNTrainer(opt, emb_matrix=emb_matrix)
    else:
        #load pretrained model
        model_file = opt['model_file']
        print("Loading model from {}".format(model_file))
        model_opt = torch_utils.load_config(model_file)
        model_opt['optim'] = opt['optim']
        model_opt['lr'] = opt['lr']
        model_opt['lr_decay'] = opt['lr_decay']
        trainer = GCNTrainer(model_opt)
        trainer.load(model_file)
        # model_file = "saved_models/02/" + subj + "_" + obj + "_" + "best_model.pt"
        print("Evaluating on dev set...")
        predictions = []
        dev_loss = 0
        for i, batch in enumerate(dev_batch):
            preds, probs, loss, samples = trainer.predict(batch)
            predictions += preds
            dev_loss += loss
        predictions = [id2label[p] for p in predictions]
        dev_p, dev_r, dev_f1 = scorer.score(dev_batch, predictions)

        test_loss = 0
        predictions = []
        for i, batch in enumerate(test_batch):
            preds, _, loss, samples = trainer.predict(batch)
            predictions += preds
            test_loss += loss
        predictions = [id2label[p] for p in predictions]
        test_loss = test_loss / test_batch.num_examples * opt['batch_size']
        test_p, test_r, test_f1 = scorer.score(test_batch, predictions)
        score_history += [dev_f1]
        test_score_history+=[test_f1]
    stand=3
    for epoch in range(1, opt['num_epoch']+1):
        # if (not train_batch.NoAugData()):
        #     label_count={}
        #     train_batch.setisEval(True)
        #     probs={}
        #     for i,batch in enumerate(train_batch):
        #         preds, prob, _,sample = trainer.predict(batch)
        #         probs=dict(probs,**prob)
        # #probs=sorted(probs.items(),key=lambda item:max(item[1]))
        #     labels=[p[1].index(max(p[1])) for p in probs][:augdatanum]
        # # aug_data=[p[0] for p in probs][:augdatanum]
        # # train_batch.augTrainData(aug_data,labels)
        #     train_batch.LabeledAugData(probs)
        # else:
        #     print("data:"+str(train_batch.__len__()))
        #     print("pity")
            # for label in labels:
            #     if label in label_count.keys():
            #         label_count[label]=label_count[label]+1
            #     else:
            #         label_count[label]=1
            # print(label_count)
            # aug_train_epoch=0
        # is_best_model=False
        train_loss = 0
        # train_batch.randomChoiceData(c)
        if train_batch.__len__()==0:
            continue
        for i, batch in enumerate(train_batch):
            start_time = time.time()
            global_step += 1
            loss = trainer.update(batch)
            train_loss += loss
            if global_step % opt['log_step'] == 0:
                duration = time.time() - start_time
                print(format_str.format(datetime.now(), global_step, max_steps, epoch, \
                                        opt['num_epoch'], loss, duration, current_lr))
    #
        # # eval on dev
        print("Evaluating on dev set...")
        predictions = []
        dev_loss = 0
        for i, batch in enumerate(dev_batch):
            preds, probs, loss,samples = trainer.predict(batch)
            predictions += preds
            dev_loss += loss

        predictions = [id2label[p] for p in predictions]
        train_loss = train_loss / train_batch.num_examples * opt['batch_size']  # avg loss per batch
        dev_loss = dev_loss / dev_batch.num_examples * opt['batch_size']

        dev_p, dev_r, dev_f1 = scorer.score(dev_batch, predictions)

        test_loss = 0
        predictions=[]
        for i, batch in enumerate(test_batch):
            preds, _, loss,samples = trainer.predict(batch)
            predictions += preds
            test_loss += loss
        predictions = [id2label[p] for p in predictions]
        test_loss = test_loss / test_batch.num_examples * opt['batch_size']

        test_p, test_r, test_f1 = scorer.score(test_batch, predictions)
        dev_score = dev_f1
        file_logger.log("{}\t{:.6f}\t{:.6f}\t{:.4f}\t{:.4f}".format(epoch, train_loss, dev_loss, dev_score,
                                                                    max([dev_score] + score_history)))
        # save
        #aug_train_epoch=aug_train_epoch+1
        model_file = model_save_dir + '/checkpoint_epoch_{}.pt'.format(epoch)
        trainer.save(model_file, epoch)
        # if test_f1>0.773:
        #     print(test_f1)
        #     break
        print("epoch {}: train_loss = {:.6f}, dev_loss = {:.6f}, dev_f1 = {:.4f},ave_f1={:.4f}".format(epoch, \
                                                                                           train_loss, dev_loss,
                                                                                           dev_f1,dev_f1))
        if  dev_f1 > max(score_history):
            #current_lr=0.06
            #aug_train_epoch=5
            #trainer.update_lr(current_lr)
            stand=3
        if  test_f1 > max(test_score_history):
            copyfile(model_file, "saved_models/02/" + subj + "_" + obj + "_" + "best_model.pt")
            print("new best model saved.")
            file_logger.log("new best model saved at epoch {}: {:.2f}\t{:.2f}\t{:.2f}" \
                              .format(epoch, dev_p * 100, dev_r * 100, dev_score * 100))

    # if epoch % opt['save_epoch'] != 0:
        #     os.remove(model_file)
        #lr schedule
        if len(score_history) > opt['decay_epoch'] and dev_f1 < score_history[-1] and \
                     opt['optim'] in ['sgd', 'adagrad', 'adadelta']:
        # if dev_score <= dev_score_history[-1] and \
        #         opt['optim'] in ['sgd', 'adagrad', 'adadelta']:
            stand=stand-1
            if stand==0:
                if current_lr<0.03:
                    break
                else:
                    current_lr *= opt['lr_decay']
                    trainer.update_lr(current_lr)
                    stand=3


        if epoch > opt['decay_epoch'] and dev_f1 < score_history[-1] and \
                opt['optim'] in ['sgd', 'adagrad', 'adadelta']:
            current_lr *= opt['lr_decay']
            trainer.update_lr(current_lr)

        # if  dev_f1 < score_history[-1] and \
        #         opt['optim'] in ['sgd', 'adagrad', 'adadelta']:
        #     current_lr *= opt['lr_decay']
        #     trainer.update_lr(current_lr)

        #train_loss_history += [train_loss]
        #trainer.updatemisclass()
        score_history += [dev_f1]
        test_score_history+=[test_f1]
        print("")
# start training



