import numpy as np
import pickle
from PIL import Image
import os

import torch
from torch.utils import data as data
import torchvision.transforms as tf
from torchvision.transforms.functional import normalize

from pyiqa.data.data_util import read_meta_info_file 
from pyiqa.data.transforms import transform_mapping, augment, PairedToTensor
from pyiqa.utils import FileClient, imfrombytes, img2tensor
from pyiqa.utils.registry import DATASET_REGISTRY

@DATASET_REGISTRY.register()
class BAPPSDataset(data.Dataset):
    """The BAPPS Dataset introduced by:

    Zhang, Richard and Isola, Phillip and Efros, Alexei A and Shechtman, Eli and Wang, Oliver
    The Unreasonable Effectiveness of Deep Features as a Perceptual Metric.
    CVPR2018
    url: https://github.com/richzhang/PerceptualSimilarity
    
    Args:
        opt (dict): Config for train datasets with the following keys:
            phase (str): 'train' or 'val'.
        mode (str):
            - 2afc: load 2afc triplet data
            - jnd: load jnd pair data
    """

    def __init__(self, opt):
        super(BAPPSDataset, self).__init__()

        import pandas as pd
        self.opt = opt

        if opt.get('override_phase', None) is None:
            self.phase = opt['phase'] 
        else:
            self.phase = opt['override_phase'] 

        self.dataset_mode = opt.get('mode', '2afc')
        val_types = opt.get('val_types', None)

        target_img_folder = opt['dataroot_target']
        self.dataroot = target_img_folder
        ref_img_folder = opt.get('dataroot_ref', None)

        self.paths_mos = pd.read_csv(opt['meta_info_file']).values.tolist()

        # read train/val/test splits
        split_file_path = opt.get('split_file', None)
        if split_file_path:
            split_index = opt.get('split_index', 1)
            with open(opt['split_file'], 'rb') as f:
                split_dict = pickle.load(f)
                splits = split_dict[split_index][self.phase]
            self.paths_mos = [self.paths_mos[i] for i in splits] 

        if self.dataset_mode == '2afc':
            self.paths_mos = [x for x in self.paths_mos if x[0] != 'jnd']
        elif self.dataset_mode == 'jnd':
            self.paths_mos = [x for x in self.paths_mos if x[0] == 'jnd']
        
        if val_types is not None:
            tmp_paths_mos = []
            for item in self.paths_mos:
                for vt in val_types:
                    if vt in item[1]:
                        tmp_paths_mos.append(item)
            self.paths_mos = tmp_paths_mos

        # TODO: paired transform
        transform_list = []
        augment_dict = opt.get('augment', None)
        if augment_dict is not None:
            for k, v in augment_dict.items():
                transform_list += transform_mapping(k, v)

        img_range = opt.get('img_range', 1.0)
        transform_list += [
                PairedToTensor(),
                ]
        self.trans = tf.Compose(transform_list)

    def __getitem__(self, index):
        is_jnd_data = self.paths_mos[index][0] == 'jnd'
        distA_path = os.path.join(self.dataroot, self.paths_mos[index][1])
        distB_path = os.path.join(self.dataroot, self.paths_mos[index][2])

        distA_pil = Image.open(distA_path).convert('RGB')
        distB_pil = Image.open(distB_path).convert('RGB')

        score = self.paths_mos[index][3]
        # original 0 means prefer p0, transfer to probability of p0
        mos_label_tensor = torch.Tensor([score]) 

        if not is_jnd_data:
            ref_path = os.path.join(self.dataroot, self.paths_mos[index][0])
            ref_img_pil = Image.open(ref_path).convert('RGB')

            distA_tensor, distB_tensor, ref_tensor = self.trans([distA_pil, distB_pil, ref_img_pil])
        else:
            distA_tensor, distB_tensor = self.trans([distA_pil, distB_pil])

        if not is_jnd_data:

            return {'ref_img': ref_tensor, 'distB_img': distB_tensor, 'distA_img': distA_tensor, 
                    'mos_label': mos_label_tensor,  
                    'img_path': ref_path, 'distB_path': distB_path, 'distA_path': distA_path}
        else:

            return {'distB_img': distB_tensor, 'distA_img': distA_tensor, 
                'mos_label': mos_label_tensor,  
                'distB_path': distB_path, 'distA_path': distA_path}


    def __len__(self):
        return len(self.paths_mos)
