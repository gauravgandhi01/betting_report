
import nflreadpy as nfl
import pandas as pd

stats = nfl.load_player_stats(2026).to_pandas()

last_week = 8

df = stats[
    (stats["season_type"] == "REG") &
    (stats["week"] <= last_week) &
    (stats["position"].isin(["WR", "RB", "TE"]))
]

season = df.groupby("player_id").agg(
    player=("player_display_name", "last"),
    team=("team", "last"),
    targets=("targets", "sum"),
    games=("week", "nunique")
).reset_index()

season["targets_per_game"] = (
    season["targets"] / season["games"]
)

previous = df[df["week"] == last_week][
    ["player_id", "receptions", "targets"]
].rename(columns={
    "receptions": "last_receptions",
    "targets": "last_targets"
})

results = season.merge(previous, on="player_id")

results = results[
    (results["targets_per_game"] >= 6) &
    (results["last_receptions"] <= 3)
].sort_values("targets_per_game", ascending=False)

print(results.to_string(index=False))
