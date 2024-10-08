import math
import torch.nn as nn

from detectron2.layers import Conv2d, DeformConv, ShapeSpec
from fcos.layers import Scale, normal_init
from typing import List


class FCOSHead(nn.Module):
    """
    Fully Convolutional One-Stage Object Detection head from [1]_.

    The FCOS head does not use anchor boxes. Instead bounding boxes are
    predicted at each pixel and a centerness measure is used to supress
    low-quality predictions.

    References:
        .. [1] https://arxiv.org/abs/1904.01355

    In our Implementation, schemetic structure is as following:

                                    /-> logits
                    /-> cls convs ->
                   /                \-> centerness
    shared convs ->
                    \-> reg convs -> regressions
    """
    def __init__(self, cfg, input_shape: List[ShapeSpec]):
        super().__init__()
        # fmt: off
        self.in_channels       = input_shape[0].channels
        self.num_classes       = cfg.MODEL.FCOS.NUM_CLASSES
        self.fpn_strides       = cfg.MODEL.FCOS.FPN_STRIDES
        self.num_shared_convs  = cfg.MODEL.FCOS.NUM_SHARED_CONVS
        self.num_stacked_convs = cfg.MODEL.FCOS.NUM_STACKED_CONVS
        self.prior_prob        = cfg.MODEL.FCOS.PRIOR_PROB
        self.use_deformable    = cfg.MODEL.FCOS.USE_DEFORMABLE
        self.norm_layer        = cfg.MODEL.FCOS.NORM
        self.ctr_on_reg        = cfg.MODEL.FCOS.CTR_ON_REG
        # fmt: on

        self._init_layers()
        self._init_weights()

    def _init_layers(self):
        """
        Initializes six convolutional layers for FCOS head and a scaling layer for bbox predictions.
        """
        self.activation = nn.ReLU()

        """ your code starts here """
        self.shared_convs = nn.Conv2d(self.in_channels, self.in_channels, kernel_size=3, stride=1, padding=1, bias=True) 
        self.norms = nn.GroupNorm(32, self.in_channels)
        self.cls_convs = nn.Conv2d(self.in_channels, self.in_channels, kernel_size=3, stride=1, padding=1, bias=True)
        self.reg_convs = nn.Conv2d(self.in_channels, self.in_channels, kernel_size=3, stride=1, padding=1, bias=True)
        self.cls_logits = nn.Conv2d(self.in_channels, self.num_classes, kernel_size=3, stride=1, padding=1)
        self.bbox_pred = nn.Conv2d(self.in_channels, 4, kernel_size=3, stride=1, padding=1)
        self.centerness = nn.Conv2d(self.in_channels, 1, kernel_size=3, stride=1, padding=1)
        self.scales = Scale(scale=1.0)
        """ your code ends here """

    def _init_weights(self):
        for modules in [
            self.shared_convs, self.cls_convs, self.reg_convs,
            self.cls_logits, self.bbox_pred, self.centerness, self.norms
        ]:
            # weight initialization with mean=0, std=0.01
            normal_init(modules,mean=0, std=0.01, bias=0)
            # pass

        # initialize the bias for classification logits
        bias_cls = -math.log((1 - self.prior_prob) / self.prior_prob)  # calculate proper value that makes cls_probability with `self.prior_prob`
        # In other words, make the initial 'sigmoid' activation of cls_logits as `self.prior_prob`
        # by controlling bias initialization
        nn.init.constant_(self.cls_logits.bias, bias_cls)

    def forward(self, features):
        """
        Arguments:
            features (list[Tensor]): FPN feature map tensors in high to low resolution.
                Each tensor in the list correspond to different feature levels.

        Returns:
            cls_scores (list[Tensor]): list of #feature levels, each has shape (N, C, Hi, Wi).
                The tensor predicts the classification probability
                at each spatial position for each of C object classes.
            bbox_preds (list[Tensor]): list of #feature levels, each has shape (N, 4, Hi, Wi).
                The tensor predicts 4-vector (l, t, r, b) box regression values for
                every position of featur map. These values are the distances from
                a specific point to each (left, top, right, bottom) edge
                of the corresponding ground truth box that the point belongs to.
            centernesses (list[Tensor]): list of #feature levels, each has shape (N, 1, Hi, Wi).
                The tensor predicts the centerness logits, where these values used to
                downweight the bounding box scores far from the center of an object.
        """
        cls_scores = []
        bbox_preds = []
        centernesses = []
        for feat_level, feature in enumerate(features):
            """ your code starts here """
            for i in range(self.num_shared_convs):
            	x = self.shared_convs(feature)
            	feature = self.activation(x)
            cls_convs = feature
            reg_convs = feature
            for i in range(self.num_stacked_convs):
            	y = self.cls_convs(cls_convs)		# classification branch conv layers
            	if self.norm_layer == "GN":			# when Group Normalization is used
            		y = self.norms(y)
            	cls_convs = self.activation(y)
            	z = self.reg_convs(reg_convs)		# regression branch conv layers
            	if self.norm_layer == "GN":			# when Group Normalization is used
            		z = self.norms(z)
            	reg_convs = self.activation(z)

            cls_scores.append(self.cls_logits(cls_convs))
            if self.ctr_on_reg:
            	centernesses.append(self.centerness(reg_convs))			# centerness branch in parallel with regression branch
            else:
            	centernesses.append(self.centerness(cls_convs))			# centerness branch in parallel with classification branch
            reg = self.bbox_pred(reg_convs)
            reg = self.scales(reg)
            bbox_preds.append(nn.functional.relu(reg)) 		# using relu insteasd of exponential function

            """ your code ends here """
        return cls_scores, bbox_preds, centernesses
