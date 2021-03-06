"""
Data loader for TACRED json files.
"""

import json
import random
import torch
import numpy as np
import copy
import json
from functools import reduce

from utils import constant
from model.tree import head_to_tree,head_to_treeEval,tree_to_adj

class DataLoader(object):
    """
    Load data from json files, preprocess and prepare batches.
    """
    def __init__(self, filenames, batch_size, opt, vocab, subj=None,obj=None,evaluation=False,corefresolve=False,is_aug=False,is_soft=False,randomchoice=False):
        self.batch_size = batch_size
        self.opt = opt
        self.vocab = vocab
        self.eval = evaluation
        self.is_eval=False
        self.label2id = constant.LABEL_TO_ID
        self.corefresolve=corefresolve
        self.is_soft = is_soft
        self.subj=subj
        self.obj=obj
        self.data_index = {}
        self.is_aug=is_aug
        self.randomchoice=randomchoice
        with open('samples.json','r') as f:
            self.ids=json.load(f)
        # with open('samples_64.json','r') as f:
        #     self.ids64=json.load(f)
        data=[]
        for filename in filenames:
            with open(filename,'r') as infile:
                data += json.load(infile)
        self.data_json = data
        if is_aug:
            aug_data = self.simulatedatajson(data)
            self.aug_data_json = aug_data
            aug_data = self.preprocess(aug_data)
            self.aug_data = [aug_data[i:i + batch_size] for i in range(0, len(aug_data), batch_size)]
        #data= self.preprocess(data,tokenizer, opt)
        data = self.preprocess(data)
        self.id2label = dict([(v, k) for k, v in self.label2id.items()])
        isOver=True
        # shuffle for training
        if not evaluation:
            indices = list(range(len(data)))
            random.shuffle(indices)
            data = [data[i] for i in indices]
        if not self.is_soft:
            self.labels = [self.id2label[d[0][-2]] for d in data]
        else:
            self.labels=[d[0][-2] for d in data]
        self.distance= [d[0][-3] for d in data]
        self.num_examples = len(data)

            # chunk into batches

        data_chunk = [data[i:i+batch_size] for i in range(0, len(data), batch_size)]
        # if not evaluation:
        #     data_chunk=[data_chunk[813]]
        # else:
        #     data_chunk=[]
        self.data = data_chunk
        self.train_data=[]
        #self.label_weight=label_weight
        print("{} batches created for {}".format(len(data_chunk), filename))

    def simulatedatajson(self,datas):
        augment_data=[]
        for d in datas:
            if len(augment_data) > 1000:
                break
            # subj_ner_list = list(constant.SUBJ_NER_TO_ID.keys())[2:]
            # obj_ner_list = list(constant.OBJ_NER_TO_ID.keys())[2:]
            subj_entities,obj_entities=self.getEntitySpan(d)
            count=0
            ners=d['stanford_ner']
            for subj_entity in subj_entities:
                for obj_entity in obj_entities:
                    if subj_entity[0] == obj_entity[0] or subj_entity[0] == d['subj_start'] and obj_entity[0] == d['obj_start']:
                        continue
                    else:
                        rd=copy.deepcopy(d)
                        rd['subj_start'] = subj_entity[0]
                        rd['subj_end']=subj_entity[-1]
                        rd['obj_start']=obj_entity[0]
                        rd['obj_end']=obj_entity[-1]
                        rd['subj_type']=ners[subj_entity[0]]
                        rd['obj_type']=ners[obj_entity[0]]
                        rd['id']=d['id']+"_"+str(count)
                        count=count+1
                        augment_data.append(rd)
        return augment_data

    def getEntitySpan(self,d):
        subj_entities = []
        obj_entities = []
        ners = d['stanford_ner']
        self.data_index[d['id']] = d
        i = 0
        while (i < len(ners)):
            ner = ners[i]
            if ner == self.subj:
                span = []
                for w in range(i, len(ners)):
                    if ners[w] == ner:
                        span.append(w)
                    else:
                        if ner == self.obj:
                            obj_entities.append(span)
                            i = w
                        subj_entities.append(span)
                        break
            elif ner == self.obj:
                span = []
                for w in range(i, len(ners)):
                    if ners[w] == ner:
                        span.append(w)
                    else:
                        i = w
                        break
                obj_entities.append(span)
            i = i + 1
        return subj_entities,obj_entities

    def preprocess(self, data):
        """ Preprocess the data and convert to ids. """
        processed = []
        rel_entities=[]
        count=0
        for d in data:
            # if d['id']=='61b3a65fb91fbb9fcc5b':
            #     continue
            # if d['id'] not in self.ids:
            #     continue
            # if (d['id'] in self.ids)^(d['id'] not in self.ids64):
            #     continue
            count+=1
            batch=self.packdata(d)
            subj_type=d['subj_type']
            obj_type=d['obj_type']
            entity_pair=[subj_type,obj_type]
            if entity_pair not in rel_entities:
                rel_entities.append(entity_pair)
            if len(batch)!=0:
                processed += batch
        return processed

    def randomChoiceData(self,cls):
        train_id=set()
        self.train_data=[]
        labels_map = dict(zip(cls, list(range( 1, 1 + len(cls)))))
        for id,d in enumerate(self.all_data):
            if d[15] in cls:
                train_id.add(id)

        chotime=2*len(train_id)
        self.num_examples=chotime
        while len(train_id)<chotime:
            id=random.choice(list(range(len(self.all_data))))
            train_id.add(id)
        for i in train_id:
            d=list(copy.deepcopy(self.all_data[i]))
            d[15]=labels_map[d[15]] if d[15] in cls else 0
            self.train_data.append(tuple(d))
        indices = list(range(len(self.train_data)))
        random.shuffle(indices)
        self.train_data = [self.train_data[i] for i in indices]
        self.labels = [self.id2label[d[-1]] for d in self.train_data]
        self.distance = [d[-2] for d in self.train_data]
        self.train_data = [self.train_data[j:j + self.batch_size] for j in range(0, len(self.train_data), self.batch_size)]

    def packdata(self,d):
        if not self.is_soft:
            relation = d['relation']
            if isinstance(relation, list):
                relation = relation.index(max(relation))
            else:
                relation = self.label2id[relation]
        else:
            relation = d['soft_label']
        # if self.subj is not None:
        #     if d['subj_type']!=self.subj or d['obj_type']!=self.obj:
        #         return []
        #rev_relation = 0
        # # if relation!=40:
        #     continue
        # rev_relation=self.findRevLabel(d['id'],"test")
        # label_count[relation]+=1
        rd = copy.deepcopy(d)
        # if 'conj' in d['stanford_deprel']:
        #     rd=self.removeconj(rd)
        head = [int(x) for x in d['stanford_head']]
        ners2id=constant.NER_TO_ID
        id2ners=dict([(v, k) for k, v in ners2id.items()])
        # subj_id = list(range(ss,se+1))
        # obj_id=list(range(os,oe+1))
        assert any([x == 0 for x in head])
        tokens = list(rd['token'])
        containDot=True
        if self.opt['lower']:
            tokens = [t.lower() for t in tokens]
        if tokens[-1]!='.':
            containDot=False
        raw_tokens = copy.deepcopy(tokens)
        # tokens = map_to_ids(tokens, vocab.word2id)
        pos = map_to_ids(rd['stanford_pos'], constant.POS_TO_ID)
        ner = map_to_ids(rd['stanford_ner'], constant.NER_TO_ID)
        deprel = map_to_ids(rd['stanford_deprel'], constant.DEPREL_TO_ID)
        head = [int(x) for x in rd['stanford_head']]
        sid = rd['id']
        assert any([x == 0 for x in head])
        l = len(tokens)

        if not self.corefresolve:
            ss, se = rd['subj_start'], rd['subj_end']
            os, oe = rd['obj_start'], rd['obj_end']
            subj_id = list(range(ss, se + 1))
            obj_id = list(range(os, oe + 1))
            tree, domains, distance= head_to_tree(head, deprel, subj_id, obj_id)

            depmap, ret, rel, resrel, domain, domain_subj, domain_obj = tree_to_adj(l, domains, tree)
            # subj_entities, obj_entities = self.getEntitySpan(rd)
            # entities_span = list(set(subj_entities + obj_entities))
            # entity_gragh=self.getEntityGragh(depmap, entities_span)
            # anonymize tokens

            tokens[ss:se + 1] = ['SUBJ-' + rd['subj_type']] * (se - ss + 1)
            tokens[os:oe + 1] = ['OBJ-' + rd['obj_type']] * (oe - os + 1)
            raw_tokens[ss:se + 1] = zip(raw_tokens[ss:se + 1], (['RAWSUBJ-' + d['subj_type']] * (se - ss + 1)))
            raw_tokens[os:oe + 1] = zip(raw_tokens[os:oe + 1], (['RAWOBJ-' + d['obj_type']] * (oe - os + 1)))

            raw_tokens.append(distance)
            subj_positions = get_positions(ss, se, l)
            obj_positions = get_positions(os, oe, l)
            tokens = map_to_ids(tokens, self.vocab.word2id)
            sdp_mask=1*(domain.T[1]==0)
        else:
            #entityspans=self.getEntitySpan(d)
            src_subj=list(range(d['subj_start'],d['subj_end'] + 1))
            src_obj=list(range(d['obj_start'], d['obj_end'] + 1))

            if 'subj_list' in rd.keys():
                subj_list=rd['subj_list']
                obj_list=rd['obj_list']
            else:
                subj_list=[src_subj]
                obj_list=[src_obj]
            # for span in subj_list:
            #     entityspans.remove(subj_list)
            # relpairs=[]
            # # interpairs=[]
            # # corefpairs=[]
            # for subj in subj_list:
            #     for obj in obj_list:
            #         if subj!=obj:
            #             relpairs.append([subj,obj])
            # corefpairs.append()
            # for s in entityspans:
            #     for o in entityspans:
            #         if s!=o:
            #             if [s,o] not in relpairs:
            #                 interpairs.append([s,o])
            # entity_mask=[]
            # coref_mask=[]
            # for pair in interpairs:
            #     mask=[0] * l
            #     mask[pair[0]]=1
            #     mask[pair[1]]=1
            # subj_mask=[]

            def notinter(a,b):
                return len(set(a)&set(b))==0

            relpairs=[]
            for subj in subj_list:
                for obj in obj_list:
                    if notinter(subj,obj):
                        relpairs.append([subj,obj])

            entity_dep=constant.no_pass
            entity_ids=[]
            for i in range(len(tokens)):
                if deprel[i] in entity_dep:
                    entity_ids.append([i])


            entity_ner = [ners2id[d['subj_type']]]
            if d['obj_type'] in ners2id.keys():
                entity_ner.append(ners2id[d['obj_type']])
            if 3 in entity_ner:
                entity_pos = [15, 20]
            else:
                entity_pos = []
            tree, domains, distance,relpair,midhead,entity_chains,sdp_domain = head_to_treeEval(head, deprel, ner,pos,entity_ner,entity_pos,relpairs,build_mid=True)
            # filterrelpair=[]
            # for pair in relpairs:
            #     subj=pair[0]
            #     obj=pair[1]
            #     if isinstance(subj,list):
            #         subj_end=subj[-1]
            #         subj_start=subj[0]
            #         cur=subj_end
            #         h=head[cur]-1
            #         while (h<=subj_end and h>=subj_start):
            #             cur=h
            #             h = head[cur] - 1
            #     layers=midhead[cur]
            #     if isinstance(obj,list):
            #         obj_end=obj[-1]
            #         obj_start=obj[0]
            #         cur=obj_end
            #         h=head[cur]-1
            #         while (h<=obj_end and h>=obj_start):
            #             cur=h
            #             h = head[cur] - 1
            #     layero=midhead[cur]
            #     if not(layero!=layers and (layers>obj_end or layers<obj_start) and (layero>subj_end or layero<subj_start)):
            #         filterrelpair.append([subj,obj])
            iscross=0
            # if len(filterrelpair)==0:
            #     iscross=1

                # if relation!=0:
                #     iscross=True
                #     print("miss lit. su")
                # return []
            # else:
            #     tree, domains, distance, relpair, midhead = head_to_treeEval(head, deprel, relpairs, build_mid=False)
            depmap, ret, rel, resrel, domain,sdp_domain, domain_subj, domain_obj = tree_to_adj(l, domains, tree,entity_chains,sdp_domain)
            # relpairs = rawrelpair
            obj_mask=[-1]*l
            subj_mask=[-1]*l
            aspect=[]
            #relpairs=[rawrelpair]
            relpairs=[relpair]
            for pair in relpairs:
                subj_span=pair[0]
                obj_span=pair[1]
                rtokens=copy.deepcopy(tokens)
                rrawtokens=copy.deepcopy(tokens)
                rsubjmask=copy.deepcopy(subj_mask)
                robjmask=copy.deepcopy(obj_mask)

                for entity_pair in entity_chains[1:]:
                    entity_span=entity_pair[0]
                    entityner=ner[entity_span[0]]
                    if entityner==2:
                        entityner=3
                    rtokens[entity_span[0]:entity_span[-1] + 1] = ['ENTITY_' +id2ners[entityner]] * (entity_span[-1] - entity_span[0] + 1)
                    rrawtokens[entity_span[0]:entity_span[-1] + 1] = zip(rrawtokens[entity_span[0]:entity_span[-1] + 1], (
                            ['ENTITY_' + id2ners[entityner]] * (entity_span[-1] - entity_span[0] + 1)))

                rtokens[subj_span[0]:subj_span[-1] + 1] = ['SUBJ-' + rd['subj_type']] * (subj_span[-1] - subj_span[0] + 1)
                #rtokens[subj_span[0]:subj_span[-1] + 1] = ['ENTITY_' + rd['subj_type']] * (
                #            subj_span[-1] - subj_span[0] + 1)

                rsubjmask[subj_span[0]:subj_span[-1] + 1] = [0] * (subj_span[-1] - subj_span[0] + 1)
                rrawtokens[subj_span[0]:subj_span[-1] + 1] = zip(rrawtokens[subj_span[0]:subj_span[-1] + 1], (
                            ['RAWSUBJ-' + d['subj_type']] * (subj_span[-1] - subj_span[0] + 1)))
                rtokens[obj_span[0]:obj_span[-1] + 1] = ['OBJ-' + rd['obj_type']] * (obj_span[-1] - obj_span[0] + 1)
                robjmask[obj_span[0]:obj_span[-1]+1]=[0]*(obj_span[-1]-obj_span[0]+1)
                rrawtokens[obj_span[0]:obj_span[-1] + 1] = zip(rrawtokens[obj_span[0]:obj_span[-1] + 1], (['RAWOBJ-' + d['obj_type']] * (obj_span[-1] - obj_span[0] + 1)))
                rrawtokens.append(distance)
                rtokens = map_to_ids(rtokens, self.vocab.word2id)
                mask = [1] * len(rtokens)
                if containDot:
                    mask[-1] = 0
                aspect.append((rtokens, pos, rsubjmask, robjmask, ner, depmap, ret, rel, resrel, deprel, domain,sdp_domain,domain_subj,
                domain_obj, mask,sid,iscross, distance, relation,rrawtokens))

            if [src_subj,src_obj] not in relpairs:
                tree, domains, distanceraw,relpair,midhead,entity_chains,sdp_domain = head_to_treeEval(head, deprel,ner, pos,entity_ner,entity_pos,[[src_subj,src_obj]],build_mid=True)
                distance=distanceraw
                depmap, ret, rel, resrel, domain, sdp_domain,domain_subj, domain_obj = tree_to_adj(l, domains, tree,entity_chains,sdp_domain)
                obj_span=src_obj
                subj_span=src_subj
                rtokens = copy.deepcopy(tokens)
                rrawtokens = copy.deepcopy(tokens)
                rsubjmask = copy.deepcopy(subj_mask)
                robjmask = copy.deepcopy(obj_mask)

                for entity_pair in entity_chains[1:]:
                    entity_span=entity_pair[-1]
                    entityner=ner[entity_span[0]]
                    if entityner==2:
                        entityner=3
                    rtokens[entity_span[0]:entity_span[-1] + 1] = ['ENTITY_' +id2ners[entityner]] * (entity_span[-1] - entity_span[0] + 1)
                    rrawtokens[entity_span[0]:entity_span[-1] + 1] = zip(rrawtokens[entity_span[0]:entity_span[-1] + 1],(['ENTITY_' + id2ners[entityner]] * (entity_span[-1] - entity_span[0] + 1)))
                rtokens[subj_span[0]:subj_span[-1] + 1] = ['SUBJ-' + rd['subj_type']] * (subj_span[-1] - subj_span[0] + 1)

                # rtokens[subj_span[0]:subj_span[-1] + 1] = ['ENTITY_' + rd['subj_type']] * (
                #         subj_span[-1] - subj_span[0] + 1)
                rsubjmask[subj_span[0]:subj_span[-1] + 1] = [0] * (subj_span[-1] - subj_span[0] + 1)
                rrawtokens[subj_span[0]:subj_span[-1] + 1] = zip(rrawtokens[subj_span[0]:subj_span[-1] + 1], (
                        ['RAWSUBJ-' + d['subj_type']] * (subj_span[-1] - subj_span[0] + 1)))
                rtokens[obj_span[0]:obj_span[-1] + 1] = ['OBJ-' + rd['obj_type']] * (obj_span[-1] - obj_span[0] + 1)
                robjmask[obj_span[0]:obj_span[-1] + 1] = [0] * (obj_span[-1] - obj_span[0] + 1)
                rrawtokens[obj_span[0]:obj_span[-1] + 1] = zip(rrawtokens[obj_span[0]:obj_span[-1] + 1], (
                            ['RAWOBJ-' + d['obj_type']] * (obj_span[-1] - obj_span[0] + 1)))
                rrawtokens.append(distance)
                rtokens = map_to_ids(rtokens, self.vocab.word2id)
                mask = [1] * len(rtokens)
                if containDot:
                    mask[-1] = 0
                aspect.append(
                    (rtokens, pos, rsubjmask, robjmask, ner, depmap, ret, rel, resrel, deprel, domain, sdp_domain,domain_subj,
                     domain_obj, mask, sid, iscross,distance, relation, rrawtokens))
        # if len(aspect)<2 or relation!=0:
        #     return []
        # subj_type = [constant.SUBJ_NER_TO_ID[d['subj_type']]]
        # obj_type = [constant.OBJ_NER_TO_ID[d['obj_type']]]
        # processed += [(tokens, pos, ner, deprel, head, subj_positions, obj_positions, subj_type, obj_type, length,relation)]
        batch= [aspect]
        return batch

    def removeconj(self,d):
        ss, se = d['subj_start'], d['subj_end']
        os, oe = d['obj_start'], d['obj_end']
        issdppath=False
        tokens=copy.deepcopy(d['token'])
        deprel=copy.deepcopy(d['stanford_deprel'])
        head=copy.deepcopy(d['stanford_head'])
        pos=copy.deepcopy(d['stanford_pos'])
        ner=copy.deepcopy(d['stanford_ner'])
        oidx = -1
        for i in range(os,oe+1):
            next=head[i]-1
            if next<os or next>oe:
                if oidx!=-1:
                    return d
                else:
                    oidx=i
        sidx=-1
        for i in range(ss, se + 1):
            next = head[i]-1
            if next < ss or next > se:
                if sidx != -1:
                    return d
                else:
                    sidx = i
        cur=sidx
        replace_id={}
        spath=[]
        while(True):
            if cur==-1:
                break
            spath.append(cur)
            if deprel[cur]=='conj':
                rep=head[cur]-1
                if rep<=oe and rep>=os:
                    break
                head[cur] = head[rep]
                replace_id[rep]=cur
                pos[cur]=pos[rep]
                deprel[cur]=deprel[rep]
                ner[cur]=ner[rep]
                head[rep]=rep+1
            cur=head[cur]-1
        cur = oidx
        while (True):
            if cur == -1:
                break
            next=head[cur]-1
            if next==cur:
                next=replace_id[next]
                head[cur]=next+1
                cur=next
                continue
            if deprel[cur] == 'conj':
                if next<=se and next>=ss:
                    break
                if next in spath:
                    i=spath.index(next)
                    head[spath[i-1]]=cur+1
                head[cur] = head[next]
                pos[cur] = pos[next]
                deprel[cur] = deprel[next]
                ner[cur] = ner[next]
                head[next] = next + 1
                next=head[cur]-1
            cur = next

        length=len(head)
        depmap=[-1]*length
        def flagrel(i):
            if depmap[i]!=-1:
                return depmap[i];
            next=head[i]-1
            if next==-1:
                depmap[i]=0
                return 0
            if next==i:
                depmap[i]=1
                return 1
            flag=flagrel(next)
            depmap[i]=flag
            return flag

        for i in range(length):
            flagrel(i)
        movestep=0
        reloc=[-1]*length
        newhead=copy.deepcopy(head)
        for i in range(length):
            if depmap[i]==1:
                movestep+=1
                continue
            else:
                reloc[i]=i-movestep
        for i in range(length):
            if reloc[i]==-1:
                continue
            else:
                pos[reloc[i]]=pos[i]
                ner[reloc[i]]=ner[i]
                deprel[reloc[i]]=deprel[i]
                tokens[reloc[i]]=tokens[i]
                if head[i]==0:
                    newhead[reloc[i]]=0
                else:
                    newhead[reloc[i]] = reloc[head[i] - 1] + 1
        assert reloc[ss]>=0 and reloc[os]>=0
        d['subj_start']=reloc[ss]
        d['subj_end']=reloc[se]
        d['obj_start']=reloc[os]
        d['obj_end']=reloc[oe]
        d['token']=tokens[:length-movestep]
        d['stanford_deprel']=deprel[:length-movestep]
        d['stanford_head']=newhead[:length-movestep]
        d['stanford_pos']=pos[:length-movestep]
        d['stanford_ner']=ner[:length-movestep]
        return d

    def getEntityGragh(self,depmap,spans):
        product=depmap
        n=depmap.shape(1)
        mulrel=depmap+np.identity(n)
        resrel=np.zeros(len(spans))
        for i in range(n):
            temp=1*(product.dot(mulrel)!=0)
            newtemp=product-temp
            if (newtemp==0).all():
                break
            row,col=newtemp.nonzeros()
            row_span_ids=-1
            col_span_ids=-1
            for j in range(len(row)):
                for k,span in enumerate(spans):
                    if row[j] in span:
                        row_span_ids=k
                    if col[j] in span:
                        col_span_ids=k
                    if row_span_ids!=-1 and col_span_ids!=-1:
                        break
            if row_span_ids==-1 or col_span_ids ==-1:
                continue
            if resrel[row_span_ids][col_span_ids]==0:
                resrel[row_span_ids][col_span_ids]=1
            else:
                for subj in spans[row_span_ids]:
                    for obj in spans[col_span_ids]:
                        newtemp[subj][obj]=0
                        newtemp[obj][subj]=0
            if (newtemp==0).all():
                break
            else:
                product=product+newtemp
        return resrel

    def LabeledAugData(self, probs):
        for d in self.aug_data_json:
            d['relation'] = probs[d['id']]
        # for d in self.data:
        #     s_label = [0] * cate_nums
        #     s_label[self.label2id[d['id']]] = 1
        # with open('aug_train_data.json', 'w') as f:
        #     json.dump(self.aug_data, f)
        model_file='dataset/'+self.subj+'_'+self.obj+'_train_data.json'
        print("save augment data at "+model_file)
        with open(model_file, 'w') as f:
            json.dump(self.aug_data_json, f)

    def simulate_data(self, id, aug_id, subj_start, subj_end, obj_start, obj_end):
        d = self.data_index[id]

        sid = id
        imp = 0
        relation = self.label2id[d['relation']]
        # if sid in imps.keys():
        #     imp = imps[sid]
        tokens = list(d['token'])

        raw_tokens = copy.deepcopy(tokens)
        pos = map_to_ids(d['stanford_pos'], constant.POS_TO_ID)
        ner = map_to_ids(d['stanford_ner'], constant.NER_TO_ID)
        deprel = map_to_ids(d['stanford_deprel'], constant.DEPREL_TO_ID)
        head = [int(x) for x in d['stanford_head']]
        # subj_id = list(range(ss, se + 1))
        # obj_id = list(range(os, oe + 1))
        l = len(tokens)
        subj_idx = list(range(subj_start, subj_end + 1))
        obj_idx = list(range(obj_start, obj_end + 1))
        tree, domains, distance = head_to_tree(head, deprel, subj_idx, obj_idx)
        # if d['subj_start'] == subj_span[0] and d['subj_end'] == subj_span[-1] and d['obj_start'] == obj_span[0] and \
        #         d['obj_end'] == obj_span[-1]:
        #     continue
        raw_tokens.append(distance)
        subj_type = d['stanford_ner'][subj_start]
        obj_type = d['stanford_ner'][obj_start]
        # if distance <= 6:
        #     continue
        depmap, ret, rel, resrel, domain, domain_id, redomian_id = tree_to_adj(l, domains, tree)

        tokens[subj_start:subj_end + 1] = ['SUBJ-' + subj_type] * (subj_end - subj_start + 1)
        tokens[obj_start:obj_end + 1] = ['OBJ-' + obj_type] * (obj_end - obj_start + 1)
        tokens = map_to_ids(tokens, self.vocab.word2id)
        subj_positions = get_positions(subj_start, subj_end, l)
        obj_positions = get_positions(obj_start, obj_end, l)
        raw_tokens[subj_start:subj_end + 1] = zip(raw_tokens[subj_start:subj_end + 1], (
                ['SUBJ-' + subj_type] * (subj_end - subj_start + 1)))
        raw_tokens[obj_start:obj_end + 1] = zip(raw_tokens[obj_start:obj_end + 1], (
                ['OBJ-' + obj_type] * (obj_end - obj_start + 1)))

        batch = [(tokens, pos, subj_positions, obj_positions, ner, depmap, ret, rel, resrel, deprel, domain, domain_id,
                  redomian_id,aug_id,distance,relation)]
        # batch_size = len(batch)
        # batch = list(zip(*batch))
        # # assert len(batch) == 10
        #
        # # sort all fields by lens for easy RNN operations
        # lens = [len(x) for x in batch[0]]
        # batch, orig_idx = sort_all(batch, lens)
        # lens = sorted(lens, reverse=True)
        # maxlen = lens[0]
        # domains = [b.shape[1] for b in batch[8]]
        # max_domain = max(domains)
        # words=batch[0]
        # words = get_long_tensor(words, batch_size)
        # masks = torch.eq(words, 0)
        # pos = get_long_tensor(batch[1], batch_size)
        # ner = get_long_tensor(batch[4], batch_size)
        #
        # depmap = padmat(batch[5], maxlen, maxlen)
        # for i in range(batch_size):
        #     depmap[i][len(tokens):, 0] = 1
        # ret = padmat(batch[6], maxlen, maxlen)
        # rel = padmat(batch[7], maxlen, maxlen)
        # resrel = padmat(batch[8], maxlen, maxlen)
        # deprel = get_long_tensor(batch[9], batch_size)
        # domain = padmat(batch[10], maxlen, max_domain)
        # domain_id = padmat(batch[11], maxlen, max_domain)
        # redomain_id = padmat(batch[12], maxlen, max_domain)
        # # head = get_long_tensor(batch[4], batch_size)
        # subj_positions = get_long_tensor(batch[2], batch_size)
        # obj_positions = get_long_tensor(batch[3], batch_size)
        # # subj_type = get_long_tensor(batch[7], batch_size)
        # # obj_type = get_long_tensor(batch[8], batch_size)
        # length = torch.LongTensor(batch[13])
        # raw_tokens = batch[14]
        # rels = torch.LongTensor(batch[15])
        # ids = batch[16]
        # imp = batch[17]
        # return (
        # words, masks, pos, subj_positions, obj_positions, ner, depmap, ret, rel, resrel, deprel, domain, domain_id,
        # redomain_id, rels,orig_idx, length, raw_tokens, ids, imp, batch[16])
        return batch

    def convert_token(self,token):
        """ Convert PTB tokens to normal tokens """
        if (token.lower() == '-lrb-'):
            return '('
        elif (token.lower() == '-rrb-'):
            return ')'
        elif (token.lower() == '-lsb-'):
            return '['
        elif (token.lower() == '-rsb-'):
            return ']'
        elif (token.lower() == '-lcb-'):
            return '{'
        elif (token.lower() == '-rcb-'):
            return '}'
        return token

    def setisEval(self,is_Eval):
        self.is_eval=is_Eval

    def getWeight(self):
        return self.label_weight

    def distances(self):
        return self.distance

    def gold(self):
        """ Return gold labels as a list. """
        return self.labels

    def __len__(self):
        if self.is_aug:
            return len(self.aug_data)
        elif self.randomchoice:
            return len(self.train_data)
        else:
            return len(self.data)

    def __getitem__(self, key):
        """ Get a batch with index. """
        if not isinstance(key, int):
            raise TypeError
        if self.is_aug:
            if key < 0 or key >= len(self.aug_data):
                raise IndexError
            batch = self.aug_data[key]
        elif self.randomchoice:
            if key < 0 or key >= len(self.train_data):
                raise IndexError
            batch = self.train_data[key]
        else:
            if key < 0 or key >= len(self.data):
                raise IndexError
            batch = self.data[key]
        lens = [len(x[0][0]) for x in batch]
        batch, orig_idx = sort_all(batch, lens)
        r_batch=[]
        batch_map={}
        for i,b in enumerate(batch):
            for j,s in enumerate(b):
                batch_map[len(r_batch)]=i
                r_batch.append(s)


        batch = list(zip(*r_batch))
        batch_size = len(r_batch)
        #assert len(batch) == 10

        # sort all fields by lens for easy RNN operations


        batch_values = list(batch_map.values())
        batch_keys = list(batch_map.keys())
        batch_mm = torch.sparse_coo_tensor((batch_values, batch_keys), torch.ones(batch_keys[-1] + 1),
                                            (batch_values[-1] + 1, batch_keys[-1] + 1)).to_dense()
        batch_mm = batch_mm / batch_mm.sum(dim=-1).unsqueeze(-1)
        lens = [len(x) for x in batch[0]]
        maxlen=lens[0]
        sdp_domain_len=[b.sum() for b in batch[11]]
        domain_len = [b.shape[1] for b in batch[10]]
        max_domain=max(domain_len)
        nid=torch.from_numpy((np.array(sdp_domain_len)*(-1)).argsort())
        rid=torch.linspace(0,batch_size-1,batch_size).long()
        order_mm=torch.sparse_coo_tensor(torch.cat((rid.unsqueeze(0),nid.unsqueeze(0)),dim=0),torch.ones(batch_size),(batch_size,batch_size)).to_dense()

        # word dropout
        if not self.eval:
            words = [word_dropout(sent, self.opt['word_dropout']) for sent in batch[0]]
        else:
            words = batch[0]

        # convert to tensors
        words=get_long_tensor(words, batch_size)
        masks = torch.eq(words, 0)
        pos = get_long_tensor(batch[1], batch_size)
        subj_pos=get_long_tensor(batch[2],batch_size)
        obj_pos=get_long_tensor(batch[3],batch_size)
        ner = get_long_tensor(batch[4], batch_size)

        depmap= padmat(batch[5], maxlen,maxlen)
        for i in range(batch_size):
            depmap[i][lens[i]:,0]=1
        ret=padmat(batch[6],maxlen,maxlen)
        rel=padmat(batch[7],maxlen,maxlen)
        resrel = padmat(batch[8], maxlen, maxlen)
        deprel = get_long_tensor(batch[9], batch_size)
        domain = padmat(batch[10], maxlen,max_domain)
        sdp_domain = padmat(batch[11], maxlen,max_domain)
        domain_subj = padmat(batch[12], maxlen,max_domain)
        domain_obj = padmat(batch[13], maxlen,max_domain)
        sdp_mask = get_long_tensor(batch[14],batch_size)
        # head = get_long_tensor(batch[4], batch_size)

        # subj_type = get_long_tensor(batch[7], batch_size)
        # obj_type = get_long_tensor(batch[8], batch_size)
        length=[]
        rels=[]
        sid=[]
        iscross=[]
        count=-1
        for i in range(len(batch[17])):
            if batch_map[i]>count:
                length.append(batch[17][i])
                sid.append(batch[15][i])
                iscross.append(batch[16][i])
                rels.append(batch[18][i])
                count=batch_map[i]
        length=torch.LongTensor(length)
        rels = torch.LongTensor(rels)
        iscross=torch.LongTensor(iscross)
        return (words, masks, pos,subj_pos,obj_pos,ner, depmap, ret, rel,resrel,deprel,domain,sdp_domain,domain_subj,domain_obj,order_mm,sdp_mask,batch_mm,rels,sid,iscross, orig_idx,length,batch[-1])

    def augTrainData(self, ids, labels):
        augdata = []
        rev_data = []
        for batch in self.aug_data:
            for d in batch:
                augdata.append(d)
        for batch in self.data:
            for d in batch:
                rev_data.append(d)
        temp=[]
        for i in range(len(ids)):
            id=int(ids[i])
            for k in range(len(augdata)):
                d=augdata[k]
                if d[-3]==id:
                    temp.append(k)
                    rev_data.append(d)
                    self.labels.append(labels[i])
                    break
        temp.sort()
        temp.reverse()
        for idx in temp:
            del augdata[idx]
        indices = list(range(len(self.data)))
        random.shuffle(indices)
        self.data = [self.data[i] for i in indices]
        self.labels = [self.labels[i] for i in indices]
        self.aug_data = [augdata[j:j + self.batch_size] for j in range(0, len(augdata), self.batch_size)]
        self.data = [rev_data[j:j + self.batch_size] for j in range(0, len(rev_data), self.batch_size)]


    def __iter__(self):
        for i in range(self.__len__()):
            yield self.__getitem__(i)


    def NoAugData(self):
        return len(self.aug_data)==0

    # def LabeledAugData(self,probs):
    #     cate_nums=len(constant.LABEL_TO_ID)
    #
    #     for d in self.aug_data_json:
    #         d['relation']=probs[d['id']]
    #     # for d in self.data_json:
    #     #     s_label=[0]*cate_nums
    #     #     s_label[self.label2id[d['relation']]]=1
    #     #     d['soft_label']=s_label
    #     data=self.aug_data_json
    #     # with open('aug_train_data.json','w') as f:
    #     #     json.dump(self.aug_data_json,f)
    #     with open('soft_train_data.json','w') as f:
    #         json.dump(data,f)



