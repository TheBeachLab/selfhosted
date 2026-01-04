# Raspberry Pi

## Build MAVROS Docker

## Calibrate stereo Cameras

docker ps

docker exec -it mavros bash

apt update
apt install -y ros-humble-camera-calibration ros-humble-v4l2-camera

Launch the nodes

ros2 run v4l2_camera v4l2_camera_node --ros-args -r image:=/left/image_raw  --param video_device:=/dev/video12
ros2 run v4l2_camera v4l2_camera_node --ros-args -r image:=/right/image_raw --param video_device:=/dev/video13

ros2 run camera_calibration cameracalibrator \
  --size 9x6 --square 0.025 \
  left:=/left/image_raw right:=/right/image_raw \
  left_camera:=/left right_camera:=/right

