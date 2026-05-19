from pathlib import Path
from kaggle_environments import make
import json
env = make("orbit_wars", configuration={"seed": 7}, debug=False)
env.run(["_build/ow_proto.py", "_build/blitz.py"])
Path("replays").mkdir(exist_ok=True)
Path("replays/g7.json").write_text(
    json.dumps(env.toJSON(), indent=2)
)