def map_to_ids(tokens, vocab):
    ids = [vocab[t] if t in vocab else constant.UNK_ID for t in tokens]
    return ids


def get_positions(start_idx, end_idx, length):
    """ Get subj/obj position sequence. """
    return list(range(-start_idx, 0)) + [0]*(end_idx - start_idx + 1) + \
            list(range(1, length-end_idx))

def padmat(mats,maxlen1,maxlen2):
    mats=[np.pad(mat,((0,maxlen1-mat.shape[0]),(0,maxlen2-mat.shape[1])),mode='constant',constant_values=(0,0)).reshape(1,maxlen1,maxlen2) for mat in mats]
    mats=np.concatenate(mats,axis=0)
    mats=torch.from_numpy(mats)
    return mats

def get_long_tensor(tokens_list, batch_size):
    """ Convert list of list of tokens to a padded LongTensor. """
    token_len = max(len(x) for x in tokens_list)
    tokens = torch.LongTensor(batch_size, token_len).fill_(constant.PAD_ID)
    for i, s in enumerate(tokens_list):
            tokens[i, :len(s)] = torch.LongTensor(s)
    return tokens

# def sort_all(batch, lens):
#     """ Sort all fields by descending order of lens, and return the original indices. """
#     unsorted_all = [lens] + [range(len(lens))] + list(batch)
#     sorted_all = [list(t) for t in zip(*sorted(zip(*unsorted_all), reverse=True))]
#return sorted_all[2:], sorted_all[1]

def sort_all(batch, lens):
    """ Sort all fields by descending order of lens, and return the original indices. """
    unsorted_all = [lens] + [range(len(lens))] + [batch]
    sorted_all = [list(t) for t in zip(*sorted(zip(*unsorted_all), reverse=True))]
    return sorted_all[2], sorted_all[1]


def word_dropout(tokens, dropout):
    """ Randomly dropout tokens (IDs) and replace them with <UNK> tokens. """
    return [constant.UNK_ID if x != constant.UNK_ID and np.random.random() < dropout \
            else x for x in tokens]

