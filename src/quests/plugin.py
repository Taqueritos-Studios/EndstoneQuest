from endstone.command import Command, CommandSender
from endstone.plugin import Plugin

from quests.commands import QuestCommand
from quests.listeners import QuestListener
from quests.managers import QuestManager


class QuestPlugin(Plugin):
    api_version = "0.11"

    commands = {
        "quests": {
            "description": "View and manage your quests",
            "usages": ["/quests [args: message]"],
            "aliases": ["quest"],
            "permissions": ["quests.command.quests"],
        },
        "questadmin": {
            "description": "Manage EndstoneQuest",
            "usages": ["/questadmin [args: message]"],
            "aliases": ["qadmin"],
            "permissions": ["quests.admin"],
        },
    }

    permissions = {
        "quests.command.quests": {
            "description": "Allows players to use quest commands.",
            "default": True,
        },
        "quests.admin": {
            "description": "Allows administrators to manage quests.",
            "default": "op",
            "children": {
                "quests.command.quests": True,
            },
        },
    }

    def on_enable(self):
        self.quest_manager = QuestManager(self)
        self.quest_command = QuestCommand(self.quest_manager)
        self.quest_listener = QuestListener(self.quest_manager)
        self.register_events(self.quest_listener)

        self.logger.info(f"EndstoneQuest enabled with {len(self.quest_manager.enabled_quests())} enabled quests.")

    def on_disable(self):
        if hasattr(self, "quest_manager"):
            self.quest_manager.save_players()

        self.logger.info("EndstoneQuest disabled.")

    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        return self.quest_command.handle(sender, command, self.normalize_args(args))

    def normalize_args(self, args: list[str]) -> list[str]:
        if len(args) == 1 and isinstance(args[0], str):
            return args[0].split()

        return args
