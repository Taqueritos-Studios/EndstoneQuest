# EndstoneQuest

EndstoneQuest is a simple quest plugin for Endstone Bedrock servers. Quests are configured in JSON, tracked per player, and completed automatically when supported Endstone events fire.

## Files

- `bedrock_server/plugins/endstone_quest-0.1.1-py2.py3-none-any.whl` - installed plugin wheel.
- `bedrock_server/plugins/quest/config.json` - plugin settings and messages.
- `bedrock_server/plugins/quest/quests.json` - quest definitions.
- `bedrock_server/plugins/quest/players.json` - generated player progress data.

Keep quest definitions in `quests.json`. `config.json` should only contain settings and messages.

## Commands

Player commands:

- `/quests help` - show player help.
- `/quests` or `/quests menu` - open the in-game quest menu.
- `/quests list` - list available quests.
- `/quests info <quest>` - show quest goals.
- `/quests start <quest>` - start a quest manually.
- `/quests progress [quest]` - show active quest progress.
- `/quests cancel <quest>` - cancel an active quest.

Admin commands:

- `/questadmin help` - show admin help.
- `/questadmin reload` - reload config, quests, and player data.
- `/questadmin list` - list quests and supported objective types.
- `/questadmin progress <player> <type> <amount> [target]` - manually add objective progress.
- `/questadmin reset <player> [quest]` - reset all or one quest for a player.
- `/questadmin complete <player> <quest>` - force-complete a quest.

Aliases:

- `/quest` for `/quests`
- `/qadmin` for `/questadmin`

## Quest Example

```json
{
    "enabled": true,
    "auto_start": true,
    "repeatable": false,
    "display_name": "&dGetting Started",
    "description": "&7Gather wood and place your first blocks.",
    "objectives": [
        {
            "id": "break_logs",
            "type": "break",
            "target": "minecraft:oak_log",
            "amount": 8,
            "description": "Break 8 oak logs"
        },
        {
            "id": "place_cobble",
            "type": "place",
            "target": "minecraft:cobblestone",
            "amount": 8,
            "description": "Place 8 cobblestone"
        }
    ],
    "rewards": {
        "items": [
            {
                "type": "minecraft:bread",
                "amount": 6
            }
        ],
        "exp": 50
    }
}
```

## Objective Types

Event-tracked objectives:

- `break`
- `place`
- `player_kill`
- `mob_kill`
- `walk`
- `smelt`
- `tame`
- `shear`
- `fish`
- `deal_damage`
- `consume`
- `breed`

Notes:

- `fish` counts picked-up fish items such as cod, salmon, tropical fish, and pufferfish.
- `tame`, `shear`, and `breed` are credited from successful player interaction events that match known entity/item combinations. Endstone 0.11 does not expose separate success-state events for these actions.

Supported objective types that currently need manual/admin progress or future Endstone API hooks:

- `craft`
- `enchant`
- `trade`
- `smith`
- `brew`

Several aliases are accepted, such as `playerkilling`, `mobkilling`, `walking`, `smelting`, `dealdamage`, `tamin`, `trading`, `brewing`, and `breeding`.

## Rewards

Supported reward fields:

- `items` - list of item rewards with `type`, `amount`, optional `name`, and optional `lore`.
- `exp` - experience points.
- `exp_levels` - experience levels.
- `commands` - console commands. Use `{player}` and `{quest}` placeholders.
- `player_commands` - commands run as the player.
- `messages` - private reward messages.
- `broadcasts` - server-wide reward messages.

## Build

From the workspace root:

```powershell
.\.venv\Scripts\python.exe -m build --wheel --outdir bedrock_server\plugins my_plugins\EndstoneQuest
```

Restart the Bedrock server after replacing the wheel.
