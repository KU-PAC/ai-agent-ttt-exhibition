uv run lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/ttyACM0 --robot.id=leader
uv run lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/ttyACM1 --robot.id=follower

rm -rf /home/kupac/.cache/huggingface/lerobot/kupac/pick_place_fixed
uv run lerobot-record --robot.type=so101_follower --robot.port=/dev/ttyACM1 --robot.id=follower --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 --teleop.id=leader --dataset.repo_id=kupac/pick_place_fixed --dataset.num_episodes=9 --dataset.si
ngle_task="Pick from A and place to B" --dataset.episode_time_s=10 --dataset.reset_time_s=5 --dataset.push_to_hub=False

uv run lerobot-replay --robot.type=so101_follower --robot.port=/dev/ttyACM1 --robot.id=follower --dataset.repo_id=kupac/pick_place_fixed09 --dataset.episode=0