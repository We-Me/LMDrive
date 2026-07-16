"""Native LMDrive inference runtime with no Leaderboard or route input."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import pygame
import torch
from PIL import Image
from torchvision import transforms

from interactive_lmdriver_config import GlobalConfig
from lavis.common.registry import registry


IMAGENET_DEFAULT_MEAN = (0.485, 0.456, 0.406)
IMAGENET_DEFAULT_STD = (0.229, 0.224, 0.225)


class PIDController:
    def __init__(self, k_p=1.0, k_i=0.0, k_d=0.0, window_size=20):
        from collections import deque

        self.k_p = k_p
        self.k_i = k_i
        self.k_d = k_d
        self._window = deque([0.0 for _ in range(window_size)], maxlen=window_size)

    def step(self, error):
        self._window.append(error)
        integral = np.mean(self._window)
        derivative = self._window[-1] - self._window[-2]
        return self.k_p * error + self.k_i * integral + self.k_d * derivative


class Resize2FixedSize:
    def __init__(self, size):
        self.size = size

    def __call__(self, pil_img):
        return pil_img.resize(self.size)


def create_carla_rgb_transform(input_size, need_scale=True):
    if isinstance(input_size, (tuple, list)):
        image_size = input_size[-2:]
        input_size_number = input_size[-1]
    else:
        image_size = input_size
        input_size_number = input_size

    transform_list = []
    if need_scale:
        resize_by_input = {
            112: (170, 128),
            128: (195, 146),
            224: (341, 256),
            256: (288, 288),
        }
        if input_size_number not in resize_by_input:
            raise ValueError("Unsupported LMDrive image size: {}".format(input_size))
        transform_list.append(Resize2FixedSize(resize_by_input[input_size_number]))
    transform_list.extend(
        [
            transforms.CenterCrop(image_size),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=torch.tensor(IMAGENET_DEFAULT_MEAN),
                std=torch.tensor(IMAGENET_DEFAULT_STD),
            ),
        ]
    )
    return transforms.Compose(transform_list)


def rotate_lidar(lidar, angle_deg):
    radians = np.deg2rad(angle_deg)
    return lidar @ np.array(
        [
            [np.cos(radians), np.sin(radians), 0, 0],
            [-np.sin(radians), np.cos(radians), 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ]
    )


def lidar_to_raw_features(lidar_xyzr):
    lidar_xyzr = np.asarray(lidar_xyzr, dtype=np.float32)
    ego_mask = (
        (lidar_xyzr[:, 0] > -1.2)
        & (lidar_xyzr[:, 0] < 1.2)
        & (lidar_xyzr[:, 1] > -1.2)
        & (lidar_xyzr[:, 1] < 1.2)
    )
    lidar_xyzr = lidar_xyzr[~ego_mask]
    if len(lidar_xyzr):
        lidar_xyzr = lidar_xyzr[np.random.permutation(len(lidar_xyzr))]

    padded = np.zeros((40000, 4), dtype=np.float32)
    number_of_points = min(40000, len(lidar_xyzr))
    padded[:number_of_points, :4] = lidar_xyzr[:number_of_points, :4]
    padded[~np.isfinite(padded)] = 0.0
    return rotate_lidar(padded, -90).astype(np.float32), number_of_points


class PygameDisplay:
    def __init__(self, request_quit: Callable[[], None]):
        self._request_quit = request_quit
        pygame.init()
        pygame.font.init()
        self._display = pygame.display.set_mode(
            (1200, 900), pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption("Native LMDrive Instruction Test")

    def render(self, display_data):
        surface = np.zeros((900, 1200, 3), np.uint8)
        surface[:, :1200] = display_data["rgb_front"]
        surface[:210, :280] = display_data["rgb_left"]
        surface[:210, 920:1200] = display_data["rgb_right"]
        surface[:210, 495:705] = display_data["rgb_center"]

        rows = (
            (display_data["time"], 710),
            (display_data["meta_control"], 740),
            (display_data["waypoints"], 770),
            (display_data["instruction"], 800),
            (display_data["notice"], 830),
        )
        for text, y_position in rows:
            cv2.putText(
                surface,
                text,
                (20, y_position),
                cv2.FONT_HERSHEY_TRIPLEX,
                0.62,
                (0, 0, 255),
                1,
            )

        for text, position in (
            ("Left View", (60, 245)),
            ("Focus View", (535, 245)),
            ("Right View", (980, 245)),
        ):
            cv2.putText(
                surface,
                text,
                position,
                cv2.FONT_HERSHEY_TRIPLEX,
                0.75,
                (139, 69, 19),
                2,
            )

        pygame_surface = pygame.surfarray.make_surface(surface.swapaxes(0, 1))
        self._display.blit(pygame_surface, (0, 0))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._request_quit()
        return surface

    @staticmethod
    def close():
        pygame.quit()


class NativeLMDriveRuntime:
    """Load LMDrive and run raw language-conditioned waypoint inference."""

    def __init__(
        self,
        request_quit: Callable[[], None],
        evaluation_status_getter: Callable[[], str],
        save_frames: bool = False,
        frame_output_dir: Optional[Path] = None,
    ) -> None:
        self.config = GlobalConfig()
        self._evaluation_status_getter = evaluation_status_getter
        self._display = PygameDisplay(request_quit)
        self._save_frames = save_frames
        self._frame_output_dir = frame_output_dir
        if self._save_frames and self._frame_output_dir is not None:
            self._frame_output_dir.mkdir(parents=True, exist_ok=True)

        self._rgb_front_transform = create_carla_rgb_transform(224)
        self._rgb_left_transform = create_carla_rgb_transform(128)
        self._rgb_right_transform = create_carla_rgb_transform(128)
        self._rgb_center_transform = create_carla_rgb_transform(
            128, need_scale=False
        )
        self._turn_controller = PIDController(
            self.config.turn_KP,
            self.config.turn_KI,
            self.config.turn_KD,
            self.config.turn_n,
        )
        self._speed_controller = PIDController(
            self.config.speed_KP,
            self.config.speed_KI,
            self.config.speed_KD,
            self.config.speed_n,
        )

        print("Building native LMDrive model (no Leaderboard, no route)...", flush=True)
        model_class = registry.get_model_class("vicuna_drive")
        model = model_class(
            preception_model=self.config.preception_model,
            preception_model_ckpt=self.config.preception_model_ckpt,
            llm_model=self.config.llm_model,
            max_txt_len=64,
            use_notice_prompt=self.config.agent_use_notice,
        )
        print("Loading LMDrive checkpoint...", flush=True)
        checkpoint = torch.load(self.config.lmdrive_ckpt, map_location="cpu")
        model.load_state_dict(checkpoint["model"], strict=False)
        self.net = model.cuda().eval()
        if bool(getattr(self.net, "has_gru_decoder", False)):
            raise RuntimeError(
                "Native route-free testing requires LMDrive's default non-GRU decoder"
            )
        if not bool(getattr(self.net.visual_encoder, "return_feature", False)):
            raise RuntimeError(
                "Native route-free testing requires a return_feature visual encoder"
            )

        self._softmax = torch.nn.Softmax(dim=1)
        self._step = -1
        self._previous_lidar = None
        self._previous_control = None
        self._visual_feature_buffer = []
        self._sample_rate = self.config.sample_rate * 2
        self._navigation_revision = -1
        self._notice_revision = -1
        self._current_notice = ""
        self._notice_frame_id = -1

    @torch.no_grad()
    def run_step(self, sensor_data, speed_mps, command_snapshot, timestamp):
        import carla

        self._step += 1
        if command_snapshot.navigation_revision != self._navigation_revision:
            self._visual_feature_buffer = []
            self._navigation_revision = command_snapshot.navigation_revision
        if command_snapshot.notice_revision != self._notice_revision:
            self._current_notice = ""
            self._notice_frame_id = -1
            self._notice_revision = command_snapshot.notice_revision

        raw_lidar = self._lidar_to_numpy(sensor_data["lidar"])
        if self._step < 20:
            # Match LMDrive's two-sweep LiDAR preparation during its initial
            # brake-only sensor warm-up.
            self._previous_lidar = raw_lidar
            control = carla.VehicleControl(throttle=0.0, steer=0.0, brake=1.0)
            self._previous_control = control
            return control
        if self._step % 2 != 0 and self._previous_control is not None:
            self._previous_lidar = raw_lidar
            return self._previous_control

        rgb_front = self._camera_to_rgb(sensor_data["rgb_front"])
        rgb_left = self._camera_to_rgb(sensor_data["rgb_left"])
        rgb_right = self._camera_to_rgb(sensor_data["rgb_right"])
        rgb_rear = self._camera_to_rgb(sensor_data["rgb_rear"])
        if self._previous_lidar is not None:
            lidar_full = np.concatenate([raw_lidar, self._previous_lidar])
        else:
            lidar_full = raw_lidar
        self._previous_lidar = raw_lidar
        lidar, number_of_points = lidar_to_raw_features(lidar_full)

        rgb_center_source = cv2.resize(rgb_front, (800, 600))
        model_input = {
            "rgb_front": self._to_cuda_image(
                self._rgb_front_transform, rgb_front
            ),
            "rgb_left": self._to_cuda_image(self._rgb_left_transform, rgb_left),
            "rgb_right": self._to_cuda_image(
                self._rgb_right_transform, rgb_right
            ),
            "rgb_rear": self._to_cuda_image(self._rgb_right_transform, rgb_rear),
            "rgb_center": self._to_cuda_image(
                self._rgb_center_transform, rgb_center_source
            ),
            "lidar": torch.from_numpy(lidar).float().cuda().unsqueeze(0),
            "num_points": torch.tensor([[number_of_points]]).cuda(),
            "velocity": torch.tensor([[float(speed_mps)]]).cuda(),
            "text_input": [command_snapshot.navigation.text],
        }

        image_embeds = self.net.visual_encoder(model_input)
        if len(self._visual_feature_buffer) > 400:
            self._visual_feature_buffer = []
        self._visual_feature_buffer.append(image_embeds)
        sampled_features = self._visual_feature_buffer[:: self._sample_rate]
        if (len(self._visual_feature_buffer) - 1) % self._sample_rate != 0:
            sampled_features.append(self._visual_feature_buffer[-1])
        image_embeds = torch.stack(sampled_features, 1)
        model_input["valid_frames"] = [image_embeds.size(1)]

        notice_text = ""
        if command_snapshot.notice is not None:
            notice_text = command_snapshot.notice.text
        if notice_text and notice_text != self._current_notice:
            self._current_notice = notice_text
            self._notice_frame_id = image_embeds.size(1) - 1
        if self.config.agent_use_notice:
            model_input["notice_text"] = [self._current_notice]
            model_input["notice_frame_id"] = [self._notice_frame_id]

        with torch.cuda.amp.autocast(enabled=True):
            waypoints, is_end = self.net(
                model_input,
                inference_mode=True,
                image_embeds=image_embeds,
            )
        waypoints = waypoints[-1].view(5, 2)
        end_probability = float(self._softmax(is_end)[-1][1])
        steer, throttle, brake = self._control_pid(waypoints, float(speed_mps))

        if end_probability > 0.75:
            self._visual_feature_buffer = []
            self._current_notice = ""
            self._notice_frame_id = -1
        if brake < 0.05:
            brake = 0.0
        if brake > 0.1:
            throttle = 0.0

        control = carla.VehicleControl(
            steer=float(steer) * 0.8,
            throttle=float(throttle),
            brake=float(brake),
        )
        surface = self._display.render(
            self._build_display_data(
                rgb_front,
                rgb_left,
                rgb_right,
                waypoints,
                control,
                command_snapshot,
                timestamp,
                speed_mps,
                end_probability,
            )
        )
        if self._save_frames and self._frame_output_dir is not None:
            Image.fromarray(surface).save(
                self._frame_output_dir / ("{:06d}.jpg".format(self._step))
            )
        self._previous_control = control
        return control

    @staticmethod
    def _camera_to_rgb(image):
        bgra = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(
            image.height, image.width, 4
        )
        return cv2.cvtColor(bgra[:, :, :3], cv2.COLOR_BGR2RGB)

    @staticmethod
    def _lidar_to_numpy(lidar_measurement):
        return np.frombuffer(lidar_measurement.raw_data, dtype=np.float32).reshape(
            -1, 4
        )

    @staticmethod
    def _to_cuda_image(transform, rgb_image):
        return transform(Image.fromarray(rgb_image)).unsqueeze(0).cuda().float()

    def _control_pid(self, waypoints, speed_mps):
        points = waypoints.data.cpu().numpy().copy()
        points[:, 1] *= -1
        desired_speed = float(np.linalg.norm(points[0] - points[1]) * 2.0)
        brake = desired_speed < self.config.brake_speed or (
            desired_speed > 1e-4 and speed_mps / desired_speed > self.config.brake_ratio
        )
        aim = (points[1] + points[0]) / 2.0
        angle = np.degrees(np.pi / 2 - np.arctan2(aim[1], aim[0])) / 90
        if speed_mps < 0.01:
            angle = 0.0
        steer = np.clip(self._turn_controller.step(angle), -1.0, 1.0)
        delta = np.clip(desired_speed - speed_mps, 0.0, self.config.clip_delta)
        throttle = np.clip(
            self._speed_controller.step(delta), 0.0, self.config.max_throttle
        )
        return float(steer), float(0.0 if brake else throttle), float(brake)

    def _build_display_data(
        self,
        rgb_front,
        rgb_left,
        rgb_right,
        waypoints,
        control,
        snapshot,
        timestamp,
        speed_mps,
        end_probability,
    ):
        points = waypoints.detach().cpu().numpy()
        evaluation = self._evaluation_status_getter()
        return {
            "rgb_front": cv2.resize(rgb_front, (1200, 900)),
            "rgb_left": cv2.resize(rgb_left, (280, 210)),
            "rgb_right": cv2.resize(rgb_right, (280, 210)),
            "rgb_center": cv2.resize(
                rgb_front[330:570, 480:720], (210, 210)
            ),
            "time": "Time: {:.2f} | Speed: {:.1f} km/h | End: {:.2f}".format(
                timestamp, speed_mps * 3.6, end_probability
            ),
            "meta_control": (
                "RAW LMDrive | Throttle: {:.2f} Steer: {:.2f} Brake: {:.2f} | {}"
            ).format(
                control.throttle,
                control.steer,
                control.brake,
                evaluation,
            ),
            "waypoints": "Model waypoints: ({:.1f}, {:.1f}), ({:.1f}, {:.1f})".format(
                points[0, 0], -points[0, 1], points[1, 0], -points[1, 1]
            ),
            "instruction": "Command: {} | Prompt: {}".format(
                snapshot.navigation.symbol, snapshot.navigation.text
            ),
            "notice": "Notice: {}".format(
                "" if snapshot.notice is None else snapshot.notice.text
            ),
        }

    def destroy(self):
        self._display.close()
        if hasattr(self, "net"):
            del self.net
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
