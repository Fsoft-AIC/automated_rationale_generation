import json

import random
import os
import numpy as np
import torch
from torch.utils.data import Dataset
from torch.nn.utils.rnn import pad_sequence


class VideoDataset(Dataset):

    def get_vocab_size(self):
        return len(self.get_vocab())

    def get_vocab(self):
        return self.ix_to_word

    def get_seq_length(self):
        return self.seq_length

    def __init__(self, opt, mode):
        super(VideoDataset, self).__init__()
        self.mode = mode  # to load train/val/test data

        # load the json file which contains information about the dataset
        self.captions = json.load(open(opt["caption_json"]))
        info = json.load(open(opt["info_json"]))
        self.ix_to_word = info['ix_to_word']
        self.word_to_ix = info['word_to_ix']
        print('vocab size is ', len(self.ix_to_word))
        self.splits = info['videos']
        print('number of train videos: ', len(self.splits['train']))
        print('number of val videos: ', len(self.splits['val']))
        print('number of test videos: ', len(self.splits['test']))

        self.feats_dir = opt["feats_dir"]
        self.c3d_feats_dir = opt['c3d_feats_dir']
        self.with_c3d = opt['with_c3d']
        print('load feats from %s' % (self.feats_dir))
        # load in the sequence data
        self.max_len = opt["max_len"]
        print('max sequence length in data is', self.max_len)

    def __getitem__(self, ix):
        """This function returns a tuple that is further passed to collate_fn
        """
        # which part of data to load
        if self.mode == 'train':
            feat_name = self.splits['train']
        elif self.mode == 'val':
            feat_name = self.splits['val']
        elif self.mode == 'test':
            feat_name = self.splits['test']
        
        fc_feat = []
        for dir in self.feats_dir:
            fc_feat.append(np.load(os.path.join(dir, feat_name[ix]+'.npy')))
        fc_feat = np.concatenate(fc_feat, axis=1)
        if self.with_c3d == 1:
            c3d_feat = np.load(os.path.join(self.c3d_feats_dir, feat_name[ix]+'.npy'))
            c3d_feat = np.mean(c3d_feat, axis=0, keepdims=True)
            fc_feat = np.concatenate((fc_feat, np.tile(c3d_feat, (fc_feat.shape[0], 1))), axis=1)
        label = np.zeros(self.max_len)
        mask = np.zeros(self.max_len)
        captions = self.captions[feat_name[ix]]['final_captions']
        gts = np.zeros((len(captions), self.max_len))
        for i, cap in enumerate(captions):
            if len(cap) > self.max_len:
                cap = cap[:self.max_len]
                cap[-1] = '<eos>'
            for j, w in enumerate(cap):
                gts[i, j] = self.word_to_ix[w]

        # random select a caption for this video
        cap_ix = random.randint(0, len(captions) - 1)
        label = gts[cap_ix]
        non_zero = (label == 0).nonzero()
        mask[:int(non_zero[0][0]) + 1] = 1

        data = {}
        data['fc_feats'] = torch.from_numpy(fc_feat).type(torch.FloatTensor)
        data['labels'] = torch.from_numpy(label).type(torch.LongTensor)
        data['masks'] = torch.from_numpy(mask).type(torch.FloatTensor)
        data['gts'] = torch.from_numpy(gts).long()
        data['video_ids'] = feat_name[ix]
        return data

    def __len__(self):
        return len(self.splits[self.mode])

def collate_batch(batch):
    padded_batch = {}
    fc_feats = [datapoint['fc_feats'] for _, datapoint in enumerate(batch)]
    labels = torch.cat([torch.unsqueeze(datapoint['labels'], 0) for _ ,datapoint in enumerate(batch)], 0)
    masks = torch.cat([torch.unsqueeze(datapoint['masks'], 0) for _ ,datapoint in enumerate(batch)], 0)
    gts = torch.cat([torch.unsqueeze(datapoint['gts'], 0) for _ ,datapoint in enumerate(batch)], 0)
    video_ids = [datapoint['video_ids'] for _, datapoint in enumerate(batch)]
    padded = pad_sequence(fc_feats, batch_first=True)
    padded_batch['fc_feats'] = padded
    padded_batch['labels'] = labels
    padded_batch['masks'] = masks
    padded_batch['gts'] = gts
    padded_batch['video_ids'] = video_ids
    return padded_batch
