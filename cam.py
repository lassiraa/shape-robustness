import torch
import torchvision.transforms as transforms
import numpy as np
from pytorch_grad_cam import GradCAM, \
    ScoreCAM, \
    GradCAMPlusPlus, \
    AblationCAM, \
    XGradCAM, \
    EigenCAM, \
    LayerCAM, \
    FullGrad, \
    GuidedBackpropReLUModel
from pytorch_grad_cam.ablation_layer import AblationLayerVit
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget
from pytorch_grad_cam.utils.image import show_cam_on_image
import cv2

from utils import reshape_transform_vit, load_model_with_target_layers, scale_image


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Create CAM visualization of video for highest prob. class')
    parser.add_argument('--in_path', type=str, required=True,
                        help='path to image')
    parser.add_argument('--class_idx', type=int, required=True,
                        help='desired class id from coco', default=17)
    parser.add_argument('--batch_size', type=int, default=32,
                        help='batch size for cam methods')
    parser.add_argument('--num_workers', type=int, default=16,
                        help='workers for dataloader')
    parser.add_argument('--model_name', type=str, default='resnet50',
                        help='name of model used for inference',
                        choices=['vit_b_32', 'vgg16_bn', 'swin_t', 'resnet50'])
    parser.add_argument('--method', type=str, default='gradcam',
                        choices=['gradcam', 'gradcam++',
                                 'scorecam', 'xgradcam',
                                 'ablationcam', 'eigencam',
                                 'eigengradcam', 'layercam', 'fullgrad',
                                 'guidedbackprop'],
                        help='Can be gradcam/gradcam++/scorecam/xgradcam'
                             '/ablationcam/eigencam/eigengradcam/layercam')
    args = parser.parse_args()

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    model, target_layers = load_model_with_target_layers(args.model_name, device)

    reshape_transform = None
    is_vit = args.model_name in ['vit_b_32', 'swin_t']

    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]
    if is_vit:
        reshape_transform = reshape_transform_vit

    image_transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Resize(224),
        transforms.CenterCrop(224)
    ])

    image_normalize = transforms.Normalize(mean=mean, std=std)

    methods = \
        {"gradcam": GradCAM,
         "scorecam": ScoreCAM,
         "gradcam++": GradCAMPlusPlus,
         "ablationcam": AblationCAM,
         "xgradcam": XGradCAM,
         "eigencam": EigenCAM,
         "fullgrad": FullGrad,
         "layercam": LayerCAM,
         "guidedbackprop": GuidedBackpropReLUModel}

    method = methods[args.method]
    is_backprop = False
    if args.method == 'guidedbackprop':
        saliency_method = method(model=model,
                                 use_cuda=torch.cuda.is_available())
        is_backprop = True
    elif args.method == 'ablationcam' and is_vit:
        saliency_method = method(model=model,
                                 target_layers=target_layers,
                                 reshape_transform=reshape_transform,
                                 use_cuda=torch.cuda.is_available(),
                                 ablation_layer=AblationLayerVit())
        saliency_method.batch_size = args.batch_size
    else:
        saliency_method = method(model=model,
                                 target_layers=target_layers,
                                 reshape_transform=reshape_transform,
                                 use_cuda=torch.cuda.is_available())
        saliency_method.batch_size = args.batch_size
    
    #  Read video and find highest probability class from first frame.
    #  Class ID is used for CAM visualization
    rgb_img = cv2.imread(f'{args.in_path}', 1)[:, :, ::-1]
    rgb_img = np.float32(rgb_img) / 255
    input = image_transform(rgb_img)
    input = image_normalize(input)
    input = input.to(device=device, dtype=torch.float32).unsqueeze(0)

    #  Process saliency map
    if is_backprop:
        saliency_map = saliency_method(input, target_category=args.class_idx)
        saliency_map = saliency_map.sum(axis=2).reshape(224, 224)
        saliency_map = np.where(saliency_map > 0, saliency_map, 0)
        saliency_map = scale_image(saliency_map, 1)
    else:
        saliency_map = saliency_method(input, [ClassifierOutputTarget(args.class_idx)])[0, :]

    cam_image = show_cam_on_image(rgb_img, saliency_map, use_rgb=True)
    cam_image = cv2.cvtColor(cam_image, cv2.COLOR_RGB2BGR)
    cv2.imwrite(f'{args.in_path.split(".")[0]}_{args.model_name}_{args.method}_{args.class_idx}_mask.jpg', saliency_map*255)
    cv2.imwrite(f'{args.in_path.split(".")[0]}_{args.model_name}_{args.method}_{args.class_idx}.jpg', cam_image)